#!/usr/bin/env bash
# backup_db.sh — nightly SQLite backup with rotation.
#
# Uses sqlite3's online .backup command, which is safe while the app is
# running (consistent snapshot, honors WAL). Plain `cp` is NOT safe.
#
# Install on the server (done once by deploy):
#   /etc/cron.d/lexio-backup:
#     15 3 * * * root /var/www/lexio/scripts/backup_db.sh >> /var/log/lexio-backup.log 2>&1
#
# Restore:
#   gunzip -k /var/backups/lexio/lexio-YYYYMMDD-HHMMSS.db.gz
#   systemctl stop lexio
#   cp <unzipped file> /var/www/lexio/lexio.db && chown www-data:www-data /var/www/lexio/lexio.db
#   systemctl start lexio

set -euo pipefail

DB="${LEXIO_DB:-/var/www/lexio/lexio.db}"
BACKUP_DIR="${LEXIO_BACKUP_DIR:-/var/backups/lexio}"
KEEP_DAYS="${LEXIO_BACKUP_KEEP_DAYS:-14}"

[[ -f "$DB" ]] || { echo "✗ database not found: $DB"; exit 1; }
mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/lexio-$STAMP.db"

sqlite3 "$DB" ".backup '$OUT'"

# Sanity: the snapshot must be a healthy SQLite db before we keep it
if [[ "$(sqlite3 "$OUT" 'PRAGMA integrity_check;')" != "ok" ]]; then
    echo "✗ backup verification failed: $OUT"
    rm -f "$OUT"
    exit 1
fi

gzip "$OUT"
gunzip -t "$OUT.gz"

# Rotate: drop backups older than KEEP_DAYS
find "$BACKUP_DIR" -name 'lexio-*.db.gz' -mtime +"$KEEP_DAYS" -delete

echo "✓ $(date -u +%FT%TZ) backed up $DB → $OUT.gz ($(du -h "$OUT.gz" | cut -f1))"
