// Parses the lexio://auth?token=...&user=... deep link used for the
// website → desktop sign-in handoff. main.js and main-overlay.js both
// register 'lexio' as their protocol and parsed this identically before
// diverging on what to DO with the result (main.js injects straight into
// its single webview's localStorage; main-overlay.js writes to store.js
// and notifies whichever windows are open) — only the parsing is shared.
function parseAuthUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.hostname !== 'auth') return null;
    const token = parsed.searchParams.get('token');
    if (!token) return null;
    const rawUser = parsed.searchParams.get('user');
    let user = null;
    if (rawUser) { try { user = JSON.parse(rawUser); } catch {} }
    return { token, user };
  } catch {
    return null;
  }
}

module.exports = { parseAuthUrl };
