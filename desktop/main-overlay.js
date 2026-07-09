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
const { app, BrowserWindow, globalShortcut, screen, Tray, Menu, ipcMain,
        clipboard, systemPreferences, shell, nativeTheme } = require('electron');
const { execFile } = require('child_process');
const path = require('path');
const store = require('./store');
const { installFileLogging, logPath } = require('./lib/log');
const { menuBarTrayIcon } = require('./lib/icons');
const { parseAuthUrl } = require('./lib/auth');
const { captureScreenPoint } = require('./lib/vision-capture');

// A packaged .app has no attached terminal — without this, "check the log"
// is impossible for a field report like this week's real-hardware trigger
// bug. Installed before any other logging so every line below is captured.
installFileLogging();

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
// Dock icon is intentional (Hub v2): clicking it opens the Hub window,
// Wispr-Flow style. The pill overlay + menu-bar tray still work as before.

let win  = null;
let tray = null;
let onboardingWin = null;
let hubWin = null;   // quick menu-bar popover (Recent / Settings / Account)
let homeWin = null;  // the real Hub window (Word Bank / Account dashboards)
let expanded = false;
let pinned = false;   // when true, losing focus (blur) does not auto-collapse
let activeFallbackShortcut = null;

// BUG #5 FIX: expand() awaits captureSelection() (clipboard dance + ⌘C,
// ~0.5-1s) before touching the window. A second trigger during that window
// used to run toggle() -> collapse() (expanded was already true) while the
// FIRST expand()'s continuation was still in flight — it would then resume,
// set bounds to EXPANDED, and show/focus the window regardless, leaving the
// panel visibly open with `expanded === false` (collapse() no-ops, and the
// next trigger's synthesized ⌘C could even land on Lexio's own now-focused
// window). Every collapse bumps this counter; any expand() run started
// before the bump checks it after its await and abandons itself if a newer
// trigger has since superseded it.
let captureGeneration = 0;

// Bottom margin and the two window sizes the pill morphs between.
// The collapsed pill is a 36px gradient disc (see pill.html). COLLAPSED is
// kept close to that size on purpose — not because of the transparency bug
// (that turned out to be Electron 34 predating this Mac's very new macOS
// "Tahoe" release; upgrading to Electron 43 fixed it outright, no residual
// artifact), just because a tight, disc-sized window is the cleaner design.
const MARGIN_BOTTOM = 10;
const COLLAPSED = { width: 44, height: 42 };
const EXPANDED  = { width: 460, height: 580 };

// Duration for CSS transition timings (handled in pill.html)
const EXPAND_MS   = 250;
const COLLAPSE_MS = 250;

// Bump when onboarding steps change — users who finished an older wizard
// (or have a stale dev-store flag) see it again on next launch.
const ONBOARDING_VERSION = 2;

