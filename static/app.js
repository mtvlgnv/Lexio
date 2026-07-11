/* ══════════════════════════════════════════════════════════
   LEXIO — client script
   ══════════════════════════════════════════════════════════ */

/* ── Constants ─────────────────────────────────────────────── */
const MAX_HISTORY = 5;
const WB_KEY      = 'lexio_wbv1';

/* ── Analytics: educator/classroom CTA clicks (Apollo campaign attribution) ── */
function trackEducatorCTA(location) {
  try { window.plausible && plausible('Educator CTA', { props: { location } }); } catch (e) {}
  try { window.posthog && posthog.capture('educator_cta_click', { location }); } catch (e) {}
}

/* ── Desktop app auth handoff ───────────────────────────────── */
// After login, if opened from the Mac app, redirect token back via lexio:// scheme
function _maybeRedirectDesktop(token, user) {
  if (!new URLSearchParams(location.search).has('desktop_auth')) return;
  const u = new URL('lexio://auth');
  u.searchParams.set('token', token);
  u.searchParams.set('user', JSON.stringify(user));
  window.location.href = u.toString();
}
// Already signed in? The login success handlers never run, so hand the
// existing session straight back to the desktop app on arrival.
document.addEventListener('DOMContentLoaded', () => {
  const tok = localStorage.getItem('lexio_token');
  if (!tok) return;
  let user = null;
  try { user = JSON.parse(localStorage.getItem('lexio_user')); } catch {}
  _maybeRedirectDesktop(tok, user || {});
});
const TWEAKS_KEY  = 'lexio_tweaks';
const VISITED_KEY = 'lexio_visited';

const STOPWORDS = new Set([
  'the','a','an','and','or','but','in','on','at','to','for','of','with',
  'by','from','it','is','was','are','were','be','been','have','has','had',
  'do','does','did','will','would','could','should','may','might','shall',
  'can','this','that','these','those','i','you','he','she','we','they',
  'not','no','so','as','if','then','than','when','what','who','which',
  'how','all','any','each','every','its','their','our','my','your','his',
  'her','just','also','into','up','out','about','over','after','before',
  'between','through','such','more','very','still','been','same','where',
  'there','here','now','only','even','back','way','well','down','get',
]);

const SAMPLES = [
  { label: 'Fiction', text: `He smiled with a warmth that, she would later realize, was entirely adventitious.` },
  { label: 'News', text: `The central bank announced a hawkish pivot, indicating that further rate hikes are imminent.` },
  { label: 'Science', text: `The experiment demonstrated a serendipitous outcome that contradicted the initial hypothesis.` },
  { label: 'Law', text: `The contract contains a severability clause, ensuring that if one provision is found invalid, the rest remains enforceable.` }
];

const PLACEHOLDERS = [
  'Paste any text here…',
  'Try a dense editorial, a legal clause, or a scientific abstract…',
  'Drop in your literary prose…',
  'Paste anything written with care',
];

/* ── State ──────────────────────────────────────────────────── */
let currentContext   = '';
let activeToken      = null;
let currentResult    = null;
let defCache         = new Map();
let history          = [];
let wordBank         = [];
let lookedUpWords    = new Set();
let currentSample    = -1;
let placeholderIdx   = 0;
let placeholderTimer = null;
let tooltipStep      = -1;
let shortcutsOpen    = false;
let currentLang      = 'auto';
let isAutoTheme      = false;

/* ── Tweaks ─────────────────────────────────────────────────── */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "warm", "fontSize": 18, "lineHeight": 2.1
}/*EDITMODE-END*/;
let currentTweaks = { ...TWEAK_DEFAULTS };

function loadTweaks() {
  try { currentTweaks = { ...TWEAK_DEFAULTS, ...JSON.parse(localStorage.getItem(TWEAKS_KEY) || '{}') }; } catch {}
}
function saveTweaks() {
  try { localStorage.setItem(TWEAKS_KEY, JSON.stringify(currentTweaks)); } catch {}
}

/* ── Word bank ──────────────────────────────────────────────── */
function loadWordBank() {
  // If the visitor isn't signed in, treat the word bank as empty and clear
  // any stale entries left behind by a previous session on this device.
  const _signedIn = !!localStorage.getItem('lexio_token');
  if (!_signedIn) {
    try { localStorage.removeItem(WB_KEY); } catch {}
    wordBank = [];
    return;
  }
  try { wordBank = JSON.parse(localStorage.getItem(WB_KEY) || '[]'); } catch { wordBank = []; }
}
function saveWordBank() {
  try { localStorage.setItem(WB_KEY, JSON.stringify(wordBank)); } catch {}
  updateWBBadge();
}
function updateWBBadge() {
  const badge = document.getElementById('wb-badge');
  if (wordBank.length > 0) {
    const prev = badge.textContent;
    badge.textContent = wordBank.length;
    badge.style.display = 'inline-flex';
    if (prev !== String(wordBank.length)) {
      badge.classList.add('pop');
      setTimeout(() => badge.classList.remove('pop'), 300);
    }
  } else {
    badge.style.display = 'none';
  }
}

/* ── Theme ──────────────────────────────────────────────────── */
function setTheme(t) {
  isAutoTheme = (t === 'auto');
  const effective = isAutoTheme
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'warm')
    : t;
  document.body.dataset.theme = effective;
  document.querySelectorAll('.theme-btn').forEach(b => b.classList.toggle('active', b.dataset.theme === t));
  document.querySelectorAll('.menu-theme-btn').forEach(b => b.classList.toggle('active', b.dataset.theme === t));
  document.querySelectorAll('.tweak-opt').forEach((b, i) => b.classList.toggle('active', ['warm','cool','dark'][i] === t));
  currentTweaks.theme = t; saveTweaks();
  window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { theme: t } }, '*');
}

/* ── Model selection ───────────────────────────────────────── */
let currentModel = 'deep';
let _pendingSwitchModel = null;   // model the user wants to switch to

const MODEL_LABELS = {
  fast: 'Fast', balanced: 'Balanced', deep: 'Deep',
  // legacy aliases
  haiku: 'Fast', 'gpt-4-mini': 'Fast', gemini: 'Balanced', sonnet: 'Deep'
};

function setModel(model) {
  currentModel = model;
  try { localStorage.setItem('lexio_model', model); } catch {}

  // Sync pill active state
  document.querySelectorAll('.model-pill').forEach(b =>
    b.classList.toggle('active', b.dataset.model === model)
  );

  // Sync mode-dropdown trigger label
  const trigLabel = document.getElementById('mode-trigger-label');
  if (trigLabel) trigLabel.textContent = MODEL_LABELS[model] || model;

  // Sync ☰ menu model buttons (mobile)
  document.querySelectorAll('[data-model-btn]').forEach(b =>
    b.classList.toggle('active', b.dataset.modelBtn === model)
  );

  // Update user preference if authenticated
  if (authToken) {
    fetch('/api/user-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
      body: JSON.stringify({ model })
    }).catch(() => {});
  }
}

/* ── Mode dropdown open/close ─────────────────────────────── */
function toggleModeDropdown(e) {
  if (e) e.stopPropagation();
  const dd = document.getElementById('mode-dropdown');
  const menu = document.getElementById('mode-menu');
  const trig = document.getElementById('mode-trigger');
  if (!dd || !menu || !trig) return;
  const willOpen = menu.classList.contains('hidden');
  menu.classList.toggle('hidden', !willOpen);
  dd.classList.toggle('open', willOpen);
  trig.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
}
function _closeModeDropdown() {
  const dd = document.getElementById('mode-dropdown');
  const menu = document.getElementById('mode-menu');
  const trig = document.getElementById('mode-trigger');
  if (!menu) return;
  menu.classList.add('hidden');
  dd?.classList.remove('open');
  trig?.setAttribute('aria-expanded', 'false');
}
function _selectMode(model) {
  _closeModeDropdown();
  // Gate Pro-only modes for non-Pro users.
  if (model !== 'fast' && !_userIsPro) {
    if (!localStorage.getItem('lexio_token')) {
      // Anonymous — prompt sign-in first.
      if (typeof openAuthModal === 'function') openAuthModal(true);
    } else {
      // Signed in but not Pro — show upgrade modal.
      if (typeof showProModal === 'function') {
        showProModal('lookup', 0, 20);
      }
    }
    return;
  }
  onModelPillClick(model);
}

/* ── "Pick how you read" preview card on the landing page ─── */
/* Brand-icon SVGs shared between the pill row and the detail-card swap. */
const MODE_BRAND_SVG = {
  Groq: '<svg viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="5" fill="#F55036"/><text x="12" y="16.5" text-anchor="middle" font-family="-apple-system,Segoe UI,Roboto,sans-serif" font-size="11" font-weight="800" fill="#fff">G</text></svg>',
  Google: '<svg viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09Z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"/><path fill="#FBBC05" d="M5.84 14.09a6.6 6.6 0 0 1 0-4.18V7.07H2.18a11 11 0 0 0 0 9.86l2.85-2.22.81-.62Z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A11 11 0 0 0 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53Z"/></svg>',
  Anthropic: '<svg viewBox="0 0 24 24"><path fill="#D97757" d="M11.5 3h1L20 21h-3.4l-1.5-4H8.9l-1.5 4H4l7.5-18Zm.5 4.5L9.7 14h4.6L12 7.5Z"/></svg>',
};
const MODE_PREVIEW = {
  fast: {
    name: 'Fast',
    provider: 'Groq',
    engine: 'Llama 3.1 8B Instant',
    desc: 'Near-instant lookups. Concise and accurate — best for high-frequency reading when you don’t want to break flow.',
    best: 'Best for: quick lookups while you’re skimming.'
  },
  balanced: {
    name: 'Balanced',
    provider: 'Google',
    engine: 'Gemini 2.5 Flash',
    desc: 'Smart and thorough — wide language coverage, strong contextual reasoning, and rich cultural nuance.',
    best: 'Best for: most readers, most of the time.'
  },
  deep: {
    name: 'Deep',
    provider: 'Anthropic',
    engine: 'Claude Sonnet 4.5',
    desc: 'Maximum depth — richer etymologies, literary-grade register, and the most precise “why this word” explanations.',
    best: 'Best for: literature, philosophy, legal prose.'
  }
};
function previewMode(mode) {
  const info = MODE_PREVIEW[mode];
  if (!info) return;
  document.querySelectorAll('.lp-mode-pill').forEach(b => {
    const isActive = b.dataset.mode === mode;
    b.classList.toggle('active', isActive);
    b.setAttribute('aria-selected', String(isActive));
  });
  const $ = id => document.getElementById(id);
  if ($('lp-mode-name'))     $('lp-mode-name').textContent     = info.name;
  if ($('lp-mode-provider-name')) $('lp-mode-provider-name').textContent = info.provider;
  if ($('lp-mode-engine'))   $('lp-mode-engine').textContent   = info.engine;
  if ($('lp-mode-desc'))     $('lp-mode-desc').textContent     = info.desc;
  if ($('lp-mode-best'))     $('lp-mode-best').textContent     = info.best;
  // Swap the provider brand icon in the detail card
  const iconEl = $('lp-mode-provider-icon');
  if (iconEl) iconEl.innerHTML = MODE_BRAND_SVG[info.provider] || '';
}
// Initial brand-icon paint so the default Balanced mode shows Google's logo
document.addEventListener('DOMContentLoaded', () => {
  const iconEl = document.getElementById('lp-mode-provider-icon');
  if (iconEl && !iconEl.innerHTML.trim()) iconEl.innerHTML = MODE_BRAND_SVG.Google;
});
// Close on outside click & on Escape
document.addEventListener('click', (e) => {
  const dd = document.getElementById('mode-dropdown');
  if (dd && !dd.contains(e.target)) _closeModeDropdown();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') _closeModeDropdown();
});

/* Smart pill click: if a result is shown, offer comparison; otherwise just switch */
function onModelPillClick(model) {
  cancelModelSwitch();  // close any open confirmation first

  // No result shown yet — just switch normally
  if (!resultWord) { setModel(model); return; }
  // Already viewing this model's result — no-op
  if (model === currentResultModel) return;

  // Already have this model's result cached — switch instantly
  if (modelResults[model]) {
    setModel(model);
    currentResultModel = model;
    showResult(resultWord, modelResults[model], false, model);
    return;
  }

  // Need to fetch — show confirmation bar
  _pendingSwitchModel = model;
  const label  = MODEL_LABELS[model] || model;
  const word   = resultWord || 'this word';
  const msg    = document.getElementById('model-switch-msg');
  msg.innerHTML = `Compare <strong class="model-switch-msg-word">${_escape(word)}</strong> with <strong>${_escape(label)}</strong>?`;
  document.getElementById('model-switch-go').onclick = confirmModelSwitch;
  document.getElementById('model-switch-confirm').classList.remove('hidden');
}

function cancelModelSwitch() {
  _pendingSwitchModel = null;
  document.getElementById('model-switch-confirm').classList.add('hidden');
}

async function confirmModelSwitch() {
  const model = _pendingSwitchModel;
  if (!model || !resultWord || !resultContext) { cancelModelSwitch(); return; }
  cancelModelSwitch();
  setModel(model);
  // Re-highlight the correct word token (fetchDefinition uses activeToken)
  document.querySelectorAll('.word-token').forEach(t => {
    if (t.textContent.toLowerCase() === resultWord) {
      activeToken = t; t.classList.add('pulsing');
    }
  });
  await fetchDefinition(resultWord, resultContext, model);
}

/* Render tabs above the definition when ≥2 models have results */
function renderModelTabs() {
  const tabs = document.getElementById('model-result-tabs');
  if (!tabs) return;
  const keys = Object.keys(modelResults);
  if (keys.length < 2) { tabs.innerHTML = ''; tabs.classList.add('hidden'); return; }

  tabs.innerHTML = keys.map(m => {
    const label = MODEL_LABELS[m] || m;
    const active = m === currentResultModel ? 'active' : '';
    const dot = active ? '<span class="tab-dot"></span>' : '';
    return `<button class="model-result-tab ${active}" onclick="switchResultModel('${m}')">${dot}${label}</button>`;
  }).join('');
  tabs.classList.remove('hidden');
}

function switchResultModel(model) {
  if (!modelResults[model]) return;
  currentResultModel = model;
  setModel(model);
  showResult(resultWord, modelResults[model], false, model);
}

async function initializeModelSelector() {
  // Load saved preference (default: deep). Migrate old names.
  const _legacyMap = {haiku:'fast','gpt-4-mini':'fast','gpt-4o-mini':'fast',gemini:'balanced',sonnet:'deep'};
  const _raw = localStorage.getItem('lexio_model') || 'deep';
  const saved = _legacyMap[_raw] || _raw;
  currentModel = saved;

  // If authenticated, prefer server-side preference
  if (authToken) {
    try {
      const res = await fetch('/api/user-model', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        currentModel = data.model;
      }
    } catch {}
  }

  // Sync pills to current model
  document.querySelectorAll('.model-pill').forEach(b =>
    b.classList.toggle('active', b.dataset.model === currentModel)
  );

  // Sync mode-dropdown trigger label
  const trigLabel = document.getElementById('mode-trigger-label');
  if (trigLabel) trigLabel.textContent = MODEL_LABELS[currentModel] || currentModel;
}

/* ── Pro modal ─────────────────────────────────────────── */
function showProModal(kind, used, limit) {
  const sub        = document.getElementById('pro-modal-sub');
  const title      = document.querySelector('#pro-modal .pro-modal-title');
  const planCard   = document.querySelector('#pro-modal .pro-plan-card');
  const resetNote  = document.querySelector('#pro-modal .pro-modal-reset');
  const signupBtn  = document.getElementById('pro-modal-signup');

  // Heuristic: limits above the free tier mean the user is on Pro and hit
  // the Pro cap (500 OCR / 20,000 credits / month).
  const isProCap = (kind === 'ocr' && limit > 10) || (kind === 'monthly_credit');

  // Anonymous visitors who run out of their free lookups should be invited to
  // create a free account (20 lookups/month) before being asked to pay for Pro.
  const isSignupNudge = !localStorage.getItem('lexio_token') && kind === 'lookup';
  if (signupBtn) signupBtn.style.display = isSignupNudge ? '' : 'none';

  if (isProCap) {
    if (title) title.textContent = "You've hit your Pro monthly cap";
    if (planCard)  planCard.style.display  = 'none';
    if (resetNote) resetNote.textContent =
      'Your Pro quota resets on the 1st of next month. If you need more, write to ' +
      'matveylgnv2021@gmail.com — I read every message.';
  } else if (isSignupNudge) {
    if (title) title.textContent = "You've used your free lookups";
    if (planCard)  planCard.style.display  = '';
    if (resetNote) resetNote.textContent =
      'A free account gives you 20 lookups every month — no card required.';
  } else {
    if (title) title.textContent = "You've hit your free limit";
    if (planCard)  planCard.style.display  = '';
    if (resetNote) resetNote.textContent =
      'Your free quota resets on the 1st of each month.';
  }

  if (kind === 'ocr') {
    sub.textContent = isProCap
      ? `You've used all ${limit} Pro OCR scans this month.`
      : `You've used all ${limit} free OCR scans this month.`;
  } else if (kind === 'monthly_credit') {
    sub.textContent =
      `You've used all ${limit.toLocaleString()} Pro credits this month. ` +
      `Fast = 1 credit, Balanced = 2, Deep = 3.`;
  } else if (isSignupNudge) {
    sub.textContent =
      `You've used all ${limit} free lookups. Create a free account to keep ` +
      `going — 20 lookups every month, free.`;
  } else {
    sub.textContent = `You've used all ${limit} free lookups this month.`;
  }
  document.getElementById('pro-modal').classList.remove('hidden');
}
function closeProModal() {
  document.getElementById('pro-modal').classList.add('hidden');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeProModal(); });

/* ── Usage pill (monthly lookups, free tier only) ─────────── */
function updateUsagePill(used, limit) {
  const pill  = document.getElementById('usage-pill');
  const text  = document.getElementById('usage-text');
  const fill  = document.getElementById('usage-fill');
  if (!pill || limit < 0) return;   // Pro = unlimited, hide pill
  const pct = Math.min(100, Math.round(used / limit * 100));
  text.textContent = `${used} / ${limit}`;
  fill.style.width = pct + '%';
  pill.classList.toggle('danger', pct >= 80);
  if (pct >= 80) pill.title = `${limit - used} lookups left this month`;
}

/* ── Hourly pill (credit budget for everyone, anonymous skipped) ── */
function updateHourlyPill(used, limit) {
  const pill = document.getElementById('hourly-pill');
  const text = document.getElementById('hourly-text');
  const fill = document.getElementById('hourly-fill');
  if (!pill) return;
  // Anonymous users have no per-user hourly limit on the server — hide pill.
  if (typeof limit !== 'number' || limit < 0) {
    pill.style.display = 'none';
    return;
  }
  pill.style.display = '';
  const pct = Math.min(100, Math.round(used / limit * 100));
  text.textContent = `${used} / ${limit}`;
  fill.style.width = pct + '%';
  pill.classList.toggle('danger', pct >= 80);
  pill.title = pct >= 80
    ? `${limit - used} credits left this hour (Fast=1, Balanced=2, Deep=3)`
    : 'Hourly credits — Fast=1, Balanced=2, Deep=3. Resets every hour.';
}

async function loadUsage() {
  try {
    const token = localStorage.getItem('lexio_token');
    const headers = token ? { Authorization: 'Bearer ' + token } : {};
    const res = await fetch('/api/usage', { headers });
    // Stale token (e.g. session pruned by MAX_SESSIONS_PER_USER on another
    // device). Server returns 401 + {code:"session_expired"} so we can
    // clear stale local auth and surface a clear "sign in again" prompt
    // instead of silently downgrading to the free-tier display.
    if (res.status === 401 && token) {
      const body = await res.json().catch(() => ({}));
      const code = body?.detail?.code;
      if (code === 'session_expired') {
        try {
          localStorage.removeItem('lexio_token');
          localStorage.removeItem('lexio_user');
        } catch {}
        authToken = null; authUser = null;
        updateAcctBtn();
        // Toast-like banner if available, otherwise the auth modal.
        if (typeof openAuthModal === 'function') openAuthModal(true);
        return;
      }
    }
    if (!res.ok) return;
    const data = await res.json();
    if (data.is_pro) {
      // Pro: monthly is unlimited (hide that pill); the hourly credit budget
      // is the only meaningful cap, so show just the hourly pill.
      const pill = document.getElementById('usage-pill');
      if (pill) pill.style.display = 'none';
      if (data.hourly) updateHourlyPill(data.hourly.used, data.hourly.limit);
    } else {
      // Free: the monthly lookup cap is the binding limit. The hourly pill
      // would carry the same number (free hourly limit == monthly == 20),
      // producing two identical bars — so hide it and show monthly only.
      updateUsagePill(data.lookup.used, data.lookup.limit);
      const hp = document.getElementById('hourly-pill');
      if (hp) hp.style.display = 'none';
    }
  } catch (_) {}
}

/* ── Lookup streak: the under-tool panel (signed-in tool-page users only) ── */
async function loadStreak() {
  const panel = document.getElementById('app-streak-panel');
  const row   = document.getElementById('app-engage-row');
  if (!panel || !document.body.classList.contains('tool-page')) return;
  const token = localStorage.getItem('lexio_token');
  if (!token) { panel.style.display = 'none'; return; }   // anon: no streak
  try {
    const res = await fetch('/api/streak', { headers: { Authorization: 'Bearer ' + token } });
    if (!res.ok) { panel.style.display = 'none'; return; }
    const d = await res.json();
    const n = d.current_streak || 0;
    const dayWord = x => x === 1 ? '1 day' : x + ' days';
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('streak-panel-days', n);
    set('streak-panel-unit', n === 1 ? 'day' : 'days');
    set('streak-panel-best', d.longest_streak ? dayWord(d.longest_streak) : '—');
    panel.style.display = '';
    panel.classList.toggle('hot', n >= 3);
    if (row) row.classList.add('shown');

    if (d.activity && d.activity.length > 0) {
      document.getElementById('app-activity-graph').style.display = '';
      if (row) row.classList.add('shown');
      // Wait for grid to finish layout, then measure and render
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          renderActivityGraph(d.activity);
        });
      });
    }
  } catch (_) { panel.style.display = 'none'; }
}

function renderActivityGraph(activity) {
  const container = document.getElementById('activity-graph-container');
  const subtitle = document.getElementById('activity-graph-subtitle');
  if (!container) return;

  const total = activity.reduce((sum, d) => sum + d.count, 0);
  if (subtitle) subtitle.textContent = `${total} words · ${activity.length} days`;

  const maxValRaw = Math.max(...activity.map(d => d.count));
  const maxVal = Math.max(5, Math.ceil(maxValRaw / 5) * 5);

  // Measure the container so the viewBox matches actual pixels (no text distortion).
  const rect = container.getBoundingClientRect();
  const W = Math.round(rect.width)  || 600;
  const H = Math.round(rect.height) || 180;
  const ml = 28, mr = 6, mt = 6, mb = 20;
  const gw = W - ml - mr;
  const gh = H - mt - mb;
  const bw = gw / activity.length;

  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%">`;

  // Y-axis dotted grid lines + labels
  const ticks = [0, Math.round(maxVal / 2), maxVal];
  ticks.forEach(t => {
    const y = mt + gh - (t / maxVal) * gh;
    svg += `<line x1="${ml}" y1="${y}" x2="${W - mr}" y2="${y}" class="activity-graph-grid-line"/>`;
    svg += `<text x="${ml - 6}" y="${y + 4}" text-anchor="end" class="activity-graph-axis-text">${t}</text>`;
  });

  // Format "Jun 12"
  const fmtDate = s => {
    const [, m, day] = s.split('-');
    return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+m - 1]
           + ' ' + +day;
  };

  // Bars + X-axis date labels
  activity.forEach((d, i) => {
    const h = d.count === 0 ? 0 : Math.max(3, (d.count / maxVal) * gh);
    const x = ml + i * bw;
    const y = mt + gh - h;
    svg += `<rect x="${x + bw * 0.12}" y="${y}" width="${Math.max(2, bw * 0.76)}" height="${h}" class="activity-graph-bar" rx="2"><title>${fmtDate(d.date)}: ${d.count} lookups</title></rect>`;

    // Show date on first, last, and every 7th bar
    if (i === 0 || i === activity.length - 1 || (activity.length > 10 && i % 7 === 0)) {
      svg += `<text x="${x + bw / 2}" y="${H - 4}" text-anchor="middle" class="activity-graph-axis-text">${fmtDate(d.date)}</text>`;
    }
  });

  svg += `</svg>`;
  container.innerHTML = svg;
}

/* ── OCR / photo-to-text ────────────────────────────── */
function triggerOCR() {
  document.getElementById('ocr-file-input').click();
}

async function handleOCRFile(input) {
  const file = input.files[0];
  if (!file) return;
  input.value = ''; // reset so same file can be re-selected

  // Show overlay with preview
  const overlay = document.getElementById('ocr-overlay');
  const preview = document.getElementById('ocr-preview');
  const status  = document.getElementById('ocr-status');
  const spinner = document.getElementById('ocr-spinner');

  preview.src = URL.createObjectURL(file);
  overlay.classList.remove('hidden');
  spinner.style.display = 'block';
  status.textContent = 'Extracting text…';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const _tok = localStorage.getItem('lexio_token');
    const _hdrs = _tok ? { 'Authorization': 'Bearer ' + _tok } : {};
    const res = await fetch('/ocr', { method: 'POST', headers: _hdrs, body: formData });
    if (!res.ok) {
      if (res.status === 402) {
        const err = await res.json().catch(() => ({}));
        const d = err.detail || {};
        cancelOCR();
        showProModal(d.kind || 'ocr', d.used || 0, d.limit || 3);
        return;
      }
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const { text } = await res.json();

    // Populate textarea and close overlay
    const ta = document.getElementById('input-text');
    ta.value = text;
    ta.dispatchEvent(new Event('input'));
    document.getElementById('char-count').textContent = `${text.length.toLocaleString()} chars`;
    cancelOCR();
  } catch (err) {
    spinner.style.display = 'none';
    status.textContent = `⚠ ${err.message}`;
  }
}

