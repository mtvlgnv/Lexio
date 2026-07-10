const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

app.disableHardwareAcceleration();

const outDir = path.join(__dirname, 'store-assets');
fs.mkdirSync(outDir, { recursive: true });

const C = {
  bg: '#15110e',
  panel: '#17120f',
  panel2: '#211914',
  line: '#3a2d26',
  ivory: '#fff5e8',
  muted: '#cbbdb1',
  dim: '#8f7f72',
  orange: '#f27a18',
  orange2: '#fb982b',
  cream: '#fbf5eb',
  ink: '#211915',
};

function esc(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function defs() {
  return `
  <defs>
    <radialGradient id="bgGlow" cx="72%" cy="55%" r="72%">
      <stop offset="0%" stop-color="#e59a55" stop-opacity=".8"/>
      <stop offset="42%" stop-color="#6d3858" stop-opacity=".74"/>
      <stop offset="78%" stop-color="#23172d" stop-opacity=".82"/>
      <stop offset="100%" stop-color="#15110e"/>
    </radialGradient>
    <linearGradient id="orange" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f4a044"/>
      <stop offset="100%" stop-color="#df7426"/>
    </linearGradient>
    <linearGradient id="warmPanel" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#5a321f"/>
      <stop offset="60%" stop-color="#704030"/>
      <stop offset="100%" stop-color="#4a2638"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%">
      <feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#050403" flood-opacity=".42"/>
    </filter>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="150%">
      <feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#050403" flood-opacity=".28"/>
    </filter>
    <style>
      .sans{font-family:-apple-system,BlinkMacSystemFont,"DM Sans","Inter","Segoe UI",sans-serif}
      .serif{font-family:Georgia,"Times New Roman",serif}
      .label{font-family:-apple-system,BlinkMacSystemFont,"DM Sans","Inter","Segoe UI",sans-serif;font-size:20px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}
    </style>
  </defs>`;
}

function logo(x, y, scale = 1) {
  return `<g transform="translate(${x} ${y}) scale(${scale})">
    <rect width="36" height="36" rx="9" fill="url(#orange)"/>
    <text x="18" y="25" class="serif" fill="#fff" font-size="20" font-weight="700" text-anchor="middle">w</text>
    <text x="50" y="25" class="serif" fill="${C.ivory}" font-size="22" font-weight="700">Lexio</text>
  </g>`;
}

function background(w, h) {
  return `<rect width="${w}" height="${h}" fill="${C.bg}"/>
  <rect width="${w}" height="${h}" fill="url(#bgGlow)"/>
  <path d="M0 ${h * .68} C${w * .18} ${h * .53} ${w * .3} ${h * .65} ${w * .44} ${h * .68} C${w * .62} ${h * .73} ${w * .72} ${h * .58} ${w * .9} ${h * .54} C${w * .96} ${h * .53} ${w} ${h * .48} ${w} ${h * .48} L${w} ${h} L0 ${h} Z" fill="#b98247" opacity=".48"/>
  <path d="M0 ${h * .79} C${w * .18} ${h * .68} ${w * .35} ${h * .82} ${w * .55} ${h * .78} C${w * .75} ${h * .74} ${w * .85} ${h * .86} ${w} ${h * .75} L${w} ${h} L0 ${h} Z" fill="#2a1832" opacity=".45"/>`;
}

function headline(x, y, lines, opts = {}) {
  const size = opts.size || 68;
  const gap = opts.gap || Math.round(size * 1.12);
  return `<text x="${x}" y="${y}" class="serif" font-size="${size}" font-weight="700" fill="${C.ivory}">
    ${lines.map((line, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : gap}">${line.replace(/\*(.*?)\*/g, `<tspan fill="${C.orange}" font-style="italic">$1</tspan>`)}</tspan>`).join('')}
  </text>`;
}

function browser(x, y, w, h, title, bodyLines, highlight) {
  const lines = bodyLines.map((line, i) => {
    const yLine = y + 126 + i * 34;
    const chunks = line.split(highlight);
    if (chunks.length === 1) return `<text x="${x + 58}" y="${yLine}" class="serif" fill="${C.muted}" font-size="22">${esc(line)}</text>`;
    return `<text x="${x + 58}" y="${yLine}" class="serif" fill="${C.muted}" font-size="22">${esc(chunks[0])}<tspan fill="${C.orange}" font-weight="700">${esc(highlight)}</tspan>${esc(chunks.slice(1).join(highlight))}</text>`;
  }).join('');
  return `<g filter="url(#shadow)">
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="26" fill="${C.panel}" stroke="${C.line}"/>
    <rect x="${x}" y="${y}" width="${w}" height="62" rx="26" fill="${C.panel2}"/>
    <circle cx="${x + 36}" cy="${y + 31}" r="7" fill="#ef6a55"/>
    <circle cx="${x + 62}" cy="${y + 31}" r="7" fill="#e8b64d"/>
    <circle cx="${x + 88}" cy="${y + 31}" r="7" fill="#66c85a"/>
    <rect x="${x + 158}" y="${y + 18}" width="${w - 316}" height="28" rx="14" fill="#15100e" stroke="${C.line}"/>
    <text x="${x + w / 2}" y="${y + 37}" class="sans" fill="#8a7b70" font-size="13" font-weight="700" text-anchor="middle">example-reading.com</text>
    <text x="${x + 58}" y="${y + 94}" class="serif" fill="${C.ivory}" font-size="28" font-weight="700">${esc(title)}</text>
    <rect x="${x + 40}" y="${y + 112}" width="${w - 80}" height="${h - 168}" rx="18" fill="#110d0b" stroke="${C.line}"/>
    ${lines}
  </g>`;
}

function lexioPopup(x, y, word, pos, contextual, definition, whyLabel = 'Origin') {
  return `<g filter="url(#soft)">
    <rect x="${x}" y="${y}" width="416" height="226" rx="18" fill="${C.cream}"/>
    <rect x="${x + .5}" y="${y + .5}" width="415" height="225" rx="17.5" fill="none" stroke="#eadfce"/>
    <text x="${x + 28}" y="${y + 44}" class="serif" fill="${C.ink}" font-size="31" font-weight="700">${esc(word)}</text>
    <rect x="${x + 236}" y="${y + 22}" width="${pos === 'phrase' ? 70 : 96}" height="26" rx="13" fill="#f6eadb"/>
    <text x="${x + (pos === 'phrase' ? 271 : 284)}" y="${y + 40}" class="sans" fill="#c96e26" font-size="12" font-weight="800" text-anchor="middle">${esc(pos)}</text>
    <text x="${x + 28}" y="${y + 84}" class="sans" fill="${C.ink}" font-size="17" font-weight="800">${esc(contextual)}</text>
    <text x="${x + 28}" y="${y + 116}" class="sans" fill="#40342c" font-size="14" font-weight="600">${esc(definition)}</text>
    <line x1="${x + 28}" y1="${y + 151}" x2="${x + 388}" y2="${y + 151}" stroke="#eadfce"/>
    <text x="${x + 28}" y="${y + 181}" class="sans" fill="#8e623f" font-size="13" font-weight="900" letter-spacing=".12em">${whyLabel.toUpperCase()}</text>
    <text x="${x + 314}" y="${y + 184}" class="sans" fill="${C.orange}" font-size="24">›</text>
  </g>`;
}

function titleCard({ id, w = 1280, h = 800, titleLines, subLines, browserSpec, popupSpec, extra = '' }) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    ${defs()}${background(w, h)}
    ${logo(72, 64, 1.08)}
    ${headline(72, 210, titleLines)}
    <text x="72" y="510" class="sans" fill="${C.ivory}" font-size="25" font-weight="700">
      ${subLines.map((line, i) => `<tspan x="72" dy="${i === 0 ? 0 : 38}">${esc(line)}</tspan>`).join('')}
    </text>
    ${browser(browserSpec.x, browserSpec.y, browserSpec.w, browserSpec.h, browserSpec.title, browserSpec.body, browserSpec.highlight)}
    ${lexioPopup(popupSpec.x, popupSpec.y, popupSpec.word, popupSpec.pos, popupSpec.contextual, popupSpec.definition, popupSpec.whyLabel || 'Why this word')}
    ${extra}
  </svg>`;
}

