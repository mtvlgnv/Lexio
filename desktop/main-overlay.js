/**
 * Lexio Glance — Wispr-style overlay (Phase 1 + Phase 2)
 * ------------------------------------------------------------------
 * A small stylish pill docked at the bottom-center of the screen,
 * always on top. Double-tap ⌘ (or click the pill) to expand it into
 * the full Lexio lookup panel; Esc / click-away collapses it back.
 *
 * Phase 2 adds "define my selection anywhere": right before the panel
 * opens, it silently captures whatever text is selected in the app
 * you were just reading (synthesized ⌘C + clipboard read/restore) and
 * feeds it straight into the lookup flow — so the panel opens already
 * showing the definition, no pasting required.
 *
 * Parallel to the existing entries (main.js, main-app.js) — run with:
 *     npm run start-overlay
 *
 * The double-tap-⌘ trigger uses the optional native module
 * `uiohook-napi`. If it isn't installed/built, the overlay still works
 * via the fallback global shortcut below, so you can try it instantly.
 *
 * Selection capture needs macOS Accessibility permission (System
 * Settings → Privacy & Security → Accessibility). Without it, the
 * panel still opens — just empty, same as Phase 1 — so nothing breaks
 * for users who haven't granted it yet.
 */
const { app, BrowserWindow, globalShortcut, screen, Tray, Menu, nativeImage, ipcMain,
        clipboard, systemPreferences, shell } = require('electron');
const { execFile } = require('child_process');
const path = require('path');
const store = require('./store');

// Same handoff the website already implements for main.js (see
// static/app.js _maybeRedirectDesktop): opening lexio.site with
// ?desktop_auth=1 makes it redirect to lexio://auth?token=...&user=...
// after a successful login/signup, instead of staying on the site.
const SIGNIN_URL = 'https://lexio.site?desktop_auth=1';

// Surface anything that would otherwise fail silently — a background
// overlay with no console attached is easy to leave in a broken state
// with zero indication of why. Both handlers just log; they don't quit.
process.on('uncaughtException',  (err) => console.error('[overlay] uncaughtException:', err));
process.on('unhandledRejection', (err) => console.error('[overlay] unhandledRejection:', err));

app.setName('Lexio Glance');
if (process.platform === 'darwin') app.dock.hide();   // live as an overlay, not a dock app

let win  = null;
let tray = null;
let onboardingWin = null;
let hubWin = null;
let expanded = false;
let activeFallbackShortcut = null;

// Bottom margin and the two window sizes the pill morphs between.
// The collapsed pill is a 36px gradient disc (see pill.html). COLLAPSED is
// kept close to that size on purpose — not because of the transparency bug
// (that turned out to be Electron 34 predating this Mac's very new macOS
// "Tahoe" release; upgrading to Electron 43 fixed it outright, no residual
// artifact), just because a tight, disc-sized window is the cleaner design.
const MARGIN_BOTTOM = 10;
const COLLAPSED = { width: 44, height: 42 };
const EXPANDED  = { width: 460, height: 580 };

// Duration/easing for the custom smooth window-grow (see animateBounds
// below) — tuned to read as a visible, deliberate "blend" from pill to
// full app, similar in spirit to the reference clip of the redesigned
// Siri "Search or Ask" bar growing from a small dot into its full pill
// shape (measured at roughly 1.2s in that clip; we use a brisker 480ms
// since this is a utility trigger, not a marketing demo — easy to retune).
const EXPAND_MS   = 480;
const COLLAPSE_MS = 260;
function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

// Manually steps a window's bounds from `from` to `to` over `duration`ms.
// (Tried switching this to native setBounds(bounds, true) for a GPU/vsync
// -composited resize, expecting it to be smoother — it wasn't; this custom
// stepped version reads better in practice, so it's back.) Also gives full
// control over duration/easing, which native animation doesn't expose.
function animateBounds(from, to, duration, easing) {
  return new Promise((resolve) => {
    const start = Date.now();
    function step() {
      if (!win || win.isDestroyed()) return resolve();
      const t = Math.min(1, (Date.now() - start) / duration);
      const e = easing(t);
      win.setBounds({
        x:      Math.round(from.x      + (to.x      - from.x)      * e),
        y:      Math.round(from.y      + (to.y      - from.y)      * e),
        width:  Math.round(from.width  + (to.width  - from.width)  * e),
        height: Math.round(from.height + (to.height - from.height) * e),
      }, false);
      if (t < 1) setTimeout(step, 1000 / 60);
      else resolve();
    }
    step();
  });
}