function cancelOCR() {
  const overlay = document.getElementById('ocr-overlay');
  overlay.classList.add('hidden');
  const preview = document.getElementById('ocr-preview');
  if (preview.src) URL.revokeObjectURL(preview.src);
  preview.src = '';
}

/* ── UI language (interface i18n) ───────────────────────────── */
let currentUILang = 'en';

const UI_T = {
  en: { tagline:'AI contextual definition solutions', saved:'Collected', panelLabel:'Text', trySample:'Try a sample', analyzeText:'Analyze text', edit:'← Edit', fetchArticle:'Fetch article', tweaks:'Tweaks', colorTheme:'Color theme', textSize:'Text size', lineHeight:'Line height', theme:'Theme', model:'AI Model', macApp:'Get the Mac app', shortcuts:'Keyboard shortcuts', clickWord:'A word will appear here', placeholderSub:'After analyzing your text, tap any word to see its precise meaning in context.', meaning:'General definition', inContext:'In this context', moreDetail:'More detail', origin:'Origin', whyWord:'Why this word?', respondIn:'Respond in', simpler:'simpler:', copy:'Copy', save:'Collect', link:'Link', share:'Share', say:'Say', uiLang:'Interface language', heroEyebrow:'For readers learning English', heroH1:"Understand languages<br>the way they're <em>really used.</em>", heroSub:"A dictionary gives you five meanings and leaves you guessing. Tap any word and Lexio reads the sentence to give you the one that fits — idioms and phrasal verbs included — explained in your own language.", tryItNow:'Try Lexio free', seeHow:'See how it works', howLabel:'How it works', step1Title:"Paste what you're reading", step1Desc:'A news article, a work email, a page from a novel — drop in any English text (or any of 11 languages).', step2Title:'Lexio reads it', step2Desc:'It reads the whole passage first, so every definition fits the sentence — not a generic entry. Takes about a second.', step3Title:'Tap any word', step3Desc:'See its exact meaning here — in your language — plus how to pronounce it and where it comes from.', trendingTitle:'What people are looking up', trendingEmpty:'No searches recorded yet this month — be the first!', featuresTitle:'Everything an English reader needs', feat1Title:'Contextual definitions', feat1Desc:'Not what the word means in general — what it means right here, in this sentence. Idioms and phrasal verbs a plain dictionary gets wrong.', feat2Title:'In your language', feat2Desc:'Reading English but thinking in another language? Get every definition explained in yours — Spanish, French, Chinese, Arabic, Japanese and more.', feat3Title:'Pronunciation', feat3Desc:'See how every word is pronounced (IPA) and hear it aloud with one tap — so you can say it, not just read it.', feat4Title:'Etymology', feat4Desc:"Understand where words come from. Knowing a word's roots makes it stick — and makes the next related word easier.", feat5Title:'Word bank', feat5Desc:'Save new words with the sentence you found them in — your English vocabulary, growing as you read.', feat6Title:'Read off paper', feat6Desc:'Snap a photo of a printed page — a book, a menu, a sign — and Lexio turns it into text you can tap, word by word.', extEyebrow:'Chrome Extension', extH2:'Look up words without leaving the page.', extP:'Select any word or sentence on any website. Lexio appears instantly with the meaning in context — no copy-paste, no tab switching.', extBtn:'Add to Chrome', extNote:'Free · Works on any page · No account required', deskH2:"Point at any word, anywhere on your Mac.", deskP:"Lexio Glance works outside the browser too — Telegram messages, PDFs, subtitles, code editors. Point your cursor at a word and double-tap: Lexio reads the screen and explains the word right there.", downloadMac:'Download for Mac', openBrowser:'Open in browser', footerTagline:'Built for people reading in English.', heroRotatorLead:'Built for people reading', heroRotatorWord1:'the news in English', heroRotatorWord2:'work emails', heroRotatorWord3:'English novels', heroRotatorWord4:'research papers', heroRotatorWord5:'for IELTS & TOEFL', heroRotatorWord6:'to move abroad', heroRotatorWord7:'to work in English', heroRotatorWord8:'to finally get fluent', heroTrust1:'20 free lookups / month', heroTrust2:'No credit card', heroTrust3:'Explained in your language', privacyPolicy:'Privacy Policy' },
  es: { tagline:'Soluciones de definición contextual con IA', saved:'Coleccionado',panelLabel:'Texto', trySample:'Probar ejemplo', analyzeText:'Analizar texto', edit:'← Editar', fetchArticle:'Obtener artículo', tweaks:'Ajustes', colorTheme:'Color del tema', textSize:'Tamaño del texto', lineHeight:'Interlineado', theme:'Tema', macApp:'Obtener la app para Mac', shortcuts:'Atajos de teclado', clickWord:'Haz clic en cualquier palabra', placeholderSub:'Tras analizar el texto, toca cualquier palabra para ver su significado preciso en contexto.', meaning:'Definición general', inContext:'En este contexto', moreDetail:'Más detalle', origin:'Origen', whyWord:'¿Por qué esta palabra?', respondIn:'Responder en', simpler:'más simple:', copy:'Copiar', save:'Coleccionar', link:'Enlace', share:'Compartir', say:'Decir', uiLang:'Idioma de interfaz', heroEyebrow:"Para lectores que aprenden inglés", heroH1:"Entiende el inglés<br>tal y como <em>se usa de verdad.</em>", heroSub:"Un diccionario te da cinco significados y te deja adivinando. Toca cualquier palabra y Lexio lee la frase para darte el significado que encaja — incluidos modismos y phrasal verbs — explicado en tu idioma.", tryItNow:'Pruébalo ahora', seeHow:'Ver cómo funciona', howLabel:'Cómo funciona', step1Title:"Pega lo que estás leyendo", step1Desc:"Una noticia, un correo de trabajo, una página de una novela — pega cualquier texto en inglés (o en cualquiera de los 11 idiomas).", step2Title:"Lexio lo lee", step2Desc:"Primero lee el pasaje completo, para que cada definición encaje en la frase — nada de entradas genéricas. Tarda un segundo.", step3Title:"Toca cualquier palabra", step3Desc:"Ve su significado exacto aquí — en tu idioma — además de cómo se pronuncia y de dónde viene.", trendingTitle:'Lo que la gente está <em>buscando</em>', trendingEmpty:'No hay búsquedas este mes todavía — ¡sé el primero!', featuresTitle:"Todo lo que necesita un lector de inglés", feat1Title:'Definiciones contextuales', feat1Desc:"No lo que la palabra significa en general, sino lo que significa aquí, en esta frase. Modismos y phrasal verbs que un diccionario normal no acierta.", feat2Title:"En tu idioma", feat2Desc:"¿Lees en inglés pero piensas en español? Recibe cada definición explicada en tu idioma — español, francés, chino, árabe, japonés y más.", feat3Title:"Pronunciación", feat3Desc:"Mira cómo se pronuncia cada palabra (AFI) y escúchala en voz alta con un toque — para que puedas decirla, no solo leerla.", feat4Title:'Etimología', feat4Desc:'Entiende de dónde vienen las palabras. Conocer las raíces hace que las recuerdes — y la próxima palabra relacionada será más fácil.', feat5Title:'Banco de palabras', feat5Desc:"Guarda palabras nuevas con la frase donde las encontraste — tu vocabulario de inglés crece mientras lees.", feat6Title:'Lee del papel', feat6Desc:'Haz una foto de una página impresa —un libro, un menú, un cartel— y Lexio la convierte en texto donde puedes tocar cada palabra.', extEyebrow:'Extensión de Chrome', extH2:'Busca palabras <em>sin</em><br>salir de la página.', extP:'Selecciona cualquier palabra o frase en cualquier sitio web. Lexio aparece al instante con el significado en contexto — sin copiar y pegar, sin cambiar de pestaña.', extBtn:'Añadir a Chrome', extNote:'Gratis · Funciona en cualquier página · Sin cuenta requerida', deskH2:"Señala cualquier palabra, en cualquier parte de tu Mac.", deskP:"La app Lexio Glance funciona también fuera del navegador: mensajes de Telegram, PDFs, subtítulos, editores de código. Apunta el cursor a una palabra y pulsa dos veces: Lexio lee la pantalla y te explica la palabra ahí mismo.", downloadMac:'Descargar para Mac', openBrowser:'Abrir en el navegador', footerTagline:"Hecho para quienes leen en inglés.", heroRotatorLead:'Hecho para quienes leen', heroRotatorWord1:'noticias en inglés', heroRotatorWord2:'correos de trabajo', heroRotatorWord3:'novelas en inglés', heroRotatorWord4:'artículos académicos', heroRotatorWord5:'para el IELTS y el TOEFL', heroRotatorWord6:'para mudarse al extranjero', heroRotatorWord7:'para trabajar en inglés', heroRotatorWord8:'para por fin hablar con fluidez', heroTrust1:'20 búsquedas gratis / mes', heroTrust2:'Sin tarjeta de crédito', heroTrust3:'Explicado en tu idioma', privacyPolicy:'Política de privacidad' },
  fr: { tagline:'Solutions de définition contextuelle par IA', saved:'Collecté',panelLabel:'Texte', trySample:'Essayer un exemple', analyzeText:'Analyser le texte', edit:'← Modifier', fetchArticle:"Récupérer l'article", tweaks:'Réglages', colorTheme:'Thème de couleur', textSize:'Taille du texte', lineHeight:'Interligne', theme:'Thème', macApp:"Obtenir l'app Mac", shortcuts:'Raccourcis clavier', clickWord:"Cliquez sur n'importe quel mot", placeholderSub:"Après analyse, appuyez sur n'importe quel mot pour voir sa signification précise dans le contexte.", meaning:'Définition générale', inContext:'Dans ce contexte', moreDetail:'Plus de détails', origin:'Origine', whyWord:'Pourquoi ce mot ?', respondIn:'Répondre en', simpler:'plus simple :', copy:'Copier', save:'Collecter', link:'Lien', share:'Partager', say:'Lire', uiLang:"Langue de l'interface", heroEyebrow:"Pour les lecteurs qui apprennent l'anglais", heroH1:"Comprenez l'anglais<br>tel qu'il <em>s'utilise vraiment.</em>", heroSub:"Un dictionnaire vous donne cinq sens et vous laisse deviner. Touchez un mot : Lexio lit la phrase et vous donne le sens qui convient — idiomes et phrasal verbs compris — expliqué dans votre langue.", tryItNow:'Essayer maintenant', seeHow:'Voir comment ça marche', howLabel:'Comment ça marche', step1Title:"Collez ce que vous lisez", step1Desc:"Un article, un e-mail professionnel, une page de roman — collez n'importe quel texte en anglais (ou dans l'une des 11 langues).", step2Title:"Lexio le lit", step2Desc:"Il lit d'abord tout le passage, pour que chaque définition colle à la phrase — pas d'entrée générique. Environ une seconde.", step3Title:"Touchez n'importe quel mot", step3Desc:"Voyez son sens exact ici — dans votre langue — plus sa prononciation et son origine.", trendingTitle:'Ce que les gens <em>recherchent</em>', trendingEmpty:'Aucune recherche ce mois-ci encore — soyez le premier !', featuresTitle:"Tout ce qu'il faut pour lire en anglais", feat1Title:'Définitions contextuelles', feat1Desc:"Pas le sens général du mot — son sens ici, dans cette phrase. Idiomes et phrasal verbs qu'un dictionnaire classique rate.", feat2Title:"Dans votre langue", feat2Desc:"Vous lisez en anglais mais pensez dans une autre langue ? Chaque définition vous est expliquée dans la vôtre — français, espagnol, chinois, arabe, japonais et plus.", feat3Title:"Prononciation", feat3Desc:"Voyez la prononciation de chaque mot (API) et écoutez-le à voix haute d'un geste — pour savoir le dire, pas seulement le lire.", feat4Title:'Étymologie', feat4Desc:"Comprenez d'où viennent les mots. Connaître les racines d'un mot le rend mémorable — et le prochain mot associé plus facile.", feat5Title:'Banque de mots', feat5Desc:"Enregistrez les mots nouveaux avec la phrase où vous les avez trouvés — votre vocabulaire anglais grandit au fil de vos lectures.", feat6Title:'Lire le papier', feat6Desc:"Utilisez Lexio depuis n'importe quelle app sur votre Mac — une app de bureau complète ou un panneau flottant dans la barre de menu.", extEyebrow:'Extension Chrome — Bêta', extH2:'Cherchez des mots <em>sans</em><br>quitter la page.', extP:"Sélectionnez n'importe quel mot ou phrase sur n'importe quel site web. Lexio apparaît instantanément avec le sens en contexte — sans copier-coller, sans changer d'onglet.", extBtn:'Ajouter à Chrome', extNote:'Gratuit · Fonctionne sur toutes les pages · Sans compte requis', deskH2:"Pointez n'importe quel mot, partout sur votre Mac.", deskP:"L'app Lexio Glance fonctionne aussi hors du navigateur : messages Telegram, PDF, sous-titres, éditeurs de code. Pointez un mot du curseur et tapez deux fois : Lexio lit l'écran et explique le mot sur place.", downloadMac:'Télécharger pour Mac', openBrowser:'Ouvrir dans le navigateur', footerTagline:"Conçu pour ceux qui lisent en anglais.", heroRotatorLead:'Conçu pour ceux qui lisent', heroRotatorWord1:'les actualités en anglais', heroRotatorWord2:'des e-mails professionnels', heroRotatorWord3:'des romans en anglais', heroRotatorWord4:'des articles de recherche', heroRotatorWord5:"pour l'IELTS et le TOEFL", heroRotatorWord6:"pour s'expatrier", heroRotatorWord7:'pour travailler en anglais', heroRotatorWord8:'pour enfin devenir bilingues', heroTrust1:'20 recherches gratuites / mois', heroTrust2:'Sans carte bancaire', heroTrust3:'Expliqué dans votre langue', privacyPolicy:'Politique de confidentialité' },
  de: { tagline:'KI-gestützte kontextuelle Definitionslösungen', saved:'Gesammelt',panelLabel:'Text', trySample:'Beispiel versuchen', analyzeText:'Text analysieren', edit:'← Bearbeiten', fetchArticle:'Artikel abrufen', tweaks:'Einstellungen', colorTheme:'Farbthema', textSize:'Schriftgröße', lineHeight:'Zeilenhöhe', theme:'Thema', macApp:'Mac-App herunterladen', shortcuts:'Tastenkürzel', clickWord:'Klicke auf ein beliebiges Wort', placeholderSub:'Klicke nach der Analyse auf ein Wort, um seine genaue Bedeutung im Kontext zu sehen.', meaning:'Allgemeine Definition', inContext:'In diesem Kontext', moreDetail:'Mehr Details', origin:'Herkunft', whyWord:'Warum dieses Wort?', respondIn:'Antworten auf', simpler:'einfacher:', copy:'Kopieren', save:'Sammeln', link:'Link', share:'Teilen', say:'Vorlesen', uiLang:'Oberflächensprache', heroEyebrow:"Für Leser, die Englisch lernen", heroH1:"Verstehe Englisch,<br>wie es <em>wirklich benutzt wird.</em>", heroSub:"Ein Wörterbuch gibt dir fünf Bedeutungen und lässt dich raten. Tippe auf ein Wort — Lexio liest den Satz und liefert die eine Bedeutung, die passt, samt Idiomen und Phrasal Verbs — erklärt in deiner Sprache.", tryItNow:'Jetzt ausprobieren', seeHow:'Wie es funktioniert', howLabel:'So funktioniert es', step1Title:"Füge ein, was du liest", step1Desc:"Ein Nachrichtenartikel, eine Arbeits-Mail, eine Romanseite — füge beliebigen englischen Text ein (oder eine von 11 Sprachen).", step2Title:"Lexio liest ihn", step2Desc:"Es liest zuerst die ganze Passage, damit jede Definition zum Satz passt — kein generischer Eintrag. Dauert etwa eine Sekunde.", step3Title:"Tippe auf ein Wort", step3Desc:"Sieh hier seine genaue Bedeutung — in deiner Sprache — plus Aussprache und Herkunft.", trendingTitle:'Was die Leute gerade <em>nachschlagen</em>', trendingEmpty:'Noch keine Suchen diesen Monat — seien Sie der Erste!', featuresTitle:"Alles, was Englisch-Leser brauchen", feat1Title:'Kontextuelle Definitionen', feat1Desc:"Nicht, was das Wort allgemein bedeutet — sondern was es genau hier, in diesem Satz bedeutet. Mit Idiomen und Phrasal Verbs, an denen normale Wörterbücher scheitern.", feat2Title:"In deiner Sprache", feat2Desc:"Du liest Englisch, denkst aber in einer anderen Sprache? Jede Definition wird in deiner erklärt — Deutsch, Spanisch, Chinesisch, Arabisch, Japanisch und mehr.", feat3Title:"Aussprache", feat3Desc:"Sieh zu jedem Wort die Lautschrift (IPA) und höre es mit einem Tipp laut — damit du es sagen kannst, nicht nur lesen.", feat4Title:'Etymologie', feat4Desc:'Verstehen Sie, wo Wörter herkommen. Die Wurzeln eines Wortes zu kennen, lässt es haften — und das nächste verwandte Wort wird leichter.', feat5Title:'Wortbank', feat5Desc:"Speichere neue Wörter mit dem Satz, in dem du sie gefunden hast — dein englischer Wortschatz wächst beim Lesen.", feat6Title:'Vom Papier lesen', feat6Desc:'Fotografiere eine gedruckte Seite – ein Buch, eine Speisekarte, ein Schild – und Lexio macht daraus antippbaren Text, Wort für Wort.', extEyebrow:'Chrome-Erweiterung', extH2:'Wörter nachschlagen <em>ohne</em><br>die Seite zu verlassen.', extP:'Wählen Sie ein beliebiges Wort oder einen Satz auf einer beliebigen Website aus. Lexio erscheint sofort mit der Bedeutung im Kontext — kein Kopieren und Einfügen, kein Tabwechsel.', extBtn:'Zu Chrome hinzufügen', extNote:'Kostenlos · Funktioniert auf jeder Seite · Kein Konto erforderlich', deskH2:"Zeige auf ein Wort — überall auf deinem Mac.", deskP:"Die Lexio-Glance-App funktioniert auch außerhalb des Browsers: Telegram-Nachrichten, PDFs, Untertitel, Code-Editoren. Zeige mit dem Cursor auf ein Wort und tippe doppelt: Lexio liest den Bildschirm und erklärt das Wort direkt dort.", downloadMac:'Für Mac herunterladen', openBrowser:'Im Browser öffnen', footerTagline:"Gebaut für alle, die auf Englisch lesen.", heroRotatorLead:'Gebaut für alle, die lesen', heroRotatorWord1:'Nachrichten auf Englisch', heroRotatorWord2:'geschäftliche E-Mails', heroRotatorWord3:'englische Romane', heroRotatorWord4:'wissenschaftliche Arbeiten', heroRotatorWord5:'für IELTS & TOEFL', heroRotatorWord6:'um ins Ausland zu ziehen', heroRotatorWord7:'um auf Englisch zu arbeiten', heroRotatorWord8:'um endlich fließend zu werden', heroTrust1:'20 kostenlose Abfragen / Monat', heroTrust2:'Keine Kreditkarte nötig', heroTrust3:'Erklärt in deiner Sprache', privacyPolicy:'Datenschutzrichtlinie' },
  it: { tagline:'Soluzioni di definizione contestuale con IA', saved:'Raccolto',panelLabel:'Testo', trySample:'Prova un esempio', analyzeText:'Analizza testo', edit:'← Modifica', fetchArticle:'Recupera articolo', tweaks:'Impostazioni', colorTheme:'Tema colore', textSize:'Dimensione testo', lineHeight:'Interlinea', theme:'Tema', macApp:"Ottieni l'app per Mac", shortcuts:'Scorciatoie da tastiera', clickWord:'Clicca su qualsiasi parola', placeholderSub:'Dopo aver analizzato il testo, tocca qualsiasi parola per vederne il significato preciso nel contesto.', meaning:'Definizione generale', inContext:'In questo contesto', moreDetail:'Più dettagli', origin:'Origine', whyWord:'Perché questa parola?', respondIn:'Rispondi in', simpler:'più semplice:', copy:'Copia', save:'Raccogli', link:'Link', share:'Condividi', say:'Pronuncia', uiLang:'Lingua interfaccia', heroEyebrow:"Per chi legge e impara l'inglese", heroH1:"Capisci l'inglese<br>come <em>si usa davvero.</em>", heroSub:"Un dizionario ti dà cinque significati e ti lascia indovinare. Tocca una parola: Lexio legge la frase e ti dà il significato giusto — modi di dire e phrasal verbs compresi — spiegato nella tua lingua.", tryItNow:'Provalo ora', seeHow:'Scopri come funziona', howLabel:'Come funziona', step1Title:"Incolla quello che stai leggendo", step1Desc:"Un articolo, un'e-mail di lavoro, una pagina di romanzo — incolla qualsiasi testo in inglese (o in una delle 11 lingue).", step2Title:"Lexio lo legge", step2Desc:"Prima legge tutto il passaggio, così ogni definizione si adatta alla frase — niente voci generiche. Ci vuole circa un secondo.", step3Title:"Tocca qualsiasi parola", step3Desc:"Vedi qui il suo significato esatto — nella tua lingua — più pronuncia e origine.", trendingTitle:'Cosa stanno <em>cercando</em> le persone', trendingEmpty:'Nessuna ricerca questo mese ancora — sii il primo!', featuresTitle:"Tutto ciò che serve a chi legge in inglese", feat1Title:'Definizioni contestuali', feat1Desc:"Non cosa significa la parola in generale — cosa significa qui, in questa frase. Con i modi di dire e i phrasal verbs che un dizionario normale sbaglia.", feat2Title:"Nella tua lingua", feat2Desc:"Leggi in inglese ma pensi in un'altra lingua? Ogni definizione è spiegata nella tua — italiano, spagnolo, cinese, arabo, giapponese e altre.", feat3Title:"Pronuncia", feat3Desc:"Vedi la trascrizione fonetica (IPA) di ogni parola e ascoltala con un tocco — per saperla dire, non solo leggere.", feat4Title:'Etimologia', feat4Desc:'Capisci da dove vengono le parole. Conoscere le radici di una parola la rende memorabile — e la prossima parola correlata sarà più facile.', feat5Title:'Banca delle parole', feat5Desc:"Salva le parole nuove con la frase in cui le hai trovate — il tuo vocabolario inglese cresce mentre leggi.", feat6Title:'Leggi dalla carta', feat6Desc:"Usa Lexio da qualsiasi app sul tuo Mac — un'app desktop completa o un pannello flottante nella barra dei menu.", extEyebrow:'Estensione Chrome', extH2:'Cerca parole <em>senza</em><br>lasciare la pagina.', extP:'Seleziona qualsiasi parola o frase su qualsiasi sito web. Lexio appare istantaneamente con il significato nel contesto — senza copia-incolla, senza cambiare scheda.', extBtn:'Aggiungi a Chrome', extNote:'Gratuito · Funziona su qualsiasi pagina · Nessun account richiesto', deskH2:"Punta una parola, ovunque sul tuo Mac.", deskP:"L'app Lexio Glance funziona anche fuori dal browser: messaggi di Telegram, PDF, sottotitoli, editor di codice. Punta il cursore su una parola e tocca due volte: Lexio legge lo schermo e spiega la parola lì.", downloadMac:'Scarica per Mac', openBrowser:'Apri nel browser', footerTagline:"Fatto per chi legge in inglese.", heroRotatorLead:'Creato per chi legge', heroRotatorWord1:'notizie in inglese', heroRotatorWord2:'e-mail di lavoro', heroRotatorWord3:'romanzi in inglese', heroRotatorWord4:'articoli di ricerca', heroRotatorWord5:'per IELTS e TOEFL', heroRotatorWord6:"per trasferirsi all'estero", heroRotatorWord7:'per lavorare in inglese', heroRotatorWord8:'per diventare finalmente fluente', heroTrust1:'20 ricerche gratuite / mese', heroTrust2:'Nessuna carta di credito', heroTrust3:'Spiegato nella tua lingua', privacyPolicy:'Informativa sulla privacy' },
  pt: { tagline:'Soluções de definição contextual com IA', saved:'Coletado',panelLabel:'Texto', trySample:'Tentar exemplo', analyzeText:'Analisar texto', edit:'← Editar', fetchArticle:'Buscar artigo', tweaks:'Ajustes', colorTheme:'Tema de cor', textSize:'Tamanho do texto', lineHeight:'Altura da linha', theme:'Tema', macApp:'Obter app para Mac', shortcuts:'Atalhos de teclado', clickWord:'Clique em qualquer palavra', placeholderSub:'Após analisar o texto, toque em qualquer palavra para ver seu significado preciso no contexto.', meaning:'Definição geral', inContext:'Neste contexto', moreDetail:'Mais detalhes', origin:'Origem', whyWord:'Por que esta palavra?', respondIn:'Responder em', simpler:'mais simples:', copy:'Copiar', save:'Coletar', link:'Link', share:'Compartilhar', say:'Falar', uiLang:'Idioma da interface', heroEyebrow:"Para leitores que aprendem inglês", heroH1:"Entenda o inglês<br>como ele é <em>usado de verdade.</em>", heroSub:"Um dicionário te dá cinco significados e deixa você adivinhando. Toque em qualquer palavra: o Lexio lê a frase e te dá o significado que encaixa — incluindo expressões e phrasal verbs — explicado no seu idioma.", tryItNow:'Experimente agora', seeHow:'Veja como funciona', howLabel:'Como funciona', step1Title:"Cole o que você está lendo", step1Desc:"Uma notícia, um e-mail de trabalho, uma página de romance — cole qualquer texto em inglês (ou em qualquer um dos 11 idiomas).", step2Title:"O Lexio lê", step2Desc:"Ele lê o trecho inteiro primeiro, para cada definição encaixar na frase — nada de verbete genérico. Leva cerca de um segundo.", step3Title:"Toque em qualquer palavra", step3Desc:"Veja o significado exato aqui — no seu idioma — além da pronúncia e da origem.", trendingTitle:'O que as pessoas estão <em>pesquisando</em>', trendingEmpty:'Nenhuma pesquisa registrada este mês ainda — seja o primeiro!', featuresTitle:"Tudo o que um leitor de inglês precisa", feat1Title:'Definições contextuais', feat1Desc:"Não o que a palavra significa em geral — o que ela significa aqui, nesta frase. Expressões e phrasal verbs que um dicionário comum erra.", feat2Title:"No seu idioma", feat2Desc:"Lê em inglês mas pensa em outro idioma? Receba cada definição explicada no seu — português, espanhol, chinês, árabe, japonês e mais.", feat3Title:"Pronúncia", feat3Desc:"Veja como cada palavra é pronunciada (AFI) e ouça em voz alta com um toque — para saber dizer, não só ler.", feat4Title:'Etimologia', feat4Desc:'Entenda de onde vêm as palavras. Conhecer as raízes de uma palavra faz ela fixar — e a próxima palavra relacionada fica mais fácil.', feat5Title:'Banco de palavras', feat5Desc:"Salve palavras novas com a frase em que você as encontrou — seu vocabulário de inglês cresce enquanto você lê.", feat6Title:'Leia do papel', feat6Desc:'Tire uma foto de uma página impressa — um livro, um menu, uma placa — e o Lexio a transforma em texto onde você toca cada palavra.', extEyebrow:'Extensão do Chrome', extH2:'Pesquise palavras <em>sem</em><br>sair da página.', extP:'Selecione qualquer palavra ou frase em qualquer site. O Lexio aparece instantaneamente com o significado em contexto — sem copiar e colar, sem trocar de aba.', extBtn:'Adicionar ao Chrome', extNote:'Gratuito · Funciona em qualquer página · Sem conta necessária', deskH2:"Aponte para qualquer palavra, em qualquer lugar do seu Mac.", deskP:"O app Lexio Glance também funciona fora do navegador: mensagens do Telegram, PDFs, legendas, editores de código. Aponte o cursor para uma palavra e toque duas vezes: o Lexio lê a tela e explica a palavra ali mesmo.", downloadMac:'Baixar para Mac', openBrowser:'Abrir no navegador', footerTagline:"Feito para quem lê em inglês.", heroRotatorLead:'Feito para quem lê', heroRotatorWord1:'notícias em inglês', heroRotatorWord2:'e-mails de trabalho', heroRotatorWord3:'romances em inglês', heroRotatorWord4:'artigos acadêmicos', heroRotatorWord5:'para o IELTS e o TOEFL', heroRotatorWord6:'para se mudar para o exterior', heroRotatorWord7:'para trabalhar em inglês', heroRotatorWord8:'para finalmente ficar fluente', heroTrust1:'20 pesquisas grátis / mês', heroTrust2:'Sem cartão de crédito', heroTrust3:'Explicado no seu idioma', privacyPolicy:'Política de privacidade' },
  nl: { tagline:'AI contextuele definitie-oplossingen', saved:'Verzameld',panelLabel:'Tekst', trySample:'Probeer een voorbeeld', analyzeText:'Tekst analyseren', edit:'← Bewerken', fetchArticle:'Artikel ophalen', tweaks:'Instellingen', colorTheme:'Kleurthema', textSize:'Tekstgrootte', lineHeight:'Regelafstand', theme:'Thema', macApp:'Mac-app downloaden', shortcuts:'Sneltoetsen', clickWord:'Klik op een woord', placeholderSub:'Klik na het analyseren op een woord om de precieze betekenis in context te zien.', meaning:'Algemene definitie', inContext:'In deze context', moreDetail:'Meer details', origin:'Herkomst', whyWord:'Waarom dit woord?', respondIn:'Antwoord in', simpler:'eenvoudiger:', copy:'Kopiëren', save:'Verzamelen', link:'Link', share:'Delen', say:'Uitspreken', uiLang:'Interfacetaal', heroEyebrow:"Voor lezers die Engels leren", heroH1:"Begrijp Engels<br>zoals het <em>écht wordt gebruikt.</em>", heroSub:"Een woordenboek geeft je vijf betekenissen en laat je gissen. Tik op een woord — Lexio leest de zin en geeft je de betekenis die past, inclusief idiomen en phrasal verbs — uitgelegd in jouw taal.", tryItNow:'Probeer het nu', seeHow:'Bekijk hoe het werkt', howLabel:'Hoe het werkt', step1Title:"Plak wat je aan het lezen bent", step1Desc:"Een nieuwsartikel, een werkmail, een pagina uit een roman — plak elke Engelse tekst (of een van de 11 talen).", step2Title:"Lexio leest het", step2Desc:"Het leest eerst de hele passage, zodat elke definitie bij de zin past — geen generiek woordenboeklemma. Duurt ongeveer een seconde.", step3Title:"Tik op een woord", step3Desc:"Zie hier de exacte betekenis — in jouw taal — plus de uitspraak en de herkomst.", trendingTitle:'Wat mensen <em>opzoeken</em>', trendingEmpty:'Nog geen zoekopdrachten deze maand — wees de eerste!', featuresTitle:"Alles wat een Engelse lezer nodig heeft", feat1Title:'Contextuele definities', feat1Desc:"Niet wat het woord in het algemeen betekent — wat het hier betekent, in deze zin. Inclusief idiomen en phrasal verbs waar een gewoon woordenboek de mist mee ingaat.", feat2Title:"In jouw taal", feat2Desc:"Lees je Engels maar denk je in een andere taal? Elke definitie wordt uitgelegd in de jouwe — Nederlands, Spaans, Chinees, Arabisch, Japans en meer.", feat3Title:"Uitspraak", feat3Desc:"Zie van elk woord de fonetische transcriptie (IPA) en hoor het hardop met één tik — zodat je het kunt zéggen, niet alleen lezen.", feat4Title:'Etymologie', feat4Desc:'Begrijp waar woorden vandaan komen. De wortels van een woord kennen maakt het memorabel — en het volgende verwante woord gemakkelijker.', feat5Title:'Woordenbank', feat5Desc:"Bewaar nieuwe woorden mét de zin waarin je ze vond — je Engelse woordenschat groeit terwijl je leest.", feat6Title:'Lees van papier', feat6Desc:'Maak een foto van een gedrukte pagina — een boek, een menu, een bord — en Lexio maakt er aantikbare tekst van, woord voor woord.', extEyebrow:'Chrome-extensie', extH2:'Zoek woorden op <em>zonder</em><br>de pagina te verlaten.', extP:'Selecteer een woord of zin op een website. Lexio verschijnt onmiddellijk met de betekenis in context — geen kopiëren en plakken, geen tabblad wisselen.', extBtn:'Toevoegen aan Chrome', extNote:'Gratis · Werkt op elke pagina · Geen account vereist', deskH2:"Wijs een woord aan, waar dan ook op je Mac.", deskP:"De Lexio Glance-app werkt ook buiten de browser: Telegram-berichten, pdf's, ondertitels, code-editors. Wijs met je cursor naar een woord en dubbeltik: Lexio leest het scherm en legt het woord meteen uit.", downloadMac:'Download voor Mac', openBrowser:'Openen in browser', footerTagline:"Gemaakt voor mensen die in het Engels lezen.", heroRotatorLead:'Gemaakt voor mensen die lezen', heroRotatorWord1:'het nieuws in het Engels', heroRotatorWord2:'werkmails', heroRotatorWord3:'Engelse romans', heroRotatorWord4:'onderzoeksartikelen', heroRotatorWord5:'voor IELTS & TOEFL', heroRotatorWord6:'om te emigreren', heroRotatorWord7:'om in het Engels te werken', heroRotatorWord8:'om eindelijk vloeiend te worden', heroTrust1:'20 gratis opzoekingen / maand', heroTrust2:'Geen creditcard nodig', heroTrust3:'Uitgelegd in jouw taal', privacyPolicy:'Privacybeleid' },
  ru: { tagline:'Решения контекстных определений с ИИ', saved:'Собрано',panelLabel:'Текст', trySample:'Попробовать пример', analyzeText:'Анализировать', edit:'← Изменить', fetchArticle:'Загрузить статью', tweaks:'Настройки', colorTheme:'Цветовая тема', textSize:'Размер текста', lineHeight:'Межстрочный интервал', theme:'Тема', macApp:'Скачать для Mac', shortcuts:'Горячие клавиши', clickWord:'Нажмите на любое слово', placeholderSub:'После анализа нажмите на любое слово, чтобы увидеть его точное значение в контексте.', meaning:'Общее определение', inContext:'В этом контексте', moreDetail:'Подробнее', origin:'Происхождение', whyWord:'Почему это слово?', respondIn:'Ответить на', simpler:'проще:', copy:'Копировать', save:'Собрать', link:'Ссылка', share:'Поделиться', say:'Произнести', uiLang:'Язык интерфейса', heroEyebrow:"Для тех, кто читает и учит английский", heroH1:"Понимайте английский так,<br>как на нём <em>действительно говорят.</em>", heroSub:"Словарь выдаёт пять значений и оставляет вас гадать. Нажмите на любое слово — Lexio прочитает предложение и даст то самое значение, которое подходит здесь, включая идиомы и фразовые глаголы, — с объяснением на вашем языке.", tryItNow:'Попробовать сейчас', seeHow:'Посмотреть, как это работает', howLabel:'Как это работает', step1Title:"Вставьте то, что читаете", step1Desc:"Новость, рабочее письмо, страница романа — вставьте любой английский текст (или текст на одном из 11 языков).", step2Title:"Lexio читает текст", step2Desc:"Сначала он читает весь отрывок целиком, поэтому каждое определение подходит именно к этому предложению, а не взято из словаря наугад. Около секунды.", step3Title:"Нажмите на любое слово", step3Desc:"Точное значение здесь — на вашем языке — плюс произношение и происхождение слова.", trendingTitle:'Что люди <em>ищут</em>', trendingEmpty:'В этом месяце поисков ещё нет — будьте первым!', featuresTitle:"Всё, что нужно читающему по-английски", feat1Title:'Контекстные определения', feat1Desc:"Не что слово значит вообще, а что оно значит именно здесь, в этом предложении. Включая идиомы и фразовые глаголы, на которых обычный словарь ошибается.", feat2Title:"На вашем языке", feat2Desc:"Читаете по-английски, а думаете на другом языке? Каждое определение объясняется на вашем — русском, испанском, китайском, арабском, японском и других.", feat3Title:"Произношение", feat3Desc:"Смотрите транскрипцию (МФА) каждого слова и слушайте его в одно касание — чтобы уметь сказать, а не только прочитать.", feat4Title:'Этимология', feat4Desc:'Понимайте, откуда берутся слова. Знание корней слова помогает запомнить — и следующее родственное слово запоминается легче.', feat5Title:'Словарный банк', feat5Desc:"Сохраняйте новые слова вместе с предложением, где вы их встретили, — ваш английский словарный запас растёт по мере чтения.", feat6Title:'Читай с бумаги', feat6Desc:'Сфотографируйте печатную страницу — книгу, меню, вывеску — и Lexio превратит её в текст, где можно нажать на любое слово.', extEyebrow:'Расширение Chrome — Бета', extH2:'Ищите слова <em>не</em><br>покидая страницы.', extP:'Выделите любое слово или предложение на любом сайте. Lexio мгновенно появляется со значением в контексте — без копирования и вставки, без переключения вкладок.', extBtn:'Добавить в Chrome', extNote:'Бесплатно · Работает на любой странице · Без регистрации', deskH2:"Наведите курсор на любое слово — где угодно на Mac.", deskP:"Приложение Lexio Glance работает и вне браузера: сообщения в Telegram, PDF, субтитры, редакторы кода. Наведите курсор на слово и дважды нажмите клавишу — Lexio прочитает экран и объяснит слово прямо там.", downloadMac:'Скачать для Mac', openBrowser:'Открыть в браузере', footerTagline:"Для тех, кто читает по-английски.", heroRotatorLead:'Создано для тех, кто читает', heroRotatorWord1:'новости на английском', heroRotatorWord2:'рабочую переписку', heroRotatorWord3:'романы на английском', heroRotatorWord4:'научные статьи', heroRotatorWord5:'для IELTS и TOEFL', heroRotatorWord6:'чтобы переехать за границу', heroRotatorWord7:'чтобы работать на английском', heroRotatorWord8:'чтобы наконец заговорить свободно', heroTrust1:'20 бесплатных запросов / месяц', heroTrust2:'Без банковской карты', heroTrust3:'Объяснение на вашем языке', privacyPolicy:'Политика конфиденциальности' },
  zh: { tagline:'AI 语境释义解决方案', saved:'已收藏',panelLabel:'文本', trySample:'试用示例', analyzeText:'分析文本', edit:'← 编辑', fetchArticle:'获取文章', tweaks:'设置', colorTheme:'颜色主题', textSize:'文字大小', lineHeight:'行高', theme:'主题', macApp:'获取Mac应用', shortcuts:'键盘快捷键', clickWord:'点击任意单词', placeholderSub:'分析文本后，点击任意单词即可查看其在上下文中的精确含义。', meaning:'一般定义', inContext:'在此上下文中', moreDetail:'更多详情', origin:'词源', whyWord:'为什么选择这个词？', respondIn:'回应语言', simpler:'更简单：', copy:'复制', save:'收藏', link:'链接', share:'分享', say:'朗读', uiLang:'界面语言', heroEyebrow:"为正在学英语的读者打造", heroH1:"理解英语<br><em>真实的用法。</em>", heroSub:"词典给你五个释义，让你自己猜。点按任意单词，Lexio 会通读整句，给出真正贴合语境的那一个释义——包括习语和短语动词——并用你的母语解释。", tryItNow:'立即试用', seeHow:'查看使用方法', howLabel:'使用方法', step1Title:"粘贴你正在读的内容", step1Desc:"新闻、工作邮件、小说页面——粘贴任何英文文本（或 11 种语言中的任意一种）。", step2Title:"Lexio 通读全文", step2Desc:"它会先读完整段文字，让每个释义都贴合句子，而不是笼统的词典条目。大约一秒钟。", step3Title:"点按任意单词", step3Desc:"就地查看它的准确含义——用你的语言——还有发音和词源。", trendingTitle:'人们正在<em>查询</em>的词', trendingEmpty:'本月尚无搜索记录——成为第一个！', featuresTitle:"英语读者需要的一切", feat1Title:'语境定义', feat1Desc:"不是这个词的泛泛之义，而是它在这句话里的确切含义。包括普通词典会弄错的习语和短语动词。", feat2Title:"用你的语言", feat2Desc:"读英语却用母语思考？每条释义都用你的语言解释——中文、西班牙语、法语、阿拉伯语、日语等。", feat3Title:"发音", feat3Desc:"查看每个单词的音标（IPA），一键听发音——不只会读，还要会说。", feat4Title:'词源', feat4Desc:'了解词语的起源。知道词根有助于记忆——下一个相关词也会更容易学习。', feat5Title:'词汇库', feat5Desc:"把生词连同出现它的句子一起保存——你的英语词汇量随阅读增长。", feat6Title:'拍照取词', feat6Desc:'拍下纸上的内容——书页、菜单、标牌——Lexio 会把它变成可点按的文字，逐词查询。', extEyebrow:'Chrome扩展——测试版', extH2:'查词<em>无需</em><br>离开页面。', extP:'在任何网站上选择任意词语或句子。Lexio即时出现，显示语境中的含义——无需复制粘贴，无需切换标签页。', extBtn:'添加到Chrome', extNote:'免费 · 适用于任何页面 · 无需账户', deskH2:"指向任意单词，Mac 上随处可用。", deskP:"Lexio Glance 应用同样适用于浏览器之外：Telegram 消息、PDF、字幕、代码编辑器。把光标指向单词，双击触发键，Lexio 读取屏幕并当场解释这个词。", downloadMac:'下载Mac版', openBrowser:'在浏览器中打开', footerTagline:"为用英语阅读的人打造。", heroRotatorLead:'专为这样的你打造：', heroRotatorWord1:'读英文新闻', heroRotatorWord2:'读工作邮件', heroRotatorWord3:'读英文小说', heroRotatorWord4:'读学术论文', heroRotatorWord5:'备考雅思、托福', heroRotatorWord6:'准备移居海外', heroRotatorWord7:'用英语工作', heroRotatorWord8:'想终于说一口流利英语', heroTrust1:'每月20次免费查词', heroTrust2:'无需信用卡', heroTrust3:'用你的母语解释', privacyPolicy:'隐私政策' },
  ja: { tagline:'AIによる文脈的定義ソリューション', saved:'収集済み',panelLabel:'テキスト', trySample:'サンプルを試す', analyzeText:'テキストを分析', edit:'← 編集', fetchArticle:'記事を取得', tweaks:'設定', colorTheme:'カラーテーマ', textSize:'文字サイズ', lineHeight:'行の高さ', theme:'テーマ', macApp:'Macアプリを入手', shortcuts:'キーボードショートカット', clickWord:'任意の単語をクリック', placeholderSub:'テキストを分析した後、任意の単語をクリックするとその正確な意味が表示されます。', meaning:'一般的な定義', inContext:'この文脈では', moreDetail:'詳細を表示', origin:'語源', whyWord:'なぜこの言葉？', respondIn:'回答言語', simpler:'より簡単：', copy:'コピー', save:'収集', link:'リンク', share:'シェア', say:'発音', uiLang:'インターフェース言語', heroEyebrow:"英語を学ぶ読み手のために", heroH1:"英語を<br><em>実際の使われ方</em>で理解する。", heroSub:"辞書は5つの意味を並べて、どれかは自分で当てるしかありません。単語をタップすると、Lexioが文全体を読み、この文脈に合うただ一つの意味を——イディオムや句動詞も含めて——あなたの母語で説明します。", tryItNow:'今すぐ試す', seeHow:'使い方を見る', howLabel:'使い方', step1Title:"読んでいる文章を貼り付ける", step1Desc:"ニュース記事、仕事のメール、小説の1ページ——英語のテキストなら何でも（11言語に対応）。", step2Title:"Lexioが読み込む", step2Desc:"まず文章全体を読むので、どの定義も文にぴったり合います。一般的な辞書の項目ではありません。約1秒。", step3Title:"単語をタップ", step3Desc:"この文での正確な意味を——あなたの言語で——発音や語源と一緒に確認できます。", trendingTitle:'人々が<em>調べている</em>こと', trendingEmpty:'今月の検索記録はまだありません — 最初の一人になりましょう！', featuresTitle:"英語を読む人に必要なすべて", feat1Title:'文脈的定義', feat1Desc:"単語の一般的な意味ではなく、この文でのこの意味。普通の辞書が間違えるイディオムや句動詞も。", feat2Title:"あなたの言語で", feat2Desc:"英語を読みながら、考えるのは母語？すべての定義をあなたの言語で——日本語、スペイン語、中国語、アラビア語など。", feat3Title:"発音", feat3Desc:"各単語の発音記号（IPA）を表示し、ワンタップで読み上げ。読めるだけでなく、言えるように。", feat4Title:'語源', feat4Desc:'単語の起源を理解することで、記憶が定着します — 次の関連単語も覚えやすくなります。', feat5Title:'単語帳', feat5Desc:"新しい単語を、出会った文ごと保存。読むほどに英語の語彙が育ちます。", feat6Title:'紙から読む', feat6Desc:'印刷されたページ（本・メニュー・看板）を撮影すると、Lexio がタップできるテキストに変換します。', extEyebrow:'Chrome拡張機能 — ベータ', extH2:'ページを離れ<em>ずに</em><br>単語を調べる。', extP:'どのウェブサイトでも任意の単語や文を選択するだけ。Lexioが即座に文脈の意味を表示します — コピー&ペーストもタブ切り替えも不要です。', extBtn:'Chromeに追加', extNote:'無料 · どのページでも使用可能 · アカウント不要', deskH2:"Macのどこでも、単語を指すだけ。", deskP:"Lexio Glanceアプリはブラウザの外でも使えます。Telegramのメッセージ、PDF、字幕、コードエディタ——カーソルを単語に合わせてダブルタップすると、Lexioが画面を読み取り、その場で意味を説明します。", downloadMac:'Mac版をダウンロード', openBrowser:'ブラウザで開く', footerTagline:"英語で読む人のために。", heroRotatorLead:'こんな読者のために：', heroRotatorWord1:'英語のニュースを読む', heroRotatorWord2:'仕事のメールを読む', heroRotatorWord3:'英語の小説を読む', heroRotatorWord4:'論文を読む', heroRotatorWord5:'IELTS・TOEFL対策をしている', heroRotatorWord6:'海外移住を考えている', heroRotatorWord7:'英語で働いている', heroRotatorWord8:'ついに英語を流暢に話したい', heroTrust1:'月20回まで無料', heroTrust2:'クレジットカード不要', heroTrust3:'あなたの言語で解説', privacyPolicy:'プライバシーポリシー' },
  ko: { tagline:'AI 맥락적 정의 솔루션', saved:'수집됨',panelLabel:'텍스트', trySample:'샘플 시도', analyzeText:'텍스트 분석', edit:'← 편집', fetchArticle:'기사 가져오기', tweaks:'설정', colorTheme:'색상 테마', textSize:'글자 크기', lineHeight:'줄 높이', theme:'테마', macApp:'Mac 앱 다운로드', shortcuts:'키보드 단축키', clickWord:'아무 단어나 클릭하세요', placeholderSub:'텍스트를 분석한 후 아무 단어나 클릭하면 문맥에서의 정확한 의미를 볼 수 있습니다.', meaning:'일반 정의', inContext:'이 맥락에서', moreDetail:'더 보기', origin:'어원', whyWord:'왜 이 단어인가?', respondIn:'응답 언어', simpler:'더 간단한:', copy:'복사', save:'수집', link:'링크', share:'공유', say:'발음', uiLang:'인터페이스 언어', heroEyebrow:"영어를 배우는 독자를 위해", heroH1:"영어를<br><em>실제 쓰임 그대로</em> 이해하세요.", heroSub:"사전은 뜻을 다섯 개 늘어놓고 알아서 고르게 합니다. 단어를 탭하면 Lexio가 문장 전체를 읽고 이 문맥에 맞는 단 하나의 뜻을 — 관용구와 구동사까지 — 당신의 언어로 설명해 줍니다.", tryItNow:'지금 시도하기', seeHow:'사용 방법 보기', howLabel:'사용 방법', step1Title:"읽고 있는 글을 붙여넣기", step1Desc:"뉴스 기사, 업무 이메일, 소설 한 페이지 — 어떤 영어 텍스트든 붙여넣으세요(11개 언어 지원).", step2Title:"Lexio가 읽습니다", step2Desc:"먼저 글 전체를 읽기 때문에 모든 정의가 문장에 딱 맞습니다. 일반 사전 항목이 아닙니다. 약 1초.", step3Title:"아무 단어나 탭", step3Desc:"이 문장에서의 정확한 뜻을 — 당신의 언어로 — 발음과 어원까지 함께 확인하세요.", trendingTitle:'사람들이 <em>찾아보는</em> 것들', trendingEmpty:'이번 달 아직 검색 기록이 없습니다 — 첫 번째가 되어보세요!', featuresTitle:"영어 독자에게 필요한 모든 것", feat1Title:'문맥적 정의', feat1Desc:"단어의 일반적인 뜻이 아니라, 바로 여기 이 문장에서의 뜻. 일반 사전이 틀리는 관용구와 구동사까지.", feat2Title:"당신의 언어로", feat2Desc:"영어로 읽지만 생각은 모국어로 하나요? 모든 정의를 당신의 언어로 — 한국어, 스페인어, 중국어, 아랍어, 일본어 등.", feat3Title:"발음", feat3Desc:"모든 단어의 발음 기호(IPA)를 보고 한 번의 탭으로 들어보세요 — 읽는 데서 끝나지 않고 말할 수 있도록.", feat4Title:'어원', feat4Desc:'단어가 어디서 왔는지 이해하세요. 단어의 어근을 알면 기억하기 쉽고 — 다음 관련 단어도 더 쉽게 배울 수 있습니다.', feat5Title:'단어 은행', feat5Desc:"새 단어를 만난 문장과 함께 저장하세요 — 읽을수록 영어 어휘가 자랍니다.", feat6Title:'종이에서 읽기', feat6Desc:'인쇄된 페이지(책, 메뉴, 표지판)를 촬영하면 Lexio가 단어마다 탭할 수 있는 텍스트로 바꿔 줍니다.', extEyebrow:'Chrome 확장 프로그램 — 베타', extH2:'페이지를 <em>떠나지 않고</em><br>단어를 검색하세요.', extP:'어떤 웹사이트에서든 단어나 문장을 선택하세요. Lexio가 즉시 문맥 속 의미와 함께 나타납니다 — 복사 붙여넣기 없이, 탭 전환 없이.', extBtn:'Chrome에 추가', extNote:'무료 · 모든 페이지에서 작동 · 계정 불필요', deskH2:"Mac 어디서든 단어를 가리키기만 하세요.", deskP:"Lexio Glance 앱은 브라우저 밖에서도 동작합니다. Telegram 메시지, PDF, 자막, 코드 에디터 — 커서를 단어에 대고 두 번 탭하면 Lexio가 화면을 읽고 바로 그 자리에서 설명합니다.", downloadMac:'Mac용 다운로드', openBrowser:'브라우저에서 열기', footerTagline:"영어로 읽는 사람들을 위해.", heroRotatorLead:'이런 분들을 위해:', heroRotatorWord1:'영어 뉴스를 읽는', heroRotatorWord2:'업무 이메일을 읽는', heroRotatorWord3:'영어 소설을 읽는', heroRotatorWord4:'논문을 읽는', heroRotatorWord5:'IELTS·TOEFL을 준비하는', heroRotatorWord6:'해외 이주를 준비하는', heroRotatorWord7:'영어로 일하는', heroRotatorWord8:'마침내 유창해지고 싶은', heroTrust1:'월 20회 무료 검색', heroTrust2:'신용카드 불필요', heroTrust3:'당신의 언어로 설명', privacyPolicy:'개인정보 처리방침' },
};

