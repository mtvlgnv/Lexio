'use strict';

// Guard: only inject once per page
if (document.getElementById('__lexio_ext_host__')) {
  throw new Error('Lexio already injected');
}

const MAX_CONTEXT_CHARS = 600;
const MAX_SEL_WORDS     = 50;   // allow up to a full sentence
const MAX_SEL_CHARS     = 400;  // but cap total characters
const DEBOUNCE_MS       = 260;

// ── State ─────────────────────────────────────────────────────────────────────
let visible     = false;
let currentWord = '';
let currentData = null;
let isSaved     = false;
let debounce    = null;
let enabled     = true;
let lastRefRect = null;
let currentLang = 'auto';

// Load initial state from storage
chrome.storage.local.get(['lexio_enabled', 'lexio_lang'], d => {
  enabled     = d.lexio_enabled !== false;
  currentLang = d.lexio_lang || 'auto';
});
chrome.storage.onChanged.addListener(changes => {
  if ('lexio_enabled' in changes) enabled     = changes.lexio_enabled.newValue !== false;
  if ('lexio_lang'    in changes) currentLang = changes.lexio_lang.newValue    || 'auto';
});

// ── Shadow DOM host ───────────────────────────────────────────────────────────
const host = document.createElement('div');
host.id = '__lexio_ext_host__';
host.style.cssText = 'all:initial;position:absolute;top:0;left:0;width:0;height:0;z-index:2147483647;pointer-events:none;';
(document.body || document.documentElement).appendChild(host);

const shadow = host.attachShadow({ mode: 'open' });