const BLANK_ICON = nativeImage.createFromDataURL(
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
);

/* ── Position helpers — bottom-center of the active display ──────── */
function boundsFor(size) {
  const cursor  = screen.getCursorScreenPoint();
  const display = screen.getDisplayNearestPoint(cursor);
  const wa = display.workArea;                        // excludes menu bar / dock
  return {
    width:  size.width,
    height: size.height,
    x: Math.round(wa.x + (wa.width - size.width) / 2),
    y: Math.round(wa.y + wa.height - size.height - MARGIN_BOTTOM),
  };
}

/* ── Selection capture (Phase 2) ──────────────────────────────────
   Grabs whatever text is selected in the app that currently has focus,
   without disturbing the user's real clipboard. Must run BEFORE we
   show/focus our own window, or the ⌘C would hit us instead of them.

   Two DIFFERENT macOS permissions gate this, and failures here were
   previously silent — logging every branch below so a stuck/broken
   capture is diagnosable from the log instead of guessed at:
     • Accessibility        — lets us detect the double-tap ⌘ at all
     • Automation            — lets us tell System Events to send ⌘C
       ("<App> wants to control System Events.app" — a SEPARATE
       permission from Accessibility, granted per-pair of apps under
       System Settings → Privacy & Security → Automation). If this
       hasn't been granted, osascript exits non-zero every time. */
function ensureAccessibility() {
  if (process.platform !== 'darwin') return true;
  const ok = systemPreferences.isTrustedAccessibilityClient(true);
  if (!ok) console.warn('[overlay] Accessibility permission not granted — skipping capture.');
  return ok;
}

// Non-prompting status check, safe to poll from the onboarding UI —
// isTrustedAccessibilityClient(true) instead shows the system prompt every
// time it's called, which would spam the user if polled on an interval.
function checkAccessibility() {
  if (process.platform !== 'darwin') return true;
  return systemPreferences.isTrustedAccessibilityClient(false);
}

function sendCmdC() {
  return new Promise((resolve) => {
    execFile('osascript',
      ['-e', 'tell application "System Events" to keystroke "c" using command down'],
      { timeout: 2000 },   // never hang forever — a blocked/denied automation call must fail, not freeze us
      (err, stdout, stderr) => {
        if (err) console.warn('[overlay] synthesized ⌘C failed (likely missing Automation permission for System Events):', stderr?.trim() || err.message);
        resolve(!err);
      });
  });
}

async function captureSelection() {
  if (process.platform !== 'darwin') return null;   // Phase 2 is macOS-only for now
  if (!ensureAccessibility()) return null;           // not granted yet — caller falls back gracefully

  const original = clipboard.readText();
  const sentinel = `__lexio_empty_${Date.now()}__`;
  clipboard.writeText(sentinel);                     // so we can detect "nothing was selected"

  const sent = await sendCmdC();
  if (!sent) { clipboard.writeText(original); return null; }

  await new Promise((r) => setTimeout(r, 150));      // give the OS a beat to complete the copy
  const captured = clipboard.readText();
  clipboard.writeText(original);                     // restore the user's real clipboard immediately

  if (!captured || captured === sentinel) {
    console.log('[overlay] capture: nothing was selected');
    return null;
  }
  console.log(`[overlay] capture: got ${captured.length} chars`);

  const recentLookups = [{ word: captured.slice(0, 80), at: Date.now() }, ...store.get().recentLookups].slice(0, 50);
  store.set({ recentLookups });
  if (hubWin && !hubWin.isDestroyed()) hubWin.webContents.send('hub:recent-updated', recentLookups);

  // If the onboarding wizard is open on its practice-run step, this real
  // capture is what it's waiting for — let it advance itself instead of
  // requiring a manual "Next" click.
  if (onboardingWin && !onboardingWin.isDestroyed()) {
    onboardingWin.webContents.send('onboarding:practice-capture', { text: captured });
  }
  return captured;
}

