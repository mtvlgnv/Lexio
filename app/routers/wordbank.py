"""Word-bank sync / export routes (Phase 2 extract)."""
import json
import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session as DBSession

from app.db import get_db
from app.models import User, WordBankEntry
from app.security import current_user
from app.limits import _is_effectively_pro
from app.schemas import WBSyncRequest

router = APIRouter()


# ── /wordbank/sync ────────────────────────────────────────────────────────────
# Cross-device word-bank sync — gated to Pro (see #6 in the monetisation
# roadmap). Free users keep their local-only word bank; Pro users get cloud
# sync as the headline qualitative feature differentiating the tiers.

@router.post("/wordbank/sync")
async def sync_wordbank(
    body: WBSyncRequest,
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    if not _is_effectively_pro(user):
        # 402 Payment Required — the client interprets this as "you tried to
        # sync but you're on the free tier" and surfaces the upgrade modal
        # without treating it as a hard error.
        raise HTTPException(
            status_code=402,
            detail={
                "code": "pro_required",
                "feature": "wordbank_sync",
                "message": "Cross-device word-bank sync is a Pro feature. Upgrade to keep your word bank in sync across all your devices.",
            },
        )

    # Index existing server entries by word (case-insensitive)
    existing = {
        e.word.lower(): e
        for e in db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    }

    # Upsert client entries
    for entry in body.entries:
        word = entry.word.strip()
        if not word:
            continue
        key = word.lower()
        entry_dict = entry.model_dump(exclude_none=True)
        # Parse the client's true save time so the DB column reflects when the
        # word was actually saved, not when it first synced (see annual_recap).
        _saved_at = None
        if entry.savedAt:
            try:
                _sa = datetime.datetime.fromisoformat(entry.savedAt.replace("Z", "+00:00"))
                _saved_at = _sa.astimezone(datetime.timezone.utc).replace(tzinfo=None) if _sa.tzinfo else _sa
            except Exception:
                _saved_at = None
        if key in existing:
            existing[key].data = json.dumps(entry_dict)
            if _saved_at:               # backfill stale sync-time columns
                existing[key].saved_at = _saved_at
        else:
            new_entry = WordBankEntry(
                user_id  = user.id,
                word     = word,
                data     = json.dumps(entry_dict),
                saved_at = _saved_at or datetime.datetime.utcnow(),
            )
            db.add(new_entry)
            existing[key] = new_entry

    db.commit()

    # Return the full server word bank to the client
    all_entries = db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    return {"entries": [json.loads(e.data) for e in all_entries]}


# ── /wordbank ─────────────────────────────────────────────────────────────────

@router.get("/wordbank")
async def get_wordbank(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    entries = db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    return {"entries": [json.loads(e.data) for e in entries]}


@router.delete("/wordbank/{word}")
async def delete_word(word: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    entry = db.query(WordBankEntry).filter(
        WordBankEntry.user_id == user.id,
        WordBankEntry.word    == word,
    ).first()
    if entry:
        db.delete(entry)
        db.commit()
    return {"ok": True}


# ── /wordbank/anki ────────────────────────────────────────────────────────────
# Anki-friendly TSV export (front-side word+context, back-side definition+
# why + etymology). Pro users only — part of the "annual bonus" feature set
# but the same export works for any Pro user. Annual subscribers get a
# "Founder" badge on the file header for fun.

@router.get("/wordbank/anki")
async def export_anki(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if not _is_effectively_pro(user):
        raise HTTPException(
            status_code=402,
            detail={"code": "pro_required", "feature": "anki_export"},
        )
    entries = db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    # TSV with two columns ("Front", "Back") — direct import into Anki
    # via File → Import. Multi-line cells use Anki's <br> convention so
    # the cards render with formatting.
    lines = ["Front\tBack"]
    for e in entries:
        try:
            d = json.loads(e.data)
        except (TypeError, ValueError):
            continue
        word        = (d.get("word") or "").replace("\t", " ").strip()
        context     = (d.get("context") or "").replace("\t", " ").strip()
        contextual  = (d.get("contextual") or d.get("definition") or "").replace("\t", " ").strip()
        why         = (d.get("why") or "").replace("\t", " ").strip()
        etym        = (d.get("etymology") or "").replace("\t", " ").strip()
        ipa         = (d.get("ipa") or "").replace("\t", " ").strip()

        front_parts = [f"<b>{word}</b>"]
        if ipa:     front_parts.append(f"<i>/{ipa}/</i>")
        if context: front_parts.append(f"<br><br>{context}")
        front = "<br>".join(front_parts).replace("\n", "<br>")

        back_parts = [contextual]
        if why:  back_parts.append(f"<br><br><i>Why this word:</i> {why}")
        if etym: back_parts.append(f"<br><br><i>Etymology:</i> {etym}")
        back = "".join(back_parts).replace("\n", "<br>")

        if word and back:
            lines.append(f"{front}\t{back}")

    body_str = "\n".join(lines)
    filename = f"lexio-anki-{datetime.datetime.utcnow().strftime('%Y%m%d')}.tsv"
    return Response(
        content=body_str,
        media_type="text/tab-separated-values; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