// ── Styles ────────────────────────────────────────────────────────────────────
const styleEl = document.createElement('style');
styleEl.textContent = `
  #lx {
    all: initial;
    position: fixed;
    width: 320px;
    max-width: calc(100vw - 24px);
    background: oklch(99.2% 0.006 75);
    border: 1px solid oklch(89% 0.014 75);
    border-radius: 14px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.14), 0 2px 8px rgba(0,0,0,0.07);
    font-family: system-ui, -apple-system, 'DM Sans', sans-serif;
    font-size: 14px;
    color: oklch(18% 0.015 65);
    pointer-events: auto;
    opacity: 0;
    transform: translateY(5px) scale(0.98);
    transition: opacity 0.14s ease, transform 0.14s ease;
    overflow: hidden;
    z-index: 2147483647;
    box-sizing: border-box;
  }
  #lx.show {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
  @media (prefers-color-scheme: dark) {
    #lx {
      background: oklch(19% 0.012 65);
      border-color: oklch(28% 0.015 65);
      color: oklch(92% 0.008 75);
      box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3);
    }
  }

  /* Header */
  .lx-head {
    display: flex; align-items: center; gap: 7px;
    padding: 12px 13px 9px;
    border-bottom: 1px solid oklch(91% 0.012 75);
  }
  @media (prefers-color-scheme: dark) { .lx-head { border-bottom-color: oklch(27% 0.014 65); } }

  .lx-word {
    font-size: 1rem; font-weight: 650; flex: 1;
    min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-family: Georgia, serif;
  }
  .lx-pos {
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; padding: 2px 7px; border-radius: 20px;
    white-space: nowrap; flex-shrink: 0;
  }
  .pos-noun { background:oklch(95% 0.05 65);  color:oklch(48% 0.16 65);  }
  .pos-verb { background:oklch(95% 0.04 240); color:oklch(44% 0.17 240); }
  .pos-adj  { background:oklch(95% 0.04 145); color:oklch(42% 0.15 145); }
  .pos-adv  { background:oklch(95% 0.04 195); color:oklch(44% 0.14 195); }
  .pos-other{ background:oklch(96% 0.06 75);  color:oklch(58% 0.17 54);  }
  @media (prefers-color-scheme: dark) {
    .pos-noun { background:oklch(22% 0.04 65);  color:oklch(72% 0.14 65);  }
    .pos-verb { background:oklch(22% 0.04 240); color:oklch(68% 0.15 240); }
    .pos-adj  { background:oklch(22% 0.04 145); color:oklch(66% 0.13 145); }
    .pos-adv  { background:oklch(22% 0.04 195); color:oklch(68% 0.12 195); }
    .pos-other{ background:oklch(22% 0.04 65);  color:oklch(68% 0.17 54);  }
  }
  .lx-close {
    width: 22px; height: 22px; border: none; background: none;
    cursor: pointer; color: oklch(55% 0.01 65);
    display: flex; align-items: center; justify-content: center;
    border-radius: 50%; font-size: 17px; line-height: 1;
    flex-shrink: 0; transition: background 0.12s; padding: 0;
  }
  .lx-close:hover { background: oklch(92% 0.06 72); }
  @media (prefers-color-scheme: dark) { .lx-close:hover { background: oklch(26% 0.04 65); } }

  /* IPA */
  .lx-ipa {
    padding: 5px 13px 0;
    font-size: 0.78rem; color: oklch(55% 0.01 65);
    font-style: italic; font-family: Georgia, serif;
  }

  /* Body */
  .lx-body { padding: 9px 13px 11px; display: flex; flex-direction: column; gap: 8px; }
  .lx-section-label {
    font-size: 0.6rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: oklch(55% 0.01 65); margin-bottom: 2px;
  }
  .lx-def {
    font-size: 0.875rem; line-height: 1.65;
    color: oklch(18% 0.015 65); font-weight: 300;
  }
  @media (prefers-color-scheme: dark) { .lx-def { color: oklch(92% 0.008 75); } }
  .lx-ctx {
    background: oklch(96% 0.06 75); border-radius: 8px;
    padding: 9px 11px 9px 16px;
    font-size: 0.8rem; line-height: 1.62;
    color: oklch(35% 0.012 65); font-style: italic;
    font-family: Georgia, serif; position: relative;
  }
  .lx-ctx::before {
    content: '"'; position: absolute; top: 1px; left: 9px;
    font-size: 1.7rem; color: oklch(58% 0.17 54); opacity: 0.22; line-height: 1;
  }
  @media (prefers-color-scheme: dark) {
    .lx-ctx { background: oklch(22% 0.04 65); color: oklch(75% 0.008 75); }
  }
  .lx-etym {
    display: flex; gap: 6px; align-items: baseline;
    padding-top: 7px; border-top: 1px solid oklch(92% 0.01 75);
  }
  @media (prefers-color-scheme: dark) { .lx-etym { border-top-color: oklch(25% 0.01 65); } }
  .lx-etym-lbl {
    font-size: 0.58rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: oklch(55% 0.01 65);
    white-space: nowrap; flex-shrink: 0;
  }
  .lx-etym-txt {
    font-size: 0.75rem; font-style: italic;
    font-family: Georgia, serif; color: oklch(55% 0.01 65); line-height: 1.45;
  }

  /* Footer */
  .lx-foot {
    display: flex; align-items: center; gap: 6px;
    padding: 7px 13px;
    border-top: 1px solid oklch(92% 0.01 75);
    background: oklch(96.5% 0.012 75);
  }
  @media (prefers-color-scheme: dark) {
    .lx-foot { border-top-color: oklch(25% 0.01 65); background: oklch(16% 0.01 65); }
  }
  .lx-save {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 10px;
    border: 1px solid oklch(88% 0.014 75); border-radius: 20px;
    background: transparent; font-family: inherit; font-size: 0.74rem;
    font-weight: 500; color: oklch(55% 0.01 65); cursor: pointer;
    transition: background 0.12s, border-color 0.12s, color 0.12s;
  }
  .lx-save:hover { background: oklch(92% 0.06 72); border-color: oklch(88% 0.08 70); color: oklch(18% 0.015 65); }
  .lx-save.saved { background: oklch(96% 0.06 75); border-color: oklch(88% 0.08 70); color: oklch(58% 0.17 54); }
  @media (prefers-color-scheme: dark) {
    .lx-save { border-color: oklch(28% 0.015 65); color: oklch(52% 0.008 70); }
    .lx-save:hover { background: oklch(26% 0.04 65); color: oklch(90% 0.008 75); }
    .lx-save.saved { background: oklch(22% 0.04 65); border-color: oklch(30% 0.06 65); color: oklch(68% 0.17 54); }
  }
  .lx-sp { flex: 1; }
  .lx-link {
    font-size: 0.7rem; color: oklch(58% 0.17 54);
    text-decoration: none; padding: 3px 5px;
    border-radius: 5px; transition: background 0.12s;
  }
  .lx-link:hover { background: oklch(95% 0.06 75); }
  @media (prefers-color-scheme: dark) { .lx-link:hover { background: oklch(22% 0.04 65); } }

  /* Language selector in footer */
  .lx-lang {
    appearance: none; -webkit-appearance: none;
    background: transparent;
    border: 1px solid oklch(88% 0.014 75);
    border-radius: 20px;
    padding: 3px 20px 3px 8px;
    font-family: inherit; font-size: 0.72rem;
    color: oklch(55% 0.01 65);
    cursor: pointer; outline: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 5px center;
    transition: border-color 0.12s;
    max-width: 110px;
  }
  .lx-lang:hover { border-color: oklch(70% 0.12 54); }
  .lx-lang:focus { border-color: oklch(58% 0.17 54); }
  @media (prefers-color-scheme: dark) {
    .lx-lang { border-color: oklch(28% 0.015 65); color: oklch(55% 0.008 70);
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
    }
    .lx-lang:hover { border-color: oklch(50% 0.12 54); }
  }

  /* Loading */
  .lx-loading {
    padding: 18px 13px; display: flex; align-items: center;
    gap: 10px; color: oklch(55% 0.01 65); font-size: 0.83rem;
  }
  .lx-spin {
    width: 15px; height: 15px; flex-shrink: 0;
    border: 2px solid oklch(88% 0.014 75);
    border-top-color: oklch(58% 0.17 54); border-radius: 50%;
    animation: spin 0.65s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Error */
  .lx-err {
    padding: 12px 13px; font-size: 0.82rem;
    color: oklch(55% 0.2 25); line-height: 1.5;
  }
`;
shadow.appendChild(styleEl);