function card1() {
  return titleCard({
    id: 1,
    titleLines: ['Understand', 'words', '*in context*'],
    subLines: ['Highlight any word or phrase.', 'Lexio explains the exact meaning', 'in the sentence you are reading.'],
    browserSpec: {
      x: 520, y: 70, w: 650, h: 540, title: 'The House on Meridian Lane', highlight: 'labyrinthine',
      body: ['The corridor bent twice before opening into', 'a room that felt strangely intimate. Every', 'detail seemed chosen with care, yet the', 'story unfolded in a labyrinthine way,', 'revealing motive that was never simple.'],
    },
    popupSpec: {
      x: 640, y: 380, word: 'labyrinthine', pos: 'adjective',
      contextual: 'Intricate and difficult to follow, like a maze.',
      definition: "Here, the plot's twists feel complex but intentional.",
      whyLabel: 'Why this word',
    },
  });
}

function card2() {
  return titleCard({
    id: 2,
    titleLines: ['Works for', '*phrases,* too'],
    subLines: ['Select a word, idiom,', 'or short phrase and get', 'the meaning that fits', 'the passage.'],
    browserSpec: {
      x: 520, y: 70, w: 650, h: 540, title: 'After the Rain', highlight: 'against the grain',
      body: ['People watched the city wake up, some with', 'hope, others with habits too heavy to shake.', 'Maya chose to walk against the grain,', 'following a quieter path that did not make', 'sense to most but felt true to her.'],
    },
    popupSpec: {
      x: 640, y: 380, word: 'against the grain', pos: 'phrase',
      contextual: 'To act or think differently from what is expected.',
      definition: 'In this passage, it suggests quiet resistance rather than rebellion.',
      whyLabel: 'Why this phrase',
    },
  });
}

