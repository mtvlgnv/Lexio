const { nativeImage } = require('electron');

// Minimal 1×1 transparent PNG — the visible tray label comes from
// tray.setTitle(), not this icon. Shared by every entry point that runs a
// text-only menu-bar tray (main.js, main-overlay.js) so it isn't redefined
// identically in each one.
const BLANK_ICON = nativeImage.createFromDataURL(
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
);

const path = require('path');
const TRAY_ICON = nativeImage.createFromPath(path.join(__dirname, 'trayIconTemplate.png'));

module.exports = { BLANK_ICON, TRAY_ICON };
