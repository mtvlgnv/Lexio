#!/usr/bin/env bash
# desktop/compact.html is the canonical source for the embedded lookup UI —
# it's also served as the website's own /compact.html. A plain copy (not a
# symlink) because nginx serves static/ straight off disk in production via
# try_files (symlinks fine there), but Starlette's StaticFiles — used when
# running the FastAPI app directly without nginx, e.g. local dev — rejects
# any static file whose real path escapes the static/ directory, 404ing on
# a symlink that points out to desktop/. A real copy has no such failure
# mode on either path.
#
# desktop/tokens.css ships alongside it for the same reason: compact.html
# links to it with a plain relative `href="tokens.css"`, so the website's
# copy needs its own tokens.css sitting next to it at static/tokens.css —
# forgetting this (bug report #4) means the live site's /compact.html 404s
# on every color variable the moment compact.html is synced without it.
#
# Run this after editing desktop/compact.html or desktop/tokens.css, before
# committing:
#   bash desktop/scripts/sync-compact.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
cp desktop/compact.html static/compact.html
cp desktop/tokens.css static/tokens.css
echo "✓ synced desktop/compact.html → static/compact.html"
echo "✓ synced desktop/tokens.css → static/tokens.css"
