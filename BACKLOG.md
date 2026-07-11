# Lexio — Agent Backlog

Self-contained task specs sized for a single agent session. Each spec makes
the product decisions upfront so a smaller agent doesn't have to; if a spec
turns out to be ambiguous anyway, interview the founder (he likes it) rather
than guessing. Read `CLAUDE.md` first; check `ROADMAP.md` for strategy
context. When you finish a task: run its **Verify** section for real, mark
it ✅ here with the date, and note anything the next agent should know.

Sizes: XS ≤ 30 min · S ≤ 2 h · M ≤ half day · L = full session.

| # | Task | Size | Depends on | Status |
|---|------|------|-----------|--------|
| B1 | Review mode (spaced repetition on Word Bank) | L | — | open |
| B2 | Thinking mode ("Think deeper" button) | M | — | ✅ done 2026-07-11 |
| B3 | Reader profile Phase 1 (explicit) | M | — | open |
| B4 | Profile interview UI (Phase 1.5) | M | B3 | open |
| B5 | Trending-words card on Hub Home | S | — | ✅ done 2026-07-11 |
| B6 | Dark-mode audit + fixes (desktop surfaces) | M | — | ✅ done 2026-07-11 |
| B7 | def-actions overflow redesign | S | — | ✅ done 2026-07-10 |
| B8 | Unify the two loading layouts | S | — | ✅ done 2026-07-10 |
| B9 | Word Bank row hover + delete affordance | XS | — | ✅ done 2026-07-10 |
| B10 | Pill tooltip copy (click vs double-tap) | XS | — | ✅ done 2026-07-10 |
| B11 | Recent tab: store full definitions, add per-row Save | M | — | ✅ done 2026-07-11 |
| B12 | "Say it" button in the panel (pronunciation) | S | — | ✅ done 2026-07-11 |
| B13 | Definition feedback (👍/👎 → server log) | M | — | open |
| B14 | Sentence mode ("explain this whole sentence") | M | — | open |
| B15 | Desktop analytics (privacy-respecting PostHog) | M | — | open |
| B16 | Onboarding permissions step restructure | S | — | open |
| B17 | Weekly recap card + digest email | M | B1 nice-to-have | open |
| B18 | i18n the hero rotator + trust badges | S | — | open |
| B19 | Windows port spike (capture helper PoC) | L | — | open |
| B20 | Release protocol run + auto-update verification | M | human: GH_TOKEN | open |

---

## B1 · Review mode — spaced repetition on the Word Bank (L)
**Goal:** the retention loop every comparable app has (WordUp/Readlang/LingQ).
**Where:** `desktop/home.html` (new "Review" sidebar section + Home card
"N words due"), word bank entries in localStorage `lexio_wbv1`.
**Decisions made:** SM-2-lite, local-first. Extend each wb entry with
`reviewAt` (ISO date, default = savedAt) and `intervalDays` (default 0).
Card = the saved `context` sentence with the word replaced by `____` →
click to reveal word + `contextual` → two buttons: **Again** (intervalDays=0,
reviewAt=now) and **Got it** (intervalDays = max(1, intervalDays*2.5),
reviewAt = now + intervalDays). A word with intervalDays ≥ 5 counts as
**learned** → new Home stat "words learned". Entries without `context`
fall back to showing the definition and asking recall of the word.
**Sync note:** the server's WBEntry schema ignores unknown fields
(`extra: ignore`) — so `reviewAt`/`intervalDays` DON'T survive server sync
round-trips. Either (a) add the two optional fields to `WBEntry` in
`app/schemas.py` + wordbank model/rows (preferred, tiny migration), or
(b) keep review state purely local. Do (a).
**Verify:** save 2 words via the panel → Review shows 2 due → grade one
Again, one Got it → localStorage shows updated fields → server GET
/wordbank returns them after sync → relaunch app, state persists.