function card3() {
  return titleCard({
    id: 3,
    titleLines: ['No tab', '*switching*'],
    subLines: ['Lexio appears where', 'you read, so your focus', 'stays on the text.'],
    browserSpec: {
      x: 440, y: 74, w: 720, h: 540, title: 'The Quiet Observatory', highlight: 'ephemeral',
      body: ['At the edge of the hill, the observatory appeared', 'modest, almost shy. Inside, shelves of journals', 'recorded decades of patient looking. It was a', 'place devoted to noticing what others overlooked:', 'the ephemeral line between night and morning.'],
    },
    popupSpec: {
      x: 620, y: 376, word: 'ephemeral', pos: 'adjective',
      contextual: 'Lasting for a very short time.',
      definition: 'Here, it highlights the fleeting nature of the moment.',
      whyLabel: 'Why this word',
    },
  });
}

function wordBankPanel(x, y) {
  const rows = [
    ['labyrinthine', 'Intricate and difficult to follow, like a maze.'],
    ['ephemeral', 'Lasting for a very short time.'],
    ['equivocal', 'Open to more than one interpretation.'],
    ['sublime', 'Of such excellence as to inspire awe.'],
    ['auspicious', 'Giving hope for future success.'],
  ];
  return `<g filter="url(#shadow)">
    <rect x="${x}" y="${y}" width="600" height="540" rx="26" fill="${C.panel}" stroke="${C.line}"/>
    <rect x="${x}" y="${y}" width="600" height="62" rx="26" fill="${C.panel2}"/>
    ${logo(x + 28, y + 18, .72)}
    <text x="${x + 548}" y="${y + 42}" class="sans" fill="${C.muted}" font-size="25" text-anchor="middle">⚙</text>
    <text x="${x + 40}" y="${y + 112}" class="sans" fill="${C.orange}" font-size="18" font-weight="800">Word Bank</text>
    <line x1="${x + 40}" y1="${y + 128}" x2="${x + 138}" y2="${y + 128}" stroke="${C.orange}" stroke-width="2"/>
    <rect x="${x + 30}" y="${y + 150}" width="540" height="300" rx="14" fill="#1f1713" stroke="${C.line}"/>
    ${rows.map((r, i) => `<g transform="translate(${x + 54} ${y + 188 + i * 52})">
      <text class="serif" fill="${C.ivory}" font-size="19" font-weight="700">${esc(r[0])}</text>
      <text x="150" y="0" class="sans" fill="${C.muted}" font-size="15">${esc(r[1])}</text>
      <text x="488" y="2" class="sans" fill="${C.orange}" font-size="20">♡</text>
    </g>`).join('')}
    <text x="${x + 40}" y="${y + 498}" class="sans" fill="${C.ivory}" font-size="15" font-weight="700">24 words saved</text>
    <text x="${x + 504}" y="${y + 498}" class="sans" fill="${C.ivory}" font-size="15" font-weight="700">Open ↗</text>
  </g>`;
}

