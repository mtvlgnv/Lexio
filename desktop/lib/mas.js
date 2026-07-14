// Mac App Store build detection. `process.mas` is set by the MAS build of
// Electron itself; LEXIO_MAS=1 lets a dev run simulate the sandboxed build's
// behavior (hotkey-only trigger, no Accessibility, IAP instead of Stripe)
// without packaging.
const IS_MAS = process.mas === true || process.env.LEXIO_MAS === '1';
module.exports = { IS_MAS };