## B2 · Thinking mode (M) — full spec in ROADMAP.md P1-4
**Order note:** do B7 first so the button has a home. Backend: make
`_define_from_image` honor `req.model` ("deep" → new
`ai._call_anthropic_vision`, Pro-gated 403 like text mode, weight 3).
Deep prompt adds `nuance` + `examples[2]` keys. Panel: "Think deeper ✦"
button on image-mode results → re-runs retained `lastImage` with
model:'deep' → renders the two extra sections.
**Verify:** live lookup on the founder's Pro account → button → richer
answer lands; free-account (or anon) path shows the upgrade prompt;
`pytest` stays green.

## B3 · Reader profile Phase 1 (M) — full spec in ROADMAP.md P1-5
DB column `User.profile_json`, `GET/PUT /api/profile`, prompt injection in
BOTH /define paths with the over-personalization guard sentence, "About
you" card in Hub Account. **Verify:** set profile "furniture maker" → look
up "stock" in a woodworking sentence → definition acknowledges the domain;
look up "democracy" → NO woodworking flavor.

## B4 · Profile interview UI (M) — spec in ROADMAP.md P1-5 Phase 1.5
Blocked by B3 (needs /api/profile). Hub Home card after 5 saves or 15
lookups + optional onboarding step; 3–4 skippable questions writing
profile_json; `profileInterviewDismissed` flag in `desktop/store.js`.

## B5 · Trending-words card on Hub Home (S)
**Where:** `desktop/home.html` renderHome(). Fetch `GET /stats/top-words`
(the endpoint feeding the homepage's trending section — check its exact
path/shape in `app/routers/` first). Card: "Lexio readers are looking up:"
+ 5 words as chips; click → `window.lexioHub.relookup(word)`.
**Verify:** card renders real words; clicking one opens the panel with
that word defined.

## B6 · Dark-mode audit (M) — DESIGN_ROADMAP #1
Flip macOS appearance (or force `nativeTheme.themeSource = 'dark'`
temporarily in dev), capture every surface with the lexio-ocr binary
(pixels, not DOM — see CLAUDE.md), fix contrast failures in home.html,
compact.html additions (lang-select, capture thumb, save button), and
onboarding. Commit before/after captures paths in the commit message.

## B7 · def-actions overflow redesign (S) — DESIGN_ROADMAP #2
Decision made: two rows. Row 1: Save · Copy · New lookup. Row 2 (right-
aligned, smaller): language select + future "Think deeper ✦". Keep total
height ≤ 64px at 460px panel width. Run sync-compact.sh after.

## B8 · Unify loading layouts (S) — DESIGN_ROADMAP #3
Adopt the image-lookup loading structure (title + optional thumb +
skeleton lines) as THE loading component in compact.html; text lookups
pass no thumb. One function, both callers.

## B9 · Word Bank hover states (XS) — DESIGN_ROADMAP #4
`.wb-entry:hover` background var(--surface); `.wb-del` opacity 0 →
1 on row hover. Also cursor:pointer affordance review.

## B10 · Pill tooltip copy (XS) — DESIGN_ROADMAP #11
`pill.html` title + the dynamic update in the trigger-symbol handler:
"Click: open panel · Double-tap ⌃: define the word at your pointer".

