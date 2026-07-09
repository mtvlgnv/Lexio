# Lexio Glance — Bug Report

*Written 2026-07-03, against the current working tree (post design-pass: tokens.css,
new genie expand animation, segmented model control). Ordered by severity within
each section.*

**Status as of 2026-07-04: all software-owned items fixed, verified live end-to-end
(TextEdit → double-tap/pill → auto-context → definition). Gemini's items (#3, #6,
#14, #18) landed independently during the same session. Only #20 (informational,
no action needed) and #21 (font-bundling, deferred as low-priority polish) remain
open. See "Ownership split" below for the item-by-item breakdown.**

**Separately discovered while verifying, NOT a desktop bug:** the `/define`
backend is returning intermittent 502s ("The AI model returned an unexpected
response") — confirmed via direct, repeated `curl` against production with a
valid Pro token: 2 of 3 identical requests failed just now. Retries with the
same payload succeed and return correct, contextual definitions, so the
desktop-side request format and auth are confirmed correct. This looks like
upstream AI-provider flakiness and is worth someone's attention on the backend
side — outside this report's scope (desktop app only).

---

## P0 — The reported bug: "Reading context…" hangs forever

### 1. ~~`overlay:context-ready` loses the race against the panel injection~~ — RESOLVED

**Symptom (user-reported, frequent):** panel opens, shows *"Reading context for
"word"…"*, and never advances.

**Root cause — a race inversion introduced by two changes meeting:**

The context read got fast. The live log now shows it completing in **147–513ms**
(`overlay.log`, e.g. `context read completed in 184ms`), versus the ~6.5s it took
when the two-phase flow was designed. Meanwhile the design pass added a **250ms
`.capturing` pulse delay** in [pill.html](pill.html) `expand()` before
`lexioDesktopInput` is injected into the webview. So the ordering assumption baked
into pill.html — *"The context read always outlives the fast word capture, so the
webview is already loaded by the time this fires — no queuing needed"* — is now
false most of the time. Two concrete failure paths:

- **Path A (guaranteed, first lookup of every session):** on the first expand the
  webview is created fresh; `frameReady` is false for ~1–3s (cold load). The
  context read finishes in ~200–500ms, main sends `overlay:context-ready`, and
  pill.html **drops it on the floor**: `if (frameReady) injectContextReady(payload)`
  — no else, no queue ([pill.html:300-305](pill.html)). The panel then finishes
  loading, `lexioDesktopInput(w, null)` runs, shows "Reading context…", and waits
  for an event that already came and went. Stuck forever.
- **Path B (coin-flip on warm frames):** even with `frameReady === true`, the input
  injection is delayed 250ms by the `.capturing` timer, plus an `executeJavaScript`
  round-trip. When the context read completes in under ~400ms,
  `lexioContextReady(word, ctx)` executes in the webview **before**
  `lexioDesktopInput` has set `pendingContextWord`. The guard
  `if (word !== pendingContextWord) return;` in [compact.html](compact.html)
  silently discards the context (pendingContextWord is still null/stale), then the
  loading state is shown and waits forever.

**Fix sketch (both ends, belt and braces):**
- pill.html: buffer the context payload if `frameReady` is false *or* if the
  initial payload hasn't been injected yet; flush it right after `injectAndAnalyze`.
- compact.html: instead of discarding a non-matching `lexioContextReady`, stash
  `{word, ctx}` in a one-slot variable; have `lexioDesktopInput` check the stash
  when it enters the `ctx === null` branch and consume it if the word matches.
- Add a renderer-side safety timeout (~4s) on the "Reading context…" state that
  falls back to defining with the word alone — no state in this pipeline should be
  able to wait unbounded on a single IPC message.

### 2. ~~`TIMEOUT_MS = 2500` silently reintroduces the original wrong-definition bug under load~~ — RESOLVED

*Resolved 2026-07-04.* `lib/context.js` was rebuilt around a new primary
strategy, `lib/ax-reader.py` (direct ctypes calls to the macOS Accessibility
API — no System Events, no AppleEvents — normally completes in ~100ms), with
the old JXA approach demoted to a fallback that only runs if the fast path
comes back empty. Timeouts are now sane for what each path actually is: 3s on
the (normally instant) fast path, 8s on the (genuinely slow, ~6.5s observed)
fallback. Combined with this session's renderer-side 4s safety timeout (#1's
fix), no path can silently degrade to a wrong definition without the user at
least seeing the "couldn't read context" note. Original writeup kept below for
the record.