function setUILang(code) {
  currentUILang = code;
  try { localStorage.setItem('lexio_ui_lang', code); } catch {}
  const t = UI_T[code] || UI_T.en;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    if (t[key] !== undefined) el.textContent = t[key];
  });
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.dataset.i18nHtml;
    if (t[key] !== undefined) el.innerHTML = t[key];
  });
  // textarea placeholder
  const ta = document.getElementById('input-text');
  if (ta) ta.placeholder = code === 'en' ? 'Paste any text here — an article, a quote, a paragraph…' :
    ({es:'Pega cualquier texto aquí — un artículo, una cita, un párrafo…', fr:'Collez votre texte ici — un article, une citation, un paragraphe…', de:'Fügen Sie Ihren Text hier ein — einen Artikel, ein Zitat, einen Absatz…', it:"Incolla il tuo testo qui — un articolo, una citazione, un paragrafo…", pt:'Cole seu texto aqui — um artigo, uma citação, um parágrafo…', nl:'Plak uw tekst hier — een artikel, een citaat, een alinea…', ru:'Вставьте текст сюда — статью, цитату, абзац…', zh:'在此粘贴任何文本——文章、引文、段落…', ja:'テキストをここに貼り付けてください — 記事、引用、段落など…', ko:'여기에 텍스트를 붙여넣으세요 — 기사, 인용문, 단락…'}[code] || ta.placeholder);
  document.documentElement.lang = code;
  // Sync header lang picker label
  const lbl = document.getElementById('lang-hdr-label');
  const _langLabels = { en:'EN', es:'ES', fr:'FR', de:'DE', it:'IT', pt:'PT', nl:'NL', ru:'RU', zh:'中文', ja:'日本語', ko:'한국어' };
  if (lbl) lbl.textContent = _langLabels[code] || code.toUpperCase();
  document.querySelectorAll('.lang-hdr-item').forEach(el =>
    el.classList.toggle('selected', el.dataset.code === code)
  );
}

