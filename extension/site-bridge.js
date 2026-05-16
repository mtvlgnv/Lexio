'use strict';
// Runs ONLY on lexio.site. Reads the website's auth token from localStorage
// and copies it into the extension so users don't have to sign in twice.

(function () {
  function readWebsiteAuth() {
    try {
      const token = localStorage.getItem('lexio_token');
      const user  = localStorage.getItem('lexio_user');
      if (!token) return null;
      let parsedUser = null;
      try { parsedUser = user ? JSON.parse(user) : null; } catch {}
      return { token, user: parsedUser };
    } catch {
      return null;
    }
  }

  function sync() {
    const w = readWebsiteAuth();
    if (!w) return;
    chrome.runtime.sendMessage(
      { type: 'SYNC_AUTH', token: w.token, user: w.user },
      // No-op callback; we don't care about the response.
      () => { /* swallow errors when service worker is asleep */ void chrome.runtime.lastError; }
    );
  }

  // 1. Sync on load
  sync();

  // 2. Sync when the website's localStorage changes (e.g. user signs in/out in another tab)
  window.addEventListener('storage', (e) => {
    if (e.key === 'lexio_token' || e.key === 'lexio_user') sync();
  });

  // 3. Re-sync when the tab becomes visible again (user might have logged in
  //    in another tab; the 'storage' event only fires in OTHER tabs).
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') sync();
  });
})();
