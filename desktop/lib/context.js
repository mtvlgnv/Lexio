/**
 * Best-effort "auto-expand to the surrounding sentence" for a captured
 * selection — highlight ONE WORD, get a CONTEXTUAL definition.
 *
 * Three parallel strategies (first good win inside the resolver):
 *   1. DOM block read — when Lexio Glance itself is frontmost (our windows)
 *   2. ax-reader.py — ctypes AX API with cursor anchoring + Chromium tree flip
 *   3. JXA / System Events — slow fallback for native apps
 */
const { execFile } = require('child_process');
const path = require('path');

const AX_READER_PATH = path.join(__dirname, 'ax-reader.py');

const READ_VALUE_JXA = `
  function run() {
    try {
      var se = Application("System Events");
      var proc = se.applicationProcesses.whose({ frontmost: true })[0];
      var focused = proc.attributes.byName("AXFocusedUIElement").value();

      try {
        var sel = focused.attributes.byName("AXSelectedText").value();
        if (sel && sel.length > 1) return sel;
      } catch(e) {}

      try {
        var val = focused.attributes.byName("AXValue").value();
        if (val && val.length > 1) return val;
      } catch(e) {}

      try {
        var el = focused;
        for (var i = 0; i < 6; i++) {
          el = el.attributes.byName("AXParent").value();
          try {
            var parentVal = el.attributes.byName("AXValue").value();
            if (parentVal && parentVal.length > 10) return parentVal;
          } catch(e2) {}
        }
      } catch(e) {}

      function collectText(element, depth) {
        if (depth > 5) return "";
        var result = "";
        try {
          var role = element.attributes.byName("AXRole").value();
          if (role === "AXStaticText") {
            try {
              var tv = element.attributes.byName("AXValue").value();
              if (tv) result += tv + " ";
            } catch(e) {}
            return result;
          }
          if (role === "AXTextField" || role === "AXTextArea" || role === "AXWebArea") {
            try {
              var fv = element.attributes.byName("AXValue").value();
              if (fv && fv.length > 1) return fv;
            } catch(e) {}
          }
        } catch(e) {}
        try {
          var children = element.attributes.byName("AXChildren").value();
          var limit = Math.min(children.length, 120);
          for (var i = 0; i < limit; i++) {
            if (result.length > 4000) break;
            result += collectText(children[i], depth + 1);
          }
        } catch(e) {}
        return result;
      }

      var collected = collectText(focused, 0);
      if (collected.trim().length > 1) return collected.trim();

      try {
        var parent = focused.attributes.byName("AXParent").value();
        var parentCollected = collectText(parent, 0);
        if (parentCollected.trim().length > 1) return parentCollected.trim();
      } catch(e) {}

      return "";
    } catch (e) {
      return "";
    }
  }
`;

const AX_READER_TIMEOUT_MS = 3000;
const JXA_TIMEOUT_MS = 8000;
const WINDOW = 240;

function expandToSentence(fullText, matchIndex, matchLen) {
  const start = Math.max(0, matchIndex - WINDOW);
  const end = Math.min(fullText.length, matchIndex + matchLen + WINDOW);
  const slice = fullText.slice(start, end);
  const localIndex = matchIndex - start;
  const before = slice.slice(0, localIndex);
  const match = slice.slice(localIndex, localIndex + matchLen);
  const after = slice.slice(localIndex + matchLen);

  const sentenceStart = Math.max(before.lastIndexOf('. '), before.lastIndexOf('! '), before.lastIndexOf('? '), before.lastIndexOf('\n'));
  const trimmedBefore = sentenceStart >= 0 ? before.slice(sentenceStart + 2) : before;

  const sentenceEnd = after.search(/[.!?](?=\s|$)/);
  const trimmedAfter = sentenceEnd >= 0 ? after.slice(0, sentenceEnd + 1) : after;

  return (trimmedBefore + match + trimmedAfter).trim();
}

function findWordInText(fullText, word) {
  const w = (word || '').trim();
  if (!w || !fullText) return null;

  let idx = fullText.indexOf(w);
  if (idx >= 0) return { idx, len: w.length };

  const lower = fullText.toLowerCase();
  const lw = w.toLowerCase();
  idx = lower.indexOf(lw);
  if (idx >= 0) return { idx, len: w.length };

  const bare = w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
  if (bare && bare !== w) {
    idx = fullText.indexOf(bare);
    if (idx >= 0) return { idx, len: bare.length };
    idx = lower.indexOf(bare.toLowerCase());
    if (idx >= 0) return { idx, len: bare.length };
  }
  return null;
}

function contextFromText(fullText, word, source) {
  if (!fullText || fullText.length <= word.length) return null;
  const hit = findWordInText(fullText, word);
  if (!hit) return null;
  const sentence = expandToSentence(fullText, hit.idx, hit.len);
  if (sentence.length <= word.length) return null;
  console.log(`[overlay] context: ${source} → ${sentence.length} chars`);
  return sentence;
}

function startContextRead({ cursor, domSnapshot } = {}) {
  let activeChild = null;
  let cancelled = false;

  function spawn(label, cmd, args, timeoutMs) {
    return new Promise((resolve) => {
      const start = Date.now();
      activeChild = execFile(cmd, args, { timeout: timeoutMs, killSignal: 'SIGKILL' }, (err, stdout) => {
        activeChild = null;
        const elapsed = Date.now() - start;
        if (cancelled) return resolve('');
        if (err) {
          console.log(`[overlay] ${label} ${err.killed ? `timed out after ${timeoutMs}ms` : 'failed: ' + err.message} (${elapsed}ms)`);
          return resolve('');
        }
        const text = (stdout || '').trim();
        console.log(`[overlay] ${label} completed in ${elapsed}ms, got ${text.length} chars`);
        resolve(text);
      });
    });
  }

  const axArgs = [AX_READER_PATH];
  if (cursor && Number.isFinite(cursor.x) && Number.isFinite(cursor.y)) {
    axArgs.push(String(Math.round(cursor.x)), String(Math.round(cursor.y)));
  }

  const axPending = (async () => {
    const fast = await spawn('ax-reader.py', '/usr/bin/python3', axArgs, AX_READER_TIMEOUT_MS);
    if (cancelled) return '';
    if (fast && fast.length > 1) return fast;

    console.log('[overlay] ax-reader.py returned empty, falling back to JXA...');
    return spawn('JXA fallback', 'osascript', ['-l', 'JavaScript', '-e', READ_VALUE_JXA], JXA_TIMEOUT_MS);
  })();

  const resolver = async (word) => {
    if (domSnapshot) {
      const domText = await domSnapshot;
      if (!cancelled && domText) {
        const fromDom = contextFromText(domText, word, 'dom');
        if (fromDom) return fromDom;
      }
    }

    const axText = await axPending;
    if (!cancelled && axText) {
      const fromAx = contextFromText(axText, word, 'ax');
      if (fromAx) return fromAx;
    }

    console.log('[overlay] context: none available (using selection as-is)');
    return word;
  };

  resolver.cancel = () => {
    cancelled = true;
    if (activeChild) { try { activeChild.kill('SIGKILL'); } catch {} }
  };

  return resolver;
}

module.exports = { startContextRead, expandToSentence, findWordInText };