function setLang(lang) {
  currentLang = lang;
  defCache.clear(); // cached results are language-specific
  try { localStorage.setItem('lexio_lang', lang); } catch {}
  // Re-fetch current word in new language if one is active
  if (currentResult) {
    fetchDefinition(currentResult.word, currentResult.context || currentContext);
  }
}
function setFontSize(v) {
  document.getElementById('token-view').style.fontSize = v + 'px';
  document.getElementById('input-text').style.fontSize = v + 'px';
  document.getElementById('font-size-val').textContent = v;
  currentTweaks.fontSize = +v; saveTweaks();
  window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { fontSize: +v } }, '*');
}
function setLineHeight(v) {
  document.getElementById('token-view').style.lineHeight = v;
  document.getElementById('input-text').style.lineHeight = v;
  document.getElementById('line-height-val').textContent = parseFloat(v).toFixed(1);
  currentTweaks.lineHeight = +v; saveTweaks();
  window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { lineHeight: +v } }, '*');
}
function applyTweaks() {
  setTheme(currentTweaks.theme);
  document.getElementById('font-size-slider').value = currentTweaks.fontSize;
  setFontSize(currentTweaks.fontSize);
  document.getElementById('line-height-slider').value = currentTweaks.lineHeight;
  setLineHeight(currentTweaks.lineHeight);
}

window.addEventListener('message', e => {
  if (e.data?.type === '__activate_edit_mode')   document.getElementById('tweaks-panel').classList.add('visible');
  if (e.data?.type === '__deactivate_edit_mode') document.getElementById('tweaks-panel').classList.remove('visible');
});
window.parent.postMessage({ type: '__edit_mode_available' }, '*');

/* ── Placeholder rotation ───────────────────────────────────── */
function startPlaceholderRotation() {
  if (placeholderTimer) return;
  placeholderTimer = setInterval(() => {
    const ta = document.getElementById('input-text');
    if (ta.value.length > 0 || document.activeElement === ta) return;
    ta.classList.add('ph-fading');
    setTimeout(() => {
      placeholderIdx = (placeholderIdx + 1) % PLACEHOLDERS.length;
      ta.placeholder = PLACEHOLDERS[placeholderIdx];
      requestAnimationFrame(() => ta.classList.remove('ph-fading'));
    }, 380);
  }, 4000);
}
function stopPlaceholderRotation() { clearInterval(placeholderTimer); placeholderTimer = null; }

/* ── Sample texts ───────────────────────────────────────────── */
function cycleSample() {
  currentSample = (currentSample + 1) % SAMPLES.length;
  const ta = document.getElementById('input-text');
  ta.value = SAMPLES[currentSample].text;
  updateCharCount();
  ta.focus();
  document.getElementById('sample-btn').textContent =
    `↻ Next (${SAMPLES[(currentSample + 1) % SAMPLES.length].label})`;
}

/* Hero CTA — pre-fill a Literature sample and immediately analyze
   so the first interaction is the product working, not a scroll. */
// True when the tool composer is actually on this page: on "/app" always, and
// the marketing landing ("/"): the tool lives on "/app", so CTAs navigate there.
// The ?try=1 instant demo is the one exception — it mounts the tool inline.
function toolOnThisPage() {
  if (document.body.classList.contains('tool-page')) return true;
  if (document.body.classList.contains('landing-page')) {
    return document.body.classList.contains('demo-mode');
  }
  return true; // Electron / unknown — tool is present
}

function tryHeroSample() {
  // On the mobile landing the tool isn't here — go to the dedicated tool page,
  // which re-runs this with the sample loaded once it boots.
  if (!toolOnThisPage()) {
    window.location.href = '/app?go=sample';
    return;
  }
  // Pick the Literature sample (index 3) — best vocab payoff for readers
  const litIdx = SAMPLES.findIndex(s => s.label === 'Literature');
  currentSample = litIdx >= 0 ? litIdx : 0;
  const ta = document.getElementById('input-text');
  ta.value = SAMPLES[currentSample].text;
  updateCharCount();
  window.scrollTo({ top: 0, behavior: 'smooth' });
  // Wait for scroll to settle, then trigger analysis
  setTimeout(() => {
    if (typeof analyze === 'function') analyze();
  }, 320);
}

/* ── Char count & URL detection ─────────────────────────────── */
const inputText = document.getElementById('input-text');
inputText.addEventListener('input', updateCharCount);
function updateCharCount() {
  const n = inputText.value.length;
  document.getElementById('char-count').textContent = n > 0 ? `${n.toLocaleString()} chars` : '';
  checkForURL(inputText.value.trim());
  autoGrowInput();
}

/* Mobile: auto-grow textarea so long pasted text isn't trapped behind
   an inner scrollbar. On desktop we leave the fixed flex-1 height. */
const _mobileMQ = window.matchMedia('(max-width: 760px)');
function autoGrowInput() {
  if (!_mobileMQ.matches) {
    inputText.style.height = '';
    return;
  }
  inputText.style.height = 'auto';
  // +2px for the trailing newline a textarea reserves
  inputText.style.height = Math.max(90, inputText.scrollHeight + 2) + 'px';
}
_mobileMQ.addEventListener('change', autoGrowInput);
window.addEventListener('resize', autoGrowInput);

const URL_RE = /^https?:\/\/[^\s]{4,}/i;
function checkForURL(text) {
  const isURL = URL_RE.test(text);
  document.getElementById('url-bar').classList.toggle('hidden', !isURL);
  if (isURL) document.getElementById('url-preview').textContent = text.length > 65 ? text.slice(0,62)+'…' : text;
}
async function fetchArticle() {
  const url = inputText.value.trim();
  const btn = document.getElementById('url-fetch-btn');
  btn.textContent = 'Fetching…'; btn.disabled = true; hideError();
  try {
    const resp = await fetch('/fetch-text', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url}) });
    if (!resp.ok) { const e = await resp.json().catch(()=>({detail:resp.statusText})); throw new Error(e.detail||`HTTP ${resp.status}`); }
    const { text } = await resp.json();
    inputText.value = text; updateCharCount();
    document.getElementById('url-bar').classList.add('hidden');
  } catch(err) { showError(err.message); }
  finally { btn.textContent = 'Fetch article'; btn.disabled = false; }
}

/* ── Drag & drop ────────────────────────────────────────────── */
function setupDragAndDrop() {
  const panel = document.getElementById('left-panel');
  panel.addEventListener('dragenter', e => { if([...e.dataTransfer.types].includes('Files')){ e.preventDefault(); panel.classList.add('drag-over'); } });
  panel.addEventListener('dragover',  e => { e.preventDefault(); panel.classList.add('drag-over'); });
  panel.addEventListener('dragleave', e => { if(!panel.contains(e.relatedTarget)) panel.classList.remove('drag-over'); });
  panel.addEventListener('drop', e => {
    e.preventDefault(); panel.classList.remove('drag-over');
    const file = e.dataTransfer.files[0]; if(!file) return;
    if(!file.name.endsWith('.txt') && !file.type.startsWith('text/')) { showError('Only plain-text (.txt) files are supported.'); return; }
    const reader = new FileReader();
    reader.onload = ev => { inputText.value = ev.target.result.slice(0,8000); updateCharCount(); };
    reader.readAsText(file);
  });
}

/* ── Analyze ────────────────────────────────────────────────── */
function analyze() {
  const raw = inputText.value.trim(); if(!raw) return;
  // Anonymous users get their ANON_LOOKUP_LIMIT (5) free lookups before any
  // sign-up wall. The backend enforces the cap (/define is optional-auth and
  // returns 402 when spent, which fetchDefinition() surfaces as the signup
  // modal), so do NOT hard-wall cold visitors here — that was killing the funnel.
  if(URL_RE.test(raw)) { fetchArticle(); return; }
  currentContext = raw; hideError();
  renderTokens(raw); stopPlaceholderRotation();
  inputText.classList.add('hidden');
  document.getElementById('token-view').classList.remove('hidden');
  document.getElementById('edit-btn').classList.remove('hidden');
  document.getElementById('analyze-btn').classList.add('hidden');
  document.getElementById('sample-btn').classList.add('hidden');
  document.getElementById('char-count').textContent = '';
  document.getElementById('url-bar').classList.add('hidden');
  // Reading stats
  const stats = computeReadingStats(raw);
  const statsEl = document.getElementById('reading-stats');
  statsEl.textContent = stats; statsEl.classList.remove('hidden');
  showSmartPlaceholder(raw);

  if (typeof updateAppCompact === 'function') updateAppCompact();
  maybeShowSpaceFiller();
}

// Short passages leave a lot of blank space below the text, which reads as
// broken rather than intentional. Fill it with a dashed drop-zone hint that
// doubles as a discoverable "add more text" affordance.
function maybeShowSpaceFiller() {
  const tv = document.getElementById('token-view');
  if (!tv) return;
  const existing = tv.querySelector('.space-filler-hint');
  if (existing) existing.remove();
  requestAnimationFrame(() => {
    if (tv.classList.contains('hidden')) return;
    if (tv.clientHeight - tv.scrollHeight < 160) return;
    const hint = document.createElement('div');
    hint.className = 'space-filler-hint';
    hint.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <span>Got more to read? Drag &amp; drop a .txt file, or <span class="filler-edit-link" id="filler-edit-link">paste a longer passage</span>.</span>
    `;
    tv.appendChild(hint);
    document.getElementById('filler-edit-link').addEventListener('click', resetToEdit);
  });
}

function computeReadingStats(text) {
  const words = (text.match(/([\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF\u3400-\u4DBF]|[A-Za-z\u00C0-\u024F\u0400-\u04FF\u0600-\u06FF\u0590-\u05FF\u0900-\u097F\u0370-\u03FF]+)/g) || []).length;
  const mins  = Math.max(1, Math.round(words / 200));
  return `${words.toLocaleString()} words · ~${mins} min read`;
}

/* ── Reset to edit ──────────────────────────────────────────── */
function resetToEdit() {
  document.getElementById('token-view').classList.add('hidden');
  inputText.classList.remove('hidden');
  document.getElementById('edit-btn').classList.add('hidden');
  document.getElementById('analyze-btn').classList.remove('hidden');
  document.getElementById('sample-btn').classList.remove('hidden');
  document.getElementById('reading-stats').classList.add('hidden');
  inputText.value = currentContext;
  activeToken = null; currentResult = null;
  clearModelResults(); cancelModelSwitch();
  showPlaceholder(); hideError(); updateCharCount(); startPlaceholderRotation();
  if (typeof updateAppCompact === 'function') updateAppCompact();
}

/* ── Sentence boundary detection ────────────────────────────── */
function computeSentenceBoundaries(text) {
  const starts = [0];
  const re = /[.!?]+\s+/g;
  let m;
  while ((m = re.exec(text)) !== null) starts.push(m.index + m[0].length);
  return starts;
}
function getSentenceIndex(charPos, starts) {
  let idx = 0;
  for (let i = 1; i < starts.length; i++) {
    if (charPos >= starts[i]) idx = i; else break;
  }
  return idx;
}

/* ── Tokenize & render (with staggered wave-in) ─────────────── */
function renderTokens(text) {
  const container = document.getElementById('token-view');
  container.innerHTML = '';
  // Split into clickable tokens.
  // CJK characters (Chinese, Japanese, Korean) are matched one at a time since
  // they have no spaces between words. All other scripts match full words.
  const parts = text.split(/([\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF\u3400-\u4DBF\uF900-\uFAFF]|[A-Za-z\u00C0-\u024F\u0400-\u04FF\u0600-\u06FF\u0750-\u077F\u0590-\u05FF\u0900-\u097F\u0370-\u03FF\u0E00-\u0E7F''‑-]+)/);
  const sentStarts = computeSentenceBoundaries(text);
  let wordIdx = 0;
  let charPos = 0;
  const totalWords = parts.filter((_,i) => i%2===1).length;
  const doStagger  = totalWords < 200;

  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const span = document.createElement('span');
      span.className   = 'word-token';
      span.textContent = part;
      span.setAttribute('role', 'button');
      span.setAttribute('tabindex', '0');
      span.dataset.sentence = getSentenceIndex(charPos, sentStarts);
      if (doStagger) span.style.animationDelay = Math.min(wordIdx * 5, 320) + 'ms';
      else           span.style.animationDelay = '0ms';
      if (lookedUpWords.has(part.toLowerCase())) span.classList.add('looked-up');
      span.addEventListener('click',   () => handleWordClick(span, part));
      span.addEventListener('keydown', e => { if(e.key==='Enter'||e.key===' '){ e.preventDefault(); handleWordClick(span, part); } });
      container.appendChild(span);
      wordIdx++;
    } else {
      container.appendChild(document.createTextNode(part));
    }
    charPos += part.length;
  });
  container.addEventListener('mouseup', handleTextSelection);

  // Onboarding hint for new users: gently pulse an interesting word
  const allWords = Array.from(container.querySelectorAll('.word-token'));
  if (allWords.length > 0) {
    const attempts = parseInt(localStorage.getItem('lexio_click_hints') || '0');
    
    // Find the specific word "adventitious", or fallback to a word that is >= 4 chars and ideally not a stopword
    const targetWord = allWords.find(w => w.textContent.toLowerCase().replace(/[^a-z]/g, '') === 'adventitious') 
      || allWords.find(w => w.textContent.length >= 4 && (typeof STOPWORDS === 'undefined' || !STOPWORDS.has(w.textContent.toLowerCase()))) 
      || allWords[0];
      
    const isSampleWord = targetWord.textContent.toLowerCase().includes('adventitious');
    
    if (attempts < 5 || isSampleWord) {
      if (!isSampleWord) {
        localStorage.setItem('lexio_click_hints', attempts + 1);
      }
      
      targetWord.classList.add('demo-pulse');
      
      const clearHint = () => {
        targetWord.classList.remove('demo-pulse');
        container.removeEventListener('mousedown', clearHint);
      };
      container.addEventListener('mousedown', clearHint);
    }
  }
}

/* ── Smart placeholder with suggested word chips ─────────────── */
function showSmartPlaceholder(text) {
  const words = [...text.matchAll(/[A-Za-z\u00C0-\u024F]+/g)]
    .map(m => m[0])
    .filter(w => w.length >= 6 && !STOPWORDS.has(w.toLowerCase()));

  const sub    = document.getElementById('placeholder-sub');
  const chips  = document.getElementById('suggest-chips');

  if (words.length === 0) {
    sub.textContent = 'Click any word to see its precise meaning in context.';
    chips.classList.add('hidden'); chips.innerHTML = '';
    return;
  }

  // Pick up to 3 diverse interesting words
  const seen = new Set();
  const picks = [];
  const shuffled = [...words].sort(() => Math.random() - 0.5);
  for (const w of shuffled) {
    const lc = w.toLowerCase();
    if (!seen.has(lc)) { seen.add(lc); picks.push(w); }
    if (picks.length >= 3) break;
  }

  sub.textContent = 'Try one of these — or click any word that catches your eye.';
  chips.innerHTML = picks.map(w =>
    `<button class="suggest-chip" data-word="${_escape(w)}">${_escape(w)}</button>`
  ).join('');
  chips.querySelectorAll('.suggest-chip').forEach(btn =>
    btn.addEventListener('click', () => clickSuggested(btn.dataset.word))
  );
  chips.classList.remove('hidden');
}

function clickSuggested(word) {
  for (const t of document.querySelectorAll('.word-token')) {
    if (t.textContent.toLowerCase() === word.toLowerCase()) {
      t.scrollIntoView({ behavior:'smooth', block:'center' }); t.click(); return;
    }
  }
}

/* ── Multi-word selection ───────────────────────────────────── */
function handleTextSelection() {
  const sel = window.getSelection();
  const selText = sel?.toString().trim();
  if (!selText || !selText.includes(' ')) return;
  const container = document.getElementById('token-view');
  if (!sel.anchorNode || !container.contains(sel.anchorNode)) return;
  clearHighlights();
  const phrase = selText.replace(/\s+/g,' ').slice(0,60);
  sel.removeAllRanges();
  fetchDefinition(phrase, currentContext);
}

/* ── Word click ─────────────────────────────────────────────── */
function handleWordClick(span, word) {
  clearHighlights();
  const lc = word.toLowerCase();
  const sentIdx = span.dataset.sentence;
  document.querySelectorAll('.word-token').forEach(t => {
    if (t === span) return;
    if (t.dataset.sentence === sentIdx) t.classList.add('in-sentence');
    if (t.textContent.toLowerCase() === lc) t.classList.add('same-word');
  });
  activeToken = span;
  span.classList.add('active', 'pulsing');
  fetchDefinition(word, currentContext);

}

function clearHighlights() {
  document.querySelectorAll('.word-token.active,.word-token.same-word,.word-token.pulsing,.word-token.in-sentence')
    .forEach(t => t.classList.remove('active','same-word','pulsing','in-sentence'));
}

/* ── POS → badge colour ─────────────────────────────────────── */
function posType(pos) {
  const p = (pos||'').toLowerCase();
  if (p.includes('noun'))  return 'noun';
  if (p.includes('verb'))  return 'verb';
  if (p.includes('adj'))   return 'adj';
  if (p.includes('adv'))   return 'adv';
  return 'other';
}

/* ── Cache key (includes model so each model is cached separately) ── */
function cacheKey(word, context, model) { return word.toLowerCase()+'::'+context.slice(0,120)+'::'+currentLang+'::'+(model||currentModel); }

/* ── Per-word model results (cleared on new word click) ─────── */
let resultWord    = null;   // word currently shown in right panel
let _retryCount   = 0;     // re-requests for current word
let resultContext = null;   // context it was looked up in
let modelResults  = {};     // { modelKey: data } for resultWord
let currentResultModel = null;  // which model's result is displayed

function clearModelResults() {
  resultWord = null; resultContext = null;
  modelResults = {}; currentResultModel = null;
  const tabs = document.getElementById('model-result-tabs');
  if (tabs) { tabs.innerHTML = ''; tabs.classList.add('hidden'); }
}

/* ── Fetch definition ───────────────────────────────────────── */
async function fetchDefinition(word, context, modelOverride, bypassCache=false) {
  hideError();
  cancelModelSwitch();
  const model = modelOverride || currentModel;
  const key = cacheKey(word, context, model);
  if (!bypassCache && defCache.has(key)) {
    if (activeToken) activeToken.classList.remove('pulsing');
    // Still store in modelResults so tabs render correctly
    modelResults[model] = defCache.get(key);
    showResult(word, defCache.get(key), false, model); return;
  }
  showLoading(word);
  try {
    const _tok = localStorage.getItem('lexio_token');
    const _hdrs = { 'Content-Type': 'application/json' };
    if (_tok) _hdrs['Authorization'] = 'Bearer ' + _tok;
    const resp = await fetch('/define', { method:'POST', headers:_hdrs, body:JSON.stringify({word,context,lang:currentLang,model}) });
    if (!resp.ok) {
      if (resp.status === 403) {
        const err = await resp.json().catch(() => ({}));
        const d = err.detail || {};
        clearHighlights(); activeToken = null;
        showPlaceholder();
        if (d.code === 'pro_required') {
          showProModal('model', 0, 0);
          throw new Error(d.message || 'This mode requires a Pro plan.');
        }
        throw new Error(d.message || 'Not allowed.');
      }
      if (resp.status === 429) {
        const err = await resp.json().catch(() => ({}));
        const d = err.detail || {};
        clearHighlights(); activeToken = null;
        showPlaceholder();
        if (d.code === 'hourly_limit') {
          const mins = Math.max(1, Math.ceil((d.reset_in || 0) / 60));
          const modeLabel = (MODEL_LABELS[d.model] || d.model || 'this mode');
          const weight = d.weight || 1;
          throw new Error(
            `⏱ Hourly limit reached — you've used ${d.used}/${d.limit} credits this hour. ` +
            `${modeLabel} costs ${weight} credit${weight !== 1 ? 's' : ''} per lookup. ` +
            `Try again in ${mins} minute${mins !== 1 ? 's' : ''}, or switch to a lighter mode.`
          );
        }
        throw new Error('⏱ Too many requests — wait a moment and try again.');
      }
      if (resp.status === 402) {
        const err = await resp.json().catch(() => ({}));
        const d = err.detail || {};
        clearHighlights(); activeToken = null;
        showPlaceholder();
        showProModal(d.kind || 'lookup', d.used || 0, d.limit || 20);
        return;
      }
      const err = await resp.json().catch(()=>({detail:resp.statusText}));
      throw new Error(err.detail||`HTTP ${resp.status}`);
    }
    const data = await resp.json();
    if (data._usage)  updateUsagePill(data._usage.used, data._usage.limit);
    if (data._hourly) updateHourlyPill(data._hourly.used, data._hourly.limit);
    loadStreak();   // a lookup may have started or extended today's streak
    defCache.set(key, data);
    modelResults[model] = data;
    addToHistory(word, data);
    if (activeToken) activeToken.classList.remove('pulsing');
    // Mark all tokens of this word as looked-up
    lookedUpWords.add(word.toLowerCase());
    document.querySelectorAll('.word-token').forEach(t => {
      if (t.textContent.toLowerCase() === word.toLowerCase()) t.classList.add('looked-up');
    });
    showResult(word, data, false, model);
  } catch(err) {
    clearHighlights(); activeToken = null;
    showPlaceholder(); showError(err.message);
  }
}

/* ── History ────────────────────────────────────────────────── */
function addToHistory(word, data) {
  if (history.length>0 && history[0].word.toLowerCase()===word.toLowerCase()) return;
  history.unshift({word,data}); if(history.length>MAX_HISTORY) history.pop();
}
function renderHistory() {
  const strip = document.getElementById('history-strip');
  const bar   = document.getElementById('history-header');
  if (history.length <= 1) {
    strip.innerHTML = ''; strip.classList.add('hidden');
    if (bar) { bar.innerHTML = ''; bar.classList.add('hidden'); }
    return;
  }
  const chipsHtml = '<span class="history-label">Recent</span>' +
    history.slice(1).map((h,i) =>
      `<button class="history-chip"
        data-tip="${_escape((h.data.contextual||'').slice(0,80)+(h.data.contextual?'…':''))}"
        data-idx="${i+1}"
        onmouseenter="showChipTooltip(event,this.dataset.tip)"
        onmouseleave="hideChipTooltip()"
        onclick="showCached(this.dataset.idx|0)">${_escape(h.word)}<span class="history-chip-pos"> ${_escape(h.data.pos||'')}</span></button>`
    ).join('');
  // Populate pinned bar (above def); hide old in-scroll strip
  if (bar) { bar.innerHTML = chipsHtml; bar.classList.remove('hidden'); }
  strip.classList.add('hidden');
}
function showCached(idx) {
  const {word,data} = history[idx];
  clearHighlights(); activeToken = null;
  document.querySelectorAll('.word-token').forEach(t => { if(t.textContent.toLowerCase()===word.toLowerCase()) t.classList.add('same-word'); });
  showResult(word, data, true);
}

