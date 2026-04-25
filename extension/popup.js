'use strict';

// ── Load state ────────────────────────────────────────────────────────────────
chrome.runtime.sendMessage({ type: 'GET_STATE' }, state => {
  // Enabled toggle
  document.getElementById('enabled-toggle').checked = state.enabled;

  // Language
  document.getElementById('lang-select').value = state.lang || 'auto';

  // Word bank count
  const n = state.wbCount || 0;
  document.getElementById('wb-count').textContent =
    n === 0 ? 'No words collected yet' : `${n} word${n !== 1 ? 's' : ''} collected`;

  // Auth state
  if (state.user) {
    showSignedIn(state.user);
  } else {
    showSignedOut();
  }
});

// ── Toggle enable/disable ─────────────────────────────────────────────────────
document.getElementById('enabled-toggle').addEventListener('change', e => {
  chrome.runtime.sendMessage({ type: 'SET_ENABLED', enabled: e.target.checked });
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

  btn.disabled = true;
  btn.textContent = 'Signing in…';

  chrome.runtime.sendMessage({ type: 'AUTH_LOGIN', email, password }, resp => {
    btn.disabled = false;
    btn.textContent = 'Sign in';
    if (resp?.ok) {
      showSignedIn(resp.user);
    } else {
      errEl.textContent = resp?.error || 'Sign in failed. Check your credentials.';
      errEl.classList.remove('hidden');
    }
  });
});

// Enter key in auth inputs
['auth-email', 'auth-password'].forEach(id => {
  document.getElementById(id).addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('auth-submit').click();
  });
});

// ── Auth: sign out ────────────────────────────────────────────────────────────
document.getElementById('signout-btn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'AUTH_LOGOUT' }, () => showSignedOut());
});

// ── UI helpers ────────────────────────────────────────────────────────────────
function showSignedIn(user) {
  document.getElementById('signed-out').style.display = 'none';
  document.getElementById('signed-in').style.display  = '';

  const name  = user.name  || user.email?.split('@')[0] || '?';
  const email = user.email || '';

  document.getElementById('user-name').textContent  = name;
  document.getElementById('user-email').textContent = email;

  const av = document.getElementById('user-avatar');
  av.textContent = name.charAt(0).toUpperCase();
}

function showSignedOut() {
  document.getElementById('signed-in').style.display  = 'none';
  document.getElementById('signed-out').style.display = '';
  document.getElementById('auth-email').value    = '';
  document.getElementById('auth-password').value = '';
  document.getElementById('auth-error').classList.add('hidden');
}
