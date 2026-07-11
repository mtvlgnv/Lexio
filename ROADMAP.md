# Lexio Glance — Priority Roadmap (written 2026-07-08)

For any agent (or human) picking up this codebase: this is the prioritized,
implementation-ready backlog as of the v1.3.0 vision-first rebuild. Read
"Architecture now" first — several older docs/comments describe pipelines
that no longer exist.

## Architecture now (post-rebuild)

Every desktop lookup is: double-tap trigger (uiohook-napi, `main-overlay.js`)
→ native helper `desktop/bin/lexio-ocr` (Swift, ScreenCaptureKit) captures
~800×500 JPEG around the cursor with a **magenta ring drawn at the exact
cursor point** and the overlay window excluded by CGWindowID → base64 JPEG
→ `POST /define` with `image_base64` + `image_mime` + `lang` →
`_define_from_image()` in `app/routers/define.py` → Gemini 2.5 Flash
identifies the ringed word AND defines it in one call → panel
(`desktop/compact.html`, embedded via `desktop/pill.html` webview) renders
definition + "What Lexio saw" thumbnail + language picker.

- The old DOM→AX→OCR text pipeline (`lib/context.js`, `lib/ax-reader.py`,
  JXA fallback) is **dormant but in-tree**. The web app (`/app`) still uses
  the text path of `/define` (word+context), which is fully supported.
- Billing: image lookups debit the normal lookup bucket (5 anon / 20 free /
  Pro unlimited) at "balanced" hourly weight. NOT the photo-scanner bucket.
- Hard-won platform notes live as comments in `native/lexio-ocr/main.swift`
  (SCK sourceRect is TOP-LEFT origin — do not "fix" it back) and
  `native/build-ocr.sh` (the helper MUST be Developer-ID signed with
  hardened runtime + timestamp or notarization of the whole app fails).
- `desktop/compact.html` is canonical; run `bash desktop/scripts/sync-compact.sh`
  after editing it (ships copies to `static/`).
- Deploy: push to main, then `ssh root@188.245.144.73 "sudo /var/www/lexio/deploy.sh"`.
- Desktop release: `cd desktop && APPLE_ID=… APPLE_APP_SPECIFIC_PASSWORD=… npm run dist`
  (Developer ID "Matvei Loginov", team 8TJHY75AV5, in the login keychain).

---

## P0-1 · Fix the stale download link — ✅ DONE 2026-07-09 (/download/mac live, nginx allowlisted, modal updated)

`static/index.html` desktop modal links to
`github.com/mtvlgnv/Lexio/releases/download/v1.1.5-glance/Lexio-Glance-1.1.5-arm64.dmg`
— two majors behind; predates every capture fix. After publishing the
v1.3.0 release: update the href, AND add a server-side redirect
(`/download/mac` → latest release asset) in the FastAPI app or nginx so
the site never goes stale again. **Nginx gotcha:** prod nginx only proxies
an explicit path-prefix allowlist — a new `/download` route 404s until
added to the regex and nginx reloaded.

Verify: `curl -sIL https://lexio.site/download/mac | grep -E "HTTP|location"`.

## P0-2 · Auto-update — ⚙️ WIRED 2026-07-09 (updater + zip target + publish config in place; verify against the first published release, see step 4 gotcha)

No update mechanism exists at all. Users are stranded on whatever DMG they
installed. The repo already publishes GitHub releases, which is exactly
what electron-updater's GitHub provider consumes.

Implementation:
1. `npm i electron-updater` in `desktop/`.
2. package.json `build`: add `"publish": [{"provider": "github", "owner": "mtvlgnv", "repo": "Lexio"}]`
   and add a **`zip` target** alongside `dmg` — electron-updater on macOS
   updates FROM THE ZIP, not the DMG. Both artifacts get signed/notarized
   by the existing pipeline; `latest-mac.yml` must be uploaded to the
   release (electron-builder generates it; `npm run dist -- --publish always`
   or upload manually).
3. In `main-overlay.js`: `autoUpdater.checkForUpdatesAndNotify()` on app
   ready + every ~6h. Menu-bar tray item "Check for updates…". On
   update-downloaded, unobtrusive prompt → `quitAndInstall()`.
4. Tag format: existing tags are `v1.3.0-glance`; electron-updater expects
   the tag to contain the semver — `v1.3.0-glance` parses fine, but verify
   with a draft release before trusting it; otherwise switch to plain `v1.3.0`.

