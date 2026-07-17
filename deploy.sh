#!/usr/bin/env bash
# deploy.sh — pull latest code and restart the lexio service.
# Usage (on the server):
#   sudo /var/www/lexio/deploy.sh
#
# For nginx route changes, also run:
#   sudo /var/www/lexio/deploy.sh --nginx

set -euo pipefail

cd /var/www/lexio

echo "── pulling latest from git ──"
git pull --ff-only

echo
echo "── pre-deploy database backup ──"
if [[ -x scripts/backup_db.sh ]]; then
    scripts/backup_db.sh || echo "⚠ backup failed — continuing deploy (check sqlite3 is installed)"
else
    echo "⚠ scripts/backup_db.sh missing — skipping"
fi

# Ensure the nightly backup cron is installed (idempotent).
if [[ ! -f /etc/cron.d/lexio-backup ]]; then
    echo "15 3 * * * root /var/www/lexio/scripts/backup_db.sh >> /var/log/lexio-backup.log 2>&1" > /etc/cron.d/lexio-backup
    chmod 644 /etc/cron.d/lexio-backup
    echo "✓ installed nightly backup cron (/etc/cron.d/lexio-backup)"
fi

echo
echo "── rebuilding prerendered language pages ──"
if venv/bin/python3 build_lang_pages.py; then
    echo "✓ static/{es,fr,de,it,pt,nl,ru,zh,ja,ko}/index.html up to date"
else
    echo "⚠ build_lang_pages.py failed — continuing deploy, but language pages may be stale"
fi

echo
echo "── restarting lexio (uvicorn) ──"
systemctl restart lexio
# Poll for readiness rather than fixed sleep — uvicorn workers take ~5s to bind.
for i in {1..15}; do
    if curl -fs -o /dev/null -m 2 http://127.0.0.1:8000/api/config; then
        echo "✓ lexio is running (ready after ${i}s)"
        break
    fi
    sleep 1
    if [[ $i -eq 15 ]]; then
        echo "✗ lexio failed to start within 15s — check: journalctl -u lexio -n 30"
        exit 1
    fi
done

# Show nginx.conf diff if the repo template differs from the live config.
# (We don't auto-apply because the live config has Certbot SSL blocks not in the template.)
if [[ "${1:-}" == "--nginx" ]]; then
    echo
    echo "── nginx live-vs-repo diff ──"
    if diff -q /etc/nginx/sites-enabled/lexio nginx.conf >/dev/null; then
        echo "✓ no nginx changes"
    else
        echo "⚠ live nginx config differs from repo template."
        echo "  Live:  /etc/nginx/sites-enabled/lexio"
        echo "  Repo:  /var/www/lexio/nginx.conf"
        echo "  Review the diff and patch the live config manually, then:"
        echo "    sudo nginx -t && sudo systemctl reload nginx"
        echo
        diff /etc/nginx/sites-enabled/lexio nginx.conf || true
    fi
fi

echo
echo "── smoke test ──"
curl -s -o /dev/null -w "  / → HTTP %{http_code}\n" https://lexio.site/
curl -s -o /dev/null -w "  /glossary → HTTP %{http_code}\n" https://lexio.site/glossary
curl -s -o /dev/null -w "  /works → HTTP %{http_code}\n" https://lexio.site/works
curl -s -o /dev/null -w "  /sitemap.xml → HTTP %{http_code}\n" https://lexio.site/sitemap.xml
curl -s -o /dev/null -w "  /es/ → HTTP %{http_code}\n" https://lexio.site/es/
curl -s -o /dev/null -w "  /ja/ → HTTP %{http_code}\n" https://lexio.site/ja/

echo
echo "✓ deploy complete"
