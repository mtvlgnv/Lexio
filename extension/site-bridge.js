'use strict';

// Runs on lexio.site only.
// Reads the auth token from the website's localStorage and forwards it to
// the background service worker so the extension can sync the word bank
// without requiring a separate login in the extension popup.

(function () {
  try {
    const token = localStorage.getItem('lexio_token');
    chrome.runtime.sendMessage({ type: 'SITE_TOKEN', token: token || null });
  } catch (e) {}
})();
