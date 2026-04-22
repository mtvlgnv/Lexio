const { app, BrowserWindow, globalShortcut, Menu, shell } = require('electron');

app.setName('Lexio');

// On macOS, keep the process alive even when the window is hidden
// so the global hotkey still works.
if (process.platform === 'darwin') {
  app.dock.hide();
}

let win = null;

function createWindow() {
  win = new BrowserWindow({
    width: 920,
    height: 700,
    minWidth: 680,
    minHeight: 460,

    // Always float above other apps
    alwaysOnTop: true,
    level: 'floating',          // macOS window level

    // Frameless — we use the header as a drag handle inside the page
    frame: false,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 14, y: 13 },

    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },

    show: false,
    backgroundColor: '#f5efe8',  // matches warm --bg so no flash on load

    // macOS frosted-glass effect
    vibrancy: 'under-window',
    visualEffectState: 'active',
    roundedCorners: true,
  });

  // Load Lexio with compact=1 so the page makes the header draggable
  win.loadURL('http://lexio.site?compact=1');

  win.once('ready-to-show', () => win.show());

  // Closing the window hides it — the app lives in the global hotkey
  win.on('close', e => {
    e.preventDefault();
    win.hide();
  });

  // Open external links in the real browser, not inside the overlay
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

function toggle() {
  if (!win) return;
  if (win.isVisible() && win.isFocused()) {
    win.hide();
  } else {
    win.show();
    win.focus();
  }
}

app.whenReady().then(() => {
  createWindow();

  // Global hotkey — works even when another app has focus
  const ok = globalShortcut.register('CommandOrControl+Shift+L', toggle);
  if (!ok) console.warn('Could not register global shortcut');

  // Re-show when the user clicks the dock icon (macOS)
  app.on('activate', () => {
    if (win && !win.isVisible()) win.show();
  });
});

app.on('will-quit', () => globalShortcut.unregisterAll());

// Quit properly on Cmd+Q despite the close-to-hide behaviour
app.on('before-quit', () => {
  win?.removeAllListeners('close');
});

// Single instance — if launched again, just surface the existing window
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) { win.show(); win.focus(); }
  });
}