/* ── Chip tooltip ───────────────────────────────────────────── */
const chipTooltip = document.getElementById('chip-tooltip');
function showChipTooltip(e, text) {
  chipTooltip.textContent = text;
  chipTooltip.style.display = 'block';
  const rect = e.currentTarget.getBoundingClientRect();
  chipTooltip.style.left = (rect.left + rect.width/2) + 'px';
  chipTooltip.style.top  = (rect.top - 10) + 'px';
  chipTooltip.style.transform = 'translate(-50%,-100%)';
}
function hideChipTooltip() { chipTooltip.style.display = 'none'; }

/* ── Panel states ───────────────────────────────────────────── */
function showPlaceholder() {
  document.getElementById('def-placeholder').classList.remove('hidden');
  document.getElementById('def-loading').classList.add('hidden');
  document.getElementById('def-result').classList.add('hidden');
  document.getElementById('history-strip').classList.add('hidden');
  const bar = document.getElementById('history-header');
  if (bar) bar.classList.add('hidden');
}
function showLoading(word) {
  document.getElementById('def-placeholder').classList.add('hidden');
  document.getElementById('def-loading').classList.remove('hidden');
  document.getElementById('def-result').classList.add('hidden');
  document.getElementById('loading-word-label').textContent = word || '';
  // Keep history bar visible while loading so user can see recent words
  renderHistory();
}

/* ── Show result with sequential cascade animation ──────────── */
function showResult(word, data, fromHistory=false, model) {
  document.getElementById('def-placeholder').classList.add('hidden');
  document.getElementById('def-loading').classList.add('hidden');
  currentResult = {word, data, context: currentContext};

  // Track per-word model state (only for live clicks, not history)
  if (!fromHistory) {
    const usedModel = model || currentModel;
    if (resultWord !== word.toLowerCase()) {
      // New word — reset model results and retry counter
      modelResults = {};
      resultWord    = word.toLowerCase();
      resultContext = currentContext;
      _retryCount   = 0;
    }
    modelResults[usedModel]  = data;
    currentResultModel       = usedModel;
    renderModelTabs();
    updateRetryBtn();
  }

  // Populate
  document.getElementById('def-word').textContent = word;

  // IPA
  const ipaRow = document.getElementById('ipa-row');
  const ipaEl  = document.getElementById('def-ipa');
  if (data.ipa && data.ipa !== 'null') {
    ipaEl.textContent = data.ipa; ipaRow.classList.remove('hidden');
  } else { ipaRow.classList.add('hidden'); }

  const posBadge  = document.getElementById('def-pos');
  const wordCount = word.trim().split(/\s+/).length;
  const isPhrase  = wordCount > 1;
  posBadge.textContent = isPhrase ? (data.pos || 'phrase') : (data.pos || '');
  posBadge.dataset.pos = isPhrase && !data.pos ? 'other' : posType(data.pos);

  // Register tag
  const regEl = document.getElementById('def-register');
  if (data.register && data.register !== 'neutral') {
    regEl.textContent = data.register; regEl.classList.remove('hidden');
  } else { regEl.classList.add('hidden'); }

  // Simpler
  const simplerRow  = document.getElementById('def-simpler');
  const simplerWord = document.getElementById('def-simpler-word');
  const s = data.simpler;
  // Only show if it's a genuine short synonym (≤3 words), not a sentence the AI wrote
  const simplerIsValid = s && s !== 'null' && s.toLowerCase() !== word.toLowerCase()
    && s.trim().split(/\s+/).length <= 3 && !s.includes(',') && !s.includes(';');
  if (simplerIsValid) {
    simplerWord.textContent = s; simplerRow.classList.remove('hidden');
  } else { simplerRow.classList.add('hidden'); }

  // Definition (general meaning — returned for all lookups now)
  const defSection = document.getElementById('def-definition-section');
  const defEl      = document.getElementById('def-definition');
  if (data.definition && data.definition !== 'null') {
    defEl.textContent = data.definition;
    defSection.classList.remove('hidden');
  } else {
    defSection.classList.add('hidden');
  }

  document.getElementById('def-contextual').textContent = data.contextual || '';
  document.getElementById('def-why').textContent        = data.why || '';

  // Etymology — in progressive disclosure section
  const etymRow = document.getElementById('etymology-row');
  const etymEl  = document.getElementById('def-etymology');
  if (data.etymology && data.etymology !== 'null') {
    etymEl.textContent = data.etymology; etymRow.classList.remove('hidden');
  } else { etymRow.classList.add('hidden'); }
  // Show more-toggle when there's extra detail to reveal
  const moreToggle = document.getElementById('more-toggle');
  const moreSection = document.getElementById('more-section');
  const hasExtra = (data.etymology && data.etymology !== 'null');
  if (moreToggle) moreToggle.style.display = hasExtra ? 'inline-flex' : 'none';
  // Collapse more-section on every new word
  if (moreSection) moreSection.classList.remove('open');
  if (moreToggle) moreToggle.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg> More detail';

  updateSaveBtn(word);

  document.getElementById('def-result').classList.remove('hidden');

  // On mobile the right panel sits below the text panel; scroll it into view
  // so the user doesn't have to discover it manually after tapping a word.
  if (window.innerWidth <= 760) {
    document.querySelector('.panel-right')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  if (!fromHistory) renderHistory();

  // Explored counter
  const exploredEl = document.getElementById('explored-line');
  if (lookedUpWords.size > 1) {
    exploredEl.textContent = `${lookedUpWords.size} words explored`;
    exploredEl.classList.remove('hidden');
  } else { exploredEl.classList.add('hidden'); }
}

/* ── More toggle ────────────────────────────────────────────── */
function toggleMoreSection() {
  const sec  = document.getElementById('more-section');
  const btn  = document.getElementById('more-toggle');
  const open = sec.classList.toggle('open');
  btn.innerHTML = open
    ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg> Less detail'
    : '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg> More detail';
}

/* ── Copy ───────────────────────────────────────────────────── */
/* ── Retry / re-request definition ─────────────────────────── */
const MAX_RETRIES = 5;

function updateRetryBtn() {
  const btn = document.getElementById('retry-btn');
  if (!btn || !resultWord) return;
  const remaining = MAX_RETRIES - _retryCount;
  if (remaining <= 0) {
    btn.style.display = 'none';
  } else {
    btn.style.display = '';
    document.getElementById('retry-label').textContent =
      remaining < MAX_RETRIES ? `Try again (${remaining} left)` : 'Try again';
  }
}

function retryDefinition() {
  if (!currentResult || _retryCount >= MAX_RETRIES) return;
  _retryCount++;
  updateRetryBtn();
  fetchDefinition(currentResult.word, currentResult.context || currentContext, currentResultModel, true);
}

function copyDefinition() {
  if (!currentResult) return;
  const {word,data} = currentResult;
  const lines = [`${word} (${data.pos})`,'',data.contextual];
  if (data.etymology && data.etymology!=='null') lines.push('','Origin: '+data.etymology);
  lines.push('','↳ '+data.why);
  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    const btn=document.getElementById('copy-btn'); const orig=btn.innerHTML;
    btn.textContent='✓ Copied'; setTimeout(()=>{btn.innerHTML=orig;},2000);
  }).catch(()=>showError('Could not access clipboard.'));
}

/* ── Permalink ──────────────────────────────────────────────── */
function copyPermalink() {
  if (!currentResult) return;
  const url = new URL(window.location.href.split('?')[0]);
  url.searchParams.set('word', currentResult.word);
  url.searchParams.set('context', currentContext.slice(0,600));
  navigator.clipboard.writeText(url.toString()).then(() => {
    const btn=document.getElementById('link-btn'); const orig=btn.innerHTML;
    btn.textContent='✓ Copied'; setTimeout(()=>{btn.innerHTML=orig;},2000);
  }).catch(()=>showError('Could not copy link.'));
}

/* ── Share as image ─────────────────────────────────────────── */
async function shareAsImage() {
  if (!currentResult) return;
  const btn = document.getElementById('share-btn');
  const orig = btn.innerHTML; btn.textContent = '…';
  try {
    const { word, data } = currentResult;
    const meaning    = data.meaning    || '';
    const contextual = data.contextual || '';
    const pos        = (data.pos || '').toUpperCase();
    const DPR = 2;
    const W   = 760, PAD = 52;
    const ACCENT = '#b5541a', TEXT = '#1c1714', MUTED = '#7a6f68',
          LABEL = '#a89890', BG = '#faf8f5', BORDER = '#e4dcd4',
          BADGE_BG = '#f0e6dc';

    // ── helpers ───────────────────────────────────────────────
    function rr(ctx, x, y, w, h, r) {
      ctx.beginPath();
      ctx.moveTo(x+r, y);
      ctx.lineTo(x+w-r, y); ctx.arcTo(x+w,y,x+w,y+r,r);
      ctx.lineTo(x+w, y+h-r); ctx.arcTo(x+w,y+h,x+w-r,y+h,r);
      ctx.lineTo(x+r, y+h); ctx.arcTo(x,y+h,x,y+h-r,r);
      ctx.lineTo(x, y+r); ctx.arcTo(x,y,x+r,y,r);
      ctx.closePath();
    }
    function wrapLines(ctx, text, maxW) {
      const words = text.split(' '), lines = [];
      let line = '';
      for (const w of words) {
        const test = line ? line + ' ' + w : w;
        if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = w; }
        else line = test;
      }
      if (line) lines.push(line);
      return lines;
    }

    // ── measure pass to get final height ─────────────────────
    const tmp = document.createElement('canvas');
    tmp.width = W * DPR; tmp.height = 10;
    const tc = tmp.getContext('2d');
    tc.scale(DPR, DPR);

    let y = PAD;
    y += 58 + 12;                           // word
    if (pos) y += 30 + 14;                 // badge
    y += 14 + 8;                            // MEANING label
    tc.font = '400 18px DM Sans,sans-serif';
    y += wrapLines(tc, meaning, W-PAD*2).length * 29 + 24;
    if (contextual) {
      y += 1 + 24;                          // divider + gap
      y += 14 + 8;                          // IN THIS CONTEXT label
      tc.font = '300 17px DM Sans,sans-serif';
      y += wrapLines(tc, contextual, W-PAD*2).length * 27 + 20;
    }
    y += 1 + 22 + 22 + PAD;               // footer divider + footer + pad

    // ── draw pass ─────────────────────────────────────────────
    const canvas = document.createElement('canvas');
    canvas.width = W * DPR; canvas.height = y * DPR;
    const ctx = canvas.getContext('2d');
    ctx.scale(DPR, DPR);

    // background card
    ctx.fillStyle = BG;
    rr(ctx, 0, 0, W, y, 28); ctx.fill();

    let cy = PAD;

    // word
    ctx.fillStyle = TEXT;
    ctx.font = '600 52px Lora,Georgia,serif';
    ctx.fillText(word, PAD, cy + 46);
    cy += 58;

    // POS badge
    if (pos) {
      cy += 12;
      ctx.font = '700 11px DM Sans,Arial,sans-serif';
      const bw = ctx.measureText(pos).width + 22;
      ctx.fillStyle = BADGE_BG; rr(ctx, PAD, cy, bw, 24, 12); ctx.fill();
      ctx.fillStyle = ACCENT;
      ctx.fillText(pos, PAD + 11, cy + 16);
      cy += 24 + 14;
    } else { cy += 14; }

    // MEANING label
    ctx.font = '700 11px DM Sans,Arial,sans-serif';
    ctx.fillStyle = LABEL;
    ctx.fillText('MEANING', PAD, cy + 11);
    cy += 14 + 8;

    // meaning text
    ctx.font = '400 18px DM Sans,Arial,sans-serif';
    ctx.fillStyle = TEXT;
    for (const line of wrapLines(ctx, meaning, W - PAD*2)) {
      ctx.fillText(line, PAD, cy + 18); cy += 29;
    }
    cy += 24;

    // contextual block
    if (contextual) {
      ctx.strokeStyle = BORDER; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(PAD, cy); ctx.lineTo(W-PAD, cy); ctx.stroke();
      cy += 24;

      ctx.font = '700 11px DM Sans,Arial,sans-serif';
      ctx.fillStyle = LABEL;
      ctx.fillText('IN THIS CONTEXT', PAD, cy + 11);
      cy += 14 + 8;

      ctx.font = '300 17px DM Sans,Arial,sans-serif';
      ctx.fillStyle = MUTED;
      for (const line of wrapLines(ctx, contextual, W - PAD*2)) {
        ctx.fillText(line, PAD, cy + 17); cy += 27;
      }
      cy += 20;
    }

    // footer divider
    ctx.strokeStyle = BORDER; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PAD, cy); ctx.lineTo(W-PAD, cy); ctx.stroke();
    cy += 22;

    // footer branding
    ctx.font = '600 14px DM Sans,Arial,sans-serif';
    ctx.fillStyle = ACCENT;
    ctx.fillText('Lexio', PAD, cy + 14);
    ctx.font = '400 14px DM Sans,Arial,sans-serif';
    ctx.fillStyle = MUTED;
    ctx.fillText('· lexio.site', PAD + ctx.measureText('Lexio').width + 5, cy + 14);
    ctx.fillStyle = LABEL;
    const tag = 'AI contextual definitions';
    ctx.fillText(tag, W - PAD - ctx.measureText(tag).width, cy + 14);

    // ── share or download ─────────────────────────────────────
    const filename = `lexio-${word.toLowerCase()}.png`;
    canvas.toBlob(async blob => {
      try {
        const f = new File([blob], filename, { type: 'image/png' });
        if (navigator.canShare?.({ files: [f] })) {
          await navigator.share({ files: [f], title: word }); return;
        }
      } catch {}
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = filename; a.click();
    }, 'image/png');

  } catch(e) { showError('Could not generate card.'); }
  finally { btn.innerHTML = orig; }
}

/* ── Save / word bank ───────────────────────────────────────── */
function isSaved(word) { return wordBank.some(e=>e.word.toLowerCase()===word.toLowerCase()); }
function updateSaveBtn(word) {
  const btn   = document.getElementById('save-btn');
  const icon  = document.getElementById('save-icon');
  const label = document.getElementById('save-label');
  if (isSaved(word)) {
    btn.classList.add('saved'); btn.title='Remove from collection';
    icon.setAttribute('fill','currentColor'); label.textContent='Collected';
  } else {
    btn.classList.remove('saved'); btn.title='Add to collection';
    icon.setAttribute('fill','none'); label.textContent='Collect';
  }
}
function toggleSave() {
  if (!currentResult) return;
  const {word,data} = currentResult;
  if (isSaved(word)) { wordBank=wordBank.filter(e=>e.word.toLowerCase()!==word.toLowerCase()); }
  else { wordBank.unshift({word,pos:data.pos||'',contextual:data.contextual||'',why:data.why||'',simpler:data.simpler||null,etymology:data.etymology||null,register:data.register||null,context:extractSentence(currentContext,word),savedAt:new Date().toISOString()}); }
  saveWordBank(); updateSaveBtn(word);
}

function openWordBank()   {
  // Reset the search filter every time the modal opens so users
  // don't get stuck on a stale query.
  _wbSearchQuery = '';
  const si = document.getElementById('wb-search');
  if (si) si.value = '';
  const clr = document.getElementById('wb-search-clear');
  if (clr) clr.style.display = 'none';
  renderWordBankList();
  document.getElementById('wb-overlay').classList.remove('hidden');
}
function closeWordBank()  { document.getElementById('wb-overlay').classList.add('hidden'); }

let _wbSearchQuery = '';
function filterWordBank(q, clear) {
  _wbSearchQuery = (q || '').trim().toLowerCase();
  if (clear) {
    _wbSearchQuery = '';
    const si = document.getElementById('wb-search');
    if (si) si.value = '';
  }
  const clr = document.getElementById('wb-search-clear');
  if (clr) clr.style.display = _wbSearchQuery ? '' : 'none';
  renderWordBankList();
}

function renderWordBankList() {
  const list=document.getElementById('wb-list'), count=document.getElementById('wb-count');
  const emptyMsg = document.getElementById('wb-empty-msg');
  count.textContent = wordBank.length===0?'':`${wordBank.length} word${wordBank.length!==1?'s':''}`;
  if (!wordBank.length) {
    const signedOut = !authUser;
    list.innerHTML = signedOut
      ? '<div class="wb-empty"><p style="margin-bottom:12px">Sign in to save words and sync across devices.</p><button class="auth-submit" style="width:auto;padding:8px 20px;font-size:0.85rem" onclick="closeWordBank();openAuthModal()">Sign in</button></div>'
      : '<p class="wb-empty">No saved words yet.<br>Click the bookmark icon on any definition to save it here.</p>';
    if (emptyMsg) emptyMsg.style.display = 'none';
    return;
  }
  // Filter against search query (matches word OR definition OR context).
  const q = _wbSearchQuery;
  const matches = q
    ? wordBank.map((e, i) => ({ e, i })).filter(({ e }) => {
        const blob = ((e.word || '') + ' ' + (e.contextual || '') + ' ' + (e.context || '') + ' ' + (e.definition || '')).toLowerCase();
        return blob.includes(q);
      })
    : wordBank.map((e, i) => ({ e, i }));
  if (matches.length === 0) {
    list.innerHTML = '';
    if (emptyMsg) emptyMsg.style.display = '';
    return;
  }
  if (emptyMsg) emptyMsg.style.display = 'none';
  list.innerHTML = matches.map(({ e, i }) =>
    `<div class="wb-entry"><div class="wb-entry-header"><span class="wb-word">${_escape(e.word)}</span>${e.pos?`<span class="wb-pos">${_escape(e.pos)}</span>`:''}<button class="wb-delete" onclick="deleteFromBank(${i})" title="Remove">×</button></div><p class="wb-def">${_escape(e.contextual||e.definition||'')}</p></div>`
  ).join('');
}
function deleteFromBank(i) { wordBank.splice(i,1); saveWordBank(); renderWordBankList(); }

function extractSentence(text, word) {
  // Split on sentence boundaries (. ! ? followed by space or end)
  const sentences = text.match(/[^.!?\n]+[.!?\n]*/g) || [];
  const lower = word.toLowerCase();
  // Find shortest sentence that contains the word (avoids grabbing huge run-ons)
  const hits = sentences.filter(s => s.toLowerCase().includes(lower));
  if (!hits.length) return text.slice(0, 220).trim();
  const hit = hits.sort((a, b) => a.length - b.length)[0];
  return hit.trim();
}

/* ── Flashcard review ───────────────────────────────────────── */
let _fcQueue=[], _fcTotal=0, _fcKnown=0, _fcFlipped=false;

function openFlashcards() {
  if (!wordBank.length) { alert('Save some words first — click the bookmark on any definition.'); return; }
  closeWordBank();
  fcStart();
  document.getElementById('fc-overlay').classList.remove('hidden');
}
function closeFlashcards() { document.getElementById('fc-overlay').classList.add('hidden'); }

function fcStart() {
  _fcQueue = [...wordBank].sort(() => Math.random() - 0.5);
  _fcTotal = _fcQueue.length;
  _fcKnown = 0;
  document.getElementById('fc-done').classList.add('hidden');
  document.getElementById('fc-card-wrap').style.display = '';
  document.getElementById('fc-actions').classList.add('hidden');
  fcShowCard();
}

function fcShowCard() {
  const done = _fcTotal - _fcQueue.length;
  document.getElementById('fc-progress').textContent = `${done + 1} / ${_fcTotal}`;
  const e = _fcQueue[0];
  document.getElementById('fc-word').textContent = e.word;
  const sentence = e.context ? extractSentence(e.context, e.word) : '';
  document.getElementById('fc-ctx').textContent  = sentence ? `"${sentence}"` : '';
  document.getElementById('fc-pos').textContent  = e.pos || '';
  document.getElementById('fc-pos').style.display = e.pos ? '' : 'none';
  document.getElementById('fc-def').textContent  = e.contextual || '';
  const card = document.getElementById('fc-card');
  card.classList.remove('flipped');
  card.style.cssText = '';
  _fcFlipped = false;
}

function flipCard() {
  if (_fcFlipped) return;
  _fcFlipped = true;
  document.getElementById('fc-card').classList.add('flipped');
  setTimeout(() => document.getElementById('fc-actions').classList.remove('hidden'), 320);
}

function fcNext(known) {
  if (known) _fcKnown++;
  _fcQueue.shift();
  if (!_fcQueue.length) { fcFinish(); return; }
  const card = document.getElementById('fc-card');
  const dir  = known ? '60px' : '-60px';
  card.style.cssText = `opacity:0;transform:translateX(${dir});transition:opacity 0.17s,transform 0.17s`;
  document.getElementById('fc-actions').classList.add('hidden');
  setTimeout(() => { fcShowCard(); }, 170);
}

function fcFinish() {
  document.getElementById('fc-card-wrap').style.display = 'none';
  document.getElementById('fc-actions').classList.add('hidden');
  const pct = Math.round((_fcKnown / _fcTotal) * 100);
  document.getElementById('fc-done-emoji').textContent = pct >= 80 ? '🎉' : pct >= 50 ? '💪' : '📖';
  document.getElementById('fc-done-sub').textContent =
    `You knew ${_fcKnown} of ${_fcTotal} word${_fcTotal !== 1 ? 's' : ''} (${pct}%).`;
  document.getElementById('fc-progress').textContent = `${_fcTotal} / ${_fcTotal}`;
  document.getElementById('fc-done').classList.remove('hidden');
}

