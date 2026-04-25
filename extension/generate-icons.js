// Run with: node generate-icons.js
// Requires: npm install canvas  (or use the system canvas if available)
// Generates PNG icons from an SVG-like canvas drawing.

const { createCanvas } = require('canvas');
const fs = require('fs');
const path = require('path');

const sizes = [16, 32, 48, 128];

for (const size of sizes) {
  const canvas = createCanvas(size, size);
  const ctx    = canvas.getContext('2d');
  const r      = size * 0.25; // corner radius

  // Background: accent orange
  ctx.fillStyle = '#c2601a'; // approx oklch(58% 0.17 54)
  roundRect(ctx, 0, 0, size, size, r);
  ctx.fill();

  // Letter "w"
  ctx.fillStyle = '#ffffff';
  ctx.font      = `bold ${size * 0.58}px Georgia, serif`;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('w', size / 2, size / 2 + size * 0.04);

  const buf = canvas.toBuffer('image/png');
  const out = path.join(__dirname, 'icons', `icon${size}.png`);
  fs.writeFileSync(out, buf);
  console.log(`✓ icon${size}.png`);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}
