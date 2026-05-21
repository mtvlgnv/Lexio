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
echo "── restarting lexio (uvicorn) ──"
systemctl restart lexio
sleep 2
if systemctl is-active --quiet lexio; then
    echo "✓ lexio is running"
else
    echo "✗ lexio failed to start — check: journalctl -u lexio -n 30"
    exit 1
fi

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

echo
echo "✓ deploy complete"