// ── Popup element ─────────────────────────────────────────────────────────────
const popup = document.createElement('div');
popup.id = 'lx';
shadow.appendChild(popup);

// ── Utilities ─────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function posClass(pos) {
  if (!pos) return 'pos-other';
  const p = pos.toLowerCase();
  if (p.includes('noun'))  return 'pos-noun';
  if (p.includes('verb'))  return 'pos-verb';
  if (p.includes('adj'))   return 'pos-adj';
  if (p.includes('adv'))   return 'pos-adv';
  return 'pos-other';
}

function svgBookmark(filled) {
  return filled
    ? `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`
    : `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`;
}

function getContext(anchorEl) {
  let el = anchorEl;
  while (el && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
    const d = window.getComputedStyle(el).display;
    if (/^(block|flex|grid|table|list-item)/.test(d)) break;
    el = el.parentElement;
  }
  return (el?.innerText || document.body?.innerText || '').slice(0, MAX_CONTEXT_CHARS);
}

// ── Popup positioning ─────────────────────────────────────────────────────────
function positionPopup(refRect) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const pw = Math.min(320, vw - 24);
  const ph = popup.offsetHeight || 180; // use measured height or fallback

  let x = refRect.left + refRect.width / 2 - pw / 2;
  x = Math.max(12, Math.min(vw - pw - 12, x));

  // Below selection by default; flip above if not enough room
  let y = refRect.bottom + 10;
  if (y + ph > vh - 12 && refRect.top - ph - 10 > 12) {
    y = refRect.top - ph - 10;
  }
  y = Math.max(12, y);

  popup.style.left  = `${x}px`;
  popup.style.top   = `${y}px`;
  popup.style.width = `${pw}px`;
}

// ── Show / hide ───────────────────────────────────────────────────────────────
function showPopup(refRect) {
  lastRefRect = refRect;
  positionPopup(refRect);
  host.style.pointerEvents = 'auto';
  // Small rAF so transition fires after position is set
  requestAnimationFrame(() => popup.classList.add('show'));
  visible = true;
}

