"""Usage-limit and rate-limit constants.

Extracted verbatim from main.py (Phase 2). These are plain literals with no
environment or import-time side effects, so they can be imported anywhere.
Env-derived settings (SECRET_KEY, SMTP, API keys, SITE_URL) intentionally
stay closer to their use sites for now and will move in a later step.
"""

import os

# ── Usage limits ─────────────────────────────────────────────────────────────
FREE_LOOKUP_LIMIT = 20    # signed-in free tier: lookups per month (Fast only)
ANON_LOOKUP_LIMIT = 5     # anonymous (no account): free lookups before sign-up
FREE_OCR_LIMIT    = 3
TRIAL_DAYS        = 3

# ── Hourly weighted rate limit ───────────────────────────────────────────────
# Every lookup costs "credits" based on the model used. The weights reflect
# relative compute cost so the limit can't be gamed by spamming Deep mode.
MODEL_WEIGHTS = {"fast": 1, "balanced": 2, "deep": 3}

# Per-hour credit budgets. Pro gets a generous budget that supports very heavy
# reading (≈ 40 Deep / 60 Balanced / 120 Fast lookups per hour) while still
# protecting the service from automated abuse. Free is tighter so a single
# burst can't drain the entire monthly allowance.
HOURLY_LIMIT_PRO  = 120
HOURLY_LIMIT_FREE = 20

# Per-month credit ceiling for Pro accounts. Caps absolute exposure to a single
# abusing account at ~$33/month in Anthropic costs while remaining ~5× more
# than any real reader could ever consume. Free users are already bounded by
# FREE_LOOKUP_LIMIT (20 lookups, fast-only = 20 credits/month).
MONTHLY_CREDIT_CAP_PRO = 20000

# Hard monthly OCR cap for Pro. Realistic heavy use is <100/month; this leaves
# 5× headroom and prevents OCR-spam abuse with GPT-4o vision (~$0.03/scan).
PRO_OCR_MONTHLY_CAP = 500

# Family plan: 1 owner + 3 members.
FAMILY_PLAN_SEATS = int(os.getenv("FAMILY_PLAN_SEATS", "4"))