function card4() {
  const w = 1280, h = 800;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    ${defs()}${background(w, h)}${logo(72,64,1.08)}
    ${headline(72, 230, ['Build your', '*word bank*'])}
    <text x="72" y="510" class="sans" fill="${C.ivory}" font-size="25" font-weight="700">
      <tspan x="72">Save words you want</tspan><tspan x="72" dy="38">to remember and</tspan><tspan x="72" dy="38">revisit them later.</tspan>
    </text>
    ${wordBankPanel(520, 90)}
  </svg>`;
}

function card5() {
  return titleCard({
    id: 5,
    titleLines: ['Read across', '*languages*'],
    subLines: ['Understand nuance without', 'flattening every word into', 'a translation.'],
    browserSpec: {
      x: 440, y: 74, w: 720, h: 540, title: 'Voces en la penumbra', highlight: 'matiz',
      body: ['El orador habló con cuidado, tratando de captar', 'cada matiz de aquella historia que había viajado', 'tanto tiempo. No se trataba solo de lo que ocurrió,', 'sino de cómo se recordaba.'],
    },
    popupSpec: {
      x: 620, y: 384, word: 'matiz', pos: 'noun',
      contextual: 'A subtle shade of meaning, tone, or difference.',
      definition: 'Here, it refers to nuance in how the speaker frames the idea.',
      whyLabel: 'Why this word',
    },
  });
}

function settingsPanel(x, y) {
  return `<g filter="url(#shadow)">
    <rect x="${x}" y="${y}" width="600" height="540" rx="26" fill="${C.panel}" stroke="${C.line}"/>
    <rect x="${x}" y="${y}" width="600" height="62" rx="26" fill="${C.panel2}"/>
    ${logo(x + 28, y + 18, .72)}
    <text x="${x + 548}" y="${y + 42}" class="sans" fill="${C.muted}" font-size="25" text-anchor="middle">⚙</text>
    <text x="${x + 40}" y="${y + 112}" class="sans" fill="${C.orange}" font-size="15" font-weight="900" letter-spacing=".12em">BEHAVIOR</text>
    ${settingRow(x, y + 144, 'Auto-popup on selection', 'On', true)}
    <text x="${x + 40}" y="${y + 226}" class="sans" fill="${C.orange}" font-size="15" font-weight="900" letter-spacing=".12em">AI MODE</text>
    ${modeButton(x + 40, y + 250, 'Fast', 'Llama 3.1 8B', true)}
    ${modeButton(x + 220, y + 250, 'Balanced', 'Gemini 2.5', false, 'PRO')}
    ${modeButton(x + 400, y + 250, 'Deep', 'Claude', false, 'PRO')}
    <text x="${x + 40}" y="${y + 350}" class="sans" fill="${C.orange}" font-size="15" font-weight="900" letter-spacing=".12em">LANGUAGE</text>
    <rect x="${x + 40}" y="${y + 372}" width="520" height="50" rx="10" fill="#1f1713" stroke="${C.line}"/>
    <text x="${x + 62}" y="${y + 404}" class="sans" fill="${C.ivory}" font-size="16" font-weight="700">Auto-detect</text>
    <text x="${x + 532}" y="${y + 405}" class="sans" fill="${C.dim}" font-size="18">⌄</text>
    <text x="${x + 40}" y="${y + 476}" class="sans" fill="${C.orange}" font-size="15" font-weight="900" letter-spacing=".12em">WORD BANK</text>
    <text x="${x + 40}" y="${y + 510}" class="sans" fill="${C.ivory}" font-size="16" font-weight="700">24 words saved</text>
    <text x="${x + 502}" y="${y + 510}" class="sans" fill="${C.ivory}" font-size="16" font-weight="700">Open ↗</text>
  </g>`;
}

function settingRow(x, y, label, value, on) {
  return `<rect x="${x + 40}" y="${y}" width="520" height="54" rx="10" fill="#1f1713" stroke="${C.line}"/>
    <text x="${x + 62}" y="${y + 34}" class="sans" fill="${C.ivory}" font-size="17" font-weight="700">${esc(label)}</text>
    <text x="${x + 440}" y="${y + 34}" class="sans" fill="${C.muted}" font-size="15" font-weight="700">${esc(value)}</text>
    <rect x="${x + 492}" y="${y + 16}" width="44" height="24" rx="12" fill="${on ? C.orange : '#4a3b32'}"/>
    <circle cx="${x + (on ? 524 : 504)}" cy="${y + 28}" r="10" fill="#fff5e8"/>`;
}

function modeButton(x, y, name, sub, active, tag = '') {
  return `<g>
    <rect x="${x}" y="${y}" width="150" height="66" rx="12" fill="${active ? '#2c2018' : '#1f1713'}" stroke="${active ? C.orange : C.line}"/>
    <text x="${x + 16}" y="${y + 26}" class="sans" fill="${C.ivory}" font-size="17" font-weight="800">${name}</text>
    <text x="${x + 16}" y="${y + 49}" class="sans" fill="${C.dim}" font-size="13" font-weight="700">${sub}</text>
    ${tag ? `<rect x="${x + 104}" y="${y + 10}" width="36" height="18" rx="9" fill="#f6eadb"/><text x="${x + 122}" y="${y + 23}" class="sans" fill="${C.orange}" font-size="9" font-weight="900" text-anchor="middle">${tag}</text>` : ''}
  </g>`;
}

function card6() {
  const w = 1280, h = 800;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    ${defs()}${background(w, h)}${logo(72,64,1.08)}
    ${headline(72, 202, ['You control', '*the reading*', 'flow'], { size: 62 })}
    <text x="72" y="492" class="sans" fill="${C.ivory}" font-size="24" font-weight="700">
      <tspan x="72">Use automatic lookup,</tspan><tspan x="72" dy="36">right-click lookup, or</tspan><tspan x="72" dy="36">turn auto-popup off</tspan><tspan x="72" dy="36">anytime.</tspan>
    </text>
    ${settingsPanel(520, 86)}
  </svg>`;
}

