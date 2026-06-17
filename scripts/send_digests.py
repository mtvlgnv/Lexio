#!/usr/bin/env python3
"""Weekly re-engagement digest sender.

Run as a single process (NOT inside the multi-worker web app) so each eligible
user gets at most one email per run. Intended to be fired by a systemd timer or
cron once a day; the per-user DIGEST_INTERVAL_DAYS throttle means a user only
actually receives one roughly every 7 days.

Eligibility: verified, not opted out, not due again yet, and with at least a few
words saved server-side (Pro users — free banks live only in the browser).

Usage:
    cd /var/www/lexio && venv/bin/python scripts/send_digests.py [--dry-run]
"""
import os
import sys
import datetime

# Make the app package importable when run from the project root, and load the
# same .env the web app uses (SECRET_KEY, SMTP_*, DB path, SITE_URL).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.db import SessionLocal
from app.models import User, WordBankEntry
from app.email import send_weekly_digest, DIGEST_INTERVAL_DAYS, SMTP_USER


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not SMTP_USER:
        print("SMTP not configured — nothing to send.")
        return 0

    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        cutoff = now - datetime.timedelta(days=DIGEST_INTERVAL_DAYS)
        candidates = (
            db.query(User)
            .filter(User.digest_opt_out == 0, User.email_verified == 1)
            .all()
        )
        eligible = sent = skipped = 0
        for u in candidates:
            if u.last_digest_at and u.last_digest_at > cutoff:
                continue  # already nudged this cycle
            word_count = (
                db.query(WordBankEntry).filter(WordBankEntry.user_id == u.id).count()
            )
            if word_count < 3:
                continue  # not enough saved words to be worth an email
            eligible += 1
            if dry_run:
                print(f"[dry-run] would email {u.email} ({word_count} words)")
                continue
            if send_weekly_digest(db, u):
                sent += 1
            else:
                skipped += 1
        print(
            f"digest run complete: eligible={eligible} sent={sent} "
            f"skipped={skipped} dry_run={dry_run}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
