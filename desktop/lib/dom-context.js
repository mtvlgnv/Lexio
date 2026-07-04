/**
 * Read surrounding text from a focused Lexio Glance window via the DOM.
 * Electron renderers don't expose their HTML through the macOS AX tree,
 * but we own these windows — getSelection() + a climb to the nearest
 * readable block is instant and exact.
 */
const { BrowserWindow } = require('electron');

// Runs inside the focused renderer. Returns the best-effort paragraph/block
// that contains the current selection (not just the selected substring).
const CAPTURE_BLOCK_JS = `
(() => {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return '';
  const word = sel.toString().trim();
  if (!word) return '';
  let node = sel.anchorNode;
  if (node && node.nodeType === Node.TEXT_NODE) node = node.parentElement;
  let el = node;
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  while (el && el !== document.body) {
    const t = norm(el.innerText || el.textContent);
    if (t.length >= word.length + 8 && t.toLowerCase().includes(word.toLowerCase())) return t;
    el = el.parentElement;
  }
  const body = norm(document.body.innerText || document.body.textContent);
  return body.slice(0, 6000);
})()
`;

async function readBlockFromFrame(frame) {
  try {
    const text = await frame.executeJavaScript(CAPTURE_BLOCK_JS);
    return (text || '').trim();
  } catch {
    return '';
  }
}

async function captureDomBlockFromFocusedWindow() {
  const focused = BrowserWindow.getFocusedWindow();
  if (!focused || focused.isDestroyed()) return '';
  try {
    const { webContents } = focused;
    const frames = webContents.mainFrame?.framesInSubtree || [webContents.mainFrame];
    for (const frame of frames) {
      const text = await readBlockFromFrame(frame);
      if (text.length > 0) {
        console.log(`[overlay] dom-context: got ${text.length} chars from frame`);
        return text;
      }
    }
    return '';
  } catch (err) {
    console.log('[overlay] dom-context: focused window read failed:', err.message);
    return '';
  }
}

function beginDomContextCapture(isOwnAppFrontmost) {
  if (!isOwnAppFrontmost) return Promise.resolve('');
  return captureDomBlockFromFocusedWindow();
}

module.exports = { beginDomContextCapture, captureDomBlockFromFocusedWindow };