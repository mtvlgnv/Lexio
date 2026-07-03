# Lexio Glance — Structure & Design Review

*Written 2026-07-02, against commit `fbc7664`. Covers the desktop overlay app
(`desktop/`) and the parts of the web app it embeds.*

---

## 1. What exists today — architecture map

```
Lexio Glance.app  (Electron 43, ad-hoc signed, arm64 DMG)
│
├─ main-overlay.js        main process: pill window, expand/collapse animation,
│                         selection capture (osascript ⌘C), double-tap-⌘ trigger
│                         (uiohook-napi), tray, lexio:// auth handler, IPC hub
├─ store.js               local persistence — lexio-store.json in userData
│                         { onboardingComplete, auth, recentLookups, settings }
│
├─ pill.html              renderer 1: collapsed gradient pill + expanded panel
│    └─ <webview> ──────► compact.html (local copy)   the actual lookup UI
├─ onboarding.html        renderer 2: 5-step first-run wizard
├─ hub.html               renderer 3: tray dropdown — Recent / Settings / Account
│
├─ preload-overlay.js     lexioOverlay    (expand/collapse IPC)
├─ preload-onboarding.js  lexioOnboarding (permissions, sign-in, finish)
├─ preload-hub.js         lexioHub        (recent, auth, settings)
│
└─ Sibling entry points sharing this folder (NOT shipped behavior, but shipped bytes):
   main.js       "Lexio Mini" tray app  (legacy, loads lexio.site/compact.html)
   main-app.js   "Lexio" full dock app  (legacy, loads lexio.site?app=1)
```

**Data flow for a lookup:** double-tap ⌘ → `captureSelection()` (clipboard
sentinel + synthesized ⌘C) → text piped over IPC → pill.html injects it into
the webview via `executeJavaScript` → compact.html calls
`POST https://lexio.site/define` → definition renders in its bottom sheet.

**Auth flow (as designed):** "Sign in" → system browser opens
`lexio.site?desktop_auth=1` → after login the site redirects to
`lexio://auth?token=…&user=…` → `open-url` handler writes `store.auth` and
notifies the onboarding/hub windows.

---

## 2. Critical functional gaps (fix before any visual work)

### 2.1 Sign-in is broken end-to-end — two separate bugs ⚠️ P0

