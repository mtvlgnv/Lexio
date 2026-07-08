/**
 * Screen-point capture — grabs the pixels around the cursor and hands them
 * to the backend's /define endpoint as an image. This is the SOLE context
 * source for Lexio Glance: no DOM read, no Accessibility API, no local OCR.
 * The backend's multimodal call (Gemini 2.5 Flash) does the word
 * identification AND the contextual definition in one shot from the image.
 *
 * The heavy lifting is a tiny native helper (native/lexio-ocr,
 * ScreenCaptureKit) — spawned as a child process. It returns a base64 PNG
 * of the captured region; this module just resolves that (or null on
 * failure) so main-overlay.js can hand it to the renderer.
 *
 * Requires Screen Recording permission for Lexio Glance.
 */
const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');
const { app, screen } = require('electron');

const CAPTURE_TIMEOUT_MS = 4000;

// The compiled helper can't live inside app.asar (a Mach-O binary can't be
// exec'd from an archive) — it's asarUnpack'd to app.asar.unpacked/bin in
// packaged builds, and lives at desktop/bin in dev.
function captureBinaryPath() {
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

// Resolves to { image_base64, width, height, ms } or null.
function captureScreenPoint({ x, y, width = 800, height = 500 }) {
  const bin = captureBinaryPath();
  if (!fs.existsSync(bin)) {
    console.log('[overlay] lexio-ocr binary missing — screen capture unavailable (run npm run build-ocr)');
    return Promise.resolve(null);
  }
  // Clamp the region to the display holding the cursor. Near a screen edge
  // the cursor can't stay centered — the helper draws its marker ring at the
  // true cursor offset within this rect, so the region's exact position must
  // be decided HERE, where display bounds are known, not re-derived there.
  const d = screen.getDisplayNearestPoint({ x: Math.round(x), y: Math.round(y) }).bounds;
  const rw = Math.min(width, d.width);
  const rh = Math.min(height, d.height);
  const rx = Math.max(d.x, Math.min(Math.round(x - rw / 2), d.x + d.width - rw));
  const ry = Math.max(d.y, Math.min(Math.round(y - rh / 2), d.y + d.height - rh));
  const args = ['--x', String(Math.round(x)), '--y', String(Math.round(y)),
    '--rx', String(rx), '--ry', String(ry), '--rw', String(rw), '--rh', String(rh)];

  return new Promise((resolve) => {
    const t0 = Date.now();
    // maxBuffer default (1MB) is too small for a base64 PNG on stdout.
    execFile(bin, args, { timeout: CAPTURE_TIMEOUT_MS, killSignal: 'SIGKILL', maxBuffer: 32 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) {
          const why = err.killed ? `timed out after ${CAPTURE_TIMEOUT_MS}ms` : (stderr?.trim() || err.message);
          console.log(`[overlay] lexio-ocr capture failed: ${why}`);
          return resolve(null);
        }
        try {
          const data = JSON.parse((stdout || '').trim());
          console.log(`[overlay] screen capture completed in ${Date.now() - t0}ms → ${data.width}x${data.height}, ${data.image_base64?.length || 0} b64 chars`);
          resolve(data);
        } catch (e) {
          console.log('[overlay] lexio-ocr parse error:', e.message);
          resolve(null);
        }
      });
  });
}

module.exports = { captureScreenPoint, captureBinaryPath };