function exportCSV() {
  if (!wordBank.length) return;
  const header=['Word','Part of Speech','Contextual Definition','Why This Word','Etymology','Register','Simpler Synonym','Context (excerpt)','Saved'].join('\t');
  const rows=wordBank.map(e=>[e.word,e.pos,e.contextual,e.why,e.etymology||'',e.register||'',e.simpler||'',e.context.replace(/[\t\n\r]/g,' '),new Date(e.savedAt).toLocaleDateString()].map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join('\t'));
  const blob=new Blob([[header,...rows].join('\n')],{type:'text/tab-separated-values'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='lexio-wordbank.tsv'; a.click();
}

/* Anki TSV export — uses the server endpoint (Pro-gated). Falls back to the
   local word-bank for free users so they can still export, just without the
   server-side Pro-only field enrichment. */
async function exportAnki() {
  const tok = localStorage.getItem('lexio_token');
  if (tok) {
    try {
      const r = await fetch('/wordbank/anki', { headers: { 'Authorization': 'Bearer ' + tok } });
      if (r.status === 402) {
        if (typeof showProModal === 'function') showProModal('lookup', 0, 20);
        return;
      }
      if (r.ok) {
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'lexio-anki-' + new Date().toISOString().slice(0,10) + '.tsv';
        a.click();
        return;
      }
    } catch {}
  }
  // Fallback: build the same TSV client-side from localStorage
  if (!wordBank.length) return;
  const lines = ['Front\tBack'];
  for (const e of wordBank) {
    const w = (e.word || '').replace(/\t/g, ' ').trim();
    const ctx = (e.context || '').replace(/\t/g, ' ').trim();
    const def = (e.contextual || e.definition || '').replace(/\t/g, ' ').trim();
    const why = (e.why || '').replace(/\t/g, ' ').trim();
    const etym = (e.etymology || '').replace(/\t/g, ' ').trim();
    if (!w || !def) continue;
    const front = '<b>' + w + '</b>' + (ctx ? '<br><br>' + ctx : '');
    let back = def;
    if (why)  back += '<br><br><i>Why this word:</i> ' + why;
    if (etym) back += '<br><br><i>Etymology:</i> ' + etym;
    lines.push(front.replace(/\n/g, '<br>') + '\t' + back.replace(/\n/g, '<br>'));
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/tab-separated-values' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'lexio-anki-' + new Date().toISOString().slice(0,10) + '.tsv';
  a.click();
}

/* ── Pronounce ──────────────────────────────────────────────── */
const LANG_BCP47 = { English:'en-US', Spanish:'es-ES', French:'fr-FR', German:'de-DE', Italian:'it-IT', Portuguese:'pt-PT', Dutch:'nl-NL', Russian:'ru-RU', Chinese:'zh-CN', Japanese:'ja-JP', Korean:'ko-KR' };
function sayWord() {
  if (!currentResult || !window.speechSynthesis) return;
  const utt = new SpeechSynthesisUtterance(currentResult.word);
  utt.lang = LANG_BCP47[currentLang] || 'en-US';
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utt);
}

/* ── Error ──────────────────────────────────────────────────── */
function showError(msg) { const b=document.getElementById('error-banner'); b.textContent=msg; b.classList.remove('hidden'); }
function hideError()    { document.getElementById('error-banner').classList.add('hidden'); }

/* ── Permalink on load ──────────────────────────────────────── */
function checkPermalink() {
  const params=new URLSearchParams(window.location.search);
  const word=params.get('word'), context=params.get('context');
  if (!word||!context) return;
  inputText.value=context; updateCharCount(); analyze();
  requestAnimationFrame(()=>{
    for (const t of document.querySelectorAll('.word-token')) {
      if (t.textContent.toLowerCase()===word.toLowerCase()) { t.scrollIntoView({behavior:'smooth',block:'center'}); t.click(); break; }
    }
  });
}


/* ── Keyboard shortcuts ─────────────────────────────────────── */
function toggleShortcuts() {
  shortcutsOpen=!shortcutsOpen;
  document.getElementById('shortcuts-overlay').classList.toggle('hidden',!shortcutsOpen);
}

/* ── Desktop app modal ──────────────────────────────────── */
function openDesktopModal()  { document.getElementById('desktop-modal').classList.remove('hidden'); }
function closeDesktopModal() {
  document.getElementById('desktop-modal').classList.add('hidden');
  document.getElementById('desktop-not-found').classList.add('hidden');
}
function tryOpenDesktop() {
  document.getElementById('desktop-not-found').classList.add('hidden');
  window.location.href = 'lexio://open';
  setTimeout(() => document.getElementById('desktop-not-found').classList.remove('hidden'), 1500);
}

/* ── Menu dropdown ──────────────────────────────────────── */
let menuOpen = false;
function toggleMenu() {
  menuOpen = !menuOpen;
  document.getElementById('menu-dropdown').classList.toggle('hidden', !menuOpen);
  document.getElementById('menu-btn').classList.toggle('active', menuOpen);
}
function closeMenu() {
  menuOpen = false;
  document.getElementById('menu-dropdown').classList.add('hidden');
  document.getElementById('menu-btn').classList.remove('active');
}

/* ── Header language picker ─────────────────────────────────── */
let langPickerOpen = false;
const LANG_LABELS = { en:'EN', es:'ES', fr:'FR', de:'DE', it:'IT', pt:'PT', nl:'NL', ru:'RU', zh:'中文', ja:'日本語', ko:'한국어' };

// ── Landing Page Nav Dropdowns ────────────────────────────────
let openNavDropdown = null;

function toggleNavDropdown(id) {
  if (openNavDropdown === id) {
    closeAllNavDropdowns();
    return;
  }
  closeAllNavDropdowns();
  openNavDropdown = id;
  const drop = document.getElementById(`lp-${id}-drop`);
  const btn  = document.getElementById(`lp-${id}-btn`);
  if (drop) drop.classList.remove('hidden');
  if (btn)  btn.setAttribute('aria-expanded', 'true');
  if (langPickerOpen) closeLangPicker();
}

function closeAllNavDropdowns() {
  if (!openNavDropdown) return;
  const drop = document.getElementById(`lp-${openNavDropdown}-drop`);
  const btn  = document.getElementById(`lp-${openNavDropdown}-btn`);
  if (drop) drop.classList.add('hidden');
  if (btn)  btn.setAttribute('aria-expanded', 'false');
  openNavDropdown = null;
}

function toggleLangPicker() {
  langPickerOpen = !langPickerOpen;
  if (langPickerOpen) closeAllNavDropdowns();
  document.getElementById('lang-hdr-drop').classList.toggle('hidden', !langPickerOpen);
  document.getElementById('lang-hdr-btn').classList.toggle('active', langPickerOpen);
  document.getElementById('lang-hdr-btn').setAttribute('aria-expanded', langPickerOpen);
  if (menuOpen) closeMenu();
}
function closeLangPicker() {
  langPickerOpen = false;
  const drop = document.getElementById('lang-hdr-drop');
  if (drop) drop.classList.add('hidden');
  const btn = document.getElementById('lang-hdr-btn');
  if (btn) { btn.classList.remove('active'); btn.setAttribute('aria-expanded', 'false'); }
}
function pickUILang(code) {
  setUILang(code);
  closeLangPicker();
  // Mark selected
  document.querySelectorAll('.lang-hdr-item').forEach(el =>
    el.classList.toggle('selected', el.dataset.code === code)
  );
  document.getElementById('lang-hdr-label').textContent = LANG_LABELS[code] || code.toUpperCase();
}
document.addEventListener('click', e => {
  if (openNavDropdown && !e.target.closest('.lp-nav-drop-wrap')) closeAllNavDropdowns();
  if (langPickerOpen && !e.target.closest('.lang-hdr-wrap')) closeLangPicker();
});
function updateMenuTheme() {
  const cur = document.body.dataset.theme;
  document.querySelectorAll('.menu-theme-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.theme === cur || (cur === 'warm' && !b.dataset.theme))
  );
}
document.addEventListener('click', e => {
  if (menuOpen && !e.target.closest('.menu-wrap')) closeMenu();
});

/* ── Auth / User accounts ───────────────────────────────── */
let authToken = null;
let authUser  = null;

function updateGreeting() {
  const title = document.querySelector('#def-placeholder .placeholder-title');
  if (title) title.textContent = 'A word will appear here';
}

function updateAcctBtn() {
  const btn = document.getElementById('acct-btn');
  if (authUser) {
    btn.textContent = (authUser.name || authUser.email)[0].toUpperCase();
    btn.classList.add('signed-in');
    btn.title = authUser.email;
  } else {
    btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
    btn.classList.remove('signed-in');
    btn.title = 'Sign in';
  }
  updateGreeting();
  // The word bank is an account feature — hide its header chip when signed out.
  const wbBtn = document.querySelector('.wb-header-btn');
  if (wbBtn) wbBtn.style.display = authUser ? '' : 'none';
}

function openAuthModal(fromAnalyze) {
  const modal = document.getElementById('auth-modal');
  modal.classList.remove('hidden');
  const prompt = document.getElementById('auth-prompt');
  if (prompt) prompt.style.display = fromAnalyze ? '' : 'none';
  if (authUser) {
    document.getElementById('auth-signed-out').style.display = 'none';
    const si = document.getElementById('auth-signed-in');
    si.style.display = 'flex';
    document.getElementById('auth-avatar').textContent       = (authUser.name || authUser.email)[0].toUpperCase();
    document.getElementById('auth-profile-name').textContent = authUser.name || '—';
    document.getElementById('auth-profile-email').textContent = authUser.email;
    // Word bank count
    const wbEl = document.getElementById('ap-wb-count');
    if (wbEl) wbEl.textContent = wordBank.length ? `${wordBank.length} word${wordBank.length !== 1 ? 's' : ''} →` : 'Empty →';
    // Current mode
    const modeEl = document.getElementById('ap-mode-val');
    if (modeEl) modeEl.textContent = currentModel ? (currentModel.charAt(0).toUpperCase() + currentModel.slice(1)) : '—';
    // Fetch live plan + usage and populate
    _populateAccountPanel();
    // Family-plan panel (silently no-op for solo users)
    loadFamilyPanel();
  } else {
    document.getElementById('auth-signed-out').style.display = '';
    document.getElementById('auth-signed-in').style.display  = 'none';
    switchAuthTab(fromAnalyze ? 'register' : 'login');
  }
}

/* ── Family-plan panel inside the account modal ─────────────────────
   Renders three states:
     - solo  → hidden (user is on monthly/yearly Pro or free)
     - owner → seat usage + member list + invite form
     - member → "you're on X's family plan" note
   The panel is silent for solo users; only owners and members see it. */
async function loadFamilyPanel() {
  const section = document.getElementById('ap-family-section');
  const content = document.getElementById('ap-family-content');
  if (!section || !content) return;
  const token = localStorage.getItem('lexio_token');
  if (!token) { section.style.display = 'none'; return; }
  let info;
  try {
    const r = await fetch('/family/info', { headers: { 'Authorization': 'Bearer ' + token } });
    if (!r.ok) { section.style.display = 'none'; return; }
    info = await r.json();
  } catch { section.style.display = 'none'; return; }

  if (info.role === 'solo') {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';

  if (info.role === 'member') {
    const owner = info.owner_name || info.owner_email || 'the plan owner';
    content.innerHTML =
      '<p class="ap-family-member-note">You\'re on <strong>' +
      _escape(owner) +
      '</strong>\'s Lexio Family plan — Pro features are unlocked for you.</p>';
    return;
  }

  // Owner view
  const seats = info.seats || 4;
  const used  = info.used  || 1;
  const members = info.members || [];
  const pending = info.pending || [];
  const meEmail = (authUser && authUser.email) || '';

  let html = '<div class="ap-family-seats"><strong>' + used + ' of ' + seats + '</strong> seats used</div>';
  html += '<div class="ap-family-list">';
  // Owner row
  html += '<div class="ap-family-row you">' +
    '<span class="ap-family-row-email">' + _escape(meEmail) + '</span>' +
    '<span class="ap-family-row-tag">You · owner</span>' +
    '</div>';
  members.forEach(m => {
    html += '<div class="ap-family-row">' +
      '<span class="ap-family-row-email">' + _escape(m.email) + '</span>' +
      '<button class="ap-family-remove" title="Remove from plan" onclick="removeFamilyMember(' + (m.id || 0) + ', \'' + _escape(m.email).replace(/\'/g, '\\\'') + '\')">×</button>' +
      '</div>';
  });
  html += '</div>';

  pending.forEach(p => {
    html += '<p class="ap-family-pending">Invitation pending for ' + _escape(p.email) + '</p>';
  });

  const remaining = seats - used - (pending ? pending.length : 0);
  if (remaining > 0) {
    html +=
      '<form class="ap-family-invite-form" onsubmit="return inviteFamilyMember(event)">' +
        '<input type="email" id="ap-family-invite-email" placeholder="invite by email" required autocomplete="off">' +
        '<button type="submit" id="ap-family-invite-btn">Invite</button>' +
      '</form>';
  }
  html += '<div class="ap-family-status" id="ap-family-status"></div>';

  content.innerHTML = html;
}

function _escape(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function inviteFamilyMember(ev) {
  if (ev && ev.preventDefault) ev.preventDefault();
  const input = document.getElementById('ap-family-invite-email');
  const btn   = document.getElementById('ap-family-invite-btn');
  const stat  = document.getElementById('ap-family-status');
  const token = localStorage.getItem('lexio_token');
  if (!input || !token) return false;
  const email = (input.value || '').trim();
  if (!email) return false;
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
  if (stat) { stat.className = 'ap-family-status'; stat.textContent = ''; }
  try {
    const r = await fetch('/family/invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ email }),
    });
    const j = await r.json().catch(() => ({}));
    if (r.ok) {
      if (stat) { stat.className = 'ap-family-status ok'; stat.textContent = 'Invitation sent to ' + email; }
      input.value = '';
      // Refresh panel
      setTimeout(loadFamilyPanel, 800);
    } else {
      const msg = (j.detail && j.detail.message) || (j.detail && j.detail.code) || 'Could not send the invitation.';
      if (stat) { stat.className = 'ap-family-status err'; stat.textContent = msg; }
    }
  } catch {
    if (stat) { stat.className = 'ap-family-status err'; stat.textContent = 'Network error.'; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Invite'; }
  }
  return false;
}

async function removeFamilyMember(memberId, email) {
  if (!memberId) return;
  if (!confirm('Remove ' + (email || 'this member') + ' from your family plan?')) return;
  const token = localStorage.getItem('lexio_token');
  if (!token) return;
  try {
    const r = await fetch('/family/member/' + memberId, {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + token },
    });
    if (r.ok) loadFamilyPanel();
  } catch {}
}

async function _populateAccountPanel() {
  const token = localStorage.getItem('lexio_token');
  if (!token) return;
  const hdrs = { Authorization: 'Bearer ' + token };
  try {
    const [proRes, usageRes] = await Promise.all([
      fetch('/api/pro-status', { headers: hdrs }),
      fetch('/api/usage',      { headers: hdrs }),
    ]);
    if (!proRes.ok || !usageRes.ok) return;
    const pro   = await proRes.json();
    const usage = await usageRes.json();

    // Show the "View your Lexio year" recap link in the footer for any
    // Pro user (paid or trial). The link goes to /recap which renders
    // the personal year-in-review.
    const recapLink = document.getElementById('ap-recap-link');
    if (recapLink) recapLink.style.display = (pro.is_pro || pro.is_trial) ? '' : 'none';

    // ── Plan card ────────────────────────────────────────────
    const badge   = document.querySelector('#ap-plan-card .ap-plan-badge');
    const desc    = document.getElementById('ap-plan-desc');
    const btn     = document.getElementById('ap-plan-btn');
    const usageSec = document.getElementById('ap-usage-section');

    if (pro.is_pro && !pro.is_trial) {
      // Paid Pro
      badge.className = 'ap-plan-badge pro';
      badge.textContent = '✦ Pro';
      desc.textContent  = 'Unlimited lookups, all modes, word bank sync.';
      btn.textContent   = 'Manage subscription →';
      btn.className     = 'ap-plan-action manage';
      btn.onclick       = () => { closeAuthModal(); handleManageSub(); };
      if (usageSec) usageSec.style.display = 'none';
    } else if (pro.is_trial) {
      // Trial
      const d = pro.trial_days_left;
      badge.className   = 'ap-plan-badge trial';
      badge.textContent = `⏳ Trial · ${d} day${d !== 1 ? 's' : ''} left`;
      desc.textContent  = 'Enjoying full Pro access. Card on file — will charge after the trial. Manage anytime.';
      btn.textContent   = 'Manage subscription →';
      btn.className     = 'ap-plan-action manage';
      btn.onclick       = () => { closeAuthModal(); handleManageSub(); };
      if (usageSec) usageSec.style.display = 'none';
    } else {
      // Free
      badge.className   = 'ap-plan-badge free';
      badge.textContent = 'Free';
      desc.textContent  = '20 lookups & 3 OCR scans per month.';
      btn.textContent   = 'Get Pro →';
      btn.className     = 'ap-plan-action upgrade';
      btn.onclick       = () => { closeAuthModal(); handleProCta(); };
      if (usageSec) usageSec.style.display = '';
      // Usage bars
      if (!usage.is_pro) {
        const lu = usage.lookup.used, ll = usage.lookup.limit;
        const ou = usage.ocr.used,   ol = usage.ocr.limit;
        const lPct = Math.min(100, Math.round(lu / ll * 100));
        const oPct = Math.min(100, Math.round(ou / ol * 100));
        const lookupBar = document.getElementById('ap-lookup-bar');
        const ocrBar    = document.getElementById('ap-ocr-bar');
        document.getElementById('ap-lookup-num').textContent = `${lu} / ${ll}`;
        document.getElementById('ap-ocr-num').textContent    = `${ou} / ${ol}`;
        if (lookupBar) { lookupBar.style.width = lPct + '%'; lookupBar.classList.toggle('danger', lPct >= 80); }
        if (ocrBar)    { ocrBar.style.width    = oPct + '%'; ocrBar.classList.toggle('danger',    oPct >= 80); }
      }
    }
  } catch (_) { /* fail silently — panel still shows static info */ }
}
function closeAuthModal() {
  document.getElementById('auth-modal').classList.add('hidden');
  document.getElementById('auth-error').classList.add('hidden');
  document.getElementById('auth-email').value = '';
  document.getElementById('auth-password').value = '';
  document.getElementById('auth-name').value = '';
  const prompt = document.getElementById('auth-prompt');
  if (prompt) prompt.style.display = 'none';
}

function switchAuthTab(tab) {
  // Preserve email value across tab switches
  const emailEl = document.getElementById('auth-email');
  const savedEmail = emailEl ? emailEl.value : '';
  document.getElementById('tab-login').classList.toggle('active', tab === 'login');
  document.getElementById('tab-register').classList.toggle('active', tab === 'register');
  document.getElementById('auth-name-field').style.display = tab === 'register' ? '' : 'none';
  document.getElementById('auth-submit').textContent = tab === 'register' ? 'Create account' : 'Sign in';
  document.getElementById('auth-submit').dataset.tab = tab;
  document.getElementById('auth-error').classList.add('hidden');
  const pwdInput = document.getElementById('auth-password');
  pwdInput.autocomplete = tab === 'register' ? 'new-password' : 'current-password';
  // Restore email after tab switch
  if (emailEl && savedEmail) emailEl.value = savedEmail;
}

async function submitAuth() {
  const tab   = document.getElementById('auth-submit').dataset.tab || 'login';
  const email = document.getElementById('auth-email').value.trim();
  const pwd   = document.getElementById('auth-password').value;
  const name  = document.getElementById('auth-name').value.trim();
  const errEl = document.getElementById('auth-error');
  const btn   = document.getElementById('auth-submit');

  errEl.classList.add('hidden');
  if (!email || !pwd) { errEl.textContent = 'Please fill in all fields.'; errEl.classList.remove('hidden'); return; }
  if (tab === 'register' && pwd.length < 8) { errEl.textContent = 'Password must be at least 8 characters.'; errEl.classList.remove('hidden'); return; }

  btn.disabled = true;
  btn.textContent = '…';

  const endpoint = tab === 'register' ? '/auth/register' : '/auth/login';
  const body = tab === 'register' ? { email, password: pwd, name: name || undefined } : { email, password: pwd };

  try {
    const res  = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Something went wrong.');
    authToken = data.token;
    authUser  = data.user;
    try { localStorage.setItem('lexio_token', authToken); localStorage.setItem('lexio_user', JSON.stringify(authUser)); } catch {}
    updateAcctBtn();
    closeAuthModal();
    syncWordBank();
    const isDesktop = new URLSearchParams(location.search).has('desktop_auth');
    _maybeRedirectDesktop(authToken, authUser);
    if (!isDesktop) window.location.reload();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = tab === 'register' ? 'Create account' : 'Sign in';
  }
}

function signOut() {
  authToken = null; authUser = null;
  try {
    localStorage.removeItem('lexio_token');
    localStorage.removeItem('lexio_user');
    // Word bank is account-scoped — purge so the next user on this device
    // doesn't inherit the previous user's saved words.
    localStorage.removeItem(WB_KEY);
    // Model preference too — Pro-only modes shouldn't persist across sign-outs.
    localStorage.removeItem('lexio_model');
  } catch {}
  wordBank = [];
  // Reset Pro state and re-lock Balanced / Deep
  _userIsPro = false;
  setModel('fast');
  if (typeof _lockProModels === 'function') _lockProModels();
  // Hide Pro/Trial header badges
  const proBadge   = document.getElementById('pro-header-badge');
  const trialBadge = document.getElementById('trial-header-badge');
  if (proBadge)   proBadge.style.display   = 'none';
  if (trialBadge) trialBadge.style.display = 'none';
  updateAcctBtn();
  updateWBBadge();
  if (typeof renderWordBank === 'function') { try { renderWordBank(); } catch {} }
  closeAuthModal();
  // Reload so the whole UI resets cleanly to the signed-out state.
  window.location.reload();
}

/* ── Forgot / Reset password ────────────────────────────────── */
function openForgotPassword() {
  closeAuthModal();
  document.getElementById('forgot-modal').classList.remove('hidden');
  document.getElementById('forgot-email').value = document.getElementById('auth-email').value || '';
  document.getElementById('forgot-error').classList.add('hidden');
  document.getElementById('forgot-success').classList.add('hidden');
  document.getElementById('forgot-submit').disabled = false;
}
function closeForgotPassword() {
  document.getElementById('forgot-modal').classList.add('hidden');
}
async function submitForgotPassword() {
  const email = document.getElementById('forgot-email').value.trim();
  const errEl = document.getElementById('forgot-error');
  const okEl  = document.getElementById('forgot-success');
  errEl.classList.add('hidden');
  okEl.classList.add('hidden');
  if (!email) { errEl.textContent = 'Please enter your email.'; errEl.classList.remove('hidden'); return; }
  document.getElementById('forgot-submit').disabled = true;
  try {
    await fetch('/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
  } catch {}
  okEl.classList.remove('hidden');
}

let _resetToken = null;
function _checkResetToken() {
  const params = new URLSearchParams(location.search);
  _resetToken = params.get('token');
  if (_resetToken && location.pathname === '/reset-password') {
    document.getElementById('reset-modal').classList.remove('hidden');
  }
}
async function submitResetPassword() {
  const pw  = document.getElementById('reset-password').value;
  const pw2 = document.getElementById('reset-password2').value;
  const errEl = document.getElementById('reset-error');
  const okEl  = document.getElementById('reset-success');
  errEl.classList.add('hidden');
  okEl.classList.add('hidden');
  if (pw.length < 8) { errEl.textContent = 'Password must be at least 8 characters.'; errEl.classList.remove('hidden'); return; }
  if (pw !== pw2)    { errEl.textContent = 'Passwords do not match.'; errEl.classList.remove('hidden'); return; }
  document.getElementById('reset-submit').disabled = true;
  try {
    const r = await fetch('/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: _resetToken, password: pw }),
    });
    const d = await r.json();
    if (!r.ok) { errEl.textContent = d.detail || 'Something went wrong.'; errEl.classList.remove('hidden'); document.getElementById('reset-submit').disabled = false; return; }
    // Auto sign-in with the new token
    authToken = d.token;
    if (d.user) { authUser = d.user; try { localStorage.setItem('lexio_token', d.token); localStorage.setItem('lexio_user', JSON.stringify(d.user)); } catch {} }
    okEl.classList.remove('hidden');
    document.getElementById('reset-submit').style.display = 'none';
    updateAcctBtn();
    setTimeout(() => { document.getElementById('reset-modal').classList.add('hidden'); history.replaceState({}, '', '/'); }, 2000);
  } catch { errEl.textContent = 'Network error. Please try again.'; errEl.classList.remove('hidden'); document.getElementById('reset-submit').disabled = false; }
}

/* ── Gumroad ────────────────────────────────────────────────── */
let _payhipUrl = null;

/* ── OAuth Sign-in (Google) ──────────────────────────────────── */
let _googleClientId = null;

async function initOAuthProviders() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    const cfg = await res.json();
    _googleClientId = cfg.google_client_id || null;

    _payhipUrl = cfg.payhip_url || null;

    if (!_googleClientId) return;
    // Show the button as soon as we have the client ID — no GSI dependency
    const wrap = document.getElementById('oauth-btn-wrap');
    if (wrap) wrap.style.display = 'flex';
  } catch {}
}

function triggerGoogleSignIn() {
  if (!_googleClientId) return;
  const nonce = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now();
  // Store nonce so we can verify it matches the claim inside the returned id_token
  try { sessionStorage.setItem('google_oauth_nonce', nonce); } catch {}
  const params = new URLSearchParams({
    client_id:     _googleClientId,
    redirect_uri:  location.origin + '/google-callback.html',
    response_type: 'id_token',
    scope:         'openid email profile',
    nonce:         nonce,
    prompt:        'select_account',
  });
  const url = 'https://accounts.google.com/o/oauth2/v2/auth?' + params;
  const w = 520, h = 620;
  const left = Math.max(0, Math.round((screen.width  - w) / 2));
  const top  = Math.max(0, Math.round((screen.height - h) / 2));
  const popup = window.open(url, 'google-oauth',
    `width=${w},height=${h},left=${left},top=${top},scrollbars=yes,resizable=yes`);
  if (!popup) { window.location.href = url; return; } // popup blocked → redirect
  const handler = async (e) => {
    if (e.origin !== location.origin || e.data?.type !== 'google-credential') return;
    window.removeEventListener('message', handler);
    try { popup.close(); } catch {}
    // Retrieve and clear the stored nonce before sending to backend
    let storedNonce = null;
    try { storedNonce = sessionStorage.getItem('google_oauth_nonce'); sessionStorage.removeItem('google_oauth_nonce'); } catch {}
    await _oauthSignIn('/auth/google', { credential: e.data.credential, nonce: storedNonce });
  };
  window.addEventListener('message', handler);
}


/* ── Shared OAuth completion ─────────────────────────────────── */
async function _oauthSignIn(endpoint, body) {
  const errEl = document.getElementById('auth-error');
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Sign-in failed');
    authToken = data.token;
    authUser  = data.user;
    try {
      localStorage.setItem('lexio_token', authToken);
      localStorage.setItem('lexio_user', JSON.stringify(authUser));
    } catch {}
    updateAcctBtn();
    closeAuthModal();
    syncWordBank();
    const isDesktop = new URLSearchParams(location.search).has('desktop_auth');
    _maybeRedirectDesktop(authToken, authUser);
    if (!isDesktop) window.location.reload();
  } catch(e) {
    if (errEl) { errEl.textContent = e.message; errEl.classList.remove('hidden'); }
  }
}

async function syncWordBank() {
  if (!authToken) return;
  try {
    const res  = await fetch('/wordbank/sync', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
      body:    JSON.stringify({ entries: wordBank }),
    });
    // 402 = free-tier user — sync is now Pro-only. Silently skip; the word
    // bank still works locally. We don't pop the upgrade modal on background
    // sync attempts (only on user-initiated actions).
    if (res.status === 402) {
      _wbSyncIsProOnly = true;
      const ind = document.getElementById('wb-sync-indicator');
      if (ind) ind.textContent = 'Local only';
      return;
    }
    if (!res.ok) return;
    _wbSyncIsProOnly = false;
    const data = await res.json();
    // Merge: server is source of truth — always pull server words down even if local is empty
    if (data.entries && data.entries.length > 0) {
      const localKeys = new Set(wordBank.map(e => e.word.toLowerCase()));
      data.entries.forEach(e => {
        if (!localKeys.has(e.word.toLowerCase())) wordBank.unshift(e);
      });
      saveWordBank(); updateWBBadge();
    }
    const ind = document.getElementById('wb-sync-indicator');
    if (ind) ind.textContent = 'Synced across devices';
    // Refresh word bank count in account panel if open
    const wbEl = document.getElementById('ap-wb-count');
    if (wbEl) wbEl.textContent = wordBank.length ? `${wordBank.length} word${wordBank.length !== 1 ? 's' : ''} →` : 'Empty →';
  } catch {}
}
let _wbSyncIsProOnly = false;