/* ── Expand / collapse ──────────────────────────────────────────── */
// Wrapped in try/catch/finally so that ANY failure here (a destroyed
// window, a hung child process, anything) still surfaces in the log AND
// still resets `expanded` — otherwise a single bad run leaves the flag
// stuck at true forever, and every future trigger silently no-ops into
// collapse() instead of expand(). This is almost certainly what "worked
// once, then nothing" was: the first run's error left this stuck.
async function expand() {
  if (expanded) return;
  expanded = true;
  try {
    if (!win || win.isDestroyed()) { console.warn('[overlay] window was gone — recreating.'); createWindow(); }
    const selection = await captureSelection();   // BEFORE resize/show/focus — see note above
    const fromBounds = win.getBounds();
    const toBounds    = boundsFor(EXPANDED);
    // Content crossfade (pill.html's CSS) starts now, in parallel with the
    // window smoothly growing below — both tuned to ~EXPAND_MS so they
    // land together instead of the content "arriving" before/after the
    // window has finished resizing.
    win.webContents.send('overlay:expand', { text: selection });
    win.setIgnoreMouseEvents(false);
    win.show();
    win.focus();
    await animateBounds(fromBounds, toBounds, EXPAND_MS, easeOutCubic);
  } catch (err) {
    console.error('[overlay] expand() failed:', err);
    expanded = false;   // never leave the toggle stuck — next trigger should get a clean retry
  }
}

function collapse() {
  if (!expanded) return;
  expanded = false;
  win.webContents.send('overlay:collapse');
  const fromBounds = win.getBounds();
  animateBounds(fromBounds, boundsFor(COLLAPSED), COLLAPSE_MS, easeOutCubic);
}

function toggle() { expanded ? collapse() : expand(); }

/* ── Window ─────────────────────────────────────────────────────── */
function createWindow() {
  const b = boundsFor(COLLAPSED);
  win = new BrowserWindow({
    ...b,
    frame: false,
    transparent: true,
    hasShadow: false,             // the pill/panel cast their own CSS shadow
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    fullscreenable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload-overlay.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // <webview> hosts compact.html as a guest context, which (unlike an
      // <iframe>) is not blocked by the site's X-Frame-Options: DENY header.
      webviewTag: true,
    },
    show: false,
  });

  // Float above almost everything, and stay visible across Spaces.
  win.setAlwaysOnTop(true, 'pop-up-menu');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  win.loadFile(path.join(__dirname, 'pill.html'));
  win.once('ready-to-show', () => win.show());

  // Replay any stored sign-in so the webview is authenticated from the first
  // open, not only after a fresh lexio://auth handoff in this session.
  win.webContents.on('did-finish-load', () => {
    const auth = store.get().auth;
    if (auth) win.webContents.send('overlay:auth', auth);
  });

  // Click-away collapses (but keeps the pill on screen).
  win.on('blur', () => collapse());

  // If the window is ever destroyed (crash, accidental close), drop the
  // stale reference so expand() knows to recreate it instead of throwing
  // "Object has been destroyed" on the next trigger.
  win.on('closed', () => { win = null; expanded = false; });
}

/* ── Onboarding window ─────────────────────────────────────────────
   A normal-sized (not pill-shaped) window shown on first launch, and
   reopenable later from the tray. Only one instance at a time — a second
   request just focuses the existing window. */
function createOnboardingWindow() {
  if (onboardingWin && !onboardingWin.isDestroyed()) { onboardingWin.focus(); return; }
  onboardingWin = new BrowserWindow({
    width: 560,
    height: 620,
    resizable: false,
    frame: false,
    backgroundColor: '#f5efe8',
    roundedCorners: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload-onboarding.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });
  onboardingWin.loadFile(path.join(__dirname, 'onboarding.html'));
  onboardingWin.once('ready-to-show', () => onboardingWin.show());
  onboardingWin.on('closed', () => { onboardingWin = null; });
}

/* ── Hub window ─────────────────────────────────────────────────────
   A small dropdown-style dashboard anchored under the tray icon —
   Recent lookups / Settings / Account, per the master plan (Settings
   merged into the Hub rather than its own window). Closes on blur, like
   a normal menu-bar dropdown, unlike the onboarding wizard. */
function createHubWindow() {
  if (hubWin && !hubWin.isDestroyed()) { hubWin.focus(); return; }
  // Same anchoring math as main.js's getPosition() for its tray dropdown.
  const trayBounds = tray ? tray.getBounds() : null;
  const width = 380, height = 520;
  hubWin = new BrowserWindow({
    width,
    height,
    x: trayBounds ? Math.round(trayBounds.x + trayBounds.width / 2 - width / 2) : undefined,
    y: trayBounds ? Math.round(trayBounds.y + trayBounds.height + 6) : undefined,
    resizable: false,
    frame: false,
    backgroundColor: '#f5efe8',
    roundedCorners: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload-hub.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });
  hubWin.loadFile(path.join(__dirname, 'hub.html'));
  hubWin.once('ready-to-show', () => hubWin.show());
  hubWin.on('blur', () => { if (hubWin && !hubWin.isDestroyed()) hubWin.close(); });
  hubWin.on('closed', () => { hubWin = null; });
}