function hidePopup() {
  popup.classList.remove('show');
  host.style.pointerEvents = 'none';
  visible = false;
  currentWord = '';
  currentData = null;
}

// ── Render helpers ────────────────────────────────────────────────────────────
function langSelectHTML() {
  const langs = [
    ['auto','Auto'],['en','English'],['es','Español'],['fr','Français'],
    ['de','Deutsch'],['it','Italiano'],['pt','Português'],['ru','Русский'],
    ['zh','中文'],['ja','日本語'],['ko','한국어'],['ar','العربية'],
    ['hi','हिन्दी'],['nl','Dutch'],['pl','Polski'],['tr','Türkçe'],['sv','Svenska'],
  ];
  const options = langs.map(([v, l]) =>
    `<option value="${v}"${v === currentLang ? ' selected' : ''}>${l}</option>`
  ).join('');
  return `<select class="lx-lang" id="lx-lang">${options}</select>`;
}

function renderLoading(word) {
  popup.innerHTML = `
    <div class="lx-head">
      <span class="lx-word">${esc(word)}</span>
      <button class="lx-close">×</button>
    </div>
    <div class="lx-loading"><div class="lx-spin"></div>Looking up in context…</div>
  `;
  popup.querySelector('.lx-close').onclick = hidePopup;
}

function renderResult(word, data) {
  const hasEtym  = data.etymology && data.etymology !== 'null';
  const hasIPA   = data.ipa       && data.ipa       !== 'null';
  const isPhrase = word.trim().split(/\s+/).length > 1;

  // For phrases: show definition (general meaning) + contextual (in this text)
  // For words:   show contextual first (in-context is primary), then general def
  const defBlock = isPhrase
    ? `${data.definition  ? `<div class="lx-def">${esc(data.definition)}</div>`  : ''}
       ${data.contextual  ? `<div class="lx-ctx">${esc(data.contextual)}</div>`  : ''}`
    : `${data.contextual  ? `<div class="lx-ctx">${esc(data.contextual)}</div>`  : ''}
       ${data.definition  ? `<div class="lx-def">${esc(data.definition)}</div>`  : ''}`;

  popup.innerHTML = `
    <div class="lx-head">
      <span class="lx-word">${esc(word)}</span>
      ${isPhrase
        ? `<span class="lx-pos pos-other">phrase</span>`
        : (data.pos ? `<span class="lx-pos ${posClass(data.pos)}">${esc(data.pos)}</span>` : '')}
      <button class="lx-close">×</button>
    </div>
    ${hasIPA ? `<div class="lx-ipa">${esc(data.ipa)}</div>` : ''}
    <div class="lx-body">
      ${defBlock}
      ${hasEtym ? `
        <div class="lx-etym">
          <span class="lx-etym-lbl">Origin</span>
          <span class="lx-etym-txt">${esc(data.etymology)}</span>
        </div>` : ''}
    </div>
    <div class="lx-foot">
      <button class="lx-save" id="lx-sv">${svgBookmark(false)} Collect</button>
      <div class="lx-sp"></div>
      ${langSelectHTML()}
    </div>
  `;

  popup.querySelector('.lx-close').onclick = hidePopup;

  // Language selector — change lang and immediately re-fetch
  const langEl = shadow.getElementById('lx-lang');
  if (langEl) {
    langEl.addEventListener('change', e => {
      currentLang = e.target.value;
      chrome.runtime.sendMessage({ type: 'SET_LANG', lang: currentLang });
      // Re-fetch in new language
      if (currentWord && lastRefRect) runDefine(currentWord, lastRefRect, null);
    });
  }

  // Check saved state then wire button
  chrome.storage.local.get('lexio_wordbank', d => {
    const bank = d.lexio_wordbank || [];
    isSaved = bank.some(e => e.word.toLowerCase() === word.toLowerCase());
    updateSaveBtn();
  });
  popup.querySelector('#lx-sv').onclick = toggleSave;

  // Re-position now that content is rendered and height is known
  if (lastRefRect) {
    requestAnimationFrame(() => positionPopup(lastRefRect));
  }
}