function smallTile() {
  const w = 440, h = 280;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    ${defs()}${background(w, h)}${logo(26,24,.8)}
    ${headline(26, 104, ['AI *contextual*', 'dictionary'], { size: 33, gap: 42 })}
    <text x="26" y="204" class="sans" fill="${C.ivory}" font-size="16" font-weight="700"><tspan x="26">Highlight. Understand.</tspan><tspan x="26" dy="24">Keep reading.</tspan></text>
    <g filter="url(#soft)">
      <rect x="250" y="96" width="164" height="154" rx="14" fill="${C.cream}"/>
      <text x="270" y="130" class="serif" fill="${C.ink}" font-size="23" font-weight="700">sublime</text>
      <rect x="270" y="144" width="74" height="20" rx="10" fill="#f6eadb"/>
      <text x="307" y="158" class="sans" fill="${C.orange}" font-size="9" font-weight="900" text-anchor="middle">adjective</text>
      <text x="270" y="186" class="sans" fill="${C.ink}" font-size="11" font-weight="800"><tspan x="270">Of such excellence</tspan><tspan x="270" dy="16">as to inspire awe.</tspan></text>
      <text x="270" y="232" class="sans" fill="#8e623f" font-size="9" font-weight="900">WHY THIS WORD</text>
    </g>
  </svg>`;
}

function marquee() {
  const w = 1400, h = 560;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    ${defs()}${background(w, h)}${logo(74,60,1.05)}
    ${headline(74, 190, ['Not every meaning.', 'The *right* meaning.'], { size: 62, gap: 74 })}
    <text x="74" y="370" class="sans" fill="${C.ivory}" font-size="24" font-weight="700"><tspan x="74">Contextual definitions</tspan><tspan x="74" dy="36">for serious readers.</tspan></text>
    <rect x="74" y="442" width="174" height="54" rx="12" fill="url(#orange)"/>
    <text x="161" y="477" text-anchor="middle" class="sans" fill="#fff" font-size="18" font-weight="850">Add to Chrome</text>
    ${browser(660, 54, 620, 410, 'A Map of Small Decisions', ['Life rarely turns on grand declarations. More often,', 'it is the small, almost invisible choices that lead us', 'somewhere unexpected. The path looked ordinary', 'at first, even sensible, but its labyrinthine turns', 'kept revealing new possibilities.'], 'labyrinthine')}
    ${lexioPopup(780, 326, 'labyrinthine', 'adjective', 'Intricate and difficult to follow, like a maze.', 'Here, it describes a path whose twists feel complex but intentional.', 'Why this word')}
  </svg>`;
}