### 2-original. `TIMEOUT_MS = 2500` silently reintroduces the original wrong-definition bug under load

[lib/context.js:60](lib/context.js) now SIGKILLs the read at 2.5s. Reads measured
**6.5s on this same machine earlier today** under session load (the log had a
string of `timed out after 1500ms` entries for the same reason). When the machine
is loaded, every read gets killed → context silently degrades to the bare word →
the model gets no sentence → **"bat" defined as the flying mammal again**, with no
UI indication anything degraded. This directly contradicts the explicit
correctness-over-latency decision the two-phase flow was built for.

**Fix sketch:** raise the ceiling back (8–10s), and when the read times out or
returns nothing, surface it: show a small "couldn't read context — defining the
word alone" note instead of pretending the definition is contextual.

---

## P1 — Broken UI shipping right now

### 3. ~~`--accent2` and `--good` were dropped from tokens.css but are still used~~ — RESOLVED (Gemini)

*Resolved 2026-07-04* — both tokens are now defined in tokens.css (light and
dark values). Sign-in button and the Accessibility "granted" dot render
correctly. Original writeup below.

### 3-original. `--accent2` and `--good` were dropped from tokens.css but are still used

The design pass moved hub.html and onboarding.html onto [tokens.css](tokens.css),
which defines neither `--accent2` nor `--good` (the old per-file `:root` blocks
that did define them were deleted). CSS treats a declaration with an undefined
`var()` as *invalid at computed-value time* → the whole declaration becomes
`unset`. Concretely:

- Hub → Account tab: **"Sign in with Lexio" button renders with no background**
  (white text on nothing) — `background: linear-gradient(135deg, var(--accent2), var(--accent))`.
- Onboarding: same class of primary CTA buttons — same invisibility.
- Hub → Settings: the Accessibility "granted" **status dot never turns green** —
  `.status-dot.granted { background: var(--good); }`.

**Fix sketch:** add `--accent2` and `--good` (light + dark values) to tokens.css.

### 4. ~~Website deployment trap: compact.html now requires tokens.css~~ — RESOLVED

`desktop/compact.html` (the canonical copy) now does
`<link rel="stylesheet" href="tokens.css" />` and deleted its inline token block.
But: `static/tokens.css` **does not exist**, `scripts/sync-compact.sh` **doesn't
copy it**, and `static/compact.html` has **drifted** (the design-pass changes were
never synced). Today the live site serves the old self-contained copy and works;
the moment anyone runs the sync script, the site's /compact.html loses every color
variable (404 on tokens.css) and renders unstyled.

Also: the Google Fonts `<link>` was removed from compact.html but `'Lora', serif`
is still referenced 3× (`.brand`, `#def-why`, `#def-etymology`) — Lora is no
longer loaded anywhere (tokens.css imports only Fraunces + DM Sans), so those
silently fall back to system serif.

**Fix sketch:** make sync-compact.sh copy tokens.css too; run it; either drop the
Lora references or add it to the tokens.css @import.

### 5. ~~Double-tap during an in-flight capture corrupts the expanded/collapsed state~~ — RESOLVED