## B11 · Recent with definitions + per-row Save (M)
**Problem:** recentLookups stores only {word, at} — can't save from Recent,
and relookup re-bills a lookup. **Change:** `overlay:report-lookup` (in
compact.html's LEXIO_LOOKUP bridge) also sends the definition payload;
store the last 50 as {word, at, data, context}. Hub Recent rows get a
bookmark button writing the same wb entry shape as the panel's
saveCurrent(). Relookup of a stored entry can render instantly from cache
(word+data) instead of re-billing — show it with a "cached" affordance and
a refresh option.
**Verify:** lookup → Recent row shows Save → saves without a new API call →
appears in Word Bank; store.json contains data payloads (cap size: strip
image thumbnails, keep text fields only).

## B12 · "Say it" — pronunciation in the panel (S)  ← new idea
ESL users need to HEAR the word, not just read IPA (the web app already
has a Say button; the desktop panel doesn't). In compact.html result
head: a small 🔊 button → `speechSynthesis.speak(new SpeechSynthesisUtterance(word))`
with `lang:'en-US'`, rate 0.9. Zero backend. Falls back silently if
speechSynthesis is unavailable in the webview (test this first!).
**Verify:** click → audible speech on a real lookup; no console errors.

## B13 · Definition feedback loop (M)  ← new idea
👍/👎 on each definition → `POST /api/feedback {word, model, verdict,
lang, mode:'image'|'text'}` (new tiny router; store rows w/ timestamp,
no context text for privacy). This is the prompt-quality dataset for
future tuning and the cheapest "was the marker fix worth it" metric.
Rate-limit 60/min/IP. Show a subtle "thanks" state. Hub could later show
"accuracy this month". **Verify:** row lands in the DB; pytest green;
buttons don't shift the def-actions layout (coordinate with B7).

## B14 · Sentence mode (M)  ← new idea
Sometimes the blocker isn't a word, it's the whole sentence (idiomatic,
grammatically knotted). UX: after a lookup, a "What does this sentence
mean?" link under the contextual definition → re-runs the SAME retained
capture with a prompt variant asking for a plain-language explanation +
translation into the user's definition language. Backend: accept
`intent: 'sentence'` on image lookups; same billing weight. No new
capture needed. **Verify:** live: knotted sentence → coherent explanation
in the panel, in the chosen language.

## B15 · Desktop analytics, privacy-respecting (M)  ← new idea
Today there is ZERO visibility into desktop usage (installs, DAU, lookup
outcomes, save rate, upgrade clicks). PostHog EU is already used on the
site. Main process: `posthog-node` capture on app-launch, lookup
(success/error only — never content), save, hub-open, upgrade-click;
anonymous distinct_id = hashed machine ID stored in store.js; a Settings
toggle "Share anonymous usage stats" (default ON, honest label) that
fully disables capture. Update privacy.html accordingly. **Verify:**
events visible in PostHog EU project; toggle stops them.

## B16 · Onboarding permissions restructure (S) — DESIGN_ROADMAP #7
Match Hub Settings' row pattern (label+hint left, status dot + button
right); reveal the stale-TCC hint only after 3 failed polls (logic
already counts polls — reuse `accessPolls`).

## B17 · Weekly recap card + digest email (M)
Home card: this week vs last week (lookups from lookupDays, saves from wb
savedAt timestamps). Server digest: check what exists around
`/email/unsubscribe` (HMAC unsubscribe already built!) — find the sending
job, add-or-fix a weekly summary email using /api/streak + wordbank
counts. Interview the founder on tone/frequency before writing copy.

## B18 · i18n hero rotator + trust badges (S) — DESIGN_ROADMAP #12
`static/index.html`: the "Built for people reading…" rotator items and
the three hero trust badges are hardcoded EN. Add data-i18n keys +
translate in all 11 locales in `static/app.js` (follow the 2026-07-08
localization commit's pattern; bump `app.js?v=` in index.html).

## B19 · Windows port spike (L) — strategy in ROADMAP.md
PoC ONLY: a ~150-line C#/C++/Rust helper (founder hasn't chosen; pick
C++/WinRT `Windows.Graphics.Capture` unless told otherwise) that takes
--x/--y/--rx/--ry/--rw/--rh, captures the region, draws the magenta ring,
prints the same JSON contract as lexio-ocr. Prove it on a Windows VM/
machine + document build steps. Do NOT wire the Electron side yet.

## B20 · Release protocol + auto-update verification (M, needs human)
Requires the founder: GitHub PAT as GH_TOKEN. Then: bump 1.3.0→1.3.1,
`npm run dist -- --publish always`, publish the release, install 1.3.0
build, confirm the in-app update prompt appears and lands on 1.3.1.
Document the whole flow as `desktop/RELEASING.md`. This is the last
manual install any user does — treat it as the release-train dry run.

---

## Idea parking lot (not yet specced — promote when ready)
- Menu-bar micro-review: one due flashcard shown in the tray popover.
- Word Bank collections/tags; classroom shared lists (educator funnel).
- CEFR level estimate evolving from lookup difficulty over time.
- "Copy as Anki card" single-entry export from the panel.
- Referral: give a friend a month of Pro (needs backend codes).
- Offline save queue (saves made offline sync when back online).
- Reading-session recap: N lookups in 10 min → "you met these 7 words".