**Bug A — site side.** `static/app.js → _maybeRedirectDesktop()` only fires
from the login/signup *success handlers*. A user who is **already signed in**
lands on `lexio.site?desktop_auth=1`, no handler runs, and nothing redirects
back to `lexio://auth`. This is exactly the reported symptom ("it follows me
to lexio.site where I'm already signed in and nothing happens").
*Fix:* on `DOMContentLoaded`, if `desktop_auth` is present **and** a token
already exists in `localStorage`, call `_maybeRedirectDesktop(token, user)`
immediately.

**Bug B — app side.** Even when the `lexio://auth` handoff works, the token
only lands in `store.js`. The **webview** (which makes all the API calls and
gates Pro models) keeps its own isolated `localStorage` in the
`persist:lexio` partition and never receives it. `compact.html` listens for a
`lexio-auth` event that only the *legacy* `main.js` ever dispatches;
`main-overlay.js` never injects into the webview. So the embedded app stays
signed out forever regardless of Bug A.
*Fix:* on auth, main → `overlay:auth` IPC → pill.html runs
`frame.executeJavaScript(...)` to set `lexio_token`/`lexio_user` and dispatch
the `lexio-auth` event (mirror of main.js:113–117). Also replay stored auth
on webview `dom-ready` so sign-in survives restarts, and mirror sign-out.

### 2.2 "Recent lookups" records the wrong thing — P1

`captureSelection()` logs the first 80 chars of the **captured selection**
(often a whole sentence) rather than the **word the user actually looked up**
(a click on a token inside the webview). The Hub's Recent tab will fill with
sentence fragments. The real lookup happens inside compact.html — it should
report the defined word back out (an `ipc-message` from the webview, or a
`console.message` bridge) and *that* is what belongs in `recentLookups`.
Items should also be clickable to re-run the lookup.

### 2.3 Ad-hoc signing resets permissions on every rebuild — accepted for now

Every rebuild produces a new ad-hoc signature; macOS TCC then treats it as a
new app: Accessibility must be re-granted (stale entries need
`tccutil reset Accessibility site.lexio.glance`), and Gatekeeper blocks first
launch. Known, documented, deferred until Apple Developer enrollment at
launch. Until then: **rebuild rarely, test in dev mode** (`npm run
start-overlay`).

---

## 3. Visual design audit

### 3.0 The core problem: four surfaces, three design systems

| Surface | Fonts | Color system | Buttons |
|---|---|---|---|
| Pill panel chrome (pill.html) | **Fraunces** + DM Sans | hex (`#f5efe8`, `#c35500`) | — |
| Onboarding + Hub | **Fraunces** + DM Sans | same hex set | orange gradient pill buttons |
| Embedded lookup UI (compact.html) | **Lora** + DM Sans | **oklch** tokens, different accent | flat gradient rectangles |
| Marketing site | **Fraunces** + Inter | its own set | its own |

The app *reads* as two different products glued together at the panel border:
Fraunces chrome around a Lora document. The single highest-leverage design
change is **one shared token sheet** (fonts, colors, radii, shadows, button
recipes) used by all four desktop surfaces. Concretely: port compact.html to
Fraunces (display) + DM Sans (UI), and to the same accent/`--bg`/`--surface`
values the chrome uses — or better, extract `desktop/tokens.css` and import it
everywhere.

### 3.1 Expanded panel / compact.html (the "main UI" — weakest surface)

1. **Paste-first, not selection-first.** The top third of the panel is a
   paste textarea + Analyze button. But the product's whole promise is
   "select anywhere → instant definition" — in the primary flow the text is
   *already captured*. The paste box should be a secondary affordance
   (collapsed one-line "or paste text…" row), and the token view + definition
   should own the space. When opened with a capture, the user should land
   directly on tokens with zero input chrome visible.
2. **The definition is the payoff but gets the leftovers.** It's a bottom
   sheet capped at `54vh` with 0.75–0.9rem text. Hierarchy should invert:
   word (Fraunces, large) → contextual meaning (the star, readable size ≥1rem)
   → why-this-meaning → etymology, with the source sentence dimmed above.
3. **Tiny-gray-text syndrome.** Nearly everything is 0.62–0.9rem muted gray.
   There is no clear reading rhythm; increase base sizes and reserve `--muted`
   for genuinely tertiary info (IPA, etymology, char count).
4. **Model selector is off-brand.** A raw `<select>` with `Gemini 🔒 /
   Sonnet 4.5 🔒` exposes vendor names and uses a lock emoji as UI. Rename to
   user-meaningful tiers (Fast / Precise), style as a segmented control, and
   gate with a proper "Pro" chip.
5. **Empty state** (dashed box + lowercase "w" glyph) is better than a blank
   void but still passive. It should teach the core gesture: "Select text in
   any app, then double-tap ⌘" with a tiny animated hint — the paste flow is
   the fallback, not the headline.
6. **Loading state** is a single italic line pinned under the input. Move it
   into the definition area (skeleton lines where the definition will
   appear) so attention doesn't jump.
7. **Error state** is a plain red strip; 402/403 upsells deserve a proper
   card with an Upgrade button, not `alert()`-grade text.

### 3.2 Pill (collapsed)

Solid: CSS blob gradient in brand colors, drift animation,
`prefers-reduced-motion` respected. Improvements:
- No state feedback — it looks identical when idle, capturing, and erroring.
  A brief pulse while capturing and a shake/tint on capture failure would
  make the invisible gesture legible.
- Hover-expand with an 80 ms debounce is aggressive for a bottom-center
  screen zone; consider hover = slight swell only, click / double-tap ⌘ =
  expand, to stop accidental openings (Wispr's bar behaves this way).

### 3.3 Hub

- Layout and tabs are clean; matches the chrome design system. Gaps: Recent
  items are inert text (no click-to-relookup, no hover affordance, no
  clear-history), Account tab is bare, and the window has a fixed 380×520
  size regardless of content.
- Tray icon is the text `" Lx "` — a real template icon (16 pt "w" glyph from
  `create-icon.js` artwork) would look native instead of like a debug label.

### 3.4 Onboarding

- Structure is right (Wispr-style: welcome → sign in → permission → practice
  → done). Weak points: the hero blob is the only visual on every screen
  (screens blur together); the Permissions screen explains *what* but not
  *why trust it* (one line on "text is read only when you trigger it" would
  do a lot); the practice step has no success animation — the status pill
  just flips text; and skipping sign-in is invisible later (Hub Account tab
  should carry the "sign in to sync" nudge, which it does — good).

### 3.5 Dark mode

compact.html has full dark tokens; the chrome (pill panel, hub, onboarding)
has **none** — a signed-in dark-mode user gets a dark document inside a cream
frame. The shared token sheet (3.0) must ship light+dark for every surface,
and the theme hash param already plumbed into the webview should come from
`nativeTheme` with live updates.

---

## 4. UX flow gaps

- **No keyboard path inside the panel:** arrows/tab don't move between word
  tokens, Enter doesn't re-open the last definition, ⌘F/type-to-search is
  absent. For a keyboard-triggered tool this matters.
- **No direct word lookup.** You cannot just type one word and get a
  definition — you must paste "text", Analyze, then click the word. A single
  input that accepts either a word or a passage would collapse the funnel.
- **Blur-collapse can eat work.** Click-away instantly collapses even with a
  definition open / text half-pasted; state *is* preserved, but there's no
  pin/keep-open affordance for reading alongside another app — the one thing
  an always-on-top overlay is for.
- **History exists but does nothing** (see 2.2): not clickable, not searchable,
  not synced (server has `UserSearchLog` but no read API — future
  `/api/recent-searches`).
- **Fallback shortcut is undiscoverable and unconfigurable** — shown in Hub
  Settings (good) but hardcoded to whichever of three candidates registered.

---

## 5. Code structure & hygiene

1. **Dead weight ships in the .app:** `desktop/app.css` (3,510 lines, ~174 KB)
   is referenced by **nothing** — grep confirms zero links. The asar also
   bundles the legacy entry points (`main.js`, `main-app.js`), `create-icon.js`
   and build scripts. Add a `files` allowlist to the electron-builder config.
2. **`compact.html` exists twice** (`desktop/` and `static/`), diverging only
   in URL handling (hash params + absolute API base). One template + a tiny
   build/copy step — or a `<base>`/config shim — would prevent silent drift;
   the desktop copy already missed one site-side fix this session.
3. **Three entry points share zero code.** `BLANK_ICON`, tray construction,
   and now the `lexio://auth` parsing are duplicated between `main.js` and
   `main-overlay.js`. Either delete the legacy entries (Glance supersedes
   Mini) or extract `desktop/lib/{tray,auth,icons}.js`.
4. **Branding leftovers:** the DMG is still titled/named
   **"Lexio Mini"** (`package.json → build.dmg.title/artifactName`) while the
   product is "Lexio Glance". *(fixed alongside this review)*
5. **`console.log` is the only telemetry.** Fine for dev, but the packaged
   app writes logs nowhere — a `--verbose` flag or a rotating file log in
   userData would make field debugging (like this week's) far less painful.
6. **`store.js` writes synchronously on the main process** — fine at this
   size; revisit only if recentLookups grows or writes become per-keystroke.

---

## 6. Prioritized roadmap

| # | Item | Impact | Effort |
|---|------|--------|--------|
| P0 | Fix sign-in end-to-end (Bugs A + B in §2.1) | Blocks accounts, Pro, sync | S — *done alongside this review* |
| P0 | Shared design tokens across all 4 surfaces; port compact.html to Fraunces/brand palette (§3.0) | Kills the "two products" feel | M |
| P1 | Panel redesign: selection-first layout, definition-as-hero, real loading/error states (§3.1) | The "main UI is ugly" complaint | M–L |
| P1 | Recent lookups: record the defined word, clickable to re-lookup (§2.2) | Makes the Hub useful | S–M |
| P1 | Dark mode for chrome surfaces + `nativeTheme` sync (§3.5) | Table stakes for a macOS overlay | S–M |
| P2 | Pill state feedback; tame hover-expand (§3.2) | Polish, fewer accidental opens | S |
| P2 | Keyboard navigation + single-word quick lookup (§4) | Power-user speed | M |
| P2 | Build hygiene: files allowlist, drop dead app.css, dedupe compact.html, extract shared modules (§5) | Smaller app, less drift | S–M |
| P3 | Tray template icon, pin-open mode, configurable hotkey, file logging | Nice-to-have | S each |
| P3 | Signing + notarization + auto-update (deferred until Apple Developer enrollment) | Distribution | M + $99/yr |
```
