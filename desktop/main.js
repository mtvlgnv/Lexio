const { app, BrowserWindow, globalShortcut, Menu, shell, Tray, nativeImage } = require('electron');

app.setName('Lexio Mini');

// Live in the menu bar, not the dock
if (process.platform === 'darwin') app.dock.hide();

let win  = null;
let tray = null;

// Minimal 1×1 transparent PNG — the visible label comes from tray.setTitle()
const BLANK_ICON = nativeImage.createFromDataURL(
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
);

/* ── Tray ───────────────────────────────────────────────── */
function createTray() {
  tray = new Tray(BLANK_ICON);
  tray.setTitle(' Lx ');
  tray.setToolTip('Lexio — contextual definitions');

  // Left-click: toggle window
  tray.on('click', (_, bounds) => toggleWindow(bounds));

  // Right-click: small context menu
  tray.on('right-click', () =>
    tray.popUpContextMenu(
      Menu.buildFromTemplate([
        { label: 'Show Lexio',  click: () => showWindow()  },
        { type: 'separator'                                  },
        { label: 'Quit Lexio', click: () => app.quit()     },
      ])
    )
  );
}

/* ── Window positioning ─────────────────────────────────── */
function getPosition(trayBounds) {
  const b = trayBounds || tray.getBounds();
  const { width, height } = win.getBounds();
  return {
    x: Math.round(b.x + b.width  / 2 - width  / 2),
    y: Math.round(b.y + b.height + 4),
  };
}

function showWindow(trayBounds) {
  const { x, y } = getPosition(trayBounds);
  win.setPosition(x, y);
  win.show();
  win.focus();
}

function toggleWindow(trayBounds) {
  if (win.isVisible() && win.isFocused()) win.hide();
  else showWindow(trayBounds);
}

/* ── BrowserWindow ──────────────────────────────────────── */
function createWindow() {
  win = new BrowserWindow({
    width:    400,
    height:   620,
    minWidth: 340,
    minHeight:440,
    maxWidth: 560,

    alwaysOnTop: true,
    level: 'pop-up-menu',   // sits above normal windows, below system UI

    frame: false,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 14, y: 13 },

    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },

    show: false,
    backgroundColor: '#f5efe8',
    vibrancy: 'under-window',
    visualEffectState: 'active',
    roundedCorners: true,
  });

  win.loadURL('https://lexio.site/compact.html');

  // Close button hides, doesn't quit
  win.on('close', e => { e.preventDefault(); win.hide(); });

  // External links open in the real browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

/* ── lexio:// URL scheme  ───────────────────────────────── */
// Lets the website's "Open in Desktop App" button surface this window.
// Works once the app is installed as a proper .app bundle.
app.setAsDefaultProtocolClient('lexio');

app.on('open-url', (event, url) => {
  event.preventDefault();
  try {
    const parsed = new URL(url);
    if (parsed.hostname === 'auth') {
      const token = parsed.searchParams.get('token');
      const user  = parsed.searchParams.get('user');
      if (token && win) {
        // Inject token into compact.html's localStorage and fire event
        win.webContents.executeJavaScript(`
          localStorage.setItem('lexio_token', ${JSON.stringify(token)});
          ${user ? `localStorage.setItem('lexio_user', ${JSON.stringify(user)});` : ''}
          window.dispatchEvent(new CustomEvent('lexio-auth', { detail: { token: ${JSON.stringify(token)}, user: ${user ? JSON.stringify(JSON.parse(user)) : 'null'} } }));
        `).catch(() => {});
      }
    }
  } catch {}
  showWindow();
});

/* ── Boot ───────────────────────────────────────────────── */
app.whenReady().then(() => {
  createWindow();
  createTray();

  // Keyboard shortcut still works from anywhere
  globalShortcut.register('CommandOrControl+Shift+L', () => toggleWindow());

  app.on('activate', () => { if (!win.isVisible()) showWindow(); });
});

app.on('will-quit', () => globalShortcut.unregisterAll());
app.on('before-quit', () => win?.removeAllListeners('close'));

// Single-instance lock
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (win) showWindow(); });
}