Gotchas: hardened runtime is already on (required for updater on notarized
apps). The app must be in /Applications (updater can't replace a
translocated/DMG-run app) — onboarding already tells users this.

Verify: install current build, publish a `v1.3.1-glance` draft with a
trivial bump, confirm in-app update prompt appears and relaunch lands on 1.3.1.

## P0-3 · Privacy policy — ✅ DONE 2026-07-09 (privacy.html + FAQ + JSON-LD describe screen captures honestly)

`static/privacy.html` and the FAQ in `static/index.html` say "only the word
and a short surrounding context window are sent". The desktop app now sends
a **screenshot of a screen region**, which can incidentally contain third-
party content (messages, emails). Update both to say a small area of the
screen around the pointer is captured, sent over HTTPS for analysis, never
stored (true today — images are not persisted server-side; keep it true).
Also update the FAQ JSON-LD blob near line ~181. Honest wording is a trust
asset; discovery-by-user is a liability.

## P1-1 · Save-to-Word-Bank — ✅ DONE 2026-07-08 (panel Save button, local-first + sync, 10-save signed-out cap)

The single most important missing feature. Backend is fully built:
`POST /wordbank/sync` (payload: `{entries: [{word, pos, ipa, definition,
contextual, why, simpler, etymology, register, savedAt, context}]}`),
`GET /wordbank`, `DELETE /wordbank/{word}`, `GET /wordbank/anki` (deck
export). The web app's Collect button in `static/app.js` shows the exact
client pattern (auth: `Bearer lexio_token` from localStorage — the desktop
webview has the same token in its partitioned localStorage after sign-in).

Add to `desktop/compact.html` def-actions row: a Save/Collect button that
posts the current `currentResult.data` + `context`. Handle signed-out
(prompt to sign in via the Hub). Piggyback: report saves to the Hub via the
existing `LEXIO_LOOKUP::`-style console bridge if the Hub needs live update.
Remember `sync-compact.sh` after editing.

## P1-2 · Hub v2 — ✅ SHIPPED 2026-07-08 (home.html: Word Bank/Recent/Settings/Account; Home/stats tab still open)

Current Hub (`desktop/hub.html`): three cramped tabs — Recent (list +
relookup), Settings (launch-at-login, trigger key, 3 permission rows),
Account (sign in/out only). It answers "how do I configure this" and never
"what am I getting out of this app".

Target: a real window with sidebar navigation, five sections:
- **Home** — this week's stats (lookups, words saved, day streak), a
  "from your word bank" word of the day, permission warnings only when
  something is broken. Stats source: `store.get().recentLookups` (local,
  capped 50 — raise the cap or aggregate counts separately) and the word
  bank. Server-side truth exists in `UserSearchLog` if cross-device stats
  are wanted later.
- **Word Bank** — synced list (word + sentence + definition), search,
  delete, **Export to Anki** button (endpoint exists — zero backend work).
- **Recent** — as today, plus per-row save-to-bank.
- **Settings** — as today, plus definition language (currently only in the
  panel's `lang-select`; read/write the same `lexio_lang` localStorage of
  the webview partition, or lift it into `store.js` and inject).
- **Account** — plan name, usage meter (every `/define` response already
  returns `_usage {used, limit}` and `_hourly` — currently discarded by the
  client; also `GET /api/pro-status` exists), Upgrade → lexio.site, sign out.

Phasing if not done in one pass: Account usage meter → Word Bank → Home.
IPC pattern to copy: `preload-hub.js` + `hub:*` handlers in `main-overlay.js`.

## P1-3 · Onboarding practice failure state — ✅ DONE 2026-07-09 (failure event + relaunch button)

`desktop/onboarding.html` step 3 waits forever on
`onboarding:practice-capture`. If the capture fails (Screen Recording
granted but macOS wants an app relaunch — common), the user stares at
"Waiting for your double-tap…" and churns. Have `captureScreenshot()` in
`main-overlay.js` also send a failure event when onboarding is open; show
"macOS may need the app to relaunch after granting Screen Recording —
quit and reopen Lexio Glance" with a relaunch button
(`app.relaunch(); app.exit()`).

## P2 · Perceived latency, streaks, referral

- ~~Show the thumbnail while the definition loads~~ ✅ DONE 2026-07-09.
- ~~Streaks/stats~~ ✅ DONE 2026-07-09 (Hub Home tab: greeting, weekly count, streak, word of the day).
- Referral/share: defer until retention exists.

