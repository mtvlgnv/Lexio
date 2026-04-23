/**
 * Renders the Lexio app icon using Electron's offscreen canvas,
 * then saves it to build/icon.png.
 *
 * Run with:  node_modules/.bin/electron create-icon.js
 */

const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs   = require('fs');

app.whenReady().then(async () => {
  const SIZE = 1024;

  const win = new BrowserWindow({
    width: SIZE, height: SIZE,
    show: false,
    webPreferences: { offscreen: true, contextIsolation: false },
  });

  // Draw the icon entirely in a <canvas> element so we can capture it.
  // Georgia is available on every macOS install — no network needed.
  const html = `
<!DOCTYPE html>
<html>
<body style="margin:0;overflow:hidden;">
<canvas id="c" width="${SIZE}" height="${SIZE}"></canvas>
<script>
const canvas = document.getElementById('c');
const ctx    = canvas.getContext('2d');
const S      = ${SIZE};
const R      = 210;          // corner radius

/* ── rounded-rect clip ─────────────────────────────── */
function roundedRect(r) {
  ctx.beginPath();
  ctx.moveTo(r, 0); ctx.lineTo(S - r, 0);
  ctx.arcTo(S, 0,   S,   r,   r);
  ctx.lineTo(S, S - r);
  ctx.arcTo(S, S,   S-r, S,   r);
  ctx.lineTo(r, S);
  ctx.arcTo(0, S,   0,   S-r, r);
  ctx.lineTo(0, r);
  ctx.arcTo(0, 0,   r,   0,   r);
  ctx.closePath();
}

/* ── background gradient ───────────────────────────── */
roundedRect(R);
const g = ctx.createLinearGradient(0, 0, S, S);
g.addColorStop(0, '#faf4ed');
g.addColorStop(1, '#ece0d0');
ctx.fillStyle = g;
ctx.fill();

/* ── subtle inner shadow ring ──────────────────────── */
roundedRect(R);
ctx.strokeStyle = 'rgba(0,0,0,0.07)';
ctx.lineWidth = 6;
ctx.stroke();

/* ── lettermark "w" ────────────────────────────────── */
ctx.font         = 'bold 560px Georgia, serif';
ctx.fillStyle    = '#9c6b3c';
ctx.textAlign    = 'center';
ctx.textBaseline = 'middle';
ctx.fillText('w', S / 2, S / 2 + 24);

document.title = 'done';
</script>
</body>
</html>`;

  await win.loadURL('data:text/html,' + encodeURIComponent(html));

  // Wait for the canvas to finish drawing
  await new Promise(resolve => {
    const t = setTimeout(resolve, 4000);
    win.webContents.on('page-title-updated', () => { clearTimeout(t); setTimeout(resolve, 100); });
  });

  const image = await win.webContents.capturePage();
  const outPath = path.join(__dirname, 'build', 'icon.png');
  fs.writeFileSync(outPath, image.toPNG());
  console.log(`✓ Icon saved → ${outPath}`);
  app.quit();
});

app.on('window-all-closed', () => {});