function renderError(msg) {
  popup.innerHTML = `
    <div class="lx-head">
      <span class="lx-word">${esc(currentWord)}</span>
      <button class="lx-close">×</button>
    </div>
    <div class="lx-err">${esc(msg)}</div>
  `;
  popup.querySelector('.lx-close').onclick = hidePopup;
}

function updateSaveBtn() {
  const btn = shadow.getElementById('lx-sv');
  if (!btn) return;
  btn.classList.toggle('saved', isSaved);
  btn.innerHTML = svgBookmark(isSaved) + (isSaved ? ' Collected' : ' Collect');
}

// ── Save / unsave ─────────────────────────────────────────────────────────────
function toggleSave() {
  if (!currentData) return;
  if (isSaved) {
    chrome.runtime.sendMessage({ type: 'UNSAVE_WORD', word: currentWord }, () => {
      isSaved = false; updateSaveBtn();
    });
  } else {
    const entry = {
      word:       currentWord,
      pos:        currentData.pos        || '',
      definition: currentData.definition || '',
      contextual: currentData.contextual || '',
      etymology:  currentData.etymology  || '',
      savedAt:    new Date().toISOString(),
    };
    chrome.runtime.sendMessage({ type: 'SAVE_WORD', entry }, () => {
      isSaved = true; updateSaveBtn();
    });
  }
}

// ── Define flow ───────────────────────────────────────────────────────────────
function runDefine(word, refRect, anchorEl) {
  const context = anchorEl ? getContext(anchorEl) : (currentData?._context || '');
  currentWord = word;
  currentData = null;

  renderLoading(word);
  if (refRect) showPopup(refRect);

  const sentWord = word;
  chrome.runtime.sendMessage({ type: 'DEFINE', word, context, lang: currentLang }, resp => {
    if (currentWord !== sentWord) return; // stale – user moved on
    if (resp?.ok) {
      currentData = { ...resp.data, _context: context };
      renderResult(word, resp.data);
    } else {
      renderError(resp?.error || 'Could not fetch definition.');
    }
  });
}

// ── Mouse-up handler ──────────────────────────────────────────────────────────
function onMouseUp(e) {
  const path = e.composedPath();
  if (path.includes(host) || path.includes(popup)) return; // click inside our popup
  if (!enabled) return;

  clearTimeout(debounce);
  debounce = setTimeout(() => {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;

    const text = sel.toString().trim().replace(/\s+/g, ' ');
    if (!text || text.split(/\s+/).length > MAX_SEL_WORDS || text.length > MAX_SEL_CHARS) return;

    const range   = sel.getRangeAt(0);
    const refRect = range.getBoundingClientRect();
    if (!refRect.width && !refRect.height) return;

    const anchorEl = sel.anchorNode?.nodeType === 3
      ? sel.anchorNode.parentElement
      : (sel.anchorNode || document.body);

    runDefine(text, refRect, anchorEl);
  }, DEBOUNCE_MS);
}

// ── Context-menu trigger from background ──────────────────────────────────────
chrome.runtime.onMessage.addListener(msg => {
  if (msg.type !== 'TRIGGER_DEFINE') return;

  const sel = window.getSelection();
  let refRect = { left: window.innerWidth / 2 - 160, width: 0, bottom: 160, top: 140 };
  if (sel && sel.rangeCount) {
    const r = sel.getRangeAt(0).getBoundingClientRect();
    if (r.width || r.height) refRect = r;
  }

  const anchorEl = sel?.anchorNode?.nodeType === 3
    ? sel.anchorNode.parentElement
    : (sel?.anchorNode || document.body);

  runDefine(msg.word, refRect, anchorEl);
});

// ── Global dismiss ────────────────────────────────────────────────────────────
document.addEventListener('mousedown', e => {
  if (!visible) return;
  // e.target is retargeted at the shadow boundary — use composedPath() to see inside
  const path = e.composedPath();
  const insidePopup = path.includes(host) || path.includes(popup);
  if (!insidePopup) hidePopup();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && visible) hidePopup();
});

document.addEventListener('mouseup', onMouseUp);