function needsOnboarding() {
  const s = store.get();
  return !s.onboardingComplete || (s.onboardingAppVersion || 0) < ONBOARDING_VERSION;
}

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

   Also starts a best-effort attempt to auto-expand to the surrounding
   sentence via Accessibility — the whole point of "highlight ONE WORD, get
   a CONTEXTUAL definition" — but does NOT wait for it here. That read takes
   several real seconds on a typical Mac (measured, not assumed — see
   lib/context.js's header). Per explicit direction, correctness beats
   latency: the caller (expand()) opens the panel immediately on the word
   alone, and only fires the actual /define request once the returned
   `contextPromise` resolves — so the several-second wait happens as a
   visible "reading context" state, not as an invisible race that quietly
   loses and ships a wrong definition (which is exactly what happened
   before this: "bat" defined as the animal in a baseball sentence, because
   context silently never arrived in time).

   Two DIFFERENT macOS permissions gate the capture itself, and failures
   here were previously silent — logging every branch below so a
   stuck/broken capture is diagnosable from the log instead of guessed at:
     • Accessibility        — lets us detect the double-tap ⌘ at all
     • Automation            — lets us tell System Events to send ⌘C
       ("<App> wants to control System Events.app" — a SEPARATE
       permission from Accessibility, granted per-pair of apps under
       System Settings → Privacy & Security → Automation). If this
       hasn't been granted, osascript exits non-zero every time. */
const ACCESSIBILITY_SETTINGS_URL =
  'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';

function checkAccessibility() {
  if (process.platform !== 'darwin') return true;
  return systemPreferences.isTrustedAccessibilityClient(false);
}

// Never call isTrustedAccessibilityClient(true) — on a rebuilt/notarized
// binary macOS often keeps a stale TCC entry (toggle looks ON in Settings
// but returns false here) and the system dialog loops without fixing it.
function ensureAccessibility() {
  if (process.platform !== 'darwin') return true;
  const ok = checkAccessibility();
  if (!ok) console.warn('[overlay] Accessibility permission not granted — skipping capture.');
  return ok;
}

function openAccessibilitySettings() {
  shell.openExternal(ACCESSIBILITY_SETTINGS_URL);
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

// Screen-point capture: no selection, no clipboard, no Accessibility read.
// The user just points the cursor at a word (no drag-select needed) and
// double-taps. We grab the pixels around the cursor and let the backend's
// multimodal model (Gemini 2.5 Flash) both identify the word AND define it
// from the image in one call — see lib/vision-capture.js and
// app/routers/define.py's _define_from_image.
async function captureScreenshot() {
  if (process.platform !== 'darwin') return null;   // macOS-only for now

  const cursor = screen.getCursorScreenPoint();
  // Keep the overlay panel out of its own screenshot — it expands while
  // the capture is in flight. getMediaSourceId() → "window:<CGWindowID>:<n>".
  const excludeWindowIds = [];
  if (win && !win.isDestroyed()) {
    try {
      const id = parseInt(win.getMediaSourceId().split(':')[1], 10);
      if (Number.isFinite(id)) excludeWindowIds.push(id);
    } catch {}
  }
  const shot = await captureScreenPoint({ x: cursor.x, y: cursor.y, excludeWindowIds });
  if (!shot || !shot.image_base64) {
    console.log('[overlay] capture: screen capture failed (check Screen Recording permission)');
    return null;
  }
  console.log(`[overlay] capture: got ${shot.width}x${shot.height} ${shot.mime || 'image/png'} in ${shot.ms}ms`);

  // If the onboarding wizard is open on its practice-run step, this real
  // capture is what it's waiting for — let it advance itself instead of
  // requiring a manual "Next" click.
  const onboardingOpen = onboardingWin && !onboardingWin.isDestroyed();
  if (onboardingOpen) {
    onboardingWin.webContents.send('onboarding:practice-capture', {});
  }

  return { imageBase64: shot.image_base64, imageMime: shot.mime || 'image/png' };
}

/* ── Expand / collapse ──────────────────────────────────────────── */
// Wrapped in try/catch/finally so that ANY failure here (a destroyed
// window, a hung child process, anything) still surfaces in the log AND
// still resets `expanded` — otherwise a single bad run leaves the flag
// stuck at true forever, and every future trigger silently no-ops into
// collapse() instead of expand(). This is almost certainly what "worked
// once, then nothing" was: the first run's error left this stuck.
// `forcedText`, when passed (e.g. re-running a Recent-tab item), skips the
// real selection capture entirely and feeds that text straight into the
// panel instead — a relookup shouldn't touch the clipboard or require
// anything to be selected in the frontmost app.
async function expand(forcedText) {
  // A relookup (forcedText, from the Hub's Recent tab) only has the word
  // itself, not the sentence it originally came from — reuse it as its own
  // context, same as the old pre-auto-context behavior.
  const forced = forcedText !== undefined ? { word: forcedText, context: forcedText } : undefined;

  if (expanded) {
    // Already open — most likely pinned. A relookup should swap the
    // content into the existing panel rather than silently no-op, since
    // pin exists specifically so the panel can stay open across other
    // actions like picking a Recent-tab item from the Hub.
    if (forced && win && !win.isDestroyed()) {
      win.webContents.send('overlay:expand', forced);
      win.show();
      win.focus();
    }
    return;
  }
  expanded = true;
  const myGeneration = ++captureGeneration;
  try {
    if (!win || win.isDestroyed()) { console.warn('[overlay] window was gone — recreating.'); createWindow(); }

    // A relookup already has its {word, context} up front (no waiting
    // needed). A real capture has neither yet — the panel opens showing a
    // "reading the screen" state immediately, and the captured image
    // arrives shortly after as a separate 'overlay:image-ready' message.
    // The word itself isn't known until the backend's vision call responds
    // (it identifies the word AND defines it from the image in one shot).
    let payload = {};
    if (forced) {
      payload = forced;
    } else {
      const capturePromise = captureScreenshot();   // BEFORE resize/show/focus — see note above
      payload = { imagePending: true };
      capturePromise.then((captured) => {
        // A newer trigger may have collapsed us (bumping captureGeneration)
        // while we were awaiting the capture — bail out rather than clobber
        // whatever state that newer trigger already established (bug #5).
        if (myGeneration !== captureGeneration || !win || win.isDestroyed()) return;
        if (captured) {
          win.webContents.send('overlay:image-ready', { imageBase64: captured.imageBase64, imageMime: captured.imageMime });
        } else {
          win.webContents.send('overlay:image-ready', { imageBase64: null });
        }
      });
    }

    const toBounds = boundsFor(EXPANDED);
    // Snapping the transparent window to max size instantly allows the
    // CSS to run butter-smooth GPU-accelerated animations natively without
    // fighting Electron's window resizing loop!
    win.setBounds(toBounds);
    win.webContents.send('overlay:expand', payload);
    win.setIgnoreMouseEvents(false);
    win.show();
    win.focus();
  } catch (err) {
    console.error('[overlay] expand() failed:', err);
    expanded = false;   // never leave the toggle stuck — next trigger should get a clean retry
  }
}

function collapse() {
  if (!expanded) return;
  expanded = false;
  captureGeneration++;   // invalidate any in-flight expand() a newer trigger has superseded (bug #5)
  // Bug #19: this previously assumed `win` was always alive whenever
  // `expanded` was true — true today only because the 'closed' handler
  // happens to reset `expanded` first, which is easy to break by accident
  // in a future change. Guard it directly instead of relying on that.
  if (win && !win.isDestroyed()) win.webContents.send('overlay:collapse');

  // Wait for the CSS genie animation to visually squish down into the pill
  // before we snap the OS window bounds back to the tiny 44x42 box.
  setTimeout(() => {
    if (!expanded && win && !win.isDestroyed()) {
      win.setBounds(boundsFor(COLLAPSED));
    }
  }, COLLAPSE_MS);
}

function toggle() { expanded ? collapse() : expand(); }

// Lexio Glance is a menu-bar background app (no Dock icon). Clicking it in
// Applications while already running used to silently toggle a 44px pill or
// quit the second process — users reasonably expect a window to appear.
function presentApp() {
  if (needsOnboarding()) {
    console.log('[overlay] showing onboarding wizard');
    createOnboardingWindow();
    return;
  }
  createHomeWindow();
}

/* ── Home window (Hub v2) ───────────────────────────────────────────
   The app's real home, Wispr-Flow style: a normal resizable window with
   sidebar navigation — Word Bank / Recent / Settings / Account. Opens on
   launch (unless started at login), on dock-icon click, and from the tray
   menu. The compact popover (createHubWindow) stays for quick access from
   the menu bar.

   partition 'persist:lexio' is load-bearing: it's the same partition as
   the lookup panel's webview, so home.html shares its localStorage —
   auth token, word bank (lexio_wbv1), and definition language — with the
   panel, with no IPC or duplicate state. */
function createHomeWindow() {
  if (homeWin && !homeWin.isDestroyed()) { homeWin.show(); homeWin.focus(); return; }
  homeWin = new BrowserWindow({
    width: 920,
    height: 600,
    minWidth: 720,
    minHeight: 460,
    title: 'Lexio Glance',
    titleBarStyle: 'hiddenInset',
    backgroundColor: chromeBackgroundColor(),
    webPreferences: {
      preload: path.join(__dirname, 'preload-hub.js'),
      partition: 'persist:lexio',
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });
  homeWin.loadFile(path.join(__dirname, 'home.html'));
  homeWin.once('ready-to-show', () => homeWin.show());
  homeWin.on('closed', () => { homeWin = null; });
}

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

  // Click-away collapses (but keeps the pill on screen) — unless the user
  // pinned the panel open, e.g. to read it alongside another app.
  win.on('blur', () => { if (!pinned) collapse(); });

  // If the window is ever destroyed (crash, accidental close), drop the
  // stale reference so expand() knows to recreate it instead of throwing
  // "Object has been destroyed" on the next trigger.
  win.on('closed', () => { win = null; expanded = false; pinned = false; });
}

// Bug #17: these two chrome windows hardcoded a light-mode background —
// tokens.css has had proper dark values for a while, and pill.html already
// live-toggles the embedded webview's theme, but a dark-mode user still saw
// a cream flash (and cream rounded corners, since `backgroundColor` paints
// through until content loads) around otherwise-dark Hub/Onboarding content.
function chromeBackgroundColor() {
  return nativeTheme.shouldUseDarkColors ? '#1f1c1a' : '#f5efe8';
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
    backgroundColor: chromeBackgroundColor(),
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
    backgroundColor: chromeBackgroundColor(),
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
ipcMain.on('overlay:start-drag', (e) => {
  const senderWin = BrowserWindow.fromWebContents(e.sender);
  if (senderWin) senderWin.startWindowDrag();
});
// Pin/keep-open: while pinned, the blur handler above won't auto-collapse —
// the one thing an always-on-top overlay is for is staying open alongside
// another app instead of vanishing the moment you click into it to read.
ipcMain.on('overlay:set-pinned', (_e, value) => { pinned = !!value; });

// Shared between the onboarding wizard and the Hub's Settings/Account tabs.
ipcMain.handle('app:accessibility-status', () => checkAccessibility());
// Screen Recording gates every lookup now (the capture IS the context
// source), so onboarding needs its live status. Note macOS may require an
// app relaunch after granting before captures actually succeed.
ipcMain.handle('app:screen-recording-status', () =>
  process.platform !== 'darwin' || systemPreferences.getMediaAccessStatus('screen') === 'granted');
ipcMain.handle('app:request-accessibility', () => {
  if (checkAccessibility()) return true;
  openAccessibilitySettings();
  return false;
});
ipcMain.on('app:open-accessibility-settings', () => openAccessibilitySettings());
ipcMain.on('app:open-signin', () => shell.openExternal(SIGNIN_URL));
// uiohook's global keyboard tap needs Input Monitoring — a SEPARATE
// permission from Accessibility on macOS 10.15+, gating any passive
// listen-all key tap (vs. a registered hotkey, which only needs
// Accessibility). There's no systemPreferences API for it like
// isTrustedAccessibilityClient(), so we can't check or prompt for it —
// only deep-link straight to the pane so the user can add it themselves.
ipcMain.on('app:open-input-monitoring-settings', () =>
  shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent'));
// Screen Recording gates the OCR context fallback (lib/ocr-context.js) —
// like Input Monitoring, there's no API to prompt for it, so deep-link.
ipcMain.on('app:open-screen-recording-settings', () =>
  shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'));
ipcMain.on('app:open-log-file', () => shell.showItemInFolder(logPath()));
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
  store.set({ onboardingComplete: true, onboardingAppVersion: ONBOARDING_VERSION });
  if (onboardingWin && !onboardingWin.isDestroyed()) onboardingWin.close();
});

// The webview reports the word it actually defined (bridged through
// pill.html's console-message listener — see pill.html/compact.html for
// why that's the mechanism) — this is what belongs in Recent, not the raw
// captured selection, which is often a whole sentence.
ipcMain.on('overlay:report-lookup', (_e, word) => {
  const w = (word || '').toString().trim().slice(0, 80);
  if (!w) return;
  const recentLookups = [{ word: w, at: Date.now() }, ...store.get().recentLookups].slice(0, 50);
  // Daily lookup counts — the local raw material for streak/stats on the
  // Hub's future Home tab (server-side streak exists but needs sign-in).
  const lookupDays = { ...(store.get().lookupDays || {}) };
  const today = new Date().toISOString().slice(0, 10);
  lookupDays[today] = (lookupDays[today] || 0) + 1;
  store.set({ recentLookups, lookupDays });
  for (const w2 of [hubWin, homeWin]) {
    if (w2 && !w2.isDestroyed()) w2.webContents.send('hub:recent-updated', recentLookups);
  }
});

ipcMain.handle('hub:get-recent', () => store.get().recentLookups);
ipcMain.handle('hub:get-auth',   () => store.get().auth);
// Clicking a Recent-tab item re-runs that exact lookup in the panel.
ipcMain.on('hub:relookup', (_e, word) => {
  if (!word) return;
  if (hubWin && !hubWin.isDestroyed()) hubWin.close();
  expand(word);
});
ipcMain.on('hub:sign-out', () => {
  store.set({ auth: null });
  for (const w of [hubWin, homeWin]) {
    if (w && !w.isDestroyed()) w.webContents.send('hub:auth-updated', null);
  }
  if (win && !win.isDestroyed()) win.webContents.send('overlay:auth', null);
});

// Fixed destination on purpose — don't accept arbitrary URLs from renderers.
ipcMain.on('app:open-pricing', () => shell.openExternal('https://lexio.site/#lp-pro'));

/* ── lexio:// URL scheme — auth handoff from the website ──────────
   Mirrors the same mechanism main.js already uses: the site redirects to
   lexio://auth?token=...&user=... after a successful login/signup when it
   was opened with ?desktop_auth=1 (see SIGNIN_URL above). */
app.setAsDefaultProtocolClient('lexio');

app.on('open-url', (event, url) => {
  event.preventDefault();
  const auth = parseAuthUrl(url);
  if (!auth) return;
  const { token, user } = auth;
  store.set({ auth: { token, user } });
  if (onboardingWin && !onboardingWin.isDestroyed()) {
    onboardingWin.webContents.send('onboarding:auth-complete', { token, user });
  }
  for (const w of [hubWin, homeWin]) {
    if (w && !w.isDestroyed()) w.webContents.send('hub:auth-updated', { token, user });
  }
  // The embedded compact.html webview keeps its own localStorage in the
  // persist:lexio partition — it never sees store.js. Forward the token
  // so pill.html can inject it (mirrors what main.js does for Lexio Mini).
  if (win && !win.isDestroyed()) {
    win.webContents.send('overlay:auth', { token, user });
  }
});

/* ── Tray (so the floating widget is always quittable) ──────────── */
function updateTrayToolTip() {
  if (!tray) return;
  const symbol = TRIGGER_KEYS[activeTriggerKey].symbol;
  tray.setToolTip(`Lexio Glance — click for recent lookups & settings, double-tap ${symbol} to look something up`);
}

function createTray() {
  tray = new Tray(menuBarTrayIcon());
  // A 1×1 transparent tray image is invisible on its own — the label is what
  // users actually see in the menu bar (same pattern as Lexio Mini).
  if (process.platform === 'darwin') tray.setTitle('Lx');
  updateTrayToolTip();
  const menu = Menu.buildFromTemplate([
    { label: 'Open Lexio',        click: () => expand() },
    { label: 'Hide',              click: () => collapse() },
    { type: 'separator' },
    { label: 'Lexio Hub',         click: () => presentApp() },
    { label: 'Getting Started',   click: () => createOnboardingWindow() },
    { type: 'separator' },
    { label: 'Quit Lexio',        click: () => app.quit() },
  ]);
  tray.on('right-click', () => tray.popUpContextMenu(menu));
  // Left-click opens the QUICK popover (recent + settings at a glance);
  // the full Hub window lives on the dock icon, launch, and the menu
  // above — menu-bar clicks are for fast in-and-out, not a dashboard.
  tray.on('click', () => {
    if (needsOnboarding()) { createOnboardingWindow(); return; }
    createHubWindow();
  });
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
    let lastBareTapAt = 0;
    let triggerHeld = false;
    let interrupted = false;

    // BUG #13 FIX: counting any two trigger-key keydowns within
    // DOUBLE_TAP_MS also fired on ⌃C, ⌃V, or any other real shortcut that
    // happens to use this modifier — holding ⌃ while working in a terminal
    // or editor could pop the panel open mid-keystroke. A genuine double-tap
    // requires the modifier to be pressed and released BARE (no other key
    // in between) on both taps — this now tracks keyup too and disqualifies
    // a tap the moment any other key is pressed while the modifier is held,
    // the same way Wispr Flow's Fn-Fn trigger behaves.
    uIOhook.on('keydown', (e) => {
      if (activeTriggerCodes.has(e.keycode)) {
        triggerHeld = true;
        interrupted = false;
      } else if (triggerHeld) {
        interrupted = true;
      }
    });
    uIOhook.on('keyup', (e) => {
      if (!activeTriggerCodes.has(e.keycode)) return;
      triggerHeld = false;
      if (interrupted) return;   // part of a real shortcut, not a bare tap
      const now = Date.now();
      if (now - lastBareTapAt < DOUBLE_TAP_MS) { lastBareTapAt = 0; toggle(); }
      else { lastBareTapAt = now; }
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
  app.on('second-instance', () => {
    console.log('[overlay] second-instance — presenting UI');
    presentApp();
  });

  app.whenReady().then(() => {
    // The double-tap-⌘ hook (uiohook) silently receives ZERO events without
    // Accessibility (and on newer macOS, Input Monitoring) — log the status
    // at boot so "trigger does nothing" is diagnosable from the log alone.
    console.log(`[overlay] accessibility permission: ${checkAccessibility() ? 'granted' : 'NOT granted — the double-tap trigger and selection capture will not work'}`);
    createWindow();
    createTray();
    registerTriggers();
    // Show the Hub on manual launch, Wispr-style — but stay silent when
    // macOS auto-started us at login (the pill alone is the right presence).
    const openedAtLogin = process.platform === 'darwin' &&
      app.getLoginItemSettings().wasOpenedAtLogin;
    if (!openedAtLogin) presentApp();
    app.on('activate', () => {
      presentApp();
      if (!win || win.isDestroyed()) createWindow();
    });
  });
}

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  try { require('uiohook-napi').uIOhook.stop(); } catch {}
});

// Keep running with no visible windows (it's a background overlay).
app.on('window-all-closed', (e) => e.preventDefault());
