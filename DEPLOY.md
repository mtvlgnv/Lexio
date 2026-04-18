# Deploying Lexio on Ubuntu 24.04 (Hetzner VPS)

## Prerequisites

- Fresh Ubuntu 24.04 VPS (Hetzner CX21 or larger)
- A domain name pointing to the server's IP (A record)
- SSH access as root (or a sudo user)

---

## 1 — Initial server setup

```bash
# Update packages
apt update && apt upgrade -y

# Create a deploy user (optional but recommended)
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
# Create the web root
mkdir -p /var/www/lexio
cd /var/www

# Clone your repo (replace URL with your actual repo)
git clone https://github.com/yourname/lexio.git lexio
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
nano .env          # paste your real Anthropic API key
```

The file should look like:
```
ANTHROPIC_API_KEY=sk-ant-...
```

Set secure permissions so only root/www-data can read it:
```bash
chown www-data:www-data .env
chmod 600 .env
```

---

## 6 — Set file ownership

```bash
chown -R www-data:www-data /var/www/lexio
```

---

## 7 — Install and start the systemd service

```bash
# Copy the unit file
cp /var/www/lexio/lexio.service /etc/systemd/system/lexio.service

# Reload systemd and enable the service
systemctl daemon-reload
systemctl enable lexio
systemctl start lexio

# Verify it started correctly
systemctl status lexio
# Should show: Active: active (running)

# Tail the logs
journalctl -u lexio -f
```

---

## 8 — Configure Nginx

```bash
# Copy the Nginx config
cp /var/www/lexio/nginx.conf /etc/nginx/sites-available/lexio

# Edit the server_name line
nano /etc/nginx/sites-available/lexio
# Replace YOUR_DOMAIN_OR_IP with your actual domain, e.g.:
#   server_name lexio.example.com;

# Enable the site
ln -s /etc/nginx/sites-available/lexio /etc/nginx/sites-enabled/lexio

# Remove the default site if still present
rm -f /etc/nginx/sites-enabled/default

# Test the config
nginx -t

# Reload Nginx
systemctl reload nginx
```

---

## 9 — Obtain an SSL certificate with Certbot

```bash
certbot --nginx -d yourdomain.com
# Follow the prompts; choose option 2 to redirect HTTP → HTTPS

# Certbot will automatically edit your nginx config and set up renewal
# Verify auto-renewal works
certbot renew --dry-run
```

---

## 10 — Verify the deployment

```bash
# Check the service is running
systemctl status lexio nginx

# Hit the API endpoint
curl -s -X POST https://yourdomain.com/define \
  -H "Content-Type: application/json" \
  -d '{"word":"ephemeral","context":"The ephemeral beauty of cherry blossoms draws millions to Japan every spring."}' | python3 -m json.tool
```

Open `https://yourdomain.com` in a browser — you should see the Lexio interface.

---

## Updating the app

```bash
cd /var/www/lexio
git pull
source venv/bin/activate
pip install -r requirements.txt   # only needed if requirements changed
deactivate
systemctl restart lexio
```

---

## Useful commands

| Task | Command |
|---|---|
| View live logs | `journalctl -u lexio -f` |
| Restart app | `systemctl restart lexio` |
| Reload Nginx | `systemctl reload nginx` |
| Check Nginx config | `nginx -t` |
| Renew SSL manually | `certbot renew` |

---

## Troubleshooting

**502 Bad Gateway** — The FastAPI process isn't running.
Check: `systemctl status lexio` and `journalctl -u lexio -n 50`

**"Failed to parse model response"** — Claude returned unexpected output.
Check your `ANTHROPIC_API_KEY` in `.env` and that the key has quota remaining.

**Permission denied on .env** — Re-run `chown www-data:www-data /var/www/lexio/.env && chmod 600 /var/www/lexio/.env`