---

## P1-4 · Thinking mode — deeper analysis on demand ✅ DONE 2026-07-11

"Think deeper and smarter, but also slower." Escalation for the lookups
where the fast answer underwhelms: dense literary passages, loaded idioms,
archaic usage, domain jargon.

**UX (the important part):** NOT a persistent mode toggle. A **"Think
deeper" button on the result panel** — you escalate only after seeing the
fast answer, re-using the capture already in hand (`lastImage` in
compact.html is retained exactly for re-runs; the language switcher
already uses it). Panel expands with richer sections when they arrive.

**Implementation:**
1. Backend: `_define_from_image()` currently hardcodes `actual_model =
   "balanced"` + Gemini. Honor `req.model`: `deep` → a new
   `ai._call_anthropic_vision(prompt, image_bytes, mime)` (Claude Sonnet
   4.5 is multimodal; mirror `_call_google_vision`'s shape; base64 image
   block + JSON-only instruction). Weight 3 credits, Pro-gated with the
   existing 403 `pro_required` flow — identical economics to text-mode Deep.
2. Deep prompt additions: request `nuance` (connotation/register vs. near
   synonyms — why THIS word and not its neighbors), `examples` (2 short
   sentences reusing the word in the same sense), keep all existing keys.
3. Panel: "Think deeper ✦" button in def-actions (visible on image-mode
   results when not already deep); click → loading state ("Thinking…" +
   capture thumb) → `fetchDefFromImage(lastImage.b64, lastImage.mime,
   {model:'deep'})`; render `nuance`/`examples` sections when present.
   Free users get the existing upgrade prompt via the 403 handler.
4. Client passes `model` through in image mode (currently sends the
   panel's `getModel()` — verify deep maps correctly rather than being
   coerced).

Effort: ~1 day incl. live verification. Direct Pro upsell surfaced at the
exact moment of dissatisfaction with the free answer.

## P1-5 · Reader profile / user memory (founder idea, planned 2026-07-09)

"The app should remember the user is a wood-worker, so the context is
suitable." Durable facts about the reader that make every definition
land in THEIR world: profession/interests (domain-sense disambiguation —
"kerf", "consideration", "stock" mean different things to different
people), native language, English level (calibrates explanation
complexity), preferred tone.

