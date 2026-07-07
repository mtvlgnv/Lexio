// Preload for the Wispr-style overlay (Phase 1 + Phase 2).
// Exposes a minimal, safe IPC surface to pill.html — no Node in the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lexioOverlay', {
  // Renderer → main: ask the main process to resize/show the window.
  requestExpand:   () => ipcRenderer.send('overlay:expand-request'),
  requestCollapse: () => ipcRenderer.send('overlay:collapse-request'),
  startDrag:       () => ipcRenderer.send('overlay:start-drag'),

  // Main → renderer: the window finished resizing; switch visual state.
  // `payload.imagePending` means a screenshot of the area around the
  // cursor is being captured — no word is known yet (the point of this
  // mode: no selection needed). The real 'overlay:image-ready' event below
  // follows once the capture resolves (see lib/vision-capture.js).
  onExpand:   (cb) => ipcRenderer.on('overlay:expand',   (_e, payload) => cb(payload || {})),
  onCollapse: (cb) => ipcRenderer.on('overlay:collapse', () => cb()),

  // Main → renderer: the screenshot for the CURRENT capture finally
  // resolved — fires once, sometime after onExpand's imagePending: true,
  // carrying the base64 PNG (or null if the capture failed / Screen
  // Recording isn't granted). The backend identifies the word AND defines
  // it from this image in one call.
  onImageReady: (cb) => ipcRenderer.on('overlay:image-ready', (_e, payload) => cb(payload)),

  // Main → renderer: sign-in state changed (payload = { token, user } or
  // null on sign-out). pill.html forwards it into the compact.html webview,
  // whose partitioned localStorage is where auth actually needs to live.
  onAuth: (cb) => ipcRenderer.on('overlay:auth', (_e, payload) => cb(payload ?? null)),

  // Display-only — which key the double-tap trigger currently listens for,
  // so the pill's tooltip doesn't lie after it's changed in Hub Settings.
  getTriggerSymbol: () => ipcRenderer.invoke('app:get-trigger-symbol'),

  // Renderer → main: the webview (via its console-message bridge) told us
  // which word was actually defined — main records it as the real recent
  // lookup instead of the raw captured selection.
  reportLookup: (word) => ipcRenderer.send('overlay:report-lookup', word),

  // Renderer → main: pin/unpin — while pinned, clicking into another app
  // won't auto-collapse the panel.
  setPinned: (value) => ipcRenderer.send('overlay:set-pinned', value),
});