/* ── Renderer → main IPC ────────────────────────────────────────── */
ipcMain.on('overlay:expand-request',   () => expand());
ipcMain.on('overlay:collapse-request', () => collapse());

// Shared between the onboarding wizard and the Hub's Settings/Account tabs.
ipcMain.handle('app:accessibility-status', () => checkAccessibility());
ipcMain.handle('app:request-accessibility', () => ensureAccessibility());
ipcMain.on('app:open-signin', () => shell.openExternal(SIGNIN_URL));
ipcMain.handle('app:get-launch-at-login', () => store.get().settings.launchAtLogin);
ipcMain.on('app:set-launch-at-login', (_e, value) => {
  app.setLoginItemSettings({ openAtLogin: !!value });
  store.set({ settings: { ...store.get().settings, launchAtLogin: !!value } });
});
ipcMain.handle('app:get-hotkey', () => activeFallbackShortcut);
ipcMain.on('app:show-onboarding', () => createOnboardingWindow());

ipcMain.handle('app:get-trigger-key', () => activeTriggerKey);
ipcMain.handle('app:get-trigger-symbol', () => TRIGGER_KEYS[activeTriggerKey].symbol);
ipcMain.handle('app:get-trigger-options', () =>
  Object.entries(TRIGGER_KEYS).map(([id, d]) => ({ id, label: d.label, symbol: d.symbol })));
ipcMain.on('app:set-trigger-key', (_e, key) => {
  applyTriggerKey(key);
  store.set({ settings: { ...store.get().settings, doubleTapKey: activeTriggerKey } });
});

ipcMain.on('onboarding:finish', () => {
  store.set({ onboardingComplete: true });
  if (onboardingWin && !onboardingWin.isDestroyed()) onboardingWin.close();
});

ipcMain.handle('hub:get-recent', () => store.get().recentLookups);
ipcMain.handle('hub:get-auth',   () => store.get().auth);
ipcMain.on('hub:sign-out', () => {
  store.set({ auth: null });
  if (hubWin && !hubWin.isDestroyed()) hubWin.webContents.send('hub:auth-updated', null);
  if (win && !win.isDestroyed()) win.webContents.send('overlay:auth', null);
});

/* ── lexio:// URL scheme — auth handoff from the website ──────────
   Mirrors the same mechanism main.js already uses: the site redirects to
   lexio://auth?token=...&user=... after a successful login/signup when it
   was opened with ?desktop_auth=1 (see SIGNIN_URL above). */
app.setAsDefaultProtocolClient('lexio');

app.on('open-url', (event, url) => {
  event.preventDefault();
  try {
    const parsed = new URL(url);
    if (parsed.hostname === 'auth') {
      const token = parsed.searchParams.get('token');
      const rawUser = parsed.searchParams.get('user');
      if (token) {
        let user = null;
        try { user = rawUser ? JSON.parse(rawUser) : null; } catch {}
        store.set({ auth: { token, user } });
        if (onboardingWin && !onboardingWin.isDestroyed()) {
          onboardingWin.webContents.send('onboarding:auth-complete', { token, user });
        }
        if (hubWin && !hubWin.isDestroyed()) {
          hubWin.webContents.send('hub:auth-updated', { token, user });
        }
        // The embedded compact.html webview keeps its own localStorage in the
        // persist:lexio partition — it never sees store.js. Forward the token
        // so pill.html can inject it (mirrors what main.js does for Lexio Mini).
        if (win && !win.isDestroyed()) {
          win.webContents.send('overlay:auth', { token, user });
        }
      }
    }
  } catch (err) {
    console.error('[overlay] failed to handle lexio:// URL:', err);
  }
});

/* ── Tray (so the floating widget is always quittable) ──────────── */
function updateTrayToolTip() {
  if (!tray) return;
  const symbol = TRIGGER_KEYS[activeTriggerKey].symbol;
  tray.setToolTip(`Lexio Glance — click for recent lookups & settings, double-tap ${symbol} to look something up`);
}

