# Lexio Refactor Plan — splitting the two monoliths

**Goal:** make `main.py` (4,028 lines) and `static/index.html` (8,305 lines) maintainable
again, folding in the known security/quick-fix items along the way. Behavior must not
change — this is a structural refactor, verified at every step.

**Decisions locked in (2026-06-10):**
- Frontend → **Vite bundler** (true ES modules, minification, hashed assets).
- This pass → write the plan **and** execute Phase 1.
- Security/quick fixes → **folded in**, not deferred.

---

## Guiding principles

1. **Behavior-preserving.** Every phase keeps the public surface identical: same routes,
   same JSON shapes, same rendered HTML/CSS. We prove it, we don't assume it.
2. **One safety net before any big move.** A route-inventory characterization test
   (Phase 1) guards the backend split; a built-output diff guards the frontend split.
3. **Small, reversible commits.** One concern per commit so a regression is a one-line
   `git revert`, not an archaeology dig.
4. **`app:app` stays importable at the same path** so `lexio.service` / uvicorn / nginx
   need no changes until we choose to touch them.

---

## Phase 1 — Foundation & safe quick-wins  *(this pass)*

Low/zero behavioral risk; lays the safety net and clears the small folded-in items.

- [x] **This plan** (`REFACTOR_PLAN.md`).
- [x] **Docs drift:** `CLAUDE.md` said free tier = *100* lookups/mo; code says **20**
      (`FREE_LOOKUP_LIMIT`, main.py:430). Fixed to 20.
- [x] **Admin key timing:** both comparisons (`_check_admin` main.py:2700; `admin_login`
      main.py:2907) used `!=`/`==` on the secret. Switched to `hmac.compare_digest`.
- [x] **Admin login brute-force:** `POST /admin` had no rate limit. Added
      `@limiter.limit("5/minute")`.
- [x] **Backend safety net:** `tests/test_routes_snapshot.py` — a characterization test
      that freezes the full `(methods, path)` route inventory on first run and fails if a
      later refactor adds/removes/renames a route. **Run it once now** to capture the
      baseline before Phase 2.
- [ ] **Pin `requirements.txt`.** The deployed versions live on the prod box (not in this
      repo's `.venv`), so pins must be captured there — the AI SDKs (anthropic, openai,
      google-genai, stripe) ship breaking changes routinely and must be exact. Run on the
      server (or wherever prod deps are installed):
      ```bash
      pip freeze > requirements.lock
      ```
      Then commit `requirements.lock` and have `deploy.sh` install from it. Keep the loose
      list as `requirements.in` for human edits. *(Left as a one-command step because it
      must reflect production, not a guess.)*

**Verify Phase 1:** `pytest tests/test_routes_snapshot.py` passes (writes baseline);
`pytest tests/test_search_log_migration.py` still passes; app boots locally.

---

## ✅ STATUS (updated)

- **Phase 1 — done.** Docs drift, admin `hmac.compare_digest` + login rate limit,
  route-inventory characterization test. (`requirements.txt` pinning still a one-command
  step you run on the prod box — see below.)
- **Phase 2 — DONE.** `main.py` went **4,031 → 89 lines** (a thin assembler). All handlers
  live in `app/` (22 modules): `json_utils, config, ai, db, models, migrations, limits,
  security, ratelimit, schemas, email, oauth` + `routers/{define, tools, auth, wordbank,
  account, family, admin, billing, content}`. Gated at every step by the test suite
  (now 16 tests) + the route snapshot (65 routes, unchanged), plus a smoke test that hits
  one route per router module (no 5xx). Caught & fixed a latent `/stats/top-words`
  `NameError` introduced mid-refactor; added a regression test for it.
- **Phase 4 — partial.** `static/index.html` **8,305 → 1,656 lines**; CSS → `static/app.css`,
  JS → `static/app.js` (parses clean). Vite bundler scaffold NOT yet set up.
- **Phase 5 — partial.** The two confirmed stored-XSS sinks (word-bank list, history chip)
  are fixed via `_escape()`. Full sweep of the remaining ~29 `innerHTML` uses + JS
  modularization still to do.
- **Phase 3 (glossary/works externalization) and Phase 6 (final verification, browser
  smoke of the extracted frontend) — not started.**

Test loop (run from `product/`): `python3 -m pytest tests/ -q` — must stay green with the
route snapshot unchanged. Needs `email-validator` installed alongside `requirements.txt`.

---

## Phase 2 — Split `main.py` into an `app/` package  *(COMPLETE — see status above)*

The file divides along seams it already has (comment banners mark most of them). Target
layout — each module is a few hundred lines, not four thousand:

```
app/
  __init__.py        # create_app() -> FastAPI; wires middleware + includes routers
  config.py          # env reads (SECRET_KEY, API keys, SMTP, limits, SITE_URL …)
  db.py              # engine, SessionLocal, Base, get_db
  models.py          # User, WordBankEntry, SearchLog, UserSearchLog, AnonUsage,
                     #   PasswordResetToken, FamilyInvitation
  migrations.py      # the hand-rolled schema_version migration runner
  security.py        # pwd hashing, JWT encode/decode, optional_user/current_user,
                     #   admin cookie + _check_admin, hmac compare
  limits.py          # slowapi limiter + the weighted hourly/monthly credit logic
  ai.py              # _call_openai/_call_google/_call_anthropic + JSON repair helpers
  routers/
    define.py        # /define, /fetch-text, /ocr, /stats/top-words
    auth.py          # /auth/* (register, login, google, apple, sessions, password, …)
    billing.py       # /stripe/*, /api/pro-status, /api/usage, price-info
    family.py        # /family/*
    admin.py         # /admin*, /api/admin/*  (HTML templates → app/templates/admin/*.html)
    content.py       # /glossary, /works, /this-week, /api/catalog, /recap, /privacy …
    misc.py          # /api/config, /api/models, /api/user-model, /app, /pro, redirects
main.py              # thin shim: `from app import create_app; app = create_app()`
```

