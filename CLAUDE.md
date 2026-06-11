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
- Core endpoint: `POST /define` (word + context + lang + mode → contextual definition).
- Three modes routed to three AI providers (all SDKs already integrated):
  - **Fast** — GPT-4o mini (free, 1 credit)
  - **Balanced** — Gemini 2.5 Flash (Pro, 2 credits)
  - **Deep** — Claude Sonnet 4.5 (Pro, 3 credits)
- Other: `/ocr`, `/fetch-text`, `/auth/{register,login,google,apple}`, `/api/{usage,pro-status}`,
  Stripe checkout/portal/webhook, `/stats/top-words`, and SEO pages (`/works`, `/glossary`).
- Auth: JWT (email/password, Google, Apple). Payments: Stripe, Free vs Pro
  ($2.99/mo, 3-day trial). Free = 20 lookups/mo + Fast only; Pro = all modes.

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

## Conventions / notes
- Frontend SPA is a single file, no build step (vanilla HTML/CSS/JS).
- Pro gating is enforced server-side (Balanced/Deep return 403 `pro_required`).
- Keep Gutenberg trademark headers stripped from any imported public-domain text.