/* ── Trending words ─────────────────────────────────────────── */
(function loadTrending() {
  const CACHE_KEY = 'lexio_trending';
  const CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours in ms

  async function fetchAndRender() {
    // Check localStorage cache first
    try {
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
      if (cached && Date.now() - cached.ts < CACHE_TTL) {
        render(cached.data);
        return;
      }
    } catch {}

    try {
      const res  = await fetch('/stats/top-words');
      if (!res.ok) throw new Error();
      const data = await res.json();
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data })); } catch {}
      render(data);
    } catch {
      // Server unreachable — hide skeleton, show nothing
      document.getElementById('trending-skeleton').classList.add('hidden');
    }
  }

  function render(data) {
    const skeleton = document.getElementById('trending-skeleton');
    const list     = document.getElementById('trending-list');
    const empty    = document.getElementById('trending-empty');
    const monthEl  = document.getElementById('trending-month');

    skeleton.classList.add('hidden');

    if (monthEl && data.month) {
      // data.month is like "JUNE 2026" — show just the month name, title-cased.
      const mn = String(data.month).split(' ')[0];
      monthEl.textContent = mn.charAt(0) + mn.slice(1).toLowerCase();
    }

    if (!data.words || data.words.length === 0) {
      empty.classList.remove('hidden');
      return;
    }

    const topWords = data.words.slice(0, 5);
    const maxCount = topWords[0].count || 1;
    list.innerHTML = topWords.map((w, i) => `
      <div class="lp-trending-item" data-word="${_escape(w.word)}" onclick="prefillWord(this.dataset.word)">
        <div class="lp-trending-rank">${i + 1}</div>
        <div class="lp-trending-word">${escHtml(w.word)}</div>
        <div class="lp-trending-bar-wrap">
          <div class="lp-trending-bar" style="width:${Math.round(w.count / maxCount * 100)}%"></div>
        </div>
        <div class="lp-trending-count">${w.count.toLocaleString()} ${w.count === 1 ? 'lookup' : 'lookups'}</div>
      </div>
    `).join('');

    list.classList.remove('hidden');
  }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  fetchAndRender();
})();

function prefillWord(word) {
  if (!toolOnThisPage()) {
    window.location.href = '/app?word=' + encodeURIComponent(word);
    return;
  }
  // Scroll to app, fill a sample sentence so the user can immediately click the word
  window.scrollTo({ top: 0, behavior: 'smooth' });
  const ta = document.getElementById('input-text');
  if (!ta.value) {
    ta.value = `The word "${word}" is used in many interesting contexts.`;
    updateCharCount && updateCharCount();
  }
}

// Restore session on load
(function restoreAuth() {
  try {
    const tok  = localStorage.getItem('lexio_token');
    const usr  = localStorage.getItem('lexio_user');
    if (tok && usr) {
      authToken = tok;
      authUser  = JSON.parse(usr);
    }
  } catch {}
  updateAcctBtn();
  if (authToken) setTimeout(syncWordBank, 1000);
})();

/* ── Init ───────────────────────────────────────────────────── */
loadWordBank(); loadTweaks(); applyTweaks(); updateWBBadge();
startPlaceholderRotation(); setupDragAndDrop(); checkPermalink();

// Scroll cue: the down-chevrons sit at the bottom of the empty landing
// state to signal "there's more below". They're visible at rest and
// retire permanently the first time the user scrolls — by then the user
// plainly knows they can scroll, and a one-way dismiss means the cue
// never flickers back or collides with the landing copy as it scrolls up.
//
// NB: we deliberately do NOT key this to the hero headline coming into
// view. On a phone the hero already sits within (or just below) the first
// viewport and the layout shifts as the carousel/fonts settle, so an
// IntersectionObserver fires on load and kills the cue before it's seen.
(function() {
  const nudge = document.getElementById('scroll-nudge');
  if (!nudge) return;
  function dismiss() {
    nudge.classList.add('hidden');
    window.removeEventListener('scroll', onScroll);
  }
  function onScroll() {
    if (window.scrollY > 24) dismiss();
  }
  window.addEventListener('scroll', onScroll, { passive: true });
})();

// Compact mode — Electron desktop overlay
if (new URLSearchParams(window.location.search).get('compact') === '1') {
  document.body.classList.add('compact');
}

// Full native app mode — Electron full app
if (new URLSearchParams(window.location.search).get('app') === '1') {
  document.body.classList.add('in-app');
}

// ── Web routing: split the marketing landing ("/") from the tool ("/app") ──
// Only applies to the normal web build; Electron loads with ?app=1 / ?compact=1
// and keeps its own full-app layout untouched.
(function routePage() {
  const sp = new URLSearchParams(window.location.search);
  if (sp.get('app') === '1' || sp.get('compact') === '1') return;
  const path = window.location.pathname.replace(/\/+$/, '') || '/';
  const isTool = path === '/app';
  document.body.classList.add(isTool ? 'tool-page' : 'landing-page');

  // On the tool page, honour preload params handed over by landing CTAs.
  if (isTool) {
    window.addEventListener('load', () => {
      const go = sp.get('go');
      const passage = sp.get('passage');
      const word = sp.get('word');
      try {
        if (go === 'sample' && typeof tryHeroSample === 'function') tryHeroSample();
        else if (passage !== null && typeof loadTryPassage === 'function') loadTryPassage(parseInt(passage, 10));
        else if (word && typeof prefillWord === 'function') prefillWord(word);
      } catch (e) { /* non-fatal: tool still usable */ }
    });
  }
})();

// ── App compact / try-passage carousel / scroll progress / back-to-top ──────

/* Compact-mode: shrink <main> when empty so the carousel is visible below.
   Grow back to full viewport height when user has input, results, or focus. */
function updateAppCompact() {
  const ta = document.getElementById('input-text');
  const tv = document.getElementById('token-view');
  const hasInput  = ta && ta.value && ta.value.trim().length > 0;
  const hasResult = tv && !tv.classList.contains('hidden');
  const focused   = document.activeElement === ta;
  const compact = !(hasInput || hasResult || focused);
  document.body.classList.toggle('app-compact', compact);
}

/* Sample literary passages — short, famous openings. Click a card to load
   into the textarea. */
const TRY_PASSAGES = [
  {
    author: 'F. Scott Fitzgerald',
    title:  'The Great Gatsby',
    excerpt: 'In my younger and more vulnerable years my father gave me some advice that I\'ve been turning over in my mind ever since.',
    text: 'In my younger and more vulnerable years my father gave me some advice that I\'ve been turning over in my mind ever since. "Whenever you feel like criticizing anyone," he told me, "just remember that all the people in this world haven\'t had the advantages that you\'ve had." He didn\'t say any more, but we\'ve always been unusually communicative in a reserved way, and I understood that he meant a great deal more than that. In consequence, I\'m inclined to reserve all judgments, a habit that has opened up many curious natures to me and also made me the victim of not a few veteran bores.'
  },
  {
    author: 'Franz Kafka',
    title:  'The Metamorphosis',
    excerpt: 'When Gregor Samsa woke one morning from uneasy dreams, he found himself transformed into a monstrous vermin.',
    text: 'When Gregor Samsa woke one morning from uneasy dreams, he found himself transformed in his bed into a monstrous vermin. He lay on his armour-hard back and saw, as he lifted his head a little, his domed, brown belly, divided by stiff arched segments, on top of which the bed-quilt could hardly keep in position and was about to slide off completely. His numerous legs, pathetically thin in comparison to the rest of his bulk, flickered helplessly before his eyes.'
  },
  {
    author: 'Virginia Woolf',
    title:  'Mrs Dalloway',
    excerpt: 'Mrs. Dalloway said she would buy the flowers herself. For Lucy had her work cut out for her.',
    text: 'Mrs. Dalloway said she would buy the flowers herself. For Lucy had her work cut out for her. The doors would be taken off their hinges; Rumpelmayer\'s men were coming. And then, thought Clarissa Dalloway, what a morning—fresh as if issued to children on a beach. What a lark! What a plunge! For so it had always seemed to her when, with a little squeak of the hinges, which she could hear now, she had burst open the French windows and plunged at Bourton into the open air.'
  },
  {
    author: 'Jane Austen',
    title:  'Pride and Prejudice',
    excerpt: 'It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.',
    text: 'It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife. However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered the rightful property of some one or other of their daughters.'
  },
  {
    author: 'George Orwell',
    title:  '1984',
    excerpt: 'It was a bright cold day in April, and the clocks were striking thirteen.',
    text: 'It was a bright cold day in April, and the clocks were striking thirteen. Winston Smith, his chin nuzzled into his breast in an effort to escape the vile wind, slipped quickly through the glass doors of Victory Mansions, though not quickly enough to prevent a swirl of gritty dust from entering along with him.'
  },
  {
    author: 'Leo Tolstoy',
    title:  'Anna Karenina',
    excerpt: 'Happy families are all alike; every unhappy family is unhappy in its own way.',
    text: 'Happy families are all alike; every unhappy family is unhappy in its own way. Everything was in confusion in the Oblonskys\' house. The wife had discovered that the husband was carrying on an intrigue with a French girl, who had been a governess in their family, and she had announced to her husband that she could not go on living in the same house with him.'
  },
  {
    author: 'Albert Camus',
    title:  'The Stranger',
    excerpt: 'Mother died today. Or, maybe, yesterday; I can\'t be sure.',
    text: 'Mother died today. Or, maybe, yesterday; I can\'t be sure. The telegram from the Home says: YOUR MOTHER PASSED AWAY. FUNERAL TOMORROW. DEEP SYMPATHY. Which leaves the matter doubtful; it could have been yesterday.'
  },
  {
    author: 'Gabriel García Márquez',
    title:  'One Hundred Years of Solitude',
    excerpt: 'Many years later, as he faced the firing squad, Colonel Aureliano Buendía was to remember that distant afternoon when his father took him to discover ice.',
    text: 'Many years later, as he faced the firing squad, Colonel Aureliano Buendía was to remember that distant afternoon when his father took him to discover ice. At that time Macondo was a village of twenty adobe houses, built on the bank of a river of clear water that ran along a bed of polished stones, which were white and enormous, like prehistoric eggs.'
  },
  {
    author: 'Herman Melville',
    title:  'Moby-Dick',
    excerpt: 'Call me Ishmael. Some years ago—never mind how long precisely—having little or no money in my purse, and nothing particular to interest me on shore, I thought I would sail about a little.',
    text: 'Call me Ishmael. Some years ago—never mind how long precisely—having little or no money in my purse, and nothing particular to interest me on shore, I thought I would sail about a little and see the watery part of the world. It is a way I have of driving off the spleen, and regulating the circulation.'
  },
  {
    author: 'Vladimir Nabokov',
    title:  'Lolita',
    excerpt: 'Lolita, light of my life, fire of my loins. My sin, my soul.',
    text: 'Lolita, light of my life, fire of my loins. My sin, my soul. Lo-lee-ta: the tip of the tongue taking a trip of three steps down the palate to tap, at three, on the teeth. Lo. Lee. Ta. She was Lo, plain Lo, in the morning, standing four feet ten in one sock.'
  },
];

function renderTryPassages() {
  const track = document.getElementById('try-grid');
  if (!track) return;
  // Render each passage TWICE in sequence so the -50% translate
  // in the keyframe loops seamlessly back to start.
  const cardHtml = (p, i) => `
    <button class="try-card" type="button" onclick="loadTryPassage(${i})">
      <span class="try-card-author">${p.author}</span>
      <span class="try-card-title">${p.title}</span>
      <span class="try-card-excerpt">${p.excerpt}</span>
    </button>
  `;
  const once = TRY_PASSAGES.map(cardHtml).join('');
  track.innerHTML = once + once;
}

function loadTryPassage(idx) {
  if (!toolOnThisPage()) {
    window.location.href = '/app?passage=' + idx;
    return;
  }
  const ta = document.getElementById('input-text');
  const p = TRY_PASSAGES[idx];
  if (!ta || !p) return;
  ta.value = p.text;
  updateAppCompact();
  // smooth-scroll back to the top so the input is centered
  window.scrollTo({ top: 0, behavior: 'smooth' });
  // allow the smooth-scroll to finish before focusing (focus jumps the page)
  setTimeout(() => { ta.focus(); ta.dispatchEvent(new Event('input', { bubbles: true })); }, 350);
}

// Scroll progress bar + back-to-top (rAF-throttled — no layout work
// on every scroll event; we coalesce to one update per animation frame).
function updateScrollUI() {
  const sp = document.getElementById('scroll-progress');
  const bt = document.getElementById('back-to-top');
  const doc = document.documentElement;
  const scrolled = doc.scrollTop || document.body.scrollTop;
  const max = Math.max(1, (doc.scrollHeight - doc.clientHeight));
  const pct = Math.min(100, (scrolled / max) * 100);
  if (sp) sp.style.width = pct + '%';
  if (bt) {
    bt.classList.toggle('visible', scrolled > 600);
    // Park the button just above the footer so it never covers footer content.
    const footer = document.querySelector('.lp-footer');
    if (footer) {
      const overlap = window.innerHeight - footer.getBoundingClientRect().top;
      bt.style.bottom = overlap > 0 ? (overlap + 24) + 'px' : '';
    }
  }
}
let _scrollRaf = null;
function scheduleScrollUI() {
  if (_scrollRaf !== null) return;
  _scrollRaf = requestAnimationFrame(() => {
    _scrollRaf = null;
    updateScrollUI();
  });
}

window.addEventListener('scroll', scheduleScrollUI, { passive: true });
window.addEventListener('resize', scheduleScrollUI);
document.addEventListener('DOMContentLoaded', () => {
  updateAppCompact();
  renderTryPassages();
  updateScrollUI();

  const ta = document.getElementById('input-text');
  if (ta) {
    ta.addEventListener('input', updateAppCompact);
    ta.addEventListener('focus', updateAppCompact);
    ta.addEventListener('blur',  updateAppCompact);
  }
});

// Restore language preference
try {
  const savedLang = localStorage.getItem('lexio_lang');
  if (savedLang) { currentLang = savedLang; document.getElementById('lang-select').value = savedLang; }
} catch {}

// Restore UI language
try {
  const savedUILang = localStorage.getItem('lexio_ui_lang');
  if (savedUILang && savedUILang !== 'en') setUILang(savedUILang);
  // Mark current language in the header picker
  document.querySelectorAll('.lang-hdr-item').forEach(el =>
    el.classList.toggle('selected', el.dataset.code === (savedUILang || 'en'))
  );
} catch {}

// Follow system dark-mode changes when Auto theme is active
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (isAutoTheme) setTheme('auto');
});

inputText.addEventListener('keydown', e => { if((e.ctrlKey||e.metaKey)&&e.key==='Enter') analyze(); });

document.addEventListener('keydown', e => {
  const tag = document.activeElement?.tagName;
  if (tag==='TEXTAREA'||tag==='INPUT') return;
  if (e.key==='Escape') { closeFlashcards(); closeWordBank(); closeDesktopModal(); closeAuthModal(); closeVerifyEmailModal(); closeMenu(); closeLangPicker(); closeAllNavDropdowns(); if(shortcutsOpen) toggleShortcuts(); }
  if (e.key==='?')  toggleShortcuts();
  if (e.key==='b'||e.key==='B') openWordBank();
});

document.getElementById('wb-overlay').addEventListener('click', e => { if(e.target===document.getElementById('wb-overlay')) closeWordBank(); });
document.getElementById('fc-overlay').addEventListener('click', e => { if(e.target===document.getElementById('fc-overlay')) closeFlashcards(); });
document.getElementById('shortcuts-overlay').addEventListener('click', e => { if(e.target===document.getElementById('shortcuts-overlay')) toggleShortcuts(); });
document.getElementById('desktop-modal').addEventListener('click', e => { if(e.target===document.getElementById('desktop-modal')) closeDesktopModal(); });
document.getElementById('auth-modal').addEventListener('click', e => { if(e.target===document.getElementById('auth-modal')) closeAuthModal(); });
// Enter key in auth inputs
['auth-email','auth-password','auth-name'].forEach(id => {
  document.getElementById(id)?.addEventListener('keydown', e => { if(e.key==='Enter') submitAuth(); });
});

// Init OAuth providers (Google + Apple)
initOAuthProviders();

// Check for password reset token in URL
_checkResetToken();

// Register the service worker for PWA / offline shell. Best-effort —
// disabled in dev or when not on HTTPS, and a missing /sw.js is fine.
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  });
}

// Show the warm-area divider only once the user has scrolled past the hero —
// hides the faint line under the passage carousel on first paint.
(function _initScrollDivider(){
  const SCROLL_THRESHOLD = 60;
  let ticking = false;
  function update(){
    document.body.classList.toggle('is-scrolled', window.scrollY > SCROLL_THRESHOLD);
    ticking = false;
  }
  window.addEventListener('scroll', () => {
    if (!ticking) { requestAnimationFrame(update); ticking = true; }
  }, { passive: true });
  update();
})();

// Init model selector
initializeModelSelector();

// Load usage + streak on page start
loadUsage();
loadStreak();

// Clean up URL if returning from Stripe checkout
if (new URLSearchParams(location.search).get('stripe') === 'success') {
  try { history.replaceState(null, '', '/'); } catch {}
  checkProStatus();
}

// Family-invite handoff: /family/accept stashes the token in sessionStorage
// and bounces here when the invitee isn't signed in. After they auth, we
// pick the token back up and complete the invitation acceptance.
(function _resumeFamilyInvite() {
  const params = new URLSearchParams(location.search);
  const wantsSignin = params.get('signin') === '1';
  const pending = sessionStorage.getItem('lexio_pending_family_invite');
  if (!pending) return;

  // If they have a token already (came back signed in), accept right away.
  const tryAccept = () => {
    const tok = localStorage.getItem('lexio_token');
    if (!tok) return false;
    fetch('/family/accept?token=' + encodeURIComponent(pending), {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + tok },
    }).then(r => {
      sessionStorage.removeItem('lexio_pending_family_invite');
      // Clean the ?signin=1 from the URL
      try { history.replaceState(null, '', '/?family=' + (r.ok ? 'ok' : 'err')); } catch {}
      if (r.ok && typeof checkProStatus === 'function') checkProStatus();
    }).catch(() => {
      sessionStorage.removeItem('lexio_pending_family_invite');
    });
    return true;
  };

  if (tryAccept()) return;

  // Otherwise pop the auth modal and retry once the user signs in.
  if (wantsSignin && typeof openAuthModal === 'function') {
    setTimeout(() => openAuthModal(false), 200);
  }
  // Watch for the auth token to appear (sign-in or sign-up completion).
  const poll = setInterval(() => {
    if (localStorage.getItem('lexio_token')) {
      clearInterval(poll);
      tryAccept();
    }
  }, 500);
  // Give up after 5 minutes so this isn't a forever-poll.
  setTimeout(() => clearInterval(poll), 5 * 60 * 1000);
})();

/* ── Pro section CTA ────────────────────────────────────── */
let _userIsPro = false;

// ── Email verification modal (Gap 4) ─────────────────────────────
//
// Opened when /stripe/create-checkout returns 403 with
// {error: "email_not_verified"}. After successful verification, optionally
// re-runs a callback (typically: resume the checkout flow).
let _verifyAfterCallback = null;
let _verifyResendCooldown = 0;

function openVerifyEmailModal(opts) {
  opts = opts || {};
  _verifyAfterCallback = typeof opts.afterVerify === 'function' ? opts.afterVerify : null;

  const modal   = document.getElementById('verify-email-modal');
  const subEl   = document.getElementById('verify-email-sub');
  const tgtEl   = document.getElementById('verify-email-target');
  const errEl   = document.getElementById('verify-email-error');
  const codeEl  = document.getElementById('verify-email-code');
  if (!modal) return;
  if (opts.message && subEl) subEl.textContent = opts.message;
  // Show which email we're verifying
  try {
    const user = JSON.parse(localStorage.getItem('lexio_user') || 'null');
    if (tgtEl) tgtEl.textContent = user && user.email ? user.email : '';
  } catch { /* ignore */ }
  if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
  if (codeEl) codeEl.value = '';
  modal.classList.remove('hidden');
  // Auto-trigger initial send so the user has a code waiting
  resendVerifyEmail({ silent: true });
  // Focus the input after the modal renders
  setTimeout(() => { codeEl && codeEl.focus(); }, 50);
}

function closeVerifyEmailModal() {
  const modal = document.getElementById('verify-email-modal');
  if (modal) modal.classList.add('hidden');
  _verifyAfterCallback = null;
}

async function resendVerifyEmail(opts) {
  opts = opts || {};
  const token = localStorage.getItem('lexio_token');
  if (!token) return;
  const btn = document.getElementById('verify-email-resend');
  // Soft client-side cooldown to keep users from spamming the resend
  const now = Date.now();
  if (now < _verifyResendCooldown) {
    if (btn) btn.textContent = 'Wait a moment before resending…';
    return;
  }
  _verifyResendCooldown = now + 25 * 1000;
  if (btn && !opts.silent) { btn.disabled = true; btn.textContent = 'Sending…'; }
  try {
    const r = await fetch('/auth/send-verification', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token },
    });

    try {
      const data = await r.clone().json();
      if (data && (data.auto_verified || data.already_verified)) {
        try {
          const u = JSON.parse(localStorage.getItem('lexio_user') || 'null');
          if (u) { u.email_verified = true; localStorage.setItem('lexio_user', JSON.stringify(u)); }
        } catch { /* ignore */ }
        const cb = _verifyAfterCallback;
        closeVerifyEmailModal();
        if (cb) setTimeout(cb, 60);
        return;
      }
    } catch { /* ignore non-JSON */ }

    if (btn && !opts.silent) {
      if (r.ok) { btn.textContent = 'Code sent — check your inbox'; }
      else      { btn.textContent = "Couldn't send — try again in a minute"; }
    }
  } catch {
    if (btn && !opts.silent) btn.textContent = 'Network error — try again';
  } finally {
    // Re-enable after a short pause regardless of outcome
    setTimeout(() => {
      const b = document.getElementById('verify-email-resend');
      if (b) { b.disabled = false; b.textContent = "Didn't get a code? Send a new one"; }
    }, 25 * 1000);
  }
}

async function submitVerifyEmail(ev) {
  ev.preventDefault();
  const codeEl = document.getElementById('verify-email-code');
  const errEl  = document.getElementById('verify-email-error');
  const submitBtn = document.getElementById('verify-email-submit');
  const token = localStorage.getItem('lexio_token');
  if (!token) { closeVerifyEmailModal(); return false; }
  const code = (codeEl.value || '').trim();
  if (!/^\d{4,10}$/.test(code)) {
    if (errEl) { errEl.textContent = 'Enter the 6-digit code from your email.'; errEl.style.display = 'block'; }
    return false;
  }
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Verifying…'; }
  if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
  try {
    const r = await fetch('/auth/verify-email', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + token,
        'Content-Type':  'application/json',
      },
      body: JSON.stringify({ code }),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      if (errEl) {
        errEl.textContent = (e && e.detail) || 'Verification failed. Please try again.';
        errEl.style.display = 'block';
      }
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Verify email'; }
      return false;
    }
    // Success — update cached user, close modal, run optional callback
    try {
      const u = JSON.parse(localStorage.getItem('lexio_user') || 'null');
      if (u) { u.email_verified = true; localStorage.setItem('lexio_user', JSON.stringify(u)); }
    } catch { /* ignore */ }
    const cb = _verifyAfterCallback;
    closeVerifyEmailModal();
    if (cb) setTimeout(cb, 60);
  } catch {
    if (errEl) { errEl.textContent = 'Network error — please try again.'; errEl.style.display = 'block'; }
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Verify email'; }
  }
  return false;
}

// ── Billing-cycle toggle (Monthly / Yearly) ──────────────────────
//
// _proPriceInfo is populated by the geo-localised price-info loader below
// and re-read by setProPlan() and handleProCta(). _proPlan is the user's
// current selection (defaults to monthly). The toggle only swaps the
// price display + period text — it doesn't trigger checkout.
let _proPlan = 'monthly';
let _proPriceInfo = null;   // { symbol, monthly_amount, yearly_amount, yearly_monthly_equiv, yearly_savings_pct, yearly_available }

function _renderProPrice() {
  if (!_proPriceInfo) return;
  const amtEl    = document.getElementById('lp-pro-amount');
  const periodEl = document.getElementById('lp-pro-period');
  const eqEl     = document.getElementById('lp-pro-period-eq');
  const anchorEl = document.getElementById('lp-pro-anchor');
  const ctaEl    = document.getElementById('lp-pro-btn');
  const sym = _proPriceInfo.symbol || '$';
  if (_proPlan === 'family' && _proPriceInfo.family_amount) {
    if (amtEl)    amtEl.textContent    = sym + _proPriceInfo.family_amount;
    if (periodEl) periodEl.textContent = '/month';
    if (eqEl) { eqEl.textContent = ''; eqEl.hidden = true; }
    if (anchorEl) {
      const seats = _proPriceInfo.family_seats || 4;
      anchorEl.textContent = 'Lexio Pro for ' + seats + ' people — one bill, one decision.';
    }
    if (ctaEl && !_userIsPro) ctaEl.textContent = 'Start family plan';
  } else if (_proPlan === 'yearly' && _proPriceInfo.yearly_amount) {
    if (amtEl)    amtEl.textContent    = sym + _proPriceInfo.yearly_amount;
    if (periodEl) periodEl.textContent = '/year';
    if (eqEl) {
      const eq = _proPriceInfo.yearly_monthly_equiv;
      eqEl.textContent = eq ? `≈ ${sym}${eq}/month — billed once a year` : '';
      eqEl.hidden = !eq;
    }
    if (anchorEl) anchorEl.textContent = 'Two paperbacks a year — and you’ll actually finish them.';
    if (ctaEl && !_userIsPro) ctaEl.textContent = 'Start 3-day free trial';
  } else {
    if (amtEl)    amtEl.textContent    = sym + (_proPriceInfo.monthly_amount || _proPriceInfo.amount || '');
    if (periodEl) periodEl.textContent = '/month';
    if (eqEl) { eqEl.textContent = ''; eqEl.hidden = true; }
    if (anchorEl) anchorEl.textContent = 'Less than one paperback a month — and you’ll actually finish them.';
    if (ctaEl && !_userIsPro) ctaEl.textContent = 'Start 3-day free trial';
  }
  // Mirror the (non-toggleable) FAQ price to whichever cycle is selected
  document.querySelectorAll('.lp-pro-amount-dynamic').forEach(el => {
    if (el.id === 'lp-pro-amount') return;   // header price handled above
    el.textContent = sym + (_proPriceInfo.monthly_amount || _proPriceInfo.amount || '');
  });
}

