"""Admin dashboard (cookie auth) + admin API (key auth) routes (Phase 2 extract)."""
import os
import hmac
import secrets
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Header, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jose import jwt
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.db import get_db, SessionLocal
from app.models import (
    User, WordBankEntry, SearchLog, UserSearchLog, AnonUsage,
    PasswordResetToken, FamilyInvitation,
)
from app.security import SECRET_KEY, ALGORITHM
from app.limits import _is_effectively_pro, _trial_days_left
from app.ratelimit import limiter

logger = logging.getLogger("lexio")
router = APIRouter()


# ── /api/admin/* ──────────────────────────────────────────────────────────────

_START_TIME = datetime.datetime.utcnow()

def _check_admin(x_admin_key: Optional[str] = Header(default=None)):
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or not x_admin_key or not hmac.compare_digest(x_admin_key, admin_key):
        raise HTTPException(status_code=403, detail="Forbidden")

@router.get("/api/admin/health")
async def admin_health(db: DBSession = Depends(get_db), _=Depends(_check_admin)):
    """Server health snapshot."""
    # DB ping
    db_ok = False
    try:
        db.execute(__import__('sqlalchemy').text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    # Disk usage
    stat = os.statvfs("/")
    disk_total = stat.f_blocks * stat.f_frsize
    disk_free  = stat.f_bfree  * stat.f_frsize
    disk_used  = disk_total - disk_free

    uptime_secs = int((datetime.datetime.utcnow() - _START_TIME).total_seconds())

    return {
        "status":      "ok" if db_ok else "degraded",
        "db":          db_ok,
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google_oauth_set":  bool(os.getenv("GOOGLE_CLIENT_ID")),
        "uptime_seconds":    uptime_secs,
        "disk": {
            "total_gb": round(disk_total / 1e9, 2),
            "used_gb":  round(disk_used  / 1e9, 2),
            "free_gb":  round(disk_free  / 1e9, 2),
            "pct_used": round(disk_used  / disk_total * 100, 1),
        },
        "server_time": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/api/admin/stats")
async def admin_stats(db: DBSession = Depends(get_db), _=Depends(_check_admin)):
    """Full statistics snapshot for the admin dashboard."""
    now   = datetime.datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - datetime.timedelta(days=7)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ── Users ────────────────────────────────────────────────────────
    total_users   = db.query(func.count(User.id)).scalar()
    users_today   = db.query(func.count(User.id)).filter(User.created_at >= today).scalar()
    users_week    = db.query(func.count(User.id)).filter(User.created_at >= week).scalar()
    users_month   = db.query(func.count(User.id)).filter(User.created_at >= month).scalar()
    oauth_users   = db.query(func.count(User.id)).filter(User.google_id != None).scalar()
    pwd_users     = db.query(func.count(User.id)).filter(User.pwd_hash != None, User.pwd_hash != "").scalar()

    # ── Word bank ────────────────────────────────────────────────────
    total_wb      = db.query(func.count(WordBankEntry.id)).scalar()
    wb_today      = db.query(func.count(WordBankEntry.id)).filter(WordBankEntry.saved_at >= today).scalar()

    # ── Searches ─────────────────────────────────────────────────────
    total_searches  = db.query(func.count(SearchLog.id)).scalar()
    searches_today  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= today).scalar()
    searches_week   = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= week).scalar()
    searches_month  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= month).scalar()

    # ── Top words all-time ────────────────────────────────────────────
    top_all = (
        db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc())
        .limit(10)
        .all()
    )

    # ── Top words this month ──────────────────────────────────────────
    top_month = (
        db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= month)
        .group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc())
        .limit(10)
        .all()
    )

    # ── Searches per day (last 30 days) ───────────────────────────────
    thirty_ago = today - datetime.timedelta(days=29)
    daily_rows = (
        db.query(
            func.date(SearchLog.searched_at).label("day"),
            func.count(SearchLog.id).label("n"),
        )
        .filter(SearchLog.searched_at >= thirty_ago)
        .group_by(func.date(SearchLog.searched_at))
        .order_by(func.date(SearchLog.searched_at))
        .all()
    )
    # Fill in missing days with 0
    daily_map = {r.day: r.n for r in daily_rows}
    daily_searches = []
    for i in range(30):
        d = (thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        daily_searches.append({"date": d, "count": daily_map.get(d, 0)})

    # ── New users per day (last 30 days) ──────────────────────────────
    user_rows = (
        db.query(
            func.date(User.created_at).label("day"),
            func.count(User.id).label("n"),
        )
        .filter(User.created_at >= thirty_ago)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )
    user_map = {r.day: r.n for r in user_rows}
    daily_users = []
    for i in range(30):
        d = (thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        daily_users.append({"date": d, "count": user_map.get(d, 0)})

    # ── Recent sign-ups ───────────────────────────────────────────────
    recent_users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "users": {
            "total":  total_users,
            "today":  users_today,
            "week":   users_week,
            "month":  users_month,
            "oauth":  oauth_users,
            "password": pwd_users,
        },
        "wordbank": {
            "total": total_wb,
            "today": wb_today,
        },
        "searches": {
            "total": total_searches,
            "today": searches_today,
            "week":  searches_week,
            "month": searches_month,
        },
        "top_words_alltime": [{"word": r.word, "count": r.n} for r in top_all],
        "top_words_month":   [{"word": r.word, "count": r.n} for r in top_month],
        "daily_searches":    daily_searches,
        "daily_users":       daily_users,
        "recent_users": [
            {
                "id":         u.id,
                "email":      u.email,
                "name":       u.name,
                "auth":       "oauth" if u.google_id else "password",
                "created_at": u.created_at.isoformat() + "Z" if u.created_at else None,
            }
            for u in recent_users
        ],
        "generated_at": now.isoformat() + "Z",
    }


def _make_admin_cookie() -> str:
    payload = {
        "admin": True,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=8),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def _verify_admin_cookie(request: Request) -> bool:
    token = request.cookies.get("admin_sess", "")
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return data.get("admin") is True
    except Exception:
        return False


# ── /admin  (server-side rendered, no JS required) ───────────────────────────

_LOGIN_FORM_TMPL = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lexio Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#f5f4f0;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border:1px solid #ddd;border-radius:12px;padding:36px;width:340px;box-shadow:0 4px 20px rgba(0,0,0,.08)}
h1{font-size:1.2rem;margin-bottom:6px}p{font-size:.82rem;color:#777;margin-bottom:18px}
input{width:100%;padding:9px 12px;border:1px solid #ddd;border-radius:8px;font-size:.9rem;margin-bottom:10px}
button{width:100%;padding:10px;background:#c47028;color:#fff;border:none;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer}
.err{color:#c00;font-size:.8rem;margin-top:8px}
</style></head><body>
<div class="box">
  <h1>Lexio Admin</h1><p>Enter your admin key to view the dashboard.</p>
  <form method="post" action="/admin">
    <input name="key" type="password" placeholder="Admin key" autofocus>
    <button type="submit">Access dashboard</button>
  </form>
  {error}
</div></body></html>"""

@router.post("/admin", response_class=HTMLResponse)
@router.post("/admin/", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def admin_login(request: Request, key: str = Form(...)):
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or not hmac.compare_digest(key, admin_key):
        error_html = _LOGIN_FORM_TMPL.replace("{error}", '<p class="err">Wrong key.</p>')
        return HTMLResponse(error_html, status_code=401)
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie("admin_sess", _make_admin_cookie(),
                    httponly=True, secure=True, samesite="strict", max_age=28800)
    return resp


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/", response_class=HTMLResponse)
async def admin_page(request: Request, db: DBSession = Depends(get_db)):
    if not _verify_admin_cookie(request):
        return HTMLResponse(_LOGIN_FORM_TMPL.replace("{error}", ""))

    # ── Gather all stats ──────────────────────────────────────────────────────
    now   = datetime.datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - datetime.timedelta(days=7)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users  = db.query(func.count(User.id)).scalar() or 0
    users_today  = db.query(func.count(User.id)).filter(User.created_at >= today).scalar() or 0
    users_week   = db.query(func.count(User.id)).filter(User.created_at >= week).scalar() or 0
    users_month  = db.query(func.count(User.id)).filter(User.created_at >= month).scalar() or 0
    oauth_users  = db.query(func.count(User.id)).filter(User.google_id != None).scalar() or 0
    pwd_users    = db.query(func.count(User.id)).filter(User.pwd_hash != None, User.pwd_hash != "").scalar() or 0

    total_wb     = db.query(func.count(WordBankEntry.id)).scalar() or 0
    wb_today     = db.query(func.count(WordBankEntry.id)).filter(WordBankEntry.saved_at >= today).scalar() or 0

    total_searches  = db.query(func.count(SearchLog.id)).scalar() or 0
    searches_today  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= today).scalar() or 0
    searches_week   = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= week).scalar() or 0
    searches_month  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= month).scalar() or 0

    top_month_rows = (db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= month).group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc()).limit(10).all())
    top_all_rows = (db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .group_by(SearchLog.word).order_by(func.count(SearchLog.id).desc()).limit(10).all())

    thirty_ago = today - datetime.timedelta(days=29)
    daily_search_rows = (db.query(func.date(SearchLog.searched_at).label("day"), func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= thirty_ago).group_by(func.date(SearchLog.searched_at)).all())
    daily_user_rows = (db.query(func.date(User.created_at).label("day"), func.count(User.id).label("n"))
        .filter(User.created_at >= thirty_ago).group_by(func.date(User.created_at)).all())

    search_map = {r.day: r.n for r in daily_search_rows}
    user_map   = {r.day: r.n for r in daily_user_rows}

    def sparkline(data_map, color):
        days  = [(thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
        vals  = [data_map.get(d, 0) for d in days]
        maxv  = max(vals) if vals else 1
        maxv  = maxv or 1
        W, H, pl, pr, pt, pb = 500, 100, 8, 8, 6, 18
        cW, cH = W - pl - pr, H - pt - pb
        def px(i): return pl + (i / (len(vals) - 1)) * cW if len(vals) > 1 else pl
        def py(v): return pt + cH - (v / maxv) * cH
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
        area = f"M{px(0):.1f},{py(vals[0]):.1f} " + " ".join(f"L{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
        area += f" L{px(len(vals)-1):.1f},{pt+cH} L{px(0):.1f},{pt+cH} Z"
        # x-axis tick labels every 10 days
        ticks = ""
        for i in [0, 9, 19, 29]:
            if i < len(days):
                import calendar
                d = datetime.datetime.strptime(days[i], "%Y-%m-%d")
                lbl = d.strftime("%b %-d")
                ticks += f'<text x="{px(i):.1f}" y="{H-2}" fill="#bbb" font-size="9" text-anchor="middle" font-family="system-ui">{lbl}</text>'
        return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:80px;display:block;overflow:visible">'
                f'<path d="{area}" fill="{color}" fill-opacity=".15"/>'
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
                f'{ticks}</svg>')

    def word_bars(rows):
        if not rows: return '<span style="color:#aaa;font-size:.8rem">No data yet.</span>'
        maxn = rows[0].n or 1
        out = []
        for i, r in enumerate(rows):
            pct = round(r.n / maxn * 100)
            out.append(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:7px">'
                f'<span style="color:#bbb;font-size:.65rem;width:14px;text-align:right">{i+1}</span>'
                f'<span style="flex:1;font-family:Georgia,serif;font-size:.84rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_h(r.word)}</span>'
                f'<div style="width:52px;height:4px;background:#eee;border-radius:2px"><div style="width:{pct}%;height:4px;background:#c47028;border-radius:2px"></div></div>'
                f'<span style="color:#aaa;font-size:.7rem;min-width:18px;text-align:right">{r.n}</span>'
                f'</div>'
            )
        return "".join(out)

    recent = (db.query(User).order_by(User.created_at.desc()).limit(20).all())

    def fmt_date(dt):
        if not dt: return "—"
        return dt.strftime("%b %-d, %Y %H:%M")

    def auth_bar(label, val, total, color):
        pct = round(val / total * 100) if total else 0
        return (f'<div style="margin-bottom:12px">'
                f'<div style="display:flex;justify-content:space-between;font-size:.78rem;color:#555;margin-bottom:4px">'
                f'<span>{label}</span><strong>{val}</strong></div>'
                f'<div style="height:7px;background:#eee;border-radius:4px">'
                f'<div style="width:{pct}%;height:7px;background:{color};border-radius:4px"></div></div></div>')

    # ── Build HTML ────────────────────────────────────────────────────────────
    def card(label, val, sub=""):
        return (f'<div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">'
                f'<div style="font-size:.68rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">{label}</div>'
                f'<div style="font-size:1.8rem;font-weight:700;color:#111;line-height:1">{val:,}</div>'
                f'{"<div style=font-size:.72rem;color:#999;margin-top:5px>" + sub + "</div>" if sub else ""}'
                f'</div>')

    def sec(title):
        return f'<div style="font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#999;margin:28px 0 12px">{title}</div>'

    health_chips = [
        ("API", True, False),
        ("Database", True, False),
        ("Anthropic key", bool(os.getenv("ANTHROPIC_API_KEY")), False),
        ("Google OAuth", bool(os.getenv("GOOGLE_CLIENT_ID")), not bool(os.getenv("GOOGLE_CLIENT_ID"))),
    ]

    # Disk
    stat = os.statvfs("/")
    disk_used_gb = round((stat.f_blocks - stat.f_bfree) * stat.f_frsize / 1e9, 1)
    disk_total_gb = round(stat.f_blocks * stat.f_frsize / 1e9, 1)
    disk_pct = round((stat.f_blocks - stat.f_bfree) / stat.f_blocks * 100, 1) if stat.f_blocks else 0
    health_chips.append((f"Disk {disk_used_gb}/{disk_total_gb} GB ({disk_pct}%)", disk_pct < 85, disk_pct > 70))

    uptime_s = int((now - _START_TIME).total_seconds())
    d, rem = divmod(uptime_s, 86400); h, rem = divmod(rem, 3600); m = rem // 60
    uptime_str = (f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m")
    health_chips.append((f"Uptime {uptime_str}", True, False))

    def chip(label, ok, warn=False):
        dot = "#f59e0b" if warn else ("#22c55e" if ok else "#ef4444")
        return (f'<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;'
                f'background:#fff;border:1px solid #e5e5e5;border-radius:20px;font-size:.78rem;font-weight:500;margin:4px">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{dot};flex-shrink:0;display:inline-block"></span>'
                f'{label}</span>')

    def _h(s): return _html.escape(str(s or "—"))

    tr_rows = "".join(
        f'<tr style="border-bottom:1px solid #f0f0f0;cursor:pointer" onclick="location.href=\'/admin/user/{u.id}\'">'
        f'<td style="padding:9px 14px;color:#aaa">{u.id}</td>'
        f'<td style="padding:9px 14px"><a href="/admin/user/{u.id}" style="color:#c47028;font-weight:500;text-decoration:none">{_h(u.name or "—")}</a></td>'
        f'<td style="padding:9px 14px">{_h(u.email)}</td>'
        f'<td style="padding:9px 14px"><span style="padding:2px 8px;border-radius:20px;font-size:.65rem;font-weight:700;text-transform:uppercase;'
        f'background:{"#dbeafe;color:#1d4ed8" if u.google_id else "#dcfce7;color:#15803d"}">'
        f'{"oauth" if u.google_id else "password"}</span></td>'
        f'<td style="padding:9px 14px;color:#aaa">{fmt_date(u.created_at)}</td>'
        f'</tr>'
        for u in recent
    )

    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lexio Admin</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f5f4f0;color:#1a1a1a;font-size:14px}}
a{{color:#c47028;text-decoration:none}}
</style>
</head><body>

<div style="display:flex;align-items:center;gap:10px;padding:14px 24px;background:#fff;border-bottom:1px solid #e5e5e5;position:sticky;top:0;z-index:10">
  <svg width="22" height="22" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="9" fill="#c47028"/><text x="18" y="25" font-family="Georgia,serif" font-size="20" font-weight="700" fill="white" text-anchor="middle">w</text></svg>
  <strong>Lexio</strong>
  <span style="font-size:.65rem;font-weight:700;padding:2px 7px;background:#fef3e2;color:#c47028;border-radius:20px;text-transform:uppercase;letter-spacing:.04em">Admin</span>
  <span style="margin-left:auto;font-size:.75rem;color:#aaa">Generated {now.strftime("%b %-d, %Y %H:%M")} UTC</span>
  <a href="/admin" style="margin-left:12px;padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555">↻ Refresh</a>
  <a href="/admin" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555">Sign out</a>
</div>

<div style="padding:24px;max-width:1280px;margin:0 auto">

  {sec("System health")}
  <div>{"".join(chip(label, ok, warn) for label, ok, warn in health_chips)}</div>

  {sec("Overview")}
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px">
    {card("Total users", total_users, f"+{users_week} this week · +{users_month} this month")}
    {card("Total searches", total_searches, f"+{searches_week} this week · +{searches_month} this month")}
    {card("Word bank entries", total_wb, f"+{wb_today} today")}
    {card("New users today", users_today, f"{users_week} this week")}
    {card("Searches today", searches_today, f"{searches_week} this week")}
    {card("WB entries today", wb_today, "")}
  </div>

  {sec("Trends — last 30 days")}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Searches per day</div>
      {sparkline(search_map, "#c47028")}
    </div>
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">New users per day</div>
      {sparkline(user_map, "#3b82f6")}
    </div>
  </div>

  {sec("Top words &amp; auth")}
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px">
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Top words — this month</div>
      {word_bars(top_month_rows)}
    </div>
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Top words — all time</div>
      {word_bars(top_all_rows)}
    </div>
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Auth breakdown</div>
      {auth_bar("Google / Apple", oauth_users, total_users, "#3b82f6")}
      {auth_bar("Email / password", pwd_users, total_users, "#22c55e")}
    </div>
  </div>

  {sec("Recent sign-ups")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden;overflow-x:auto">
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid #eee">
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">#</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Name</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Email</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Auth</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Joined</th>
      </tr></thead>
      <tbody>{tr_rows}</tbody>
    </table>
  </div>

</div>
</body></html>"""

    return HTMLResponse(html)


# ── /admin/user/{user_id} ────────────────────────────────────────────────────
@router.get("/admin/user/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(user_id: int, request: Request, db: DBSession = Depends(get_db)):
    if not _verify_admin_cookie(request):
        return HTMLResponse('<meta http-equiv="refresh" content="0;url=/admin">', status_code=302)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    now        = datetime.datetime.utcnow()
    thirty_ago = (now - datetime.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Per-user search stats ──────────────────────────────────────────────────
    total_searches = db.query(func.count(UserSearchLog.id)).filter(UserSearchLog.user_id == user_id).scalar() or 0

    daily_rows = (
        db.query(func.date(UserSearchLog.searched_at).label("day"), func.count(UserSearchLog.id).label("n"))
        .filter(UserSearchLog.user_id == user_id, UserSearchLog.searched_at >= thirty_ago)
        .group_by(func.date(UserSearchLog.searched_at))
        .all()
    )
    daily_map = {r.day: r.n for r in daily_rows}
    days = [(thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    daily_counts = [daily_map.get(d, 0) for d in days]

    top_words = (
        db.query(UserSearchLog.word, func.count(UserSearchLog.id).label("n"))
        .filter(UserSearchLog.user_id == user_id)
        .group_by(UserSearchLog.word)
        .order_by(func.count(UserSearchLog.id).desc())
        .limit(15)
        .all()
    )

    wb_entries = (
        db.query(WordBankEntry)
        .filter(WordBankEntry.user_id == user_id)
        .order_by(WordBankEntry.saved_at.desc())
        .all()
    )

    def _h(s): return _html.escape(str(s or "—"))

    # ── Sparkline ─────────────────────────────────────────────────────────────
    maxv = max(daily_counts) if daily_counts else 1
    maxv = maxv or 1
    W, H, pl, pr, pt, pb = 800, 120, 40, 12, 8, 24
    cW, cH = W - pl - pr, H - pt - pb
    n = len(daily_counts)
    def px(i): return pl + (i / (n - 1)) * cW if n > 1 else pl
    def py(v): return pt + cH - (v / maxv) * cH
    pts  = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(daily_counts))
    area = f"M{px(0):.1f},{py(daily_counts[0]):.1f} " + " ".join(f"L{px(i):.1f},{py(v):.1f}" for i, v in enumerate(daily_counts))
    area += f" L{px(n-1):.1f},{pt+cH} L{px(0):.1f},{pt+cH} Z"
    tick_html = ""
    for i in [0, 9, 19, 29]:
        if i < len(days):
            d = datetime.datetime.strptime(days[i], "%Y-%m-%d")
            lbl = d.strftime("%b %-d")
            tick_html += f'<text x="{px(i):.1f}" y="{H-2}" fill="#bbb" font-size="10" text-anchor="middle" font-family="system-ui">{lbl}</text>'
    # Y-axis
    for f in [0.5, 1.0]:
        y = py(maxv * f)
        tick_html += f'<line x1="{pl}" y1="{y:.1f}" x2="{pl+cW}" y2="{y:.1f}" stroke="#eee" stroke-width="1"/>'
        tick_html += f'<text x="{pl-4}" y="{y+4:.1f}" fill="#bbb" font-size="9" text-anchor="end" font-family="system-ui">{round(maxv*f)}</text>'
    sparkline_svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:100px;display:block;overflow:visible">'
                     f'<path d="{area}" fill="#c47028" fill-opacity=".12"/>'
                     f'<polyline points="{pts}" fill="none" stroke="#c47028" stroke-width="2" stroke-linejoin="round"/>'
                     f'{tick_html}</svg>')

    # ── Daily table ────────────────────────────────────────────────────────────
    daily_table_rows = ""
    for i in range(29, -1, -1):
        d   = days[i]
        cnt = daily_counts[i]
        if cnt == 0 and i < 25:
            continue  # skip old zero days to keep table concise
        dt  = datetime.datetime.strptime(d, "%Y-%m-%d")
        lbl = dt.strftime("%b %-d, %Y")
        bar = f'<div style="height:6px;background:#eee;border-radius:3px;width:120px"><div style="width:{round(cnt/maxv*100)}%;height:6px;background:#c47028;border-radius:3px"></div></div>'
        daily_table_rows += (
            f'<tr style="border-bottom:1px solid #f0f0f0">'
            f'<td style="padding:8px 14px;color:#555">{lbl}</td>'
            f'<td style="padding:8px 14px;font-weight:600">{cnt}</td>'
            f'<td style="padding:8px 14px">{bar}</td>'
            f'</tr>'
        )

    # ── Top words ──────────────────────────────────────────────────────────────
    top_words_html = ""
    if top_words:
        mx = top_words[0].n or 1
        for i, r in enumerate(top_words):
            pct = round(r.n / mx * 100)
            top_words_html += (
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                f'<span style="color:#bbb;font-size:.65rem;width:14px;text-align:right">{i+1}</span>'
                f'<span style="flex:1;font-family:Georgia,serif;font-size:.85rem">{_h(r.word)}</span>'
                f'<div style="width:60px;height:4px;background:#eee;border-radius:2px"><div style="width:{pct}%;height:4px;background:#c47028;border-radius:2px"></div></div>'
                f'<span style="color:#aaa;font-size:.7rem;min-width:18px;text-align:right">{r.n}</span>'
                f'</div>'
            )
    else:
        top_words_html = '<span style="color:#aaa;font-size:.82rem">No searches recorded yet.</span>'

    # ── Word bank ──────────────────────────────────────────────────────────────
    wb_html = ""
    if wb_entries:
        for e in wb_entries:
            d = json.loads(e.data)
            saved = e.saved_at.strftime("%b %-d, %Y") if e.saved_at else "—"
            wb_html += (
                f'<tr style="border-bottom:1px solid #f0f0f0">'
                f'<td style="padding:8px 14px;font-family:Georgia,serif;font-weight:500">{_h(e.word)}</td>'
                f'<td style="padding:8px 14px;color:#555;font-size:.8rem">{_h(d.get("pos","—"))}</td>'
                f'<td style="padding:8px 14px;color:#555;font-size:.8rem;max-width:340px">{_h(d.get("definition","—"))}</td>'
                f'<td style="padding:8px 14px;color:#aaa;font-size:.78rem">{saved}</td>'
                f'</tr>'
            )
    else:
        wb_html = '<tr><td colspan="4" style="padding:12px 14px;color:#aaa">No words collected yet.</td></tr>'

    auth_label = "Google / Apple OAuth" if user.google_id else "Email / password"
    joined = user.created_at.strftime("%b %-d, %Y at %H:%M UTC") if user.created_at else "—"
    pro_label = "⭐ Pro" if user.is_pro else "Free tier"
    pro_val   = 1 if user.is_pro else 0
    pro_badge_style = "background:#fef3e2;color:#c47028;border-color:#f5c87a" if user.is_pro else "background:#f5f5f5;color:#666;border-color:#ddd"

    def sec(title):
        return f'<div style="font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#999;margin:28px 0 12px">{title}</div>'

    def card(label, val, sub=""):
        return (f'<div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">'
                f'<div style="font-size:.68rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">{label}</div>'
                f'<div style="font-size:1.8rem;font-weight:700;color:#111;line-height:1">{val}</div>'
                f'{"<div style=font-size:.72rem;color:#999;margin-top:5px>" + sub + "</div>" if sub else ""}'
                f'</div>')

    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h(user.name or user.email)} — Lexio Admin</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:system-ui,sans-serif;background:#f5f4f0;color:#1a1a1a;font-size:14px}}</style>
</head><body>

<div style="display:flex;align-items:center;gap:10px;padding:14px 24px;background:#fff;border-bottom:1px solid #e5e5e5;position:sticky;top:0;z-index:10">
  <svg width="22" height="22" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="9" fill="#c47028"/><text x="18" y="25" font-family="Georgia,serif" font-size="20" font-weight="700" fill="white" text-anchor="middle">w</text></svg>
  <strong>Lexio</strong>
  <span style="font-size:.65rem;font-weight:700;padding:2px 7px;background:#fef3e2;color:#c47028;border-radius:20px;text-transform:uppercase;letter-spacing:.04em">Admin</span>
  <span style="color:#ddd;margin:0 4px">/</span>
  <span style="font-size:.9rem;color:#555">User #{user.id}</span>
  <div style="margin-left:auto;display:flex;gap:10px">
    <a href="/admin" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555;text-decoration:none">← Dashboard</a>
    <a href="/admin/user/{user_id}" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555;text-decoration:none">↻ Refresh</a>
  </div>
</div>

<div style="padding:24px;max-width:1100px;margin:0 auto">

  <!-- User info -->
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:20px;display:flex;align-items:center;gap:18px;margin-bottom:4px">
    <div style="width:52px;height:52px;border-radius:50%;background:#c47028;color:#fff;font-size:1.3rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0">
      {_h((user.name or user.email)[0].upper())}
    </div>
    <div>
      <div style="font-size:1.05rem;font-weight:700">{_h(user.name or "—")}</div>
      <div style="color:#777;font-size:.85rem;margin-top:2px">{_h(user.email)}</div>
      <div style="color:#aaa;font-size:.75rem;margin-top:4px">{auth_label} · Joined {joined}</div>
      <div style="margin-top:8px">
        <button onclick="togglePro()" id="pro-btn" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;cursor:pointer;{pro_badge_style}">{pro_label}</button>
      </div>
    </div>
  </div>
  <script>
  async function togglePro() {{
    const newVal = {pro_val} ? 0 : 1;
    await fetch('/admin/user/{user_id}/set-pro', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{is_pro: newVal}})
    }});
    location.reload();
  }}
  </script>

  {sec("Usage overview")}
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px">
    {card("Total lookups", f"{total_searches:,}")}
    {card("Words collected", f"{len(wb_entries):,}")}
    {card("Auth method", "OAuth" if user.google_id else "Password")}
  </div>

  {sec("Lookups per day — last 30 days")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:20px">
    {sparkline_svg}
  </div>

  {sec("Day-by-day breakdown")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden">
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid #eee">
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Date</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Lookups</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa"></th>
      </tr></thead>
      <tbody>{daily_table_rows or '<tr><td colspan="3" style="padding:12px 14px;color:#aaa">No activity yet.</td></tr>'}</tbody>
    </table>
  </div>

  {sec("Most looked-up words")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:20px">
    {top_words_html}
  </div>

  {sec(f"Word bank ({len(wb_entries)} words)")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden">
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid #eee">
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Word</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">POS</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Definition</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Saved</th>
      </tr></thead>
      <tbody>{wb_html}</tbody>
    </table>
  </div>

</div>
</body></html>"""

    return HTMLResponse(html)


# ── /api/admin/user/{user_id}/set-pro (API key auth) ─────────────────────────

@router.post("/api/admin/user/{user_id}/set-pro")
async def admin_set_pro(
    user_id: int,
    body: dict,
    db: DBSession = Depends(get_db),
    _: None = Depends(_check_admin),
):
    """Toggle is_pro for a user. Body: {"is_pro": 0|1}"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_pro = int(bool(body.get("is_pro", 0)))
    user.is_pro = is_pro
    db.commit()
    return {"user_id": user_id, "is_pro": is_pro}


@router.post("/admin/user/{user_id}/set-pro", response_class=JSONResponse)
async def admin_set_pro_ui(
    user_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
):
    if not _verify_admin_cookie(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_pro = int(bool(body.get("is_pro", 0)))
    user.is_pro = is_pro
    db.commit()
    return {"user_id": user_id, "is_pro": is_pro}
