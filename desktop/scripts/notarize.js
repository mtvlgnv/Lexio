/**
 * Submit the signed .app to Apple notarization and staple the ticket.
 * Required for Gatekeeper to allow opening without "unverified developer".
 *
 * Set before `npm run dist`:
 *   APPLE_ID=you@example.com
 *   APPLE_APP_SPECIFIC_PASSWORD=xxxx-xxxx-xxxx-xxxx
 *   APPLE_TEAM_ID=8TJHY75AV5   (optional — defaults to Lexio team)
 *
 * App-specific password: https://appleid.apple.com → Sign-In and Security
 * → App-Specific Passwords → Generate.
 */
const { notarize } = require('@electron/notarize');
const { execSync } = require('child_process');

exports.default = async function notarizeApp(context) {
  if (context.electronPlatformName !== 'darwin') return;

  const appleId = process.env.APPLE_ID;
  const password = process.env.APPLE_APP_SPECIFIC_PASSWORD;
  const teamId = process.env.APPLE_TEAM_ID || '8TJHY75AV5';

  if (!appleId || !password) {
    console.warn(
      '⚠ Skipping notarization — set APPLE_ID and APPLE_APP_SPECIFIC_PASSWORD.\n' +
      '  The app will be Developer ID signed but Gatekeeper will block first launch.'
    );
    return;
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = `${context.appOutDir}/${appName}.app`;
  console.log(`Notarizing ${appPath}…`);

  await notarize({ appPath, appleId, appleIdPassword: password, teamId });

  console.log('Stapling notarization ticket…');
  execSync(`xcrun stapler staple "${appPath}"`, { stdio: 'inherit' });
  console.log('✓ Notarization complete');
};