`expand()` sets `expanded = true`, then `await`s `captureSelection()` (~0.5–1s).
A second double-tap during that window runs `toggle()` → sees `expanded === true`
→ `collapse()` → sets `expanded = false` and snaps the window small. Then the
first expand's continuation runs anyway: sets bounds to EXPANDED, shows and
focuses the window — **panel visibly open while `expanded === false`**. From
there: blur can't collapse it (collapse early-returns), and the next trigger
starts a *new* capture whose synthesized ⌘C lands on Lexio's own focused window.
State soup until something resets.

**Fix sketch:** a generation counter or `capturing` flag — `toggle()` during a
capture should cancel/supersede it, and the continuation should check it's still
the current generation before touching the window.

### 6. ~~Hover-expand has no debounce~~ — RESOLVED (Gemini)

The design pass removed the 80ms hover debounce: `pill.addEventListener('mouseenter',
() => requestExpand())` fires the full pipeline — including **sending a synthesized
⌘C keystroke to the frontmost app** and spawning an osascript context read — every
time the cursor merely passes over the pill. The pill sits bottom-center, directly
in the path to the Dock. Every accidental pass-over = keystroke injection into the
user's app + a capture/read process + focus steal. This also *amplifies bug #1*
(more concurrent captures → more misordered context-ready messages) and produces
the orphaned context reads visible in the log (reads whose results nothing
consumes, from expands where nothing was selected).

