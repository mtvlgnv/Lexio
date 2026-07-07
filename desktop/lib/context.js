/**
 * Best-effort "auto-expand to the surrounding sentence" for a captured
 * selection — highlight ONE WORD, get a CONTEXTUAL definition.
 *
 * Strategies, in order (first guarded win inside the resolver):
 *   1. DOM block read — when Lexio Glance itself is frontmost (our windows)
 *   2. ax-reader.py — ctypes AX API with cursor anchoring + Chromium tree flip
 *   3. JXA / System Events — slow fallback for native apps
 *   4. Screen OCR — reads the PIXELS around the cursor via Vision. Last
 *      resort, but the ONLY thing that works for display/received text in
 *      custom-draw apps (Telegram/Discord/WhatsApp messages, subtitles,
 *      images, locked PDFs) — where the text isn't in ANY accessibility
 *      tree and there's no caret to extend a selection from. Needs Screen
 *      Recording permission; degrades to word-only without it.
 */
const { execFile } = require('child_process');
const { axReaderPath } = require('./ax-path');
const { contextFromText } = require('./text-utils');
const { runScreenOcr } = require('./ocr-context');

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

  const axArgs = [axReaderPath()];
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

    // Last resort: OCR the pixels around the cursor. This is the only source
    // that reaches display/received text in custom-draw apps (chat messages,
    // subtitles, images) — nothing above can. Runs lazily (only once DOM+AX
    // have failed) since it's the slowest path and needs Screen Recording
    // permission. Its output is guarded by the same contextFromText, so a
    // misread that grabs UI chrome degrades to word-only rather than
    // shipping a wrong definition.
    if (!cancelled && cursor && Number.isFinite(cursor.x) && Number.isFinite(cursor.y)) {
      const ocr = await runScreenOcr({ x: cursor.x, y: cursor.y, hint: word });
      if (!cancelled && ocr && ocr.context) {
        const fromOcr = contextFromText(ocr.context, word, 'ocr');
        if (fromOcr) return fromOcr;
      }
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

module.exports = { startContextRead };