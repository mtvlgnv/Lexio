# Lexio

**Contextual word definitions, powered by Claude.**

Paste any text, click **Analyze**, then tap any word to get its definition *as used in that specific passage* — not a generic dictionary entry. Lexio calls Claude Haiku with the word and its full surrounding context, returning a part of speech, a precise contextual meaning, and a note on why that word was chosen over a simpler alternative.

**Live at [lexio.site](https://lexio.site)**

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python · FastAPI · Anthropic SDK |
| Model | `claude-haiku-4-5-20251001` |
| Frontend | Vanilla HTML/CSS/JS (single file) |
| Server | Nginx · uvicorn · systemd · Ubuntu 24.04 |

---

## Run locally

**Prerequisites:** Python 3.11+, an [Anthropic API key](https://console.anthropic.com/).

```bash
git clone https://github.com/mtvlgnv/Lexio.git
cd Lexio

# Install dependencies
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env and paste your Anthropic API key

# Start
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

---

## API

### `POST /define`

```json
// Request
{ "word": "ephemeral", "context": "The full passage the word appears in..." }

// Response
{
  "pos": "adjective",
  "contextual": "Lasting for only a short time; transitory. Here it describes...",
  "why": "Ephemeral carries a poetic weight that 'short-lived' lacks, evoking..."
}
```

Rate limited to **20 requests / minute per IP**.
Input limits: `word` ≤ 60 chars, `context` ≤ 8 000 chars.

---

## Deploying to a VPS

See **[DEPLOY.md](DEPLOY.md)** for the full step-by-step guide (Ubuntu 24.04, Nginx, systemd, SSL via Certbot).

---

## Project structure

```
├── main.py          # FastAPI app — /define endpoint + static file serving
├── requirements.txt
├── .env.example     # Copy to .env and add your API key
├── .gitignore
├── static/
│   └── index.html   # Entire frontend — no build step
├── lexio.service    # systemd unit
├── nginx.conf       # Nginx reverse-proxy config
└── DEPLOY.md        # VPS deployment guide
```
