'use strict';

const API_BASE = 'https://lexio.site';

// ── In-memory definition cache (cleared when service worker restarts) ─────────
const defCache = new Map();
function cacheKey(word, context, lang, model) {
  return `${word.toLowerCase()}::${context.slice(0, 120)}::${lang}::${model || 'sonnet'}`;
}

// ── Context menu ──────────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id:       'lexio-define',
    title:    'Define with Lexio',
    contexts: ['selection'],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'lexio-define' && info.selectionText) {
    chrome.tabs.sendMessage(tab.id, {
      type: 'TRIGGER_DEFINE',
      word: info.selectionText.trim(),
    });
  }
});

// ── Message handler ───────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {

  // ── Fetch definition ────────────────────────────────────────────
  if (msg.type === 'DEFINE') {
    chrome.storage.local.get(['lexio_token', 'lexio_lang', 'lexio_model'], async (stored) => {
      // If content script sends 'auto' it may not have loaded storage yet — fall back to stored pref
      const lang  = (msg.lang && msg.lang !== 'auto') ? msg.lang : (stored.lexio_lang || 'auto');
      const model = msg.model || stored.lexio_model || 'sonnet';
      const key   = cacheKey(msg.word, msg.context || '', lang, model);

      if (defCache.has(key)) {
        sendResponse({ ok: true, data: defCache.get(key), cached: true });
        return;
      }

      try {
        const headers = { 'Content-Type': 'application/json' };
        if (stored.lexio_token) headers['Authorization'] = `Bearer ${stored.lexio_token}`;

        const resp = await fetch(`${API_BASE}/define`, {
          method:  'POST',
          headers,
          body:    JSON.stringify({ word: msg.word, context: msg.context || '', lang, model }),
        });

        if (resp.status === 429) throw new Error('Too many requests — wait a moment.');
        if (!resp.ok) {
          const e = await resp.json().catch(() => ({}));
          throw new Error(e.detail || `Server error ${resp.status}`);
        }

        const data = await resp.json();
        defCache.set(key, data);
        sendResponse({ ok: true, data });
      } catch (err) {
        sendResponse({ ok: false, error: err.message });
      }
    });
    return true; // keep channel open for async
  }

  // ── Save word to bank ────────────────────────────────────────────
  if (msg.type === 'SAVE_WORD') {
    chrome.storage.local.get(['lexio_wordbank', 'lexio_token'], async (stored) => {
      const bank  = stored.lexio_wordbank || [];
      const lower = msg.entry.word.toLowerCase();
      const idx   = bank.findIndex(e => e.word.toLowerCase() === lower);

      if (idx === -1) {
        bank.unshift(msg.entry);
        chrome.storage.local.set({ lexio_wordbank: bank });
      }

      // Sync to server if authenticated
      if (stored.lexio_token) {
        try {
          await fetch(`${API_BASE}/wordbank/sync`, {
            method:  'POST',
            headers: {
              'Content-Type':  'application/json',
              'Authorization': `Bearer ${stored.lexio_token}`,
            },
            body: JSON.stringify({ entries: bank }),
          });
        } catch {}
      }

      sendResponse({ ok: true, saved: idx === -1 });
    });
    return true;
  }

  // ── Remove word from bank ────────────────────────────────────────
  if (msg.type === 'UNSAVE_WORD') {
    chrome.storage.local.get(['lexio_wordbank', 'lexio_token'], async (stored) => {
      const bank    = stored.lexio_wordbank || [];
      const lower   = msg.word.toLowerCase();
      const updated = bank.filter(e => e.word.toLowerCase() !== lower);
      chrome.storage.local.set({ lexio_wordbank: updated });

      if (stored.lexio_token) {
        try {
          await fetch(`${API_BASE}/wordbank/sync`, {
            method:  'POST',
            headers: {
              'Content-Type':  'application/json',
              'Authorization': `Bearer ${stored.lexio_token}`,
            },
            body: JSON.stringify({ entries: updated }),
          });
        } catch {}
      }

      sendResponse({ ok: true });
    });
    return true;
  }

  // ── Auth: sign in ────────────────────────────────────────────────
  if (msg.type === 'AUTH_LOGIN') {
    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/auth/login`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ email: msg.email, password: msg.password }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Sign in failed');
        chrome.storage.local.set({ lexio_token: data.token, lexio_user: data.user });
        sendResponse({ ok: true, user: data.user });
      } catch (err) {
        sendResponse({ ok: false, error: err.message });
      }
    })();
    return true;
  }

  // ── Auth: sign out ───────────────────────────────────────────────
  if (msg.type === 'AUTH_LOGOUT') {
    chrome.storage.local.remove(['lexio_token', 'lexio_user']);
    sendResponse({ ok: true });
    return true;
  }

  // ── Get stored state (for popup) ─────────────────────────────────
  if (msg.type === 'GET_STATE') {
    chrome.storage.local.get(['lexio_token', 'lexio_user', 'lexio_lang', 'lexio_wordbank', 'lexio_enabled', 'lexio_model'], (d) => {
      sendResponse({
        token:    d.lexio_token    || null,
        user:     d.lexio_user     || null,
        lang:     d.lexio_lang     || 'auto',
        wbCount:  (d.lexio_wordbank || []).length,
        enabled:  d.lexio_enabled !== false, // default on
        model:    d.lexio_model    || 'sonnet',
      });
    });
    return true;
  }

  // ── Toggle extension on/off ──────────────────────────────────────
  if (msg.type === 'SET_ENABLED') {
    chrome.storage.local.set({ lexio_enabled: msg.enabled });
    sendResponse({ ok: true });
    return true;
  }

  // ── Set language ─────────────────────────────────────────────────
  if (msg.type === 'SET_LANG') {
    chrome.storage.local.set({ lexio_lang: msg.lang });
    defCache.clear(); // lang change invalidates cache
    sendResponse({ ok: true });
    return true;
  }

  // ── Set model ────────────────────────────────────────────────────
  if (msg.type === 'SET_MODEL') {
    chrome.storage.local.set({ lexio_model: msg.model });
    sendResponse({ ok: true });
    return true;
  }
});
