# Lexio

**Understand English the way it's really used — for readers learning English.**

Point at any word — in a pasted passage on the web, or anywhere on your Mac — and get its meaning *in that exact sentence*, not a generic dictionary entry: idioms and phrasal verbs included, explained in your own language. A dictionary hands you five definitions and lets you guess; Lexio reads the sentence first.

**Live at [lexio.site](https://lexio.site)** · Built and maintained by [@mtvlgnv](https://github.com/mtvlgnv)

---

## Highlights

- **Three reading modes** routed to three providers:
  - **Fast** — GPT-OSS 20B via Groq · near-instant, free, 1 credit
  - **Balanced** — Gemini 2.5 Flash · wide language coverage, 2 credits — also the sole engine behind every Mac app lookup (see below)
  - **Deep** — Claude Sonnet 4.5 · literary-grade reasoning, Pro only, 3 credits
- **Mac app (Lexio Glance) — vision-first.** Point your cursor at any word, anywhere (chats, PDFs, subtitles, code — not just the browser), double-tap a hotkey, and a native ScreenCaptureKit helper grabs the screen area around the pointer, marks the exact spot with a ring, and sends the image straight to Gemini — which identifies the word *and* defines it in one call. No text selection needed. Ships as a real app with a Hub (Home/Word Bank/Recent/Settings/Account), auto-updates via GitHub Releases.
- **OCR** — drop a photo of a printed page and Lexio extracts the text for analysis (Gemini, with GPT-4o vision as a fallback)
- **Word bank** — save words with the sentence you found them in; synced across devices when signed in; export to **Anki**
- **Chrome extension** — look up words on any website without leaving the page
- **16 supported languages** for input and output (the marketing site highlights the 11 most common: English, Spanish, French, German, Dutch, Russian, Japanese, Chinese, Arabic, Portuguese, Italian — the backend also accepts Korean, Hindi, Polish, Turkish, and Swedish)
- **Trending** — anonymous live view of what other readers are looking up this month
- **Privacy-conscious** — for pasted text, only the word and a short surrounding context window are sent to the AI provider; in the Mac app's point-at-word mode, a small capture of the screen area around your pointer is sent instead. Neither is stored on our servers after the request. ([privacy policy](https://lexio.site/privacy.html))

---

## Plans

| | Free | Pro |
|---|---|---|
| Word lookups / month | 20 (signed in) · 5 (anonymous) | unlimited (capped at 20,000 credits/month) |
| Image (OCR) scans / month | 3 | 500 |
| Modes available | Fast | Fast, Balanced, Deep |
| Hourly credit budget | 20 | 120 |
| Word bank sync across devices | ✓ (local-first; 10-save cap signed out) | ✓ unlimited |
| Price | $0 | $4.99/mo · $39.99/yr · $9.99/mo family (4 seats) |

New users get a **3-day free trial** of Pro. A card is required at signup (via Stripe Checkout); cancel any time before day 3 and you won't be charged.

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python · FastAPI (routers in `app/routers/`) · SQLAlchemy · Pydantic · slowapi |
| AI providers | Anthropic SDK · Groq SDK · `google-genai` · OpenAI SDK (OCR fallback only) |
| Auth | passlib (bcrypt) · python-jose (JWT) · Google Identity Services · Sign in with Apple |
| Payments | Stripe (Checkout + Billing Portal + webhooks) · multi-currency (USD/EUR/GBP) |
| Web frontend | Vanilla HTML/CSS/JS, no build step |
| Desktop app | Electron 43 · Swift (native ScreenCaptureKit capture helper) — `desktop/` |
| Storage | SQLite (with a built-in migration runner) |
| Server | nginx · uvicorn · systemd · Ubuntu 24.04 · Hetzner Cloud · Let's Encrypt |
| Distribution | Chrome extension (`static/lexio-extension.zip`) · Electron Mac app, signed + notarized (GitHub Releases, auto-updating) |

---

## Run locally

**Prerequisites:** Python 3.11+, and at least one of the AI keys ([Anthropic](https://console.anthropic.com/), [Groq](https://console.groq.com/), [Google AI Studio](https://aistudio.google.com/)).

```bash
git clone https://github.com/mtvlgnv/Lexio.git
cd Lexio

# Set up Python
python3 -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install -r requirements.txt  # or requirements.lock for pinned versions

# Configure
cp .env.example .env
# Edit .env: paste at least one AI key, and a SECRET_KEY
#   (generate with: python3 -c "import secrets; print(secrets.token_hex(32))")
# Stripe/OAuth/SMTP are optional for local development.

# Start
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000). The SQLite database (`lexio.db`) is created automatically on first run and migrated as needed.

To run the desktop app locally instead: `cd desktop && npm install && npx electron main-overlay.js` (macOS only; needs Accessibility + Screen Recording permission).

---

## API

### `POST /define`

Two request shapes, both handled by the same endpoint:

**Text lookup** (web app, Chrome extension — word + its surrounding passage):

```json
{
  "word":    "ephemeral",
  "context": "The ephemeral beauty of cherry blossoms draws millions to Japan every spring.",
  "model":   "deep",       // "fast" | "balanced" | "deep" — defaults to "sonnet"/deep
  "lang":    "auto"        // ISO 639-1 or "auto" — output language
}
```

**Image lookup** (Lexio Glance — a screenshot centered on the cursor, with a marker ring at the exact point; the model identifies the word itself):

```json
{
  "image_base64": "<base64 JPEG>",
  "image_mime":   "image/jpeg",
  "lang":         "auto"
}
```
Image lookups always route through Balanced (Gemini) regardless of `model`, and are metered against the normal lookup quota (not the OCR-scan bucket).

**Response** (single-word lookup):

```json
{
  "word":       "ephemeral",   // present only on image lookups — the model identifies it
  "pos":        "adjective",
  "ipa":        "/ɪˈfɛm.ər.əl/",
  "definition": "Lasting for only a short time; transitory.",
  "contextual": "Here, it captures the fleeting, days-long blooming window…",
  "why":        "Ephemeral carries a poetic weight that 'short-lived' lacks…",
  "simpler":    "fleeting",
  "etymology":  "From Greek ephēmeros — 'lasting only a day'.",
  "register":   "literary",
  "_usage":     { "used": 7, "limit": 20 },
  "_hourly":    { "used": 3, "limit": 120, "weight": 3, "reset_in": 2842,
                  "month_used": 47, "month_limit": 20000 }
}
```

For multi-word phrases, the `pos`, `ipa`, `simpler`, and `etymology` fields are omitted.

### Rate limiting

- **Per-IP burst**: 20 `/define` requests per minute (slowapi)
- **Per-user hourly**: 20 credits (free) / 120 credits (Pro). Each lookup costs `1`, `2`, or `3` credits based on mode — image lookups always cost 2 (Balanced weight). Resets every hour.
- **Per-Pro monthly**: 20,000 credits and 500 OCR/image scans. Safety ceiling — sized to be unreachable by any real reader.
- **Per-user monthly (free)**: 20 signed-in / 5 anonymous lookups, 3 OCR scans.

Exceeding limits returns `429` (hourly) or `402` (monthly) with a structured detail body so the UI can show actionable messages.

### Other endpoints

| Endpoint | Purpose |
|---|---|
| `POST /ocr` | Extract text from an image (multipart upload) |
| `POST /fetch-text` | Pull article text from a URL via Trafilatura |
| `POST /auth/{register,login,google,apple}` | Auth flows; returns a JWT |
| `GET/POST /wordbank`, `/wordbank/sync`, `/wordbank/anki`, `DELETE /wordbank/{word}` | Word bank CRUD + Anki deck export |
| `GET /api/{usage,pro-status,streak,user-model}` | Current usage / Pro state / lookup streak / saved model preference |
| `POST /stripe/{create-checkout,customer-portal,webhook}` | Stripe integration |
| `GET /stats/top-words` | Anonymous trending lookups (powers the landing-page widget) |
| `GET /download/mac` | Redirects to the newest Lexio Glance `.dmg` on GitHub Releases — always current |
| `GET /api/catalog`, `/api/catalog/{slug}` | Public-domain book catalog (feeds the iOS reading app's Discover tab) |

---

## Project structure

```
├── main.py                  # FastAPI bootstrap — routers, migrations, static mount (~90 lines)
├── app/                     # Backend package
│   ├── routers/             # define, auth, wordbank, account, billing, family, admin, content, tools
│   ├── ai.py                # AI provider clients (text + vision calls)
│   ├── config.py            # Limits, pricing, credit weights
│   ├── models.py, db.py, migrations.py, security.py, limits.py, schemas.py, oauth.py, email.py
├── requirements.txt / requirements.lock
├── .env.example              # Copy to .env and fill in keys
├── lexio.service              # systemd unit (production)
├── nginx.conf                 # nginx reverse-proxy + static config
├── CLAUDE.md                  # Architecture + working-agreements brief (auto-loaded by Claude Code)
├── ROADMAP.md / DESIGN_ROADMAP.md / BACKLOG.md   # Prioritized product, design, and agent-task backlogs
├── DEPLOY.md                   # VPS deployment guide
├── static/
│   ├── index.html              # Marketing landing page
│   ├── app.js                  # i18n strings + app logic for the landing page
│   ├── compact.html            # The lookup UI — served standalone AND embedded in the Mac app
│   ├── for-language-learners.html, for-students.html, for-professionals.html,
│   │   for-educators.html, for-readers.html   # ICP-specific SEO landing pages
│   ├── privacy.html, credits.html, changelog.html
│   └── lexio-extension.zip     # Packaged Chrome extension served from the site
├── extension/                  # Chrome extension source (zipped into static/)
└── desktop/                    # Electron Mac app (Lexio Glance) source
    ├── main-overlay.js         # Main process: pill overlay, capture, Hub windows, IPC
    ├── native/lexio-ocr/        # Swift ScreenCaptureKit capture helper
    ├── compact.html, pill.html, home.html, hub.html, onboarding.html
    └── store.js                 # Local persistence (userData)
```

The iOS reading app lives in its own repo: [LivelyReading](https://github.com/mtvlgnv/LivelyReading).

---

## Deploying to a VPS

See **[DEPLOY.md](DEPLOY.md)** for the full step-by-step guide (Ubuntu 24.04, nginx, systemd, SSL via Certbot, Stripe webhook setup, security headers).

---

## License

[MIT](LICENSE)