function createTray() {
  tray = new Tray(BLANK_ICON);
  tray.setTitle(' Lx ');
  updateTrayToolTip();
  const menu = Menu.buildFromTemplate([
    { label: 'Open Lexio',        click: () => expand() },
    { label: 'Hide',              click: () => collapse() },
    { type: 'separator' },
    { label: 'Recent & Settings', click: () => createHubWindow() },
    { label: 'Getting Started',   click: () => createOnboardingWindow() },
    { type: 'separator' },
    { label: 'Quit Lexio',        click: () => app.quit() },
  ]);
  tray.on('right-click', () => tray.popUpContextMenu(menu));
  // Left-click opens the Hub (dashboard), matching the Wispr/Raycast
  // pattern — the pill itself is already the quick-action trigger
  // (hover/click/double-tap ⌘), so the tray icon's own job is the
  // dashboard, not a second way to toggle the pill.
  tray.on('click', () => createHubWindow());
}

/* ── Trigger: double-tap a modifier key (native), with fallback shortcut ──
   ⌘ was the original default, but it collides with Siri's own "press ⌘
   twice" binding on macOS with no way for us to detect or work around
   that collision — Siri simply wins. Control has no default macOS or
   Siri binding, so it's the new default; Option/Shift/Command remain
   selectable in the Hub for anyone whose own setup already claims ⌃.
   Codes are uiohook-napi's UiohookKey values, inlined so this list works
   even before uiohook-napi has been `require`d (e.g. it's not installed). */
const TRIGGER_KEYS = {
  ctrl:  { label: 'Control', symbol: '⌃', codes: [29, 3613] },
  alt:   { label: 'Option',  symbol: '⌥', codes: [56, 3640] },
  shift: { label: 'Shift',   symbol: '⇧', codes: [42, 54] },
  meta:  { label: 'Command', symbol: '⌘', codes: [3675, 3676] },
};
let activeTriggerKey = 'ctrl';
let activeTriggerCodes = new Set(TRIGGER_KEYS.ctrl.codes);

function applyTriggerKey(key) {
  activeTriggerKey = TRIGGER_KEYS[key] ? key : 'ctrl';
  activeTriggerCodes = new Set(TRIGGER_KEYS[activeTriggerKey].codes);
  updateTrayToolTip();
}

// globalShortcut.register() returns false (not an exception) when another
// app already owns the combo — Cmd+Shift+L is a common one (bookmark
// managers, browsers, etc.), so we try a short list and log what actually
// registered instead of assuming the first one worked.
function registerFallbackShortcut() {
  const candidates = ['CommandOrControl+Shift+L', 'CommandOrControl+Shift+K', 'Alt+CommandOrControl+L'];
  for (const accel of candidates) {
    const ok = globalShortcut.register(accel, () => toggle());
    if (ok) { console.log(`[overlay] fallback shortcut active: ${accel}`); activeFallbackShortcut = accel; return accel; }
    console.warn(`[overlay] could not register ${accel} — likely taken by another app`);
  }
  console.error('[overlay] no fallback shortcut could be registered — use the double-tap trigger or the tray icon.');
  return null;
}

function registerTriggers() {
  registerFallbackShortcut();
  applyTriggerKey(store.get().settings.doubleTapKey || 'ctrl');

  try {
    const { uIOhook } = require('uiohook-napi');
    const DOUBLE_TAP_MS = 320;
    let lastTap = 0;
    uIOhook.on('keydown', (e) => {
      if (!activeTriggerCodes.has(e.keycode)) return;
      const now = Date.now();
      if (now - lastTap < DOUBLE_TAP_MS) { lastTap = 0; toggle(); }
      else { lastTap = now; }
    });
    uIOhook.start();
    console.log(`[overlay] double-tap trigger active: ${TRIGGER_KEYS[activeTriggerKey].label} (${TRIGGER_KEYS[activeTriggerKey].symbol})`);
  } catch (err) {
    console.warn('[overlay] uiohook-napi unavailable — using ⌘⇧L fallback only.', err.message);
  }
}

/* ── Boot ───────────────────────────────────────────────────────── */
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (win) toggle(); });

  app.whenReady().then(() => {
    // The double-tap-⌘ hook (uiohook) silently receives ZERO events without
    // Accessibility (and on newer macOS, Input Monitoring) — log the status
    // at boot so "trigger does nothing" is diagnosable from the log alone.
    console.log(`[overlay] accessibility permission: ${checkAccessibility() ? 'granted' : 'NOT granted — the double-tap trigger and selection capture will not work'}`);
    createWindow();
    createTray();
    registerTriggers();
    if (!store.get().onboardingComplete) createOnboardingWindow();
    app.on('activate', () => { if (!win) createWindow(); });
  });
}

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  try { require('uiohook-napi').uIOhook.stop(); } catch {}
});

// Keep running with no visible windows (it's a background overlay).
app.on('window-all-closed', (e) => e.preventDefault());