**Phase 1 — explicit profile (ship first, ~1 day):**
1. DB: `User.profile_json` (nullable TEXT) — `{about, english_level,
   native_lang}`. `about` is one free-text line ("furniture maker in
   Eindhoven, reads woodworking + business content").
2. API: `GET/PUT /api/profile` (auth required, ~30 lines next to
   /api/pro-status).
3. `/define` (BOTH text and image paths): for authed users, load profile
   and append to the prompt: "Reader profile: {about}. English level:
   {level}. If the word has a domain sense plausible in the on-screen
   context AND relevant to the reader's world, prefer/mention it;
   calibrate explanation complexity to their level. NEVER force the
   reader's domain onto words where it doesn't fit the context."
   (That last clause is the over-personalization guard — the #1 risk.)
4. Hub Account tab: "About you" card (one text field + level select +
   native language). Onboarding gets an optional one-liner step later.
5. Cache note: web text-mode client cache keys must include a profile
   hash or be cleared on profile change (image mode is uncached).

**Phase 1.5 — the profile interview (founder idea, added 2026-07-09):**
a short, warm, PURELY OPTIONAL interview that fills the profile
conversationally instead of via a form. Two entry points:
- Onboarding: one optional step after the practice run — "Want Lexio to
  know you a little? 3 quick questions (skippable, editable later)."
- Later, after real usage (e.g. the 15th lookup or 5th saved word): a
  one-time Hub Home card — "You've saved 5 words! Answer 3 questions so
  definitions fit your world better." Dismiss = never shown again
  (store a `profileInterviewDismissed` flag).
Questions (3–4 max, one screen each, skippable individually): what do
you do / what are you into (free text) · your English level (choices,
"not sure" allowed → infer later) · what do you mostly read in English
(news / work / fiction / study — multi-select) · native language
(pre-filled from the definition-language setting). Answers just write
the same `profile_json` as Phase 1's form — the interview IS the form,
in a friendlier costume. Every answer visible and editable in Hub →
Account afterwards. Never gate any feature on completing it.

**Phase 2 — learned memory (later, ~2-3 days):** weekly job summarizes
UserSearchLog + word bank into SUGGESTED profile lines the user confirms
in the Hub ("You read a lot about woodworking — tailor definitions?
[Yes/No]"). Consent-first, always visible/editable/deletable in Account,
privacy-policy paragraph. Never silently inferred-and-applied.

Synergy: the profile feeds BOTH normal and Thinking-mode prompts; the
two features compound (deep analysis calibrated to your level and world).

## P1-6 · Hub content expansion (researched 2026-07-09)

What comparable products put in their "home base", and what maps to
Lexio. Sources: Wispr Flow's Hub (stats card: words dictated / WPM /
streak, adaptive welcome text, real-time recent-activity feed, custom
Dictionary, referral); WordUp (Knowledge Map of known vs unknown words,
25k words ranked by real-world frequency, daily spaced-repetition
review with multiple challenge types); Readlang/LingQ (words saved from
real reading become flashcards; known-words counters as the core
progress metric).

Ranked backlog for the Hub, highest value first:
1. **Review mode (spaced repetition on the Word Bank)** — THE missing
   loop; every comparable app has it. A "Review" section (or Home card:
   "5 words due today"): flashcard = the saved sentence with the word
   blanked → reveal definition → Again/Good buttons → SM-2-lite
   intervals stored per entry (`reviewAt`, `interval` fields on the
   existing wb entries; local-first like saves). ~1-2 days. This turns
   Lexio from "lookup tool" into "learning system" and directly earns
   the "words truly learned" stat.
2. **Words-learned metric** — once review exists: a word graduating 3
   successful reviews counts as "learned"; Home stat card + the
   WordUp-style known-words framing ("214 words in your English").
3. **Weekly recap card on Home** — lookups, new words, streak vs last
   week; reuses the existing `/email` digest infra server-side for a
   matching weekly email (endpoint skeleton exists — see
   /email/unsubscribe).
4. **Trending among Lexio readers** — the site's trending-words data
   (SearchLog) as a small Home card: "readers this week are looking up
   *tariff*, *stopgap*…" — tap → lookup. Zero backend work, endpoint
   feeds the homepage already.
5. **Referral card** — Wispr-style "give a friend a month of Pro" —
   AFTER retention loops exist, needs backend referral codes.
Skip (considered, rejected for now): generic daily-goal setting (streak
already covers the habit mechanic); word-frequency rank badges (needs a
frequency dataset; revisit with review mode's grading).

---

## Windows port — now dramatically cheaper (strategic note)

The vision-first rebuild removed every hard macOS dependency from the
brain of the product. There is **no OCR anywhere** — the old "PaddleOCR on
Windows" plan is obsolete. What's actually platform-specific now:

| Concern | macOS (built) | Windows (needed) |
|---|---|---|
| Region screenshot | ScreenCaptureKit helper | `Graphics.Capture` (WinRT) or GDI `BitBlt` — a ~150-line C#/C++ helper, or even Electron's `desktopCapturer` cropped in JS (slower, zero native code) |
| Cursor marker | CGContext ring | same drawing, any bitmap API — or draw the ring in JS on a canvas before upload (portable, removes native drawing entirely) |
| Global double-tap | uiohook-napi | uiohook-napi **already supports Windows** |
| Own-window exclusion | SCK excludingWindows | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` on the overlay window — simpler than the mac approach |
| Permissions | Accessibility + Screen Recording TCC | none needed (no prompts at all) |
| Signing | Developer ID + notarization | Authenticode cert (or ship unsigned + SmartScreen warning initially) |

Everything else — pill/panel UI, compact.html, backend, billing, word
identification — is shared and already done. Estimated scope: the capture
helper + packaging (electron-builder `--win`), an installer target (nsis),
and QA. The marketing site already says "Windows on the roadmap".
Recommended sequencing: after P0s + Word Bank, before deep Hub polish —
it doubles the addressable market for the same product.

---

## Working agreements (for agents)

- The user **enjoys being interviewed**: when a task has ambiguous product
  decisions, ask 2–4 sharp multiple-choice questions up front rather than
  guessing. Act autonomously on purely technical decisions.
- Verify end-to-end before claiming success (this codebase has had three
  "works on my machine" incidents; the capture pipeline specifically can
  only be trusted via a real screenshot → real backend → real panel test).
- After editing `desktop/compact.html`, run `desktop/scripts/sync-compact.sh`.
- After every push that touches `app/` or `static/`, deploy via ssh script.
