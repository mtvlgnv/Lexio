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

  // Main → renderer: sign-in state changed (payload = { token, user } or
  // null on sign-out). pill.html forwards it into the compact.html webview,
  // whose partitioned localStorage is where auth actually needs to live.
  onAuth: (cb) => ipcRenderer.on('overlay:auth', (_e, payload) => cb(payload ?? null)),

  // Display-only — which key the double-tap trigger currently listens for,
  // so the pill's tooltip doesn't lie after it's changed in Hub Settings.
  getTriggerSymbol: () => ipcRenderer.invoke('app:get-trigger-symbol'),
});