**Sequence (each step ends green on the route snapshot):**
1. Create the package; move `config`, `db`, `models`, `migrations` (lowest coupling).
   `main.py` imports from them — no routes move yet.
2. Move `security`, `limits`, `ai` helpers.
3. Move routers one domain at a time, smallest first (misc → family → billing → auth →
   admin → content → define). Convert `@app.x` to `router = APIRouter()` + `@router.x`;
   `create_app()` does `app.include_router(...)`. **Run the snapshot test after each.**
4. Lift inline admin HTML (`_LOGIN_FORM_TMPL` and the dashboard strings) into
   `app/templates/admin/`.
5. Reduce `main.py` to the shim.

**Risks & mitigations:** circular imports (keep `get_db`/`Base` in `db.py`, models import
only `db`); decorator/limiter ordering (limiter must see `request: Request` — preserved);
module-load side effects like `Base.metadata.create_all` + `_run_migrations()` move into
`create_app()` so import is side-effect-free and testable.

**Verify Phase 2:** route snapshot identical; boot app; hit `/api/config`, `/define`
(fast), an auth round-trip, `/glossary/<slug>`, `/admin` login — all unchanged.

---

## Phase 3 — Externalize glossary/works content

`glossary.py` (682KB) and `works.py` (369KB) are generated SEO content shipped as Python
dict literals and imported into **every** worker at boot.

- Convert the `ENTRIES` / `WORKS` data to `content_data/glossary.json` +
  `content_data/works.json` (a one-time dump script).
- `app/routers/content.py` loads + caches them lazily (same pattern `catalog.py` already
  uses for the book manifest).
- Keep the rendered HTML **byte-identical** — snapshot a few pages before/after and diff.

**Why:** smaller import surface, lower per-worker memory, and content edits stop being
code edits.

---

## Phase 4 — Frontend: Vite scaffold + extract CSS/JS

`index.html` today = ~3,230 lines CSS + ~1,200 lines HTML markup + ~3,500 lines JS
(264 functions) in one file. First make it three files; modularize in Phase 5.

```
frontend/
  index.html         # markup only (~1,200 lines) + <script type=module src=/src/main.js>
  src/
    main.js          # entry (imports css + modules)
    styles/app.css   # the extracted <style> blocks
  public/            # static assets copied as-is (favicons, og images, extension zip)
vite.config.js       # build.outDir -> ../static, emptyOutDir false (preserve SEO html,
                     #   sitemaps, robots.txt, the served extension zip), base '/'
package.json
```

- External CDN tags (html2canvas, Google/Apple auth, Plausible) stay as `<script>` in the
  HTML head — they're third-party globals, not modules.
- Preserve the JSON-LD `<script type="application/ld+json">` blocks verbatim (SEO).
- **Deploy:** add `npm ci && npm run build` to `deploy.sh` before the uvicorn restart;
  FastAPI keeps serving `static/` exactly as now. Document the Node version.

**Verify Phase 4:** `npm run build`, serve, and diff the rendered DOM + computed styles
against current production for: landing, app/reader, word bank, sign-in, pricing.

---

## Phase 5 — Frontend: modularize JS + XSS sweep

Split `src/main.js` into ES modules by concern: `api.js`, `auth.js`, `wordbank.js`,
`reader.js`, `definition.js`, `billing.js`, `ui.js`, `escape.js`.

**Folded-in security fix (do it as the code moves):**
- **Stored XSS in the word-bank list** (was `index.html:6221`): `e.word`, `e.pos`, and the
  AI-generated definition are injected into `innerHTML` unescaped. These sync server-side
  across devices and the schema accepts up to 2,000 chars of arbitrary text → persistent
  XSS. Route every model/user-derived field through the existing `_escape()` (or build the
  nodes with `textContent`, as the definition popup already does correctly).
- **Chip tooltip** (was `index.html:5793`): escapes only single quotes inside an inline
  `on*=` attribute — breakable. Replace with a real listener + `textContent`, or full
  HTML-attribute escaping.
- **Sweep all 31 `innerHTML` uses.** Establish the rule: model/user text is *never*
  concatenated into `innerHTML`; it goes through `_escape()` or `textContent`. The family
  panel is the correct reference.

**Verify Phase 5:** save a word-bank entry with payload
`<img src=x onerror=alert(1)>` as the word/definition, sync, reload → renders as inert
text, no script executes. Plus the Phase 4 DOM/style diff still clean.

---

## Phase 6 — Verification & cleanup

- Route-inventory test + a small backend smoke suite (auth, define gating, stripe webhook
  signature path) green.
- Built frontend diffed against baseline; XSS regression payload confirmed inert.
- `deploy.sh` produces a working build end-to-end on a clean checkout.
- Update `CLAUDE.md` "Conventions" (the "single file, no build step" note is now obsolete —
  document the Vite build instead).

---

## Explicitly out of scope (tracked, not done here)

- **Per-worker in-memory state.** slowapi's default storage and the top-words cache are
  per-worker, so limits are ~2× configured and inconsistent. Real fix = shared store
  (Redis) — infra change, separate effort. Noted so it isn't forgotten.
- **SQLite → Postgres / Alembic.** The hand-rolled migration runner is fine at current
  scale; revisit when write concurrency hurts.
- Blocking AI calls in the async `/define` path (wrap in `asyncio.to_thread`) — worth doing
  but independent of the size refactor; can ride along in Phase 2's `define.py` extraction.
