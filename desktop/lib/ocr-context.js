/**
 * Screen OCR fallback — captures the pixels around the cursor and runs Apple
 * Vision OCR on them, for when no accessibility tree exposes the text
 * (Telegram/Discord/WhatsApp received messages, subtitles, images, locked
 * PDFs, custom-draw views). This is the ONLY context source that works on
 * display text with no caret and no AX data.
 *
 * The heavy lifting is a tiny native helper (native/lexio-ocr, ScreenCapture-
 * Kit + Vision) — spawned as a child process. It returns the recognized line
 * around the pointer as JSON; context.js runs it through the same guarded
 * sentence extraction (contextFromText) as every other source, so an OCR
 * misread that grabs UI chrome degrades to word-only rather than shipping a
 * confidently-wrong definition.
 *
 * Requires Screen Recording permission for Lexio Glance. Without it the
 * helper exits non-zero and this resolves null (→ word-only).
 */
const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');
const { app } = require('electron');

const OCR_TIMEOUT_MS = 4000;

// The compiled helper can't live inside app.asar (a Mach-O binary can't be
// exec'd from an archive) — it's asarUnpack'd to app.asar.unpacked/bin in
// packaged builds, and lives at desktop/bin in dev.
function ocrBinaryPath() {
  const candidates = [];
  if (app.isPackaged) {
    candidates.push(path.join(process.resourcesPath, 'app.asar.unpacked', 'bin', 'lexio-ocr'));
  }
  candidates.push(path.join(__dirname, '..', 'bin', 'lexio-ocr'));
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return candidates[0];
}

// Resolves to { word, context, confidence, ms } or null.
function runScreenOcr({ x, y, width = 700, height = 260, hint = '' }) {
  const bin = ocrBinaryPath();
  if (!fs.existsSync(bin)) {
    console.log('[overlay] lexio-ocr binary missing — OCR fallback unavailable (run npm run build-ocr)');
    return Promise.resolve(null);
  }
  const args = ['--x', String(Math.round(x)), '--y', String(Math.round(y)),
    '--width', String(width), '--height', String(height)];
  if (hint) args.push('--hint', hint);

  return new Promise((resolve) => {
    const t0 = Date.now();
    execFile(bin, args, { timeout: OCR_TIMEOUT_MS, killSignal: 'SIGKILL' }, (err, stdout, stderr) => {
      if (err) {
        const why = err.killed ? `timed out after ${OCR_TIMEOUT_MS}ms` : (stderr?.trim() || err.message);
        console.log(`[overlay] lexio-ocr failed: ${why}`);
        return resolve(null);
      }
      try {
        const data = JSON.parse((stdout || '').trim());
        console.log(`[overlay] lexio-ocr completed in ${Date.now() - t0}ms → word="${data.word}" context=${data.context?.length || 0} chars`);
        resolve(data);
      } catch (e) {
        console.log('[overlay] lexio-ocr parse error:', e.message);
        resolve(null);
      }
    });
  });
}

module.exports = { runScreenOcr, ocrBinaryPath };
