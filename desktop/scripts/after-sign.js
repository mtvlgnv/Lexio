/**
 * Ad-hoc code-sign the .app after electron-builder compiles it.
 * This removes the "damaged" Gatekeeper error for unsigned downloads.
 * Users will still see "unidentified developer" on first launch —
 * they can right-click → Open to bypass it once.
 */

const { execSync } = require('child_process');

exports.default = async function afterSign(context) {
  const { appOutDir, packager } = context;
  const appPath = `${appOutDir}/${packager.appInfo.productFilename}.app`;

  console.log(`Ad-hoc signing: ${appPath}`);
  execSync(`codesign --deep --force --sign - "${appPath}"`, { stdio: 'inherit' });
  console.log('✓ Ad-hoc signing complete');
};
