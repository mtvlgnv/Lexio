// Preload for the Wispr-style overlay (Phase 1 + Phase 2).
// Exposes a minimal, safe IPC surface to pill.html — no Node in the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lexioOverlay', {
  // Renderer → main: ask the main process to resize/show the window.
  requestExpand:   () => ipcRenderer.send('overlay:expand-request'),
  requestCollapse: () => ipcRenderer.send('overlay:collapse-request'),
  startDrag:       () => ipcRenderer.send('overlay:start-drag'),

  // Main → renderer: the window finished resizing; switch visual state.
  // `payload.word` (Phase 2) carries whatever was captured from the user's
  // selection in the app they were reading — absent if nothing was
  // selected or Accessibility permission hasn't been granted yet.
  // `payload.contextPending` means the surrounding-sentence read is still
  // in flight — the real 'overlay:context-ready' event below follows once
  // it resolves (a real few-second wait — see lib/context.js).
  onExpand:   (cb) => ipcRenderer.on('overlay:expand',   (_e, payload) => cb(payload || {})),
  onCollapse: (cb) => ipcRenderer.on('overlay:collapse', () => cb()),

  // Main → renderer: the auto-expanded context for the CURRENT capture
  // finally resolved — fires once, sometime after onExpand's
  // contextPending: true, carrying the same word plus the real context
  // (or the word itself again if none could be found in time).
  onContextReady: (cb) => ipcRenderer.on('overlay:context-ready', (_e, payload) => cb(payload)),

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
