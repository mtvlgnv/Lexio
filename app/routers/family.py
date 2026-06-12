"""Family-plan invitation routes (Phase 2 extract)."""
import datetime
import secrets

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session as DBSession

from app.db import get_db
from app.models import User, FamilyInvitation
from app.security import current_user
from app.email import _send_email
from app.ratelimit import limiter
from app.config import FAMILY_PLAN_SEATS

router = APIRouter()


# ── /family/* — Family plan invitations ───────────────────────────────────────
# Minimal MVP: an owner can invite up to FAMILY_PLAN_SEATS - 1 members by
# email, generating one-time tokens. Invitees follow the link, sign in (or
# sign up), and become Pro by inheritance via family_owner_id.

FAMILY_INVITE_TTL_DAYS = 14

class FamilyInviteRequest(BaseModel):
    email: EmailStr

@router.get("/family/info")
async def family_info(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    """Return the family-plan state for the current user — useful for both the
    owner (to see who's on their plan) and members (to see who they're under)."""
    if user.family_owner_id:
        owner = db.query(User).get(user.family_owner_id)
        return {
            "role":       "member",
            "owner_email": owner.email if owner else None,
            "owner_name":  (owner.name if owner else None),
        }
    # Otherwise the user is potentially the owner. Only show seats if they're
    # actually paying for a family-tier plan.
    is_family_owner = (user.subscription_interval == "family")
    members = db.query(User).filter(User.family_owner_id == user.id).all() if is_family_owner else []
    pending = []
    if is_family_owner:
        invites = (
            db.query(FamilyInvitation)
            .filter(
                FamilyInvitation.owner_id == user.id,
                FamilyInvitation.accepted_at.is_(None),
                FamilyInvitation.expires_at > datetime.datetime.utcnow(),
            )
            .all()
        )
        pending = [{"email": i.email, "invited_at": i.created_at.isoformat()} for i in invites]
    return {
        "role":     "owner" if is_family_owner else "solo",
        "seats":    FAMILY_PLAN_SEATS,
        "used":     1 + len(members),   # owner counts
        "members":  [{"id": m.id, "email": m.email, "name": m.name} for m in members],
        "pending":  pending,
    }

@router.post("/family/invite")
async def family_invite(
    body: FamilyInviteRequest,
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    """Create a family-plan invitation. Only owners on the family tier can invite."""
    if user.subscription_interval != "family":
        raise HTTPException(
            status_code=402,
            detail={"code": "family_plan_required", "message": "Upgrade to the Lexio Family plan to invite members."},
        )
    member_count = db.query(User).filter(User.family_owner_id == user.id).count()
    pending_count = db.query(FamilyInvitation).filter(
        FamilyInvitation.owner_id == user.id,
        FamilyInvitation.accepted_at.is_(None),
        FamilyInvitation.expires_at > datetime.datetime.utcnow(),
    ).count()
    # +1 for the owner themselves
    if 1 + member_count + pending_count >= FAMILY_PLAN_SEATS:
        raise HTTPException(
            status_code=400,
            detail={"code": "family_full", "message": f"All {FAMILY_PLAN_SEATS} seats are used or invited."},
        )
    invite_email = body.email.strip().lower()
    if invite_email == user.email.lower():
        raise HTTPException(status_code=400, detail={"code": "self_invite", "message": "You're already on the plan."})

    token = secrets.token_urlsafe(24)
    invite = FamilyInvitation(
        owner_id   = user.id,
        email      = invite_email,
        token      = token,
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=FAMILY_INVITE_TTL_DAYS),
    )
    db.add(invite)
    db.commit()
    accept_url = f"https://lexio.site/family/accept?token={token}"
    # Best-effort email — non-fatal if SMTP not configured.
    try:
        _send_email(
            invite_email,
            f"{user.name or user.email} invited you to Lexio Pro (Family plan)",
            f"You've been invited to join {user.name or user.email}'s Lexio Family plan.\n\n"
            f"Click here to accept and unlock Lexio Pro:\n{accept_url}\n\n"
            f"This invitation expires in {FAMILY_INVITE_TTL_DAYS} days.\n"
            f"If you don't have a Lexio account yet, you'll be prompted to create one.",
        )
    except Exception:
        pass
    return {"ok": True, "invite_url": accept_url}

@router.get("/family/accept", response_class=HTMLResponse, include_in_schema=False)
async def family_accept_page(token: str = ""):
    """Landing page for email-invite links. Pure client-side: shows the
    invitation, prompts sign-in if needed, then calls POST /family/accept."""
    safe_token = (token or "").replace('"', '').replace("'", "")[:200]
    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Accept Lexio Family invite</title>
<style>
  body {{ font-family: 'DM Sans', system-ui, sans-serif; background: oklch(96.5% 0.012 75);
          color: oklch(18% 0.015 65); min-height: 100vh;
          display: flex; align-items: center; justify-content: center; padding: 32px; }}
  .card {{ background: white; border-radius: 14px; padding: 40px 32px;
           max-width: 440px; width: 100%; box-shadow: 0 4px 24px rgba(0,0,0,0.06);
           text-align: center; }}
  h1 {{ font-family: 'Lora', serif; font-size: 1.6rem; font-weight: 600; margin-bottom: 10px; }}
  p {{ color: oklch(35% 0.012 65); line-height: 1.65; margin-bottom: 18px; }}
  .btn {{ display: inline-block; padding: 12px 24px; background: oklch(58% 0.17 54);
          color: white; border: none; border-radius: 10px; font-size: 0.95rem;
          font-weight: 600; cursor: pointer; text-decoration: none; margin-top: 8px; }}
  .btn:hover {{ opacity: 0.9; }}
  .ghost {{ display: inline-block; margin-top: 14px; color: oklch(35% 0.012 65);
            font-size: 0.88rem; text-decoration: underline; }}
  #status {{ font-size: 0.88rem; margin-top: 14px; min-height: 22px; }}
  .ok {{ color: oklch(40% 0.18 145); }}
  .err {{ color: oklch(55% 0.2 25); }}
</style></head><body>
<div class="card">
  <h1>Join a Lexio Family plan</h1>
  <p>You've been invited to join a Lexio Family plan. Accepting unlocks Lexio Pro on your account.</p>
  <button class="btn" id="accept-btn" type="button">Accept invitation</button>
  <a class="ghost" href="/">Cancel</a>
  <div id="status"></div>
</div>
<script>
const TOKEN = "{safe_token}";
const btn = document.getElementById('accept-btn');
const status = document.getElementById('status');
async function tryAccept() {{
  const authToken = localStorage.getItem('lexio_token');
  if (!authToken) {{
    status.className = 'err';
    status.textContent = 'Please sign in first, then click Accept again.';
    sessionStorage.setItem('lexio_pending_family_invite', TOKEN);
    window.location.href = '/?signin=1';
    return;
  }}
  btn.disabled = true;
  btn.textContent = 'Accepting…';
  try {{
    const r = await fetch('/family/accept?token=' + encodeURIComponent(TOKEN), {{
      method: 'POST',
      headers: {{ 'Authorization': 'Bearer ' + authToken }},
    }});
    if (r.ok) {{
      status.className = 'ok';
      status.textContent = 'Done! You\\'re now on the Family plan. Redirecting…';
      setTimeout(() => window.location.href = '/?family=ok', 1200);
    }} else {{
      const j = await r.json().catch(() => ({{}}));
      const msg = (j.detail && j.detail.message) || (j.detail && j.detail.code) || 'Could not accept the invitation.';
      status.className = 'err';
      status.textContent = msg;
      btn.disabled = false;
      btn.textContent = 'Try again';
    }}
  }} catch {{
    status.className = 'err';
    status.textContent = 'Network error. Try again.';
    btn.disabled = false;
    btn.textContent = 'Accept invitation';
  }}
}}
btn.addEventListener('click', tryAccept);
</script></body></html>"""
    return HTMLResponse(content=html)


@router.post("/family/accept")
async def family_accept(
    token: str,
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    """Accept a family-plan invitation. Requires the invitee to already be
    signed in (or signed up) so we can attach them to the owner."""
    invite = db.query(FamilyInvitation).filter(FamilyInvitation.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail={"code": "invite_not_found"})
    if invite.accepted_at:
        raise HTTPException(status_code=400, detail={"code": "invite_already_used"})
    if invite.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail={"code": "invite_expired"})

    if user.family_owner_id and user.family_owner_id != invite.owner_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "already_in_family", "message": "You're already on another family plan."},
        )
    if user.id == invite.owner_id:
        raise HTTPException(status_code=400, detail={"code": "self_accept"})

    user.family_owner_id = invite.owner_id
    invite.accepted_at   = datetime.datetime.utcnow()
    invite.accepted_by   = user.id
    db.commit()
    return {"ok": True}

@router.delete("/family/member/{member_id}")
async def family_remove_member(
    member_id: int,
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    """Owner removes a member from their family plan."""
    if user.subscription_interval != "family":
        raise HTTPException(status_code=403, detail={"code": "not_owner"})
    member = db.query(User).get(member_id)
    if not member or member.family_owner_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "member_not_found"})
    member.family_owner_id = None
    db.commit()
    return {"ok": True}