function setProPlan(plan) {
  if (plan === 'family' || plan === 'yearly') _proPlan = plan;
  else _proPlan = 'monthly';
  document.querySelectorAll('#lp-pro-toggle .lp-pro-toggle-btn').forEach(btn => {
    btn.setAttribute('aria-pressed', btn.dataset.plan === _proPlan ? 'true' : 'false');
  });
  // Reveal the per-cycle perks
  document.querySelectorAll('.lp-annual-only').forEach(el => {
    el.hidden = (_proPlan !== 'yearly');
  });
  document.querySelectorAll('.lp-family-only').forEach(el => {
    el.hidden = (_proPlan !== 'family');
  });
  _renderProPrice();
}

async function handleProCta() {
  const token = localStorage.getItem('lexio_token');
  if (!token) { openAuthModal?.(); return; }

  if (_userIsPro) {
    const lp = document.getElementById('lp-pro-btn');
    if (lp) { lp.textContent = 'Already Pro ✓'; lp.disabled = true; }
    return;
  }

  const btn = document.getElementById('lp-pro-btn');
  const origLabel = btn ? btn.textContent : '';
  if (btn) { btn.textContent = 'Redirecting…'; btn.disabled = true; }

  try {
    const r = await fetch('/stripe/create-checkout?plan=' + encodeURIComponent(_proPlan), {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token },
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      // Gap 4: handle email-not-verified by opening the verification modal
      // instead of just bubbling the message in an alert.
      const detail = e && e.detail;
      const errCode = detail && typeof detail === 'object' ? detail.error : null;
      if (r.status === 403 && errCode === 'email_not_verified') {
        if (btn) { btn.textContent = origLabel; btn.disabled = false; }
        openVerifyEmailModal({
          afterVerify: () => handleProCta(),
          message: (detail && detail.message) || 'Please verify your email before subscribing.',
        });
        return;
      }
      const msg = (typeof detail === 'string') ? detail
               : (detail && detail.message) || 'Could not start checkout. Please try again.';
      alert(msg);
      if (btn) { btn.textContent = origLabel || 'Start 3-day free trial'; btn.disabled = false; }
      return;
    }
    const { url } = await r.json();
    window.location.href = url;
  } catch {
    alert('Network error — please try again.');
    if (btn) { btn.textContent = origLabel || 'Get Pro →'; btn.disabled = false; }
  }
}

// ── Geo-localised Pro price (monthly + yearly) ───────────────────
(async function() {
  try {
    const r = await fetch('/stripe/price-info');
    if (!r.ok) return;
    const info = await r.json();
    _proPriceInfo = info;
    // Sync currency symbol on the free card
    document.querySelectorAll('.lp-free-symbol').forEach(el => {
      el.textContent = info.symbol || '$';
    });
    // Hide yearly toggle if the server hasn't been configured with a
    // yearly price yet (dev/preview boxes without STRIPE_PRICE_ID_YEARLY).
    const yearlyBtn = document.querySelector('#lp-pro-toggle .lp-pro-toggle-btn[data-plan="yearly"]');
    if (yearlyBtn && info.yearly_available === false) {
      yearlyBtn.style.display = 'none';
    }
    // Reveal the Family toggle when the server has the family price wired up
    const familyBtn = document.getElementById('lp-family-toggle-btn');
    if (familyBtn) {
      familyBtn.hidden = !info.family_available;
      const seatLbl = document.getElementById('lp-family-seats-label');
      if (seatLbl) seatLbl.textContent = (info.family_seats || 4) + ' seats';
    }
    // Update savings badge from the server-computed percentage
    const savePct = document.getElementById('lp-pro-save-pct');
    if (savePct && info.yearly_savings_pct) {
      savePct.textContent = 'save ' + info.yearly_savings_pct + '%';
    }
    _renderProPrice();
  } catch {}
})();

function _lockProModels() {
  document.querySelectorAll('.model-pill:not([data-model="fast"])').forEach(p => {
    // Don't use `disabled` — it suppresses clicks, but we still want clicks to
    // open the upgrade modal. Mark with a class instead and let `_selectMode`
    // gate the actual switch.
    p.disabled = false;
    p.classList.add('locked');
    p.title = 'Upgrade to Pro to unlock';
    p.style.opacity = '';
    p.style.cursor = '';
    // Reveal the inline PRO badge
    const badge = p.querySelector('.mode-menu-pro-badge');
    if (badge) badge.hidden = false;
  });
  // Update the dropdown footer to reflect free / anonymous tier limits
  const footer = document.getElementById('mode-menu-footer');
  if (footer) {
    const hasToken = !!localStorage.getItem('lexio_token');
    footer.innerHTML = hasToken
      ? 'Free tier · <strong>20 credits / hour</strong> · upgrade to Pro for Balanced &amp; Deep + 120/hr.'
      : 'Sign in for free credits, or upgrade to Pro for Balanced &amp; Deep + 120/hr.';
  }
  // Force fast for anonymous visitors immediately — covers the brief window
  // before checkProStatus resolves and prevents the UI showing "Deep" selected
  // from a stale localStorage entry.
  if (!localStorage.getItem('lexio_token') && currentModel !== 'fast') {
    setModel('fast');
  }
}
function _unlockProModels() {
  document.querySelectorAll('.model-pill').forEach(p => {
    p.disabled = false;
    p.classList.remove('locked');
    p.title = '';
    p.style.opacity = '';
    p.style.cursor = '';
    const badge = p.querySelector('.mode-menu-pro-badge');
    if (badge) badge.hidden = true;
  });
  // Restore Pro-budget footer
  const footer = document.getElementById('mode-menu-footer');
  if (footer) {
    footer.innerHTML = 'Pro budget · <strong>120 credits / hour</strong> · resets automatically.';
  }
}

// Lock pills immediately — unlock only if Pro is confirmed
_lockProModels();

async function checkProStatus() {
  const token = localStorage.getItem('lexio_token');
  if (!token) {
    // No auth — force fast for free guests
    if (currentModel !== 'fast') setModel('fast');
    return;
  }
  try {
    const r = await fetch('/api/pro-status', { headers: { 'Authorization': 'Bearer ' + token } });
    if (!r.ok) { if (currentModel !== 'fast') setModel('fast'); return; }
    const d = await r.json();
    _userIsPro = !!d.is_pro;
    const isPaidPro = _userIsPro && !d.is_trial;
    const isTrial   = !!d.is_trial;
    const daysLeft  = d.trial_days_left || 0;

    // Header badges
    const proBadge   = document.getElementById('pro-header-badge');
    const trialBadge = document.getElementById('trial-header-badge');
    if (proBadge)   proBadge.style.display   = isPaidPro ? '' : 'none';
    if (trialBadge) {
      trialBadge.style.display = isTrial ? '' : 'none';
      if (isTrial) trialBadge.textContent = daysLeft > 1 ? `TRIAL · ${daysLeft}d` : 'TRIAL · last day';
    }

    if (_userIsPro) {
      _unlockProModels();
      // Swap the entire Pro section into "subscription" mode for current
      // subscribers (paid Pro or active trial) — no upsell, no feature flex,
      // no pricing toggle: just plan summary + manage.
      const grid       = document.getElementById('lp-pro-grid');
      const thanks     = document.getElementById('lp-pro-thanks');
      const toggle     = document.getElementById('lp-pro-toggle');
      const refund     = document.querySelector('.lp-pro-refund');
      const secTitle   = document.getElementById('lp-pro-title');
      const secSub     = document.getElementById('lp-pro-sub');

      if (grid)   grid.style.display   = 'none';
      if (thanks) thanks.style.display = '';
      if (toggle) toggle.style.display = 'none';
      if (refund) refund.style.display = 'none';

      // (#5) Subscribers see their subscription card under the tool on /app;
      // on the marketing page (/) the pricing section is hidden for them.
      const _subSlot = document.getElementById('app-sub-slot');
      if (document.body.classList.contains('tool-page')) {
        if (_subSlot && thanks) { _subSlot.appendChild(thanks); thanks.style.display = ''; }
        // Reveal the engagement row even if the streak fetch hasn't (so the
        // card is never trapped inside a hidden row).
        const _row = document.getElementById('app-engage-row');
        if (_row) _row.classList.add('shown');
      } else if (document.body.classList.contains('landing-page')) {
        const _proSec = document.getElementById('lp-pro');
        if (_proSec) _proSec.style.display = 'none';
      }

      // Section header — calm, factual. No "celebrate you're Pro" language.
      if (secTitle) secTitle.textContent = isTrial
        ? "Your Pro trial"
        : "Your Pro subscription";
      if (secSub) {
        if (isTrial) {
          secSub.textContent = daysLeft > 1
            ? `${daysLeft} days of Pro trial left · card on file · cancel anytime.`
            : 'Last day of your Pro trial · card on file · cancel anytime.';
        } else {
          secSub.textContent = "Everything Lexio offers is unlocked — across web, the Chrome extension, and the app.";
        }
      }

      // Populate the subscription card from the extended /api/pro-status payload.
      const interval         = d.subscription_interval || null;
      const familyRole       = d.family_role || null;
      const familyOwnerName  = d.family_owner_name || null;
      const isFounder        = !!d.is_founder;
      const memberSince      = d.member_since || null;

      const statusEl   = document.getElementById('lp-sub-status');
      const planName   = document.getElementById('lp-sub-plan-name');
      const planCycle  = document.getElementById('lp-sub-plan-cycle');
      const renewsRow  = document.getElementById('lp-sub-row-renews');
      const renewsDd   = document.getElementById('lp-sub-meta-renews');
      const familyRow  = document.getElementById('lp-sub-row-family');
      const familyDd   = document.getElementById('lp-sub-meta-family');
      const founderRow = document.getElementById('lp-sub-row-founder');
      const sinceRow   = document.getElementById('lp-sub-row-since');
      const sinceDd    = document.getElementById('lp-sub-meta-since');

      // Status pill: Active (paid) or Trial · Nd
      if (statusEl) {
        statusEl.classList.toggle('is-trial', isTrial);
        if (isTrial) {
          statusEl.textContent = daysLeft > 1 ? `Trial · ${daysLeft}d` : 'Trial · last day';
        } else {
          statusEl.textContent = 'Active';
        }
      }

      // Plan name + cycle label
      const cycleLabel =
        interval === 'year'   ? 'Annual' :
        interval === 'family' ? 'Family (4 seats)' :
        interval === 'month'  ? 'Monthly' :
        familyRole === 'member' ? 'Family seat' :
        '';
      if (planName)  planName.textContent  = familyRole === 'member' ? 'Lexio Pro' : 'Lexio Pro';
      if (planCycle) planCycle.textContent = cycleLabel || (isTrial ? 'On trial' : 'Active');

      // Billing row — describe the recurring schedule
      if (renewsRow && renewsDd) {
        if (isTrial) {
          renewsDd.textContent = daysLeft > 1 ? `Trial — converts in ${daysLeft} days` : 'Trial — converts tomorrow';
        } else if (familyRole === 'member') {
          renewsDd.textContent = familyOwnerName ? `Included via ${familyOwnerName}` : 'Included via family plan';
          // For a family seat there's nothing to manage directly here; leave the
          // button (the portal call will gracefully no-op if no Stripe customer).
        } else if (interval === 'year') {
          renewsDd.textContent = 'Renews annually';
        } else if (interval === 'family') {
          renewsDd.textContent = 'Renews monthly · family plan';
        } else if (interval === 'month') {
          renewsDd.textContent = 'Renews monthly';
        } else {
          renewsDd.textContent = 'Active';
        }
      }

      // Family row — owner or member context
      if (familyRow && familyDd) {
        if (familyRole === 'owner') {
          familyDd.textContent = 'You own this plan';
          familyRow.hidden = false;
        } else if (familyRole === 'member') {
          familyDd.textContent = familyOwnerName ? `Member of ${familyOwnerName}'s plan` : 'Member of a family plan';
          familyRow.hidden = false;
        } else {
          familyRow.hidden = true;
        }
      }

      // Founder row — only show when the badge is real
      if (founderRow) founderRow.hidden = !isFounder;

      // Member since — only show if the server gave us a date
      if (sinceRow && sinceDd) {
        if (memberSince) {
          sinceDd.textContent = memberSince;
          sinceRow.hidden = false;
        } else {
          sinceRow.hidden = true;
        }
      }

      // Family seat holders have no Stripe customer of their own — there's
      // nothing for them to "manage" here. Replace the button with a note
      // instead of dumping them into a checkout for a duplicate subscription.
      const manageBtn = document.querySelector('.lp-sub-manage');
      if (manageBtn) {
        if (familyRole === 'member') {
          manageBtn.style.display = 'none';
        } else {
          manageBtn.style.display = '';
        }
      }
      // App header menu
      const mp  = document.getElementById('menu-pro-btn');
      const mmb = document.getElementById('menu-manage-btn');
      if (isPaidPro) {
        if (mp)  mp.style.display  = 'none';
        if (mmb) mmb.style.display = '';
      }
    } else {
      // Free user — lock to fast
      if (currentModel !== 'fast') setModel('fast');
    }
  } catch {
    if (currentModel !== 'fast') setModel('fast');
  }
}
checkProStatus();

async function handleManageSub(ev) {
  const token = localStorage.getItem('lexio_token');
  if (!token) return;
  // Prefer the clicked button so the loading state lands where the user
  // looked; fall back to the in-grid manage button (older code path).
  const btn = (ev && ev.currentTarget && ev.currentTarget.tagName === 'BUTTON')
    ? ev.currentTarget
    : (document.querySelector('.lp-sub-manage') || document.getElementById('lp-manage-btn'));
  const originalLabel = btn ? btn.textContent : '';
  if (btn) { btn.textContent = 'Opening…'; btn.disabled = true; }
  try {
    const r = await fetch('/stripe/customer-portal', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token },
    });
    if (r.status === 400) {
      // No Stripe customer yet (legacy trial user without card on file).
      // Route them through Checkout so they can add a card.
      handleProCta();
      return;
    }
    if (!r.ok) throw new Error();
    const { url } = await r.json();
    window.location.href = url;
  } catch {
    alert('Could not open billing portal. Please try again.');
    if (btn) { btn.textContent = originalLabel || 'Manage subscription'; btn.disabled = false; }
  }
}

// hero gradient initialized via module script below

// ── Cursor-tracking glow for buttons ──────────────────────────
(function() {
  const SELECTOR = '.lp-btn-primary, .lp-btn-ghost, button.btn-primary, .ext-dl-btn, .desktop-dl-btn';
  function attachGlow(btn) {
    function onMove(e) {
      const r = btn.getBoundingClientRect();
      btn.style.setProperty('--glow-x', ((e.clientX - r.left) / r.width  * 100).toFixed(1) + '%');
      btn.style.setProperty('--glow-y', ((e.clientY - r.top)  / r.height * 100).toFixed(1) + '%');
    }
    btn.addEventListener('pointerenter', function(e) {
      btn.classList.add('btn-glow');
      onMove(e);
    });
    btn.addEventListener('pointermove', onMove);
    btn.addEventListener('pointerleave', function() {
      btn.classList.remove('btn-glow');
      btn.style.removeProperty('--glow-x');
      btn.style.removeProperty('--glow-y');
    });
  }
  document.querySelectorAll(SELECTOR).forEach(attachGlow);
})();

// ── FAQ accordion ──────────────────────────────────────────────
document.querySelectorAll('.lp-faq-q').forEach(btn => {
  btn.addEventListener('click', function() {
    const item = this.closest('.lp-faq-item');
    const isOpen = item.classList.contains('faq-open');
    document.querySelectorAll('.lp-faq-item.faq-open').forEach(i => i.classList.remove('faq-open'));
    if (!isOpen) item.classList.add('faq-open');
  });
});

// ── Landing nav active state ───────────────────────────────────
(function() {
  // Includes both standalone nav links and the items inside the Explore dropdown.
  const navLinks = document.querySelectorAll('.lp-header-nav [data-section]');
  if (!navLinks.length) return;
  const exploreBtn = document.getElementById('lp-explore-btn');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        navLinks.forEach(l => l.classList.toggle('lp-nav-active', l.dataset.section === entry.target.id));
        // Reflect "a section is in view" on the Explore button itself.
        if (exploreBtn) {
          const anyActive = !!document.querySelector('.lp-nav-drop-item.lp-nav-active');
          exploreBtn.classList.toggle('lp-nav-active', anyActive);
        }
      }
    });
  }, { threshold: 0.15, rootMargin: '0px 0px -70% 0px' });
  navLinks.forEach(l => {
    const el = document.getElementById(l.dataset.section);
    if (el) observer.observe(el);
  });
  // Smooth scroll for nav links (and close the dropdown if the click came from it)
  navLinks.forEach(l => {
    l.addEventListener('click', e => {
      e.preventDefault();
      const target = document.getElementById(l.dataset.section);
      if (target) target.scrollIntoView({ behavior: 'smooth' });
      if (typeof closeAllNavDropdowns === 'function') closeAllNavDropdowns();
    });
  });
})();

// ── Scroll-triggered reveal animations ───────────────────────────
(function() {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const REVEAL_SELECTORS = [
    '.lp-steps', '.lp-features', '.lp-pro', '.lp-trending',
    '.lp-twin', '.lp-edu', '.lp-faq', '.lp-modes', '.lp-ext',
    '.lp-desktop', '.lp-download', '.lp-trending-compact'
  ];
  document.querySelectorAll(REVEAL_SELECTORS.join(','))
    .forEach(el => el.classList.add('lp-reveal'));
  document.querySelectorAll('.lp-steps-grid, .lp-features-grid, .lp-pro-grid, .lp-edu-grid')
    .forEach(el => el.classList.add('lp-reveal-stagger'));

  if (reduce || !('IntersectionObserver' in window)) {
    document.querySelectorAll('.lp-reveal, .lp-reveal-stagger')
      .forEach(el => el.classList.add('is-visible'));
    return;
  }
  const io = new IntersectionObserver(function(entries) {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('is-visible');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });
  document.querySelectorAll('.lp-reveal, .lp-reveal-stagger')
    .forEach(el => io.observe(el));

  // ════════ HERO REVEAL — revertible block B (added 2026-06-27) ════════
  // The hero is ABOVE the fold, so it must be visible on load — it must NOT
  // be gated behind a scroll. The old code used a central-band
  // IntersectionObserver, which left the hero permanently blank (opacity:0)
  // for any viewport where it never crossed the band and the user didn't
  // scroll (e.g. a 1-second bounce). CSS now reveals it on load (lpHeroIn);
  // this adds `is-visible` immediately as defense-in-depth, plus a timed
  // failsafe so the hero can never stay hidden even if something interferes.
  // To revert: restore the IntersectionObserver version above.
  const heroEls = document.querySelectorAll('.lp-hero-anim');
  if (heroEls.length) {
    const showHero = () => heroEls.forEach(el => el.classList.add('is-visible'));
    showHero();                  // reveal on load (immediate)
    setTimeout(showHero, 1200);  // failsafe net — guarantees visibility
  }
  // ════════ end revertible block B ════════
})();

// ── Hero word swap: DISABLED ────────────────────────────────────
// New headline is declarative ("A dictionary that reads the sentence.")
// — the italic accent is stable for clarity. Keeping the logic in case
// we want to re-enable rotation later, gated to never run.
(function() {
  const ENABLED = false;
  if (!ENABLED) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  setTimeout(function() {
    const em = document.querySelector('.lp-hero h1 em');
    if (!em) return;
    const words = ['everything.', 'Tolstoy.', 'philosophy.', 'Kafka.', 'poetry.', 'law.', 'Dostoevsky.'];
    // "everything." anchors the headline, so it gets a longer hold than the
    // rotating alternatives.
    const HOLD_DEFAULT = 5200;
    const HOLD_ROTATE  = 2800;
    let i = 0;
    function scheduleNext() {
      const hold = (words[i] === 'everything.') ? HOLD_DEFAULT : HOLD_ROTATE;
      setTimeout(function() {
        em.style.opacity = '0';
        em.style.transform = 'translateY(-6px)';
        setTimeout(function() {
          i = (i + 1) % words.length;
          em.textContent = words[i];
          em.style.transform = 'translateY(6px)';
          void em.offsetWidth; // force reflow so the transition restarts
          em.style.opacity = '1';
          em.style.transform = 'translateY(0)';
          scheduleNext();
        }, 400);
      }, hold);
    }
    scheduleNext();
  }, 250);
})();

// ── Cycling demo words in hero preview ──────────────────────────
(function() {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  const stage = document.querySelector('.lp-demo-stage');
  if (!stage) return;
  const txt       = stage.querySelector('.lp-demo-text');
  const word      = stage.querySelector('.lp-demo-word');
  const popupWord = stage.querySelector('.lp-demo-popup-word');
  const popupPos  = stage.querySelector('.lp-demo-popup-pos');
  const lines     = stage.querySelectorAll('.lp-demo-popup-line');
  if (!txt || !word || !popupWord || lines.length < 2) return;

  const states = [
    { before: "The novel's ", word: 'labyrinthine', after: ' plot left readers spellbound — twists weaving with deliberate ambiguity.',
      pos: 'adjective', inContext: 'Intricate and twisting — the plot has so many turns it feels like a maze.',
      whyWord: 'Stronger than "complex" — implies deliberate, almost architectural intricacy.' },
    { before: "The senator's ", word: 'mendacious', after: ' testimony unraveled under cross-examination.',
      pos: 'adjective', inContext: 'Knowingly false — not just wrong, but deliberately lying.',
      whyWord: 'Sharper than "false" — carries an accusation of bad faith.' },
    { before: 'Her ', word: 'sanguine', after: ' outlook persisted through every setback.',
      pos: 'adjective', inContext: 'Cheerfully optimistic, especially under difficult circumstances.',
      whyWord: 'Older and more literary than "hopeful" — implies steadiness, not naivety.' },
    { before: 'His arguments were ', word: 'specious', after: ', persuasive at first glance but hollow underneath.',
      pos: 'adjective', inContext: 'Plausible on the surface but actually wrong or misleading.',
      whyWord: 'Sharper than "weak" — implies dressed-up deception.' }
  ];

  function applyState(s) {
    const nodes = txt.childNodes;
    for (let n = 0; n < nodes.length; n++) {
      if (nodes[n] === word) {
        if (n > 0                  && nodes[n - 1].nodeType === 3) nodes[n - 1].nodeValue = s.before;
        if (n < nodes.length - 1   && nodes[n + 1].nodeType === 3) nodes[n + 1].nodeValue = s.after;
        break;
      }
    }
    word.textContent      = s.word;
    popupWord.textContent = s.word;
    popupPos.textContent  = s.pos;
    lines[0].textContent  = s.inContext;
    lines[1].textContent  = s.whyWord;
  }

  // Sync JS state swap with the CSS animation loop.
  // The CSS animation loops every 3.4s. We want to swap content
  // right when the popup is invisible (opacity 0).
  // We can't rely on setTimeout matching CSS precisely.
  let i = 0;
  popup.addEventListener('animationiteration', () => {
    // animationiteration fires at the end of each iteration (100% / 0%).
    // The popup is opacity: 0 at 0%, so it's safe to swap here!
    i = (i + 1) % states.length;
    applyState(states[i]);
  });
})();

// (Removed the "magnetic pull" effect that translated CTAs toward the cursor.)

/* ── TikTok / social instant-demo ───────────────────────────────────────────
   ?try=1 (or ?demo=1) drops a cold visitor straight into a tappable passage:
   no paste, no "Analyze", and no signup wall. The normal analyze() gates on
   auth; this path deliberately skips that. Reuses renderTokens + the anonymous
   /define path (backend grants 5 free lookups before nudging signup). */
const DEMO_PASSAGE  = "He met the news with a strange equanimity, as if grief were a language he had long since forgotten how to speak.";
const DEMO_HINT_WORD = "equanimity";

function startDemo() {
  document.body.classList.add('demo-mode');

  // Strip the marketing page — it all lives in #landing, so hiding that one
  // wrapper leaves the app, modals, and overlays fully intact.
  const landing = document.getElementById('landing');
  if (landing) landing.style.display = 'none';

  // Load the passage straight into the tappable reading view.
  const ta = document.getElementById('input-text');
  if (ta) { ta.value = DEMO_PASSAGE; ta.classList.add('hidden'); }
  currentContext = DEMO_PASSAGE;
  renderTokens(DEMO_PASSAGE);
  document.getElementById('token-view').classList.remove('hidden');
  ['analyze-btn','sample-btn','edit-btn','char-count','url-bar','reading-stats']
    .forEach(id => { const e = document.getElementById(id); if (e) e.classList.add('hidden'); });
  if (typeof stopPlaceholderRotation === 'function') stopPlaceholderRotation();
  if (typeof updateAppCompact === 'function') updateAppCompact();

  // Pulse the juicy word + a one-time "tap any word" coachmark.
  document.querySelectorAll('#token-view .word-token').forEach(t => {
    if (t.textContent.toLowerCase() === DEMO_HINT_WORD.toLowerCase()) t.classList.add('demo-pulse');
  });
  let coach = document.getElementById('demo-coachmark');
  if (!coach) {
    coach = document.createElement('div');
    coach.id = 'demo-coachmark';
    coach.className = 'demo-coachmark';
    coach.textContent = '👆 Tap any word to see what it means';
    document.body.appendChild(coach);
  }
  const tv = document.getElementById('token-view');
  tv.addEventListener('click', function retire() {
    document.querySelectorAll('#token-view .word-token.demo-pulse').forEach(t => t.classList.remove('demo-pulse'));
    if (coach) coach.remove();
    tv.removeEventListener('click', retire);
  });
}

(function initTryDemo() {
  const p = new URLSearchParams(location.search);
  if (!(p.has('try') || p.has('demo'))) return;
  function go() { try { startDemo(); } catch (e) { console.error('Lexio demo failed', e); } }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go);
  else go();
})();

