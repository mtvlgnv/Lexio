/**
 * Lexio — full Mac app
 * Standard dock app wrapping the complete Lexio website.
 */

const { app, BrowserWindow, Menu, shell, nativeTheme } = require('electron');

app.setName('Lexio');

let win = null;

/* ── Application menu ───────────────────────────────────── */
const menuTemplate = [
  {
    label: 'Lexio',
    submenu: [
      { role: 'about' },
      { type: 'separator' },
      { role: 'services' },
      { type: 'separator' },
      { role: 'hide' },
      { role: 'hideOthers' },
      { role: 'unhide' },
      { type: 'separator' },
      { role: 'quit' },
    ],
  },
  { role: 'editMenu' },
  {
    label: 'View',
    submenu: [
      { role: 'reload' },
      { role: 'forceReload' },
      { type: 'separator' },
      { role: 'resetZoom' },
      { role: 'zoomIn' },
      { role: 'zoomOut' },
      { type: 'separator' },
      { role: 'togglefullscreen' },
    ],
  },
  { role: 'windowMenu' },
  {
    label: 'Help',
    submenu: [
      {
        label: 'Open lexio.site',
        click: () => shell.openExternal('http://lexio.site'),
      },
    ],
  },
];

Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate));

/* ── Window ─────────────────────────────────────────────── */
function createWindow() {
  win = new BrowserWindow({
    width:     960,
    height:    720,
    minWidth:  600,
    minHeight: 500,

    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 18 },

    webPreferences: {
      nodeIntegration:  false,
      contextIsolation: true,
    },

    backgroundColor: '#f5efe8',
    vibrancy:            'under-window',
    visualEffectState:   'active',
    roundedCorners:      true,
  });

  win.loadURL('http://lexio.site');

  // Open all target="_blank" / window.open() links in the real browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Intercept navigating away from lexio.site (e.g. clicked an external link)
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('http://lexio.site') && !url.startsWith('https://lexio.site')) {
      e.preventDefault();
      shell.openExternal(url);
    }
  });
}

/* ── Boot ───────────────────────────────────────────────── */
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else win?.show();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