function squareSocial() {
  const w = 1200, h = 1200;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    ${defs()}${background(w, h)}${logo(82,76,1.2)}
    ${headline(82, 240, ['Read deeper.', 'Understand', '*everything.*'], { size: 78, gap: 88 })}
    <text x="82" y="558" class="sans" fill="${C.ivory}" font-size="28" font-weight="700">Lexio explains words in context.</text>
    ${browser(220, 650, 760, 390, 'The Quiet Observatory', ['The sentence looked simple until one', 'equivocal phrase changed its direction.', 'A dictionary offered meanings; Lexio showed', 'which one mattered here.'], 'equivocal')}
    ${lexioPopup(520, 824, 'equivocal', 'adjective', 'Open to more than one interpretation.', 'Here, it describes a statement that leaves room for different conclusions.', 'Why this word')}
  </svg>`;
}

const assets = [
  ['01-contextual-definition', 1280, 800, card1],
  ['02-phrase-lookup', 1280, 800, card2],
  ['03-no-tab-switching', 1280, 800, card3],
  ['04-word-bank', 1280, 800, card4],
  ['05-languages', 1280, 800, card5],
  ['06-reading-flow-settings', 1280, 800, card6],
  ['07-small-promo-tile-440x280', 440, 280, smallTile],
  ['08-marquee-1400x560', 1400, 560, marquee],
  ['09-square-social-1200x1200', 1200, 1200, squareSocial],
];

async function renderSvg(win, name, w, h, svg) {
  const svgPath = path.join(outDir, `${name}.svg`);
  const png2xPath = path.join(outDir, `${name}@2x.png`);
  const pngPath = path.join(outDir, `${name}.png`);
  fs.writeFileSync(svgPath, svg);

  win.setSize(w, h);
  await win.webContents.executeJavaScript(`
    document.documentElement.style.margin = '0';
    document.documentElement.style.width = '${w}px';
    document.documentElement.style.height = '${h}px';
    document.body.style.margin = '0';
    document.body.style.background = '#15110e';
    document.body.style.width = '${w}px';
    document.body.style.height = '${h}px';
    document.body.style.overflow = 'hidden';
    document.body.innerHTML = ${JSON.stringify(svg)};
  `);
  await new Promise(resolve => setTimeout(resolve, 120));
  const image = await win.capturePage();
  fs.writeFileSync(png2xPath, image.toPNG());

  execFileSync('sips', ['-z', String(h), String(w), png2xPath, '--out', pngPath], { stdio: 'ignore' });
}

async function main() {
  const win = new BrowserWindow({
    width: 1400,
    height: 1200,
    show: false,
    frame: false,
    resizable: false,
    webPreferences: { offscreen: true, nodeIntegration: false, contextIsolation: true },
  });
  await win.loadURL('data:text/html;charset=utf-8,<html><body></body></html>');
  for (const [name, w, h, make] of assets) {
    await renderSvg(win, name, w, h, make());
  }
  win.destroy();
  app.quit();
}

app.whenReady().then(main).catch(err => {
  console.error(err);
  app.exit(1);
});
