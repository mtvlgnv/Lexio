const { execFile } = require('child_process');

function getFrontmostPid() {
  return new Promise((resolve) => {
    execFile('lsappinfo', ['info', '-only', 'pid', 'front'], { timeout: 800 }, (err, stdout) => {
      if (err) { resolve(null); return; }
      const m = (stdout || '').match(/pid=(\d+)/);
      resolve(m ? parseInt(m[1], 10) : null);
    });
  });
}

module.exports = { getFrontmostPid };