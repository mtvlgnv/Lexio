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

## P0-1 · Fix the stale download link (trivial, do immediately)

`static/index.html` desktop modal links to
`github.com/mtvlgnv/Lexio/releases/download/v1.1.5-glance/Lexio-Glance-1.1.5-arm64.dmg`
— two majors behind; predates every capture fix. After publishing the
v1.3.0 release: update the href, AND add a server-side redirect
(`/download/mac` → latest release asset) in the FastAPI app or nginx so
the site never goes stale again. **Nginx gotcha:** prod nginx only proxies
an explicit path-prefix allowlist — a new `/download` route 404s until
added to the regex and nginx reloaded.

Verify: `curl -sIL https://lexio.site/download/mac | grep -E "HTTP|location"`.

## P0-2 · Auto-update (electron-updater + GitHub Releases)

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

## P0-3 · Privacy policy still describes the text-only pipeline

`static/privacy.html` and the FAQ in `static/index.html` say "only the word
and a short surrounding context window are sent". The desktop app now sends
a **screenshot of a screen region**, which can incidentally contain third-
party content (messages, emails). Update both to say a small area of the
screen around the pointer is captured, sent over HTTPS for analysis, never
stored (true today — images are not persisted server-side; keep it true).
Also update the FAQ JSON-LD blob near line ~181. Honest wording is a trust
asset; discovery-by-user is a liability.

## P1-1 · Save-to-Word-Bank from the desktop panel

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

## P1-2 · Hub v2 — from settings popover to Wispr-Flow-style home

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

## P1-3 · Onboarding practice-step failure state

`desktop/onboarding.html` step 3 waits forever on
`onboarding:practice-capture`. If the capture fails (Screen Recording
granted but macOS wants an app relaunch — common), the user stares at
"Waiting for your double-tap…" and churns. Have `captureScreenshot()` in
`main-overlay.js` also send a failure event when onboarding is open; show
"macOS may need the app to relaunch after granting Screen Recording —
quit and reopen Lexio Glance" with a relaunch button
(`app.relaunch(); app.exit()`).

## P2 · Perceived latency, streaks, referral

- Show the "What Lexio saw" thumbnail **while the definition loads**
  (image is in-hand before the fetch; currently shown only after).
- Streaks/stats need Hub Home first.
- Referral/share: defer until retention exists.

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
