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
        clipboard, systemPreferences } = require('electron');
const { execFile } = require('child_process');
const path = require('path');

// Surface anything that would otherwise fail silently — a background
// overlay with no console attached is easy to leave in a broken state
// with zero indication of why. Both handlers just log; they don't quit.
process.on('uncaughtException',  (err) => console.error('[overlay] uncaughtException:', err));
process.on('unhandledRejection', (err) => console.error('[overlay] unhandledRejection:', err));

app.setName('Lexio Glance');
if (process.platform === 'darwin') app.dock.hide();   // live as an overlay, not a dock app

let win  = null;
let tray = null;
let expanded = false;

// Bottom margin and the two window sizes the pill morphs between.
// The collapsed pill is a 36px gradient disc (see pill.html). COLLAPSED is
// kept close to that size on purpose — not because of the transparency bug
// (that turned out to be Electron 34 predating this Mac's very new macOS
// "Tahoe" release; upgrading to Electron 43 fixed it outright, no residual
// artifact), just because a tight, disc-sized window is the cleaner design.
const MARGIN_BOTTOM = 10;
const COLLAPSED = { width: 44, height: 42 };
const EXPANDED  = { width: 460, height: 580 };

// Roughly how long macOS's own native window-resize animation takes for a
// move of this size — used only to keep the CSS content crossfade in
// pill.html roughly in sync with the window's own growth. Not a real
// duration we control (see animateBounds below).
const EXPAND_MS   = 380;
const COLLAPSE_MS = 260;

// Smooth resize via macOS's native Core Animation-driven window resize
// (the 2nd `true` arg to setBounds). A hand-rolled JS timer loop (the
// previous approach) runs on Node's main-process event loop, which is
// prone to jitter under any concurrent work — visibly less smooth than
// letting the OS itself, GPU/vsync-composited, own the animation. We lose
// precise duration control (macOS decides the timing), but "smoother" is
// the actual goal here, and native resize looks identical to every other
// macOS window animation the user already knows.
function animateBounds(bounds) {
  if (win && !win.isDestroyed()) win.setBounds(bounds, true);
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
    // Content crossfade (pill.html's CSS) starts now, alongside the window's
    // own native smooth resize below — both tuned to ~EXPAND_MS so they
    // land together instead of the content "arriving" before/after the
    // window has finished resizing.
    win.webContents.send('overlay:expand', { text: selection });
    win.setIgnoreMouseEvents(false);
    win.show();
    win.focus();
    animateBounds(boundsFor(EXPANDED));
  } catch (err) {
    console.error('[overlay] expand() failed:', err);
    expanded = false;   // never leave the toggle stuck — next trigger should get a clean retry
  }
}

function collapse() {
  if (!expanded) return;
  expanded = false;
  win.webContents.send('overlay:collapse');
  animateBounds(boundsFor(COLLAPSED));
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

  // Click-away collapses (but keeps the pill on screen).
  win.on('blur', () => collapse());

  // If the window is ever destroyed (crash, accidental close), drop the
  // stale reference so expand() knows to recreate it instead of throwing
  // "Object has been destroyed" on the next trigger.
  win.on('closed', () => { win = null; expanded = false; });
}

/* ── Renderer → main IPC ────────────────────────────────────────── */
ipcMain.on('overlay:expand-request',   () => expand());
ipcMain.on('overlay:collapse-request', () => collapse());

/* ── Tray (so the floating widget is always quittable) ──────────── */
function createTray() {
  tray = new Tray(BLANK_ICON);
  tray.setTitle(' Lx ');
  tray.setToolTip('Lexio Glance — double-tap ⌘ or click to open');
  const menu = Menu.buildFromTemplate([
    { label: 'Open Lexio',  click: () => expand() },
    { label: 'Hide',        click: () => collapse() },
    { type: 'separator' },
    { label: 'Quit Lexio',  click: () => app.quit() },
  ]);
  tray.on('right-click', () => tray.popUpContextMenu(menu));
  tray.on('click', () => toggle());
}

/* ── Trigger: double-tap ⌘ (native), with fallback shortcut ─────── */
// globalShortcut.register() returns false (not an exception) when another
// app already owns the combo — Cmd+Shift+L is a common one (bookmark
// managers, browsers, etc.), so we try a short list and log what actually
// registered instead of assuming the first one worked.
function registerFallbackShortcut() {
  const candidates = ['CommandOrControl+Shift+L', 'CommandOrControl+Shift+K', 'Alt+CommandOrControl+L'];
  for (const accel of candidates) {
    const ok = globalShortcut.register(accel, () => toggle());
    if (ok) { console.log(`[overlay] fallback shortcut active: ${accel}`); return accel; }
    console.warn(`[overlay] could not register ${accel} — likely taken by another app`);
  }
  console.error('[overlay] no fallback shortcut could be registered — use double-tap ⌘ or the tray icon.');
  return null;
}

function registerTriggers() {
  registerFallbackShortcut();

  // Preferred: double-tap the ⌘ (Meta) key, like Wispr's double-tap Fn.
  try {
    const { uIOhook, UiohookKey } = require('uiohook-napi');
    const METAS = new Set([UiohookKey.Meta, UiohookKey.MetaRight]);
    const DOUBLE_TAP_MS = 320;
    let lastTap = 0;
    uIOhook.on('keydown', (e) => {
      if (!METAS.has(e.keycode)) return;
      const now = Date.now();
      if (now - lastTap < DOUBLE_TAP_MS) { lastTap = 0; toggle(); }
      else { lastTap = now; }
    });
    uIOhook.start();
    console.log('[overlay] double-tap ⌘ trigger active');
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
    createWindow();
    createTray();
    registerTriggers();
    app.on('activate', () => { if (!win) createWindow(); });
  });
}

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  try { require('uiohook-napi').uIOhook.stop(); } catch {}
});

// Keep running with no visible windows (it's a background overlay).
app.on('window-all-closed', (e) => e.preventDefault());
