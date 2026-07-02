// Preload for the Wispr-style overlay (Phase 1 + Phase 2).
// Exposes a minimal, safe IPC surface to pill.html — no Node in the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lexioOverlay', {
  // Renderer → main: ask the main process to resize/show the window.
  requestExpand:   () => ipcRenderer.send('overlay:expand-request'),
  requestCollapse: () => ipcRenderer.send('overlay:collapse-request'),

  // Main → renderer: the window finished resizing; switch visual state.
  // `payload.text` (Phase 2) carries whatever was captured from the
  // user's selection in the app they were reading — null if nothing
  // was selected or Accessibility permission hasn't been granted yet.
  onExpand:   (cb) => ipcRenderer.on('overlay:expand',   (_e, payload) => cb(payload || {})),
  onCollapse: (cb) => ipcRenderer.on('overlay:collapse', () => cb()),
});
