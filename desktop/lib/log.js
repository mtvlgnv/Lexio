/**
 * Rotating file log for the packaged app — a double-clicked .app has no
 * attached terminal, so console.log alone leaves zero trail once shipped.
 * Tees console.log/warn/error to userData/logs/overlay.log in addition to
 * their normal stdout/stderr behavior. No new dependency (electron-log etc.)
 * — this data is low-volume and the rotation rule is trivial, matching the
 * rest of this app's hand-rolled, dependency-light persistence (store.js).
 */
const { app } = require('electron');
const fs = require('fs');
const path = require('path');

const MAX_BYTES = 2 * 1024 * 1024; // one rotated backup kept past this size

let cachedPath = null;
function logPath() {
  if (cachedPath) return cachedPath;
  const dir = path.join(app.getPath('userData'), 'logs');
  fs.mkdirSync(dir, { recursive: true });
  cachedPath = path.join(dir, 'overlay.log');
  return cachedPath;
}

function rotateIfNeeded(p) {
  try {
    if (fs.statSync(p).size > MAX_BYTES) fs.renameSync(p, p.replace(/\.log$/, '.1.log'));
  } catch {} // ENOENT — nothing written yet, nothing to rotate
}

function writeLine(level, args) {
  try {
    const p = logPath();
    rotateIfNeeded(p);
    const msg = args.map((a) => (a instanceof Error ? a.stack : String(a))).join(' ');
    fs.appendFileSync(p, `[${new Date().toISOString()}] [${level}] ${msg}\n`);
  } catch {} // logging must never be the thing that crashes the app
}

function installFileLogging() {
  ['log', 'warn', 'error'].forEach((level) => {
    const original = console[level].bind(console);
    console[level] = (...args) => { original(...args); writeLine(level, args); };
  });
}

module.exports = { installFileLogging, logPath };
