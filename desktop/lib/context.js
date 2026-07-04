/**
 * Best-effort "auto-expand to the surrounding sentence" for a captured
 * selection — the whole point of the product is highlight ONE WORD, get a
 * CONTEXTUAL definition, but a bare Cmd+C only ever captures exactly what
 * was highlighted. If that's a single word, the model would otherwise
 * receive that word as its own "context", which isn't context at all.
 *
 * Reads the frontmost app's focused UI element's text content via the macOS
 * Accessibility API, then locates the already-captured word inside it and
 * expands to sentence boundaries.
 *
 * PRIMARY: ax-reader.py — a lightweight Python script that calls the AX API
 * directly via ctypes. Runs in ~100ms. Works with native apps AND Electron/
 * Chromium apps (Claude, VS Code, Slack) by walking the AX tree to collect
 * text from AXStaticText child nodes.
 *
 * FALLBACK: The original System Events JXA approach (slow, ~6.5s, but
 * battle-tested on native apps).
 */
const { execFile } = require('child_process');
const path = require('path');

const AX_READER_PATH = path.join(__dirname, 'ax-reader.py');

// Fallback: slow System Events JXA approach
const READ_VALUE_JXA = `
  function run() {
    try {
      var se = Application("System Events");
      var proc = se.applicationProcesses.whose({ frontmost: true })[0];
      var focused = proc.attributes.byName("AXFocusedUIElement").value();

      // Try AXValue on focused element
      try {
        var val = focused.attributes.byName("AXValue").value();
        if (val && val.length > 1) return val;
      } catch(e) {}

      // Walk UP the tree
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

      // Walk DOWN collecting AXStaticText children
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
          if (role === "AXTextField" || role === "AXTextArea") {
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

      // Try parent's subtree
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

// Chars to look each direction before trimming down to sentence boundaries —
// generous enough that real sentences fit, small enough to keep the eventual
// model prompt cheap regardless of how long the source document is.
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

// Starts the (possibly slow) context read immediately, and returns a
// function that, given the already-captured word, resolves to the best
// available context — never throws, degrades to the word itself if the
// read didn't find it.
//
// The returned function also carries a `.cancel()` method (bug #16): the
// read starts before captureSelection() knows whether anything was even
// selected, so a trigger that turns out empty (an accidental hover, no
// text under the cursor) used to leave its ax-reader.py/osascript child
// process running to completion for no reason — harmless once, but a real
// pile-up if triggers fire in quick succession. The caller cancels it as
// soon as it knows the read's result will never be used.
function startContextRead() {
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

  const pending = (async () => {
    // Primary: Python ctypes (~100ms)
    const fast = await spawn('ax-reader.py', '/usr/bin/python3', [AX_READER_PATH], AX_READER_TIMEOUT_MS);
    if (cancelled) return '';
    if (fast && fast.length > 1) return fast;

    // Fallback: JXA via System Events (~6.5s)
    console.log('[overlay] ax-reader.py returned empty, falling back to JXA...');
    return spawn('JXA fallback', 'osascript', ['-l', 'JavaScript', '-e', READ_VALUE_JXA], JXA_TIMEOUT_MS);
  })();

  const resolver = async (word) => {
    const fullText = await pending;
    if (!fullText || fullText.length <= word.length) return word;
    const idx = fullText.indexOf(word);
    return idx === -1 ? word : expandToSentence(fullText, idx, word.length);
  };
  resolver.cancel = () => {
    cancelled = true;
    if (activeChild) { try { activeChild.kill('SIGKILL'); } catch {} }
  };
  return resolver;
}

module.exports = { startContextRead };
