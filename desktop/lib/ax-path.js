const { app } = require('electron');
const fs = require('fs');
const path = require('path');

// ax-reader.py must live on a real filesystem path — Python cannot execute
// files inside app.asar (see overlay.log: Errno 20 Not a directory).
function axReaderPath() {
  const candidates = [];
  if (app.isPackaged) {
    candidates.push(path.join(process.resourcesPath, 'app.asar.unpacked', 'lib', 'ax-reader.py'));
  }
  candidates.push(path.join(__dirname, 'ax-reader.py'));
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return candidates[0];
}

module.exports = { axReaderPath };