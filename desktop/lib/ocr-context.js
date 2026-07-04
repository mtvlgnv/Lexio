/**
 * Screen OCR fallback — captures text around the cursor via Apple Vision when
 * Accessibility cannot return surrounding context (subtitles, images, locked
 * PDFs, Electron views, or AX only returning the selected substring).
 */
const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');
const { app } = require('electron');
const { expandToSentence, findWordInText } = require('./text-utils');

const OCR_TIMEOUT_MS = 4000;

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

function runScreenOcr({ x, y, width = 600, height = 200, hint = '' }) {
  const bin = ocrBinaryPath();
  if (!fs.existsSync(bin)) {
    return Promise.resolve(null);
  }
  const args = ['--x', String(Math.round(x)), '--y', String(Math.round(y)),
    '--width', String(width), '--height', String(height)];
  if (hint) args.push('--hint', hint);

  return new Promise((resolve) => {
    const t0 = Date.now();
    execFile(bin, args, { timeout: OCR_TIMEOUT_MS, killSignal: 'SIGKILL' }, (err, stdout, stderr) => {
      if (err) {
        console.log(`[overlay] lexio-ocr ${err.killed ? 'timed out' : 'failed'}: ${stderr?.trim() || err.message}`);
        return resolve(null);
      }
      try {
        const data = JSON.parse(stdout.trim());
        console.log(`[overlay] lexio-ocr completed in ${Date.now() - t0}ms → word="${data.word}" context=${data.context?.length || 0} chars`);
        resolve(data);
      } catch (e) {
        console.log('[overlay] lexio-ocr parse error:', e.message);
        resolve(null);
      }
    });
  });
}

/** Returns expanded sentence context, or null if OCR didn't beat the AX result. */
async function ocrContextForWord({ cursor, word, axText }) {
  if (!cursor || !word) return null;

  const axLen = (axText || '').trim().length;
  const wordLen = word.trim().length;
  // AX already gave us a real paragraph — skip OCR.
  if (axLen > wordLen + 20) {
    const hit = findWordInText(axText, word);
    if (hit) return expandToSentence(axText, hit.idx, hit.len);
  }

  const ocr = await runScreenOcr({ x: cursor.x, y: cursor.y, hint: word });
  if (!ocr?.context || ocr.context.length <= wordLen) return null;

  const ctx = ocr.context.trim();
  const hit = findWordInText(ctx, word);
  if (hit) return expandToSentence(ctx, hit.idx, hit.len);
  return ctx.length > wordLen ? ctx : null;
}

module.exports = { runScreenOcr, ocrContextForWord, ocrBinaryPath };