# Lexio — Project Context

## What Lexio is
**A contextual word-definition engine for serious readers and language learners.**
You read text, tap any word, and get its meaning *in that exact sentence* — not a
generic dictionary entry — plus part of speech, IPA, etymology, register, and why
the author chose that word. Words can be saved to a synced **word bank**.

- **Live in production** at [lexio.site](https://lexio.site).
- Built over ~the last month by [@mtvlgnv](https://github.com/mtvlgnv).

## The vision (north star)
An **iOS reading app, Apple Books-like in aesthetic, with Lexio built in.** The user
reads a book inside the app and taps any word for its contextual meaning. This turns
Lexio from "paste your own text" into "a beautiful library of books you read in-app."

## Surfaces
| Surface | Status | Location |
|---|---|---|
| Web app (SPA) | Live | `static/index.html`, served by FastAPI |
| Chrome extension | Live | `extension/` (zipped into `static/`) |
| Electron Mac app | Live (GitHub Releases) | `desktop/` |
| **iOS reading app** | In its OWN repo now | github.com/mtvlgnv/LivelyReading (was `ios/`) |

## Backend
- Python · FastAPI · SQLAlchemy · SQLite (`lexio.db`) · slowapi rate limiting.
- Core endpoint: `POST /define` — TWO input shapes:
  - text: `word + context + lang + model` (web app, extension)
  - image: `image_base64 + image_mime + lang` (desktop app — the model
    identifies the ringed word AND defines it in one call)
- Three modes routed to three AI providers (all SDKs already integrated):
  - **Fast** — GPT-OSS 20B via Groq, strict JSON schema (free, 1 credit)
  - **Balanced** — Gemini 2.5 Flash (2 credits; also ALL image lookups)
  - **Deep** — Claude Sonnet 4.5 (Pro, 3 credits)
- Other: `/ocr`, `/fetch-text`, `/auth/{register,login,google,apple}`, `/api/{usage,pro-status}`,
  Stripe checkout/portal/webhook, `/stats/top-words`, and SEO pages (`/works`, `/glossary`).
- Auth: JWT (email/password, Google, Apple). Payments: Stripe, Free vs Pro
  ($4.99/mo, $39.99/yr, $9.99 family ×4, 3-day trial). Free = 20 lookups/mo
  (anon 5/mo by IP) + Fast only; Pro = all modes, unlimited lookups.
- Positioning (July 2026 reframe): the ICP is **English learners / ESL
  readers** — hero, features, and 11 locales all sell "the meaning that fits
  the sentence, explained in your own language".

## Languages
11 in and out: English, Spanish, French, German, Italian, Portuguese, Russian,
Japanese, Chinese, Korean, Arabic. (See `ios/.../Models/Language.swift`.)

## iOS app  (moved OUT to its own repo: github.com/mtvlgnv/LivelyReading)
NOTE: As of 2026-06-01 the iOS app was moved out of this monorepo into a
standalone PUBLIC repo **LivelyReading** (cloned at `/Users/mtvlgnv/LivelyReading`).
The Xcode target/bundle is still `LexioReader` / `site.lexio.reader` (repo name
differs; no full rebrand yet). This backend repo keeps the catalog API the app
calls. The notes below describe that app for reference.

### iOS app structure
- SwiftUI. Models: `ReadingItem` (plain `title`+`body` text — **no chapter/EPUB
  structure yet**; comment notes "EPUB import is a planned follow-up"),
  `Language`, `ReadingMode`, `WordBankEntry`, `Definition`, `Account`.
- Views: `Library`, `Reader`, `AddText` (paste), `WordBank`, `Settings`, `SignIn`.
- Services: `LexioAPI` (has define/auth/wordbank — **no catalog/books endpoint**),
  `LibraryStore`, `WordBankStore`, `Disk`, `Keychain`, `Speech`, `Theme`.
- **Content today comes only from user-pasted text.** There is no built-in library
  of readable books.

## Book catalog (BUILT — 2026-06-01)
A **book catalog + import** so the iOS library is filled with readable books
(not just pasted text). Content = **multi-language public-domain classics** from
Project Gutenberg (legal, free, ideal for language learners; sidesteps the fact
that modern "popular" books are all copyrighted). What exists now:
- `scripts/build_catalog.py` — curated multi-language SEED of Gutenberg ids;
  downloads text, strips PG boilerplate, writes `catalog_data/manifest.json` +
  `catalog_data/texts/<slug>.txt`. Re-run to rebuild/extend. (2 seed ids failed:
  Pinocchio gid 28732 wrong id; Os Lusíadas gid 3333 transient — fix later.)
- `catalog_data/` — generated; **24 books across 8 languages** (en 10, fr 5, de 3,
  es 2, it 1, pt 1, ru 1, ja 1).
- `catalog.py` — loads the manifest, serves metadata + text (lazy/cached).
- `main.py` — `GET /api/catalog` (langs + all books, JSON) and
  `GET /api/catalog/{slug}` (metadata + full `body`). Added just before the
  StaticFiles `/` mount so they aren't shadowed. **Not yet deployed to lexio.site.**
- iOS: `Models/CatalogBook.swift`, `LexioAPI.catalog()/catalogBook(slug:)`,
  `Views/BrowseView.swift` (Discover tab — language filter chips, book list,
  detail with "Add to Library" → imports text into `LibraryStore` and pushes the
  reader). `LibraryStore.add` now returns the item + has `contains(title:)`.
  `RootView` has a new **Discover** tab. Builds clean (Xcode 26.5, iOS sim).

### Verified
- Backend routes return 200/404 correctly via FastAPI TestClient.
- iOS app compiles (`xcodegen generate` + `xcodebuild` BUILD SUCCEEDED).
- NOT yet run end-to-end in the simulator against a live backend (app's
  `Config.apiBaseURL` is production, which lacks the new routes until deployed).

### Still open
- Likely shape recap (done): import pipeline → JSON catalog API → iOS Browse.
- **No new reading features.** The only reader interaction is the existing
  tap-a-word → contextual-definition popup (`DefinitionSheet` + `LexioAPI.define`).
  There is NO "AI companion" (no summaries/recaps/chat). The catalog just feeds
  readable books into the existing reader.
- **Open decisions (not yet settled):**
  1. Launch target: TestFlight beta vs full App Store release (affects ~30-day timeline).
  2. Chapter model: extend `ReadingItem` with chapters vs one-item-per-chapter vs
     whole-book-as-one-blob. (Deferred.)

## Desktop app — VISION-FIRST since 2026-07-08 (the big one)
Lexio Glance (`desktop/`) no longer reads text via Accessibility/OCR. Every
lookup: double-tap ⌃ → Swift helper (`native/lexio-ocr`, ScreenCaptureKit)
captures ~800×500 JPEG around the cursor with a **magenta ring at the exact
cursor point**, overlay window excluded by CGWindowID → `POST /define` with
`image_base64` → Gemini identifies + defines the ringed word. Panel shows the
capture ("What Lexio saw"), Save-to-Word-Bank, and a definition-language
picker. Hub v2 = real window (`home.html`: Home/Word Bank/Recent/Settings/
Account) sharing the `persist:lexio` partition with the panel (one
localStorage: token, `lexio_wbv1`, `lexio_lang`). Auto-update via
electron-updater + GitHub Releases is wired (needs `GH_TOKEN` +
`--publish always`, or manually attach dmg+zip+latest-mac.yml).

**Hard-won platform truths — do NOT "fix" these back:**
- `SCStreamConfiguration.sourceRect` is TOP-left-origin display coords;
  feeding cocoa bottom-left rects mirrors the capture vertically.
- The Swift helper MUST be Developer-ID signed + hardened runtime +
  timestamp (`native/build-ocr.sh` does it) or notarization of the whole
  app is rejected — this killed Glance 1.2.0 once already.
- Exclude only the OVERLAY window from captures, never the whole app
  (app-wide exclusion breaks the onboarding practice step).

## Planning docs (read before picking work)
- `ROADMAP.md` — prioritized product/engineering backlog with statuses.
- `DESIGN_ROADMAP.md` — design debt, observed vs needs-audit.
- `BACKLOG.md` — self-contained task specs sized for a single agent
  session; pick one, follow its Verify section, mark it done.

## Working agreements (from the founder)
- **Interview when ambiguous**: for product/design decisions with several
  plausible options, ask 2–4 sharp multiple-choice questions up front
  (AskUserQuestion) — he explicitly enjoys this. Act autonomously on
  purely technical choices.
- **Verify pixels, not just DOM** for desktop UI: spawn
  `desktop/bin/lexio-ocr` from bash (it sees real pixels; excludes nothing
  without `--exclude-window`) to screenshot Electron windows. A real
  rendering bug (`.hidden` undefined) once passed every DOM check.
- After editing `desktop/compact.html` or `desktop/tokens.css`:
  `bash desktop/scripts/sync-compact.sh` before committing.
- Deploy after every push touching `app/` or `static/`:
  `ssh root@188.245.144.73 "sudo /var/www/lexio/deploy.sh"`. New top-level
  routes 404 until added to the nginx location allowlist
  (`/etc/nginx/sites-enabled/lexio` line ~74) + `nginx -t` + reload —
  and never leave backup files inside `sites-enabled/`.
- Tests: `python3 -m pytest tests/ -q` must stay green (16 tests).
- Desktop release: `cd desktop && APPLE_ID=… APPLE_APP_SPECIFIC_PASSWORD=…
  npm run dist` (Developer ID team 8TJHY75AV5 in the login keychain).

## Conventions / notes
- Frontend SPA is a single file, no build step (vanilla HTML/CSS/JS).
- Pro gating is enforced server-side (Balanced/Deep return 403 `pro_required`).
- Keep Gutenberg trademark headers stripped from any imported public-domain text.
