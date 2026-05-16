'use strict';

const API_BASE = 'https://lexio.site';

// ── In-memory definition cache (cleared when service worker restarts) ─────────
const defCache = new Map();
function cacheKey(word, context, lang, model) {
  return `${word.toLowerCase()}::${context.slice(0, 120)}::${lang}::${model}`;
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
      const lang  = (msg.lang && msg.lang !== 'auto') ? msg.lang : (stored.lexio_lang || 'auto');
      const model = stored.lexio_model || 'fast';
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

        if (resp.status === 402) {
          const err = await resp.json().catch(() => ({}));
          const d   = err.detail || {};
          const msg402 = d.kind === 'lookup'
            ? `Monthly limit reached (${d.used || 0}/${d.limit || 100} lookups). Upgrade to Pro for unlimited lookups.`
            : 'Monthly limit reached. Upgrade to Pro at lexio.site.';
          sendResponse({ ok: false, error: msg402, code: 'limit_exceeded' });
          return;
        }

        if (resp.status === 403) {
          const err = await resp.json().catch(() => ({}));
          const d   = err.detail || {};
          sendResponse({
            ok:    false,
            error: d.message || 'This mode requires a Pro plan. Upgrade at lexio.site.',
            code:  'pro_required',
          });
          return;
        }

        if (resp.status === 429) {
          const err = await resp.json().catch(() => ({}));
          const d   = err.detail || {};
          const mins = Math.max(1, Math.ceil((d.reset_in || 0) / 60));
          sendResponse({
            ok:    false,
            error: `Hourly limit reached. Try again in ${mins} minute${mins !== 1 ? 's' : ''}.`,
            code:  'hourly_limit',
          });
          return;
        }

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
    return true;
  }

  // ── Auth bridge from lexio.site — copy website session into extension ────
  if (msg.type === 'SYNC_AUTH') {
    if (!msg.token) { sendResponse({ ok: false }); return true; }
    chrome.storage.local.get(['lexio_token'], async (stored) => {
      // If the extension already has a working token, do not overwrite —
      // user may have signed in to a different account in the extension.
      if (stored.lexio_token === msg.token) { sendResponse({ ok: true, unchanged: true }); return; }
      const updates = { lexio_token: msg.token };
      if (msg.user) updates.lexio_user = msg.user;
      chrome.storage.local.set(updates);
      // Fetch Pro status with the new token
      try {
        const r = await fetch(`${API_BASE}/api/pro-status`, {
          headers: { 'Authorization': `Bearer ${msg.token}` },
        });
        if (r.ok) {
          const pd    = await r.json();
          const trial = !!pd.is_trial;
          const isPro = !!(pd.is_pro || trial);
          chrome.storage.local.set({ lexio_is_pro: isPro, lexio_trial: trial });
          sendResponse({ ok: true, is_pro: isPro, trial });
          return;
        }
      } catch {}
      sendResponse({ ok: true });
    });
    return true;
  }

  // ── Fetch Pro status from server ─────────────────────────────────
  if (msg.type === 'GET_PRO_STATUS') {
    chrome.storage.local.get(['lexio_token'], async (stored) => {
      if (!stored.lexio_token) {
        chrome.storage.local.set({ lexio_is_pro: false, lexio_trial: false });
        sendResponse({ is_pro: false, trial: false });
        return;
      }
      try {
        const resp = await fetch(`${API_BASE}/api/pro-status`, {
          headers: { 'Authorization': `Bearer ${stored.lexio_token}` },
        });
        if (!resp.ok) { sendResponse({ is_pro: false, trial: false }); return; }
        const data  = await resp.json();
        const isPro = !!(data.is_pro || data.is_trial);
        chrome.storage.local.set({ lexio_is_pro: isPro, lexio_trial: !!data.is_trial });
        sendResponse({ is_pro: isPro, trial: !!data.is_trial });
      } catch {
        sendResponse({ is_pro: false, trial: false });
      }
    });
    return true;
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
      if (!stored.lexio_token) {
        sendResponse({ ok: true, saved: idx === -1, synced: false, reason: 'no_auth' });
        return;
      }
      try {
        const r = await fetch(`${API_BASE}/wordbank/sync`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${stored.lexio_token}` },
          body: JSON.stringify({ entries: bank }),
        });
        if (r.ok) {
          sendResponse({ ok: true, saved: idx === -1, synced: true });
        } else if (r.status === 401) {
          chrome.storage.local.remove(['lexio_token', 'lexio_user', 'lexio_is_pro', 'lexio_trial']);
          sendResponse({ ok: true, saved: idx === -1, synced: false, reason: 'token_expired' });
        } else {
          sendResponse({ ok: true, saved: idx === -1, synced: false, reason: 'server', status: r.status });
        }
      } catch {
        sendResponse({ ok: true, saved: idx === -1, synced: false, reason: 'network' });
      }
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
      if (!stored.lexio_token) {
        sendResponse({ ok: true, synced: false, reason: 'no_auth' });
        return;
      }
      try {
        const r = await fetch(`${API_BASE}/wordbank/sync`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${stored.lexio_token}` },
          body: JSON.stringify({ entries: updated }),
        });
        sendResponse({ ok: true, synced: r.ok });
      } catch {
        sendResponse({ ok: true, synced: false, reason: 'network' });
      }
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
        // Fetch Pro status immediately after login
        try {
          const ps  = await fetch(`${API_BASE}/api/pro-status`, {
            headers: { 'Authorization': `Bearer ${data.token}` },
          });
          if (ps.ok) {
            const pd    = await ps.json();
            const isPro = !!(pd.is_pro || pd.is_trial);
            chrome.storage.local.set({ lexio_is_pro: isPro, lexio_trial: !!pd.is_trial });
            // Downgrade model if no longer Pro
            if (!isPro) {
              chrome.storage.local.get(['lexio_model'], (s) => {
                if (s.lexio_model && s.lexio_model !== 'fast') {
                  chrome.storage.local.set({ lexio_model: 'fast' });
                }
              });
            }
            sendResponse({ ok: true, user: data.user, is_pro: isPro, trial: !!pd.is_trial });
            return;
          }
        } catch {}
        sendResponse({ ok: true, user: data.user, is_pro: false, trial: false });
      } catch (err) {
        sendResponse({ ok: false, error: err.message });
      }
    })();
    return true;
  }

  // ── Auth: sign out ───────────────────────────────────────────────
  if (msg.type === 'AUTH_LOGOUT') {
    chrome.storage.local.remove(['lexio_token', 'lexio_user', 'lexio_is_pro', 'lexio_trial']);
    chrome.storage.local.set({ lexio_model: 'fast' });
    sendResponse({ ok: true });
    return true;
  }

  // ── Get stored state (for popup) ─────────────────────────────────
  if (msg.type === 'GET_STATE') {
    chrome.storage.local.get(
      ['lexio_token', 'lexio_user', 'lexio_lang', 'lexio_wordbank', 'lexio_enabled', 'lexio_model', 'lexio_is_pro', 'lexio_trial', 'lexio_auto_popup'],
      (d) => {
        sendResponse({
          token:     d.lexio_token   || null,
          user:      d.lexio_user    || null,
          lang:      d.lexio_lang    || 'auto',
          model:     d.lexio_model   || 'fast',
          wbCount:   (d.lexio_wordbank || []).length,
          enabled:   d.lexio_enabled    !== false,
          autoPopup: d.lexio_auto_popup !== false,  // default true
          isPro:     d.lexio_is_pro  || false,
          trial:     d.lexio_trial   || false,
        });
      }
    );
    return true;
  }

  // ── Toggle extension on/off ──────────────────────────────────────
  if (msg.type === 'SET_ENABLED') {
    chrome.storage.local.set({ lexio_enabled: msg.enabled });
    sendResponse({ ok: true });
    return true;
  }

  // ── Toggle auto-popup-on-selection ───────────────────────────────
  // When false, content.js will skip selection-triggered lookups but
  // the right-click "Define with Lexio" context menu still works.
  if (msg.type === 'SET_AUTO_POPUP') {
    chrome.storage.local.set({ lexio_auto_popup: !!msg.autoPopup });
    sendResponse({ ok: true });
    return true;
  }

  // ── Set language ─────────────────────────────────────────────────
  if (msg.type === 'SET_LANG') {
    chrome.storage.local.set({ lexio_lang: msg.lang });
    defCache.clear();
    sendResponse({ ok: true });
    return true;
  }

  // ── Set model ────────────────────────────────────────────────────
  if (msg.type === 'SET_MODEL') {
    chrome.storage.local.set({ lexio_model: msg.model });
    defCache.clear();
    sendResponse({ ok: true });
    return true;
  }
});
