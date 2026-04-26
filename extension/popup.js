'use strict';

// ── Load state ────────────────────────────────────────────────────────────────
chrome.runtime.sendMessage({ type: 'GET_STATE' }, state => {
  // Enabled toggle
  document.getElementById('enabled-toggle').checked = state.enabled;

  // Language
  document.getElementById('lang-select').value = state.lang || 'auto';

  // Auth state
  if (state.user) {
    showSignedIn(state.user);
  } else {
    showSignedOut();
  }
});

// Load word bank directly from storage for the list
chrome.storage.local.get('lexio_wordbank', d => {
  renderWordBank(d.lexio_wordbank || []);
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

// ── Word bank list ────────────────────────────────────────────────────────────
function renderWordBank(bank) {
  const countEl = document.getElementById('wb-count');
  const listEl  = document.getElementById('wb-list');
  const n = bank.length;

  countEl.textContent = n === 0 ? 'No words collected yet' : `${n} word${n !== 1 ? 's' : ''} collected`;

  if (n === 0) {
    listEl.innerHTML = '<div class="wb-empty">Words you collect will appear here.</div>';
    return;
  }

  listEl.innerHTML = bank.map((e, i) => {
    const word = e.word || '';
    const pos  = e.pos  || '';
    const def  = e.contextual || e.definition || '';
    return `
      <div class="wb-item" data-idx="${i}">
        <div class="wb-item-body">
          <div class="wb-item-word">${esc(word)}</div>
          <div class="wb-item-def"><span class="wb-item-pos">${esc(pos)}</span>${esc(def)}</div>
        </div>
        <button class="wb-del" data-word="${esc(word)}" title="Remove">✕</button>
      </div>`;
  }).join('');

  listEl.querySelectorAll('.wb-del').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const word = btn.dataset.word;
      chrome.runtime.sendMessage({ type: 'UNSAVE_WORD', word }, () => {
        chrome.storage.local.get('lexio_wordbank', d => renderWordBank(d.lexio_wordbank || []));
      });
    });
  });
}

function esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
