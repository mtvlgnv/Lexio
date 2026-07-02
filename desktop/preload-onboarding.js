// Preload for the onboarding wizard. Exposes a minimal, safe IPC surface to
// onboarding.html — no Node in the renderer. Mirrors preload-overlay.js's
// contextBridge pattern.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lexioOnboarding', {
  getAccessibilityStatus: () => ipcRenderer.invoke('onboarding:accessibility-status'),
  requestAccessibility:   () => ipcRenderer.invoke('onboarding:request-accessibility'),
  openSignIn:             () => ipcRenderer.send('onboarding:open-signin'),
  setLaunchAtLogin:       (v) => ipcRenderer.send('onboarding:set-launch-at-login', v),
  finish:                 () => ipcRenderer.send('onboarding:finish'),

  // Main → renderer: pushed once the lexio://auth deep link lands, or once
  // a real (non-empty) selection is captured during the practice step.
  onAuthComplete:    (cb) => ipcRenderer.on('onboarding:auth-complete',    (_e, payload) => cb(payload || {})),
  onPracticeCapture: (cb) => ipcRenderer.on('onboarding:practice-capture', (_e, payload) => cb(payload || {})),
});
