// Preload for the Hub (menu-bar dashboard: Recent / Settings / Account).
// Exposes a minimal, safe IPC surface to hub.html — no Node in the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lexioHub', {
  getRecent: () => ipcRenderer.invoke('hub:get-recent'),
  getLookupDays: () => ipcRenderer.invoke('hub:get-lookup-days'),
  getAuth:   () => ipcRenderer.invoke('hub:get-auth'),
  signOut:   () => ipcRenderer.send('hub:sign-out'),
  // `cached` ({context, data}) is optional — pass it for a Recent-tab
  // entry that already has its definition, so the relookup renders for
  // free instead of billing a fresh /define call (B11).
  relookup:  (word, cached) => ipcRenderer.send('hub:relookup', cached ? { word, cached } : word),

  getAccessibilityStatus: () => ipcRenderer.invoke('app:accessibility-status'),
  getScreenRecordingStatus: () => ipcRenderer.invoke('app:screen-recording-status'),
  requestAccessibility:   () => ipcRenderer.invoke('app:request-accessibility'),
  openSignIn:             () => ipcRenderer.send('app:open-signin'),
  getLaunchAtLogin:       () => ipcRenderer.invoke('app:get-launch-at-login'),
  setLaunchAtLogin:       (v) => ipcRenderer.send('app:set-launch-at-login', v),
  getHotkey:              () => ipcRenderer.invoke('app:get-hotkey'),
  showOnboarding:         () => ipcRenderer.send('app:show-onboarding'),
  openInputMonitoringSettings: () => ipcRenderer.send('app:open-input-monitoring-settings'),
  openScreenRecordingSettings: () => ipcRenderer.send('app:open-screen-recording-settings'),
  openLogFile: () => ipcRenderer.send('app:open-log-file'),
  openPricing: () => ipcRenderer.send('app:open-pricing'),

  getTriggerKey:          () => ipcRenderer.invoke('app:get-trigger-key'),
  getTriggerOptions:      () => ipcRenderer.invoke('app:get-trigger-options'),
  setTriggerKey:          (id) => ipcRenderer.send('app:set-trigger-key', id),

  // B4/P1-5 Phase 1.5: Home-tab profile-interview card state.
  getProfileInterviewDismissed: () => ipcRenderer.invoke('app:get-profile-interview-dismissed'),
  dismissProfileInterview:      () => ipcRenderer.send('app:dismiss-profile-interview'),

  // B15: privacy-respecting analytics — outcome-only, no content ever.
  getShareAnalytics: () => ipcRenderer.invoke('app:get-share-analytics'),
  setShareAnalytics: (v) => ipcRenderer.send('app:set-share-analytics', v),
  reportSave:        () => ipcRenderer.send('overlay:report-save'),

  onRecentUpdated: (cb) => ipcRenderer.on('hub:recent-updated', (_e, payload) => cb(payload || [])),
  onAuthUpdated:   (cb) => ipcRenderer.on('hub:auth-updated',   (_e, payload) => cb(payload || null)),
});
