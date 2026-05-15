# Lexio

**Contextual word definitions for serious readers.**

Paste any text, click **Analyze**, then tap any word to see what it means *in that exact sentence* — not a generic dictionary entry. Lexio sends the word plus its full surrounding passage to one of three AI providers and returns the contextual meaning, part of speech, IPA, etymology, register, and why the author probably chose that word over a simpler synonym.

**Live at [lexio.site](https://lexio.site)** · Built and maintained by [@mtvlgnv](https://github.com/mtvlgnv)

---

## Highlights

- **Three reading modes** routed to three providers:
  - **Fast** — GPT-4o Mini · near-instant lookups, 1 credit
  - **Balanced** — Gemini 2.5 Flash · wide language coverage, 2 credits
  - **Deep** — Claude Sonnet 4.5 · literary-grade reasoning, 3 credits
- **OCR** — drop a photo of a page and Lexio extracts the text for analysis (Gemini or GPT-4o vision)
- **Word bank** — save words to revisit; synced across devices when signed in
- **Chrome extension** — look up words on any website without leaving the page
- **Mac app** — full app or menu-bar overlay (`⌘⇧L`) so Lexio is always one shortcut away
- **11 languages in, 11 languages out** — analyze prose in Spanish, French, German, Dutch, Russian, Japanese, Chinese, Arabic, Portuguese, Italian, English; pick the output language independently
- **Trending** — anonymous live view of what other readers are looking up this month
- **Privacy-first** — only the word and a short context window are sent to the AI; the full text never leaves your browser ([privacy policy](https://lexio.site/privacy.html))

---

## Plans

| | Free | Pro |
|---|---|---|
| Word lookups / month | 100 | unlimited (capped at 20,000 credits/month) |
| Image (OCR) scans / month | 3 | 500 |
| Modes available | Fast | Fast, Balanced, Deep |
| Hourly credit budget | 20 | 120 |
| Word bank sync across devices | — | ✓ |
| Price | $0 | from $2.99 / €2.99 / £2.99 per month |

New users get a **3-day free trial** of Pro. A card is required at signup (via Stripe Checkout); cancel any time before day 3 and you won't be charged.

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python · FastAPI · SQLAlchemy · Pydantic · slowapi |
| AI providers | Anthropic SDK · OpenAI SDK · `google-genai` |
| Auth | passlib (bcrypt) · python-jose (JWT) · Google Identity Services · Sign in with Apple |
| Payments | Stripe (Checkout + Billing Portal + webhooks) · multi-currency (USD/EUR/GBP) |
| Frontend | Vanilla HTML/CSS/JS, single file, no build step |
| Storage | SQLite (with built-in migration runner) |
| Server | nginx · uvicorn · systemd · Ubuntu 24.04 · Hetzner Cloud · Let's Encrypt |
| Distribution | Chrome extension (`static/lexio-extension.zip`) · Electron Mac apps (GitHub Releases) |

---

## Run locally

**Prerequisites:** Python 3.11+, and at least one of the AI keys ([Anthropic](https://console.anthropic.com/), [OpenAI](https://platform.openai.com/), [Google AI Studio](https://aistudio.google.com/)).

```bash
git clone https://github.com/mtvlgnv/Lexio.git
cd Lexio

# Set up Python
python3 -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env: paste at least one AI key. Stripe/OAuth/SMTP are optional
# for local development.

# Start
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000). The SQLite database (`lexio.db`) is created automatically on first run and migrated as needed.

---

## API

### `POST /define`

```json
// Request
{
  "word":    "ephemeral",
  "context": "The ephemeral beauty of cherry blossoms draws millions to Japan every spring.",
  "model":   "deep",       // "fast" | "balanced" | "deep" — defaults to "deep"
  "lang":    "auto"        // ISO 639-1 or "auto" — output language
}

// Response (single-word lookup)
{
  "pos":        "adjective",
  "ipa":        "/ɪˈfɛm.ər.əl/",
  "definition": "Lasting for only a short time; transitory.",
  "contextual": "Here, it captures the fleeting, days-long blooming window…",
  "why":        "Ephemeral carries a poetic weight that 'short-lived' lacks…",
  "simpler":    "fleeting",
  "etymology":  "From Greek ephēmeros — 'lasting only a day'.",
  "register":   "literary",
  "_usage":     { "used": 7, "limit": 100 },
  "_hourly":    { "used": 3, "limit": 120, "weight": 3, "reset_in": 2842,
                  "month_used": 47, "month_limit": 20000 }
}
```

For multi-word phrases, the `pos`, `ipa`, `simpler`, and `etymology` fields are omitted.

### Rate limiting

- **Per-IP burst**: 20 `/define` requests per minute (slowapi)
- **Per-user hourly**: 20 credits (free) / 120 credits (Pro). Each lookup costs `1`, `2`, or `3` credits based on mode. Resets every hour.
- **Per-Pro monthly**: 20,000 credits and 500 OCR scans. Safety ceiling — sized to be unreachable by any real reader.
- **Per-user monthly (free)**: 100 lookups, 3 OCR scans.

Exceeding limits returns `429` (hourly) or `402` (monthly) with a structured detail body so the UI can show actionable messages.

### Other endpoints

| Endpoint | Purpose |
|---|---|
| `POST /ocr` | Extract text from an image (multipart upload) |
| `POST /fetch-text` | Pull article text from a URL via Trafilatura |
| `POST /auth/{register,login,google,apple}` | Auth flows; returns a JWT |
| `GET /api/{usage,pro-status,user-model}` | Current usage / Pro state / saved model preference |
| `POST /stripe/{create-checkout,customer-portal,webhook}` | Stripe integration |
| `GET /stats/top-words` | Anonymous trending lookups (powers the landing-page widget) |

---

## Project structure

```
├── main.py                  # FastAPI app: routes, models, migrations, Stripe
├── requirements.txt
├── .env.example             # Copy to .env and fill in keys
├── .gitignore
├── lexio.service            # systemd unit (production)
├── nginx.conf               # nginx reverse-proxy + static config
├── DEPLOY.md                # VPS deployment guide
├── README.md
├── LICENSE
├── static/
│   ├── index.html           # Entire SPA frontend — single file, no build
│   ├── privacy.html         # Privacy policy
│   ├── credits.html         # Credits page
│   ├── robots.txt
│   ├── sitemap.xml
│   ├── lexio-extension.zip  # Packaged Chrome extension served from the site
│   └── pro/                 # Legacy pricing page (kept for /pro route)
├── extension/               # Chrome extension source (zipped into static/)
└── desktop/                 # Electron Mac app source (built into GitHub Releases)
```

---

## Deploying to a VPS

See **[DEPLOY.md](DEPLOY.md)** for the full step-by-step guide (Ubuntu 24.04, nginx, systemd, SSL via Certbot, Stripe webhook setup, security headers).

---

## License

[MIT](LICENSE)
