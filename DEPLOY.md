# Deploying Lexio on Ubuntu 24.04 (Hetzner VPS)

## Prerequisites

- Fresh Ubuntu 24.04 VPS (Hetzner CX21 or larger)
- A domain name pointing to the server's IP (A record)
- SSH access as root (or a sudo user)
- At least one AI API key (Anthropic, OpenAI, or Google). All three for the full Fast/Balanced/Deep matrix.
- A Stripe account (for the Pro tier — optional in development, required in production)

---

## 1 — Initial server setup

```bash
apt update && apt upgrade -y

# Optional: create a non-root deploy user
adduser deploy
usermod -aG sudo deploy
```

---

## 2 — Install system dependencies

```bash
apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx
```

---

## 3 — Clone the repository

```bash
mkdir -p /var/www/lexio
cd /var/www
git clone https://github.com/mtvlgnv/Lexio.git lexio
cd /var/www/lexio
```

---

## 4 — Set up the Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

---

## 5 — Configure the environment file

```bash
cp .env.example .env
nano .env
```

### Environment variables

**Required (core):**

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key. Generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. **Never commit.** |
| `ANTHROPIC_API_KEY` | Powers **Deep** mode (Claude Sonnet 4.5). |
| `GROQ_API_KEY` | Powers **Fast** mode (GPT-OSS 20B via Groq). |
| `GROQ_FAST_MODEL` | Optional override for Fast tier (default: `openai/gpt-oss-20b`). |
| `GROQ_FAST_MAX_TOKENS` | Max completion tokens for Fast tier (default: `1200`). |
| `OPENAI_API_KEY` | OCR fallback (no longer used for Fast mode). |
| `GOOGLE_API_KEY` | Powers **Balanced** mode (Gemini 2.5 Flash) and primary OCR. |

You need at least one AI key for the app to start, but only the mode whose key is set will work.

**Required for Pro tier:**

| Variable | Purpose |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_live_…` (or `sk_test_…` while testing). |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` — Stripe gives you this when you create a webhook endpoint. |
| `STRIPE_PRICE_ID` | The multi-currency price ID for the Pro subscription. |
| `SITE_URL` | Your public site origin, e.g. `https://lexio.site`. Used in Stripe redirect URLs. |

**Optional (OAuth sign-in):**

| Variable | Purpose |
|---|---|
| `GOOGLE_CLIENT_ID` | "Sign in with Google" — leave blank to disable. |
| `APPLE_SERVICES_ID` | "Sign in with Apple" — leave blank to disable. |

**Optional (email — for password reset):**

| Variable | Purpose |
|---|---|
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | Any standard SMTP relay (Mailgun, Postmark, SES, etc.). |

**Optional (admin):**

| Variable | Purpose |
|---|---|
| `ADMIN_KEY` | Bearer token for admin-only endpoints. |

### File permissions

The `.env` contains secrets — lock it down:

```bash
chown www-data:www-data .env
chmod 600 .env
```

---

## 6 — Set file ownership

```bash
chown -R www-data:www-data /var/www/lexio
```

The SQLite database (`lexio.db`) is created on first launch in the working directory. Migrations run automatically on every startup — no manual step needed.

---

## 7 — Install and start the systemd service

```bash
cp /var/www/lexio/lexio.service /etc/systemd/system/lexio.service

systemctl daemon-reload
systemctl enable lexio
systemctl start lexio

systemctl status lexio
journalctl -u lexio -f
```

The service hardening (NoNewPrivileges, PrivateTmp, ProtectSystem=strict, ReadWritePaths=/var/www/lexio) is already in `lexio.service`.

---

## 8 — Configure nginx

```bash
cp /var/www/lexio/nginx.conf /etc/nginx/sites-available/lexio
nano /etc/nginx/sites-available/lexio
# Replace YOUR_DOMAIN_OR_IP with your actual domain
ln -s /etc/nginx/sites-available/lexio /etc/nginx/sites-enabled/lexio
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

### Recommended security headers

Add these inside the HTTPS `server { ... }` block (after Certbot has run, step 9):

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options    "nosniff"  always;
add_header X-Frame-Options           "SAMEORIGIN" always;
add_header X-XSS-Protection          "1; mode=block" always;
add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
```

Reload nginx after editing: `nginx -t && systemctl reload nginx`.

---

## 9 — Obtain an SSL certificate with Certbot

```bash
certbot --nginx -d yourdomain.com
# Choose option 2 to redirect HTTP → HTTPS.

certbot renew --dry-run
```

---

## 10 — Configure Stripe (if running Pro)

1. In the Stripe Dashboard, create a **Product** named "Lexio Pro" with a recurring monthly price. Add additional currencies (EUR, GBP) on the same Price object.
2. Copy the price ID into `.env` as `STRIPE_PRICE_ID`.
3. Create a **webhook endpoint** at `https://yourdomain.com/stripe/webhook` and subscribe to:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the webhook signing secret (`whsec_…`) into `.env` as `STRIPE_WEBHOOK_SECRET`.
5. Restart the service: `systemctl restart lexio`.

### Trial behavior

New users who go through Checkout get a **3-day free trial** with `payment_method_collection: "always"` — Stripe collects the card up-front and charges automatically on day 3 unless the user cancels in the Billing Portal. Trial eligibility is based on the local `stripe_customer_id`: users who've already been Stripe customers (cancelled before, or trial already consumed) check out without a trial.

---

## 11 — Verify the deployment

```bash
systemctl status lexio nginx

# Basic API check (no auth, lookups against the free tier)
curl -s -X POST https://yourdomain.com/define \
  -H "Content-Type: application/json" \
  -d '{"word":"ephemeral","context":"The ephemeral beauty of cherry blossoms.","model":"fast"}' \
  | python3 -m json.tool

# Usage endpoint (anonymous)
curl -s https://yourdomain.com/api/usage | python3 -m json.tool
```

Open `https://yourdomain.com` — you should see the Lexio app.

---

## Updating the app

```bash
cd /var/www/lexio
git pull origin main

# Only if requirements.txt changed
source venv/bin/activate && pip install -r requirements.txt && deactivate

systemctl restart lexio
```

The migration runner inside `main.py` will automatically apply any new schema migrations on startup. Each migration is idempotent and tracked in the `schema_version` table.

---

## Useful commands

| Task | Command |
|---|---|
| Live logs | `journalctl -u lexio -f` |
| Restart app | `systemctl restart lexio` |
| Reload (no downtime) | `systemctl reload nginx` |
| Check nginx config | `nginx -t` |
| Renew SSL manually | `certbot renew` |
| Inspect DB | `python3 -c 'import sqlite3; [print(r) for r in sqlite3.connect("/var/www/lexio/lexio.db").execute("SELECT version, description FROM schema_version ORDER BY version")]'` |

---

## Troubleshooting

**502 Bad Gateway** — uvicorn isn't running.
`systemctl status lexio && journalctl -u lexio -n 80`

**`AttributeError` on Stripe webhook** — SDK version mismatch.
Make sure `stripe` in `requirements.txt` is current (the code uses `event.to_dict()` for SDK v15+ compatibility).

**Free user sees Balanced/Deep as available** — frontend cached.
Hard-refresh the page. The frontend locks Pro-only models until `/api/pro-status` confirms.

**Empty geo-detected currency** — `ip-api.com` is rate-limiting.
The endpoint already uses HTTP (the free tier doesn't allow HTTPS); if your VPS is sharing an IP with many calls, fall back to a paid IP-geo provider or accept the default USD.

**Permission denied on `.env`** —
`chown www-data:www-data /var/www/lexio/.env && chmod 600 /var/www/lexio/.env`
