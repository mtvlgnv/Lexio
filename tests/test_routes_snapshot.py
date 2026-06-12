"""
Route-inventory characterization test — the safety net for the Phase 2
main.py -> app/ router split (see REFACTOR_PLAN.md).

It freezes the full public route surface (HTTP method + path for every
APIRoute) into tests/routes_snapshot.json on first run, then fails if any
later change adds, removes, or renames a route. During the refactor the
inventory must stay byte-for-byte identical: same routes, just relocated.

Workflow:
  1. Run once on the CURRENT (pre-refactor) code to capture the baseline:
       pytest tests/test_routes_snapshot.py
     -> writes routes_snapshot.json (commit it).
  2. Refactor. Re-run after every extraction. A diff means you changed the
     surface — intended? update the snapshot deliberately:
       UPDATE_ROUTES_SNAPSHOT=1 pytest tests/test_routes_snapshot.py
"""
import json
import os
from pathlib import Path

from starlette.routing import Route as StarletteRoute

from main import app

SNAPSHOT = Path(__file__).resolve().parent / "routes_snapshot.json"


def _current_routes():
    """Sorted, stable list of "METHOD,METHOD path" for every real route.

    Excludes the StaticFiles mount and websocket/mount entries that have no
    `methods`, so the snapshot tracks only the API/page surface.
    """
    rows = []
    for r in app.routes:
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        if not methods or path is None:
            continue
        verbs = ",".join(sorted(m for m in methods if m != "HEAD"))
        rows.append(f"{verbs} {path}")
    return sorted(set(rows))


def test_route_inventory_unchanged():
    current = _current_routes()

    if os.environ.get("UPDATE_ROUTES_SNAPSHOT") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(json.dumps(current, indent=2) + "\n")
        # First-run / explicit-update: capture and pass so the baseline exists.
        return

    expected = json.loads(SNAPSHOT.read_text())

    missing = [r for r in expected if r not in current]
    added = [r for r in current if r not in expected]

    assert not missing and not added, (
        "Route surface changed vs tests/routes_snapshot.json.\n"
        f"  REMOVED/renamed ({len(missing)}): {missing}\n"
        f"  ADDED ({len(added)}): {added}\n"
        "If this is intentional, re-run with UPDATE_ROUTES_SNAPSHOT=1."
    )