**Fix sketch:** restore a debounce (≥150ms), or better: hover only swells the pill,
click/double-tap actually expands (this was DESIGN_REVIEW §3.2's recommendation).

### 7. ~~The 250ms `.capturing` timer races collapse~~ — RESOLVED

In pill.html `expand()`, the `.expanded` class is applied inside a 250ms
`setTimeout`. If the user mouses away (or Esc's) during those 250ms, the collapse
runs first (removes `.expanded`, main snaps bounds to COLLAPSED after 180ms), then
the timer fires and **adds `.expanded` back** — a full-size panel now renders
clipped inside a 44×42 window (a white sliver above the pill), with main and
renderer disagreeing about state until the next trigger.

**Fix sketch:** store the timer, cancel it in `collapse()`; or gate the timer
callback on `body` not having been collapsed since.

### 8. ~~Pill "blob" teleports to the top of the window around expand/collapse~~ — RESOLVED

*Resolved 2026-07-04 as a side effect of Gemini's pill.html redesign.* The pill
and panel used to be two flex siblings inside `.shell`, so an invisible
full-height panel box could push the pill to the top of the window. The new
markup merges them into one `.morph-container` that itself morphs from a 36px
circle to the full panel — `.shell` now has exactly one flex child, so
`justify-content: flex-end` keeps it bottom-anchored at every size. No
teleport possible by construction. Left in the report for the record; original
writeup below.

### 8-original. Pill "blob" teleports to the top of the window around expand/collapse (caught on screen recording)

*Filed 2026-07-04 from a user screen capture.*

**Symptom:** for a split second around collapse, the gradient blob renders far
ABOVE its resting spot — roughly where the top of the panel was — then snaps back
to the bottom. Also occurs (less noticed) during the 250ms pre-expand window.

**Root cause:** `.shell` lays out pill-then-panel in a flex column. The design
pass changed the base `.panel` rule from `flex: 0 0 0; height: 0` to
`flex: 1; height: auto` (the genie transform needs a full-size box to scale).
Consequence: whenever `body` does NOT have `.expanded` while the OS window is
still at the tall EXPANDED bounds, the invisible-but-full-height panel claims all
space below the pill and pushes the pill to the window's TOP edge (~540px above
its resting place). That state exists twice by design:

- **collapse:** `overlay:collapse` removes `.expanded` immediately, but main only
  snaps the window bounds down after `COLLAPSE_MS = 180ms` — the pill fades in at
  the top of a 580px-tall window for those 180ms (exactly the captured frame);
- **expand-with-word:** main snaps bounds to EXPANDED first, and pill.html delays
  adding `.expanded` by 250ms for the `.capturing` pulse — same wrong layout.

**Fix sketch:** take the panel out of layout flow — `position: absolute;
inset: 0` within `.shell` (its `transform-origin: bottom center` already suits
this) — so the pill stays pinned at flex-end bottom regardless of the panel's
box. A transition-delay on the pill's opacity would only mask one direction;
absolute positioning fixes both structurally. Same cluster as #5–#7.

### 9. ~~`fetchDef` has no network timeout~~ — RESOLVED

Once context resolves and the real `/define` request fires, a hung connection
(captive portal, server stall — the 502s seen today were real) leaves the skeleton
loader up forever. There's no `AbortController`, no timeout, no retry. To the user
this is indistinguishable from bug #1 — "it searches indefinitely."

**Fix sketch:** `AbortController` with a ~15s timeout wired into the existing
`showError` path (which already correctly drops direct-mode back to the editor).

### 10. ~~Stale panel state on empty-capture expand~~ — RESOLVED

`collapse()` never resets compact.html, and an expand with nothing selected
(`payload = {}`) injects nothing. So the panel re-opens showing **whatever was on
screen last** — including a stale "Reading context…" (which, combined with #1,
looks permanently stuck) or a stale definition for a word the user looked up an
hour ago.

**Fix sketch:** on expand with an empty payload, inject a lightweight reset (clear
loading/error, show empty state) — or have compact reset itself on a
`document.visibilitychange`-equivalent signal from pill.

---

## P2 — Real bugs, lower blast radius

### 11. ~~Recent list fills with duplicates~~ — RESOLVED

`showResult()` fires the `LEXIO_LOOKUP::` console bridge on **every render**, not
per lookup: cache hits and the Enter-to-reopen shortcut each prepend another copy
of the same word to `recentLookups`. One reading session can push the same word
into Recent five times.
*Fix:* emit the bridge from `fetchDef`'s success path only (post-network), or
dedupe consecutive identical words in main's `overlay:report-lookup` handler.

### 12. ~~Esc doesn't collapse when focus is inside the webview~~ — RESOLVED

pill.html's Esc handler is on *its own* document; once the user clicks into the
lookup panel (the common case — it autofocuses), keystrokes go to the webview and
Esc does nothing. Needs a `before-input-event` listener on the webview's
webContents (or an Esc handler inside compact.html that calls the console bridge).

### 13. ~~Modifier-combo typing triggers the double-tap~~ — RESOLVED

The uiohook handler counts any two ⌃ keydowns within 320ms as a double-tap — but
⌃C followed by ⌃V (or holding ⌃ and tapping it again during shortcut-heavy work in
a terminal/editor) matches too, popping the panel open mid-work. A real double-tap
detector should require the modifier to be pressed and released **bare** (no other
key between down and up) on both taps — this is how Wispr Flow's Fn-Fn behaves.

### 14. ~~Invalid CSS block in compact.html (dark-mode pro chip)~~ — RESOLVED (Gemini)

*Resolved 2026-07-04* — the two selectors are now split into separate,
correctly-formed rules. Original writeup below.

```css
html.dark-theme .pro-chip,
@media (prefers-color-scheme: dark) { html:not(.light-theme) .pro-chip } {
```
An `@media` can't appear inside a selector list — the parser drops the whole rule.
Dark-mode users get the light chip colors (near-invisible text on the chip).

### 15. ~~Legacy `gemini` model value survives in localStorage~~ — RESOLVED

The model picker was rebuilt as Fast/Precise (haiku/sonnet), but a user whose
stored `lexio_compact_model` is `gemini` (the old dropdown) isn't migrated:
`lockFreeModels()` only checks `['sonnet']`, so `model: "gemini"` keeps being sent
to `/define`. Add a migration: anything not in `{haiku, sonnet}` → `haiku`.

### 16. ~~Context read spawns even when it can't be used~~ — RESOLVED

The osascript read starts before we know whether anything was selected; when the
capture comes back empty (`nothing was selected` — every accidental hover), the
read's result is simply never consumed (orphaned processes visible in the log).
Similarly a long-passage capture (token view) never uses the read. Cheap fix: keep
a handle to the child process and kill it when `captureSelection` returns
null/long-text.

### 17. ~~Dark mode: window chrome vs. content mismatch~~ — RESOLVED

tokens.css now has proper dark values and pill.html live-toggles the webview theme
(good!), but the Hub and Onboarding `BrowserWindow`s still hardcode
`backgroundColor: '#f5efe8'` — in dark mode their rounded corners and any repaint
flash show cream around dark content. Same for the static "double-tap **⌘ or ⌃**"
copy in compact.html's empty state (ignores the configured trigger key, unlike
hub's dynamic version).

---

## P3 — Notes / polish

*(Renumbered 2026-07-04 — these previously restarted at 17, colliding with P2's
own #17. Now continuous with the rest of the document: 18–21.)*

18. **Pill is not actually draggable** despite `-webkit-app-region: drag` — the
    `.pill-blobs` child (`no-drag`) covers the entire disc (`inset: -8%`), so
    there's no grabbable area left. Pre-existing, but the comment promises drag.
    *(Superseded in practice: pill.html now has an explicit Cmd/Ctrl+drag
    handler via `overlay:start-drag`, so basic dragging works; still worth a
    real affordance — this is Gemini's #18 in the ownership split below.)*
19. **`collapse()` has no `win` null-guard** on `win.webContents.send` — currently
    safe only because the `closed` handler resets `expanded` first. Fragile.
20. **Onboarding practice step** now receives the trimmed word instead of the full
    selection (`{ text: word }`) — fine today; note if the practice copy ever says
    "select a phrase".
21. **tokens.css `@import` of Google Fonts** means offline users get system-font
    fallbacks everywhere in the chrome; acceptable, but consider bundling the two
    font files at packaging time.

---

## Ownership split

**Gemini (design/interaction judgment):**
- **#3** — add `--accent2` + `--good` to tokens.css (light *and* dark values; it's
  their token sheet, the color choice is aesthetic).
- **#6** — redesign the pill hover interaction (hover = swell only? debounce?).
  Hard engineering constraint from #6's writeup: **hover must never trigger the
  capture pipeline** (synthesized ⌘C / osascript reads) — only click or the
  double-tap may. Behavior choice is theirs within that line.
- **#14** — fix the malformed dark-mode `.pro-chip` CSS block (their segmented
  control, their dark palette).
- **#18** — pill draggability: needs an interaction design, not just CSS (Electron
  drag regions don't deliver reliable clicks, so "draggable AND clickable" needs a
  deliberate affordance — edge ring, modifier-drag, whatever they prefer).
- Sub-decision from **#4**: keep Lora (re-add to the tokens.css @import) or drop
  the three remaining `'Lora'` references. Their typography call; flag the answer
  back so the software side can sync it.

**Software (everything else — correctness, state machine, build/deploy):**
- **#1, #2** — context-delivery race + timeout policy (the P0 pair).
- **#4** — sync-script/tokens.css shipping mechanics (minus the Lora decision).
- **#5, #7, #8** — the state-machine/animation-timing cluster, fixed as one
  refactor (generation counter in main + panel out of layout flow). Gemini's genie
  animation look is preserved; only the mechanics change.
- **#9, #10, #11, #12, #13, #15, #16, #17, #19, #20, #21.**

*(#2's "couldn't read context" note ships functional-but-plain; Gemini can restyle
it in their pass.)*

---

## Suggested attack order

1. #1 + #2 together (they're one subsystem: delivery + timeout policy) — kills the
   reported bug and the silent wrong-definition regression.
2. #3, #4 (30-minute fixes, visibly broken UI / deploy trap).
3. #5, #6, #7, #8 (the state-machine/animation cluster — best fixed as one refactor: a single
   `generation` counter owned by main, checked by every async continuation).
4. #9, #10 (network + stale-state hygiene), then P2 batch.
