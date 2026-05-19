const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

app.disableHardwareAcceleration();

const svgPath = path.join(__dirname, 'lexio-promo-card.svg');
const outPath = path.join(__dirname, 'lexio-promo-card.png');

async function main() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    frame: false,
    resizable: false,
    transparent: false,
    webPreferences: {
      offscreen: true,
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  await win.loadFile(svgPath);
  await new Promise(resolve => setTimeout(resolve, 300));
  const image = await win.capturePage();
  fs.writeFileSync(outPath, image.toPNG());
  app.quit();
}

app.whenReady().then(main).catch(err => {
  console.error(err);
  app.exit(1);
});
