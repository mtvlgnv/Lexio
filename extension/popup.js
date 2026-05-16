'use strict';

let isPro   = false;
let isTrial = false;

// ── Load state then fetch live Pro status ─────────────────────────────────────
chrome.runtime.sendMessage({ type: 'GET_STATE' }, state => {
  isPro   = state.isPro   || false;
  isTrial = state.trial   || false;

  // Enabled toggle
  document.getElementById('enabled-toggle').checked = state.enabled;

  // Auto-popup on selection toggle (default true)
  document.getElementById('auto-popup-toggle').checked = state.autoPopup !== false;

  // Language
  document.getElementById('lang-select').value = state.lang || 'auto';

  // Model selector
  setActiveModel(state.model || 'fast', isPro);

  // Word bank count
  const n = state.wbCount || 0;
  document.getElementById('wb-count').textContent =
    n === 0 ? 'No words saved yet' : `${n} word${n !== 1 ? 's' : ''} saved`;

  // Auth state
  if (state.user) {
    showSignedIn(state.user, isPro, isTrial);
  } else {
    showSignedOut();
  }

  // Refresh Pro status from server in background (user may have upgraded)
  if (state.token) {
    chrome.runtime.sendMessage({ type: 'GET_PRO_STATUS' }, result => {
      if (!result) return;
      const freshPro   = result.is_pro || false;
      const freshTrial = result.trial  || false;
      if (freshPro !== isPro || freshTrial !== isTrial) {
        isPro   = freshPro;
        isTrial = freshTrial;
        setActiveModel(state.model || 'fast', isPro);
        if (state.user) showSignedIn(state.user, isPro, isTrial);
      }
    });
  }
});

// ── Model selector ────────────────────────────────────────────────────────────
function setActiveModel(model, pro) {
  const grid = document.getElementById('model-grid');
  grid.classList.toggle('is-pro', pro);

  ['fast', 'balanced', 'deep'].forEach(m => {
    const btn = document.getElementById(`model-btn-${m}`);
    btn.classList.toggle('active', m === model);
    btn.classList.toggle('locked', !pro && m !== 'fast');
  });
}

document.getElementById('model-grid').addEventListener('click', e => {
  const btn = e.target.closest('.model-btn');
  if (!btn) return;
  const model = btn.dataset.model;
  if (!model) return;

  if (!isPro && model !== 'fast') {
    // Not Pro — show upgrade prompt
    document.getElementById('upgrade-link').classList.remove('hidden');
    document.getElementById('signed-in').scrollIntoView({ behavior: 'smooth' });
    return;
  }

  chrome.runtime.sendMessage({ type: 'SET_MODEL', model }, () => {
    setActiveModel(model, isPro);
  });
});

// ── Toggle enable/disable ─────────────────────────────────────────────────────
document.getElementById('enabled-toggle').addEventListener('change', e => {
  chrome.runtime.sendMessage({ type: 'SET_ENABLED', enabled: e.target.checked });
});

// ── Toggle auto-popup-on-selection ───────────────────────────────────────────
document.getElementById('auto-popup-toggle').addEventListener('change', e => {
  chrome.runtime.sendMessage({ type: 'SET_AUTO_POPUP', autoPopup: e.target.checked });
});

// ── Language change ───────────────────────────────────────────────────────────
document.getElementById('lang-select').addEventListener('change', e => {
  chrome.runtime.sendMessage({ type: 'SET_LANG', lang: e.target.value });
});

// ── Auth: sign in ─────────────────────────────────────────────────────────────
document.getElementById('auth-submit').addEventListener('click', async () => {
  const email    = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  const errEl    = document.getElementById('auth-error');
  const btn      = document.getElementById('auth-submit');

  errEl.classList.add('hidden');
  if (!email || !password) {
    errEl.textContent = 'Please enter your email and password.';
    errEl.classList.remove('hidden');
    return;
  }

  btn.disabled    = true;
  btn.textContent = 'Signing in…';

  chrome.runtime.sendMessage({ type: 'AUTH_LOGIN', email, password }, resp => {
    btn.disabled    = false;
    btn.textContent = 'Sign in';
    if (resp?.ok) {
      isPro   = resp.is_pro  || false;
      isTrial = resp.trial   || false;
      showSignedIn(resp.user, isPro, isTrial);
      setActiveModel('fast', isPro);
    } else {
      errEl.textContent = resp?.error || 'Sign in failed. Check your credentials.';
      errEl.classList.remove('hidden');
    }
  });
});

['auth-email', 'auth-password'].forEach(id => {
  document.getElementById(id).addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('auth-submit').click();
  });
});

// ── Auth: sign out ────────────────────────────────────────────────────────────
document.getElementById('signout-btn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'AUTH_LOGOUT' }, () => {
    isPro   = false;
    isTrial = false;
    setActiveModel('fast', false);
    showSignedOut();
  });
});

// ── UI helpers ────────────────────────────────────────────────────────────────
function showSignedIn(user, pro, trial) {
  document.getElementById('signed-out').style.display = 'none';
  document.getElementById('signed-in').style.display  = '';

  const name  = user.name  || user.email?.split('@')[0] || '?';
  const email = user.email || '';

  document.getElementById('user-name').textContent  = name;
  document.getElementById('user-email').textContent = email;

  const av = document.getElementById('user-avatar');
  av.textContent = name.charAt(0).toUpperCase();

  // Pro / Trial badges
  document.getElementById('pro-badge').classList.toggle('hidden', !pro || trial);
  document.getElementById('trial-badge').classList.toggle('hidden', !trial);

  // Upgrade CTA — shown for free signed-in users only
  document.getElementById('upgrade-link').classList.toggle('hidden', pro);
}

function showSignedOut() {
  document.getElementById('signed-in').style.display  = 'none';
  document.getElementById('signed-out').style.display = '';
  document.getElementById('auth-email').value    = '';
  document.getElementById('auth-password').value = '';
  document.getElementById('auth-error').classList.add('hidden');
}
