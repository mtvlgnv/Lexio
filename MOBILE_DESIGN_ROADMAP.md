# Lexio Website — Mobile Design Roadmap

Started 2026-07-12. Companion to `DESIGN_ROADMAP.md` (which is Lexio
*Glance*, the Mac app) — this file tracks *mobile web* bugs on
lexio.site. Same conventions: items marked **observed** were seen and
measured in a real mobile viewport (not guessed from reading CSS); items
marked **audit** are suspected and need a look before fixing. Keep this
list honest: add the file:line and the actual measured numbers, not "this
looks off."

Scope: `static/index.html` (marketing landing, `body.landing-page`) and
`static/app.js` / `static/app.css` (shared with `/app`, the tool page).
Tested at 375×812 and 390×844 (iPhone SE / iPhone 14 class viewports) via
the Claude Preview tool's mobile emulation against a local server.

## How these were found (so the next agent trusts — or re-checks — them)

Both items below were confirmed with real `getBoundingClientRect()` /
`getComputedStyle()` measurements taken live against the rendered page,
not just eyeballed from a screenshot. A screenshot showed a *third*
apparent bug — a ~17px sliver of page background visible on the left
edge of both the mobile nav drawer (`#menu-dropdown`) and the sign-in
modal — but it did NOT reproduce when measured: the sign-in modal's own
overlay element measured a perfect `x:0, y:0, width:390, height:844`
(exactly the viewport, no gap) even though the screenshot still showed
one. That means the sliver is a capture/compositing artifact of the
preview tool itself, not a real CSS bug — **don't re-file it** unless you
reproduce it with an actual measurement (rect/computed style), not just a
screenshot, ideally on a real device or real mobile Chrome DevTools
emulation rather than this harness.

## P0 — actively hurting

1. **Landing-page header overlaps the H1 by 44px on mobile** (observed,
   measured). `static/app.css:1451` — `body.landing-page header` is
   `position: absolute; top: 16px; height: 60px` (the "Clay-style pill"
   floating header), so it's removed from document flow entirely. The
   hero's own top padding (`static/app.css:3333`,
   `@media (max-width: 760px) { .lp-hero { padding: 40px 20px 32px; } }`)
   doesn't reserve enough clearance for it. Measured live at 390×844:
   header renders at `top:16, bottom:76`; the H1 renders starting at
   `top:32` — a **44px overlap** (the header pill sits directly on top of
   the first line of "Understand languages the way they're really
   used."). This is the literal bug the founder reported after a fresh
   DMG install ("tıne way tney're" — the ascenders of the first visible
   line are cut off behind the header).
   **Fix direction:** increase `.lp-hero`'s mobile `padding-top` enough to
   clear `header.bottom` with a visible gap — the header is 60px tall
   starting 16px down, so padding-top needs to be at least ~90-96px, not
   40px. (Don't just hardcode a bigger number and call it done — the
   pill's height can change if nav content wraps to two lines on very
   narrow phones; consider either measuring header height in JS and
   setting a CSS custom property, or building in enough margin that it's
   safe across realistic header heights.)
   **Verify:** load `/` at 375×812 and 390×844, screenshot AND measure
   `header.getBoundingClientRect().bottom` vs
   `document.querySelector('.lp-hero h1').getBoundingClientRect().top` —
   the second must be ≥ the first plus a comfortable gap (16-24px), not
   just non-negative.

## P1 — makes it feel unfinished

2. **Hero rotator ("Built for people reading…") breaks into a disconnected
   layout on mobile** (observed, measured). `static/app.css:1675` —
   `.lp-hero-rotator { display: flex; ... }` lays the static lead text
   ("Built for people reading") and `.lp-hero-rotator-words`
   (`static/app.css:1685`, fixed `width: 180px`) side by side as flex
   children with no mobile override. At 335-390px content width, giving
   180px to the rotating word leaves too little room for the lead text,
   which wraps to two lines while the rotating word ends up floating to
   the right, visually disconnected from the sentence it's supposed to
   complete (e.g. "Built for people / reading" on two lines, then
   "research papers" sitting alone to the right instead of reading as
   "Built for people reading research papers"). Same root component that
   B18 i18n'd this session (`data-i18n="heroRotatorWord1-8"` etc,
   `static/index.html`) — no i18n issue here, purely a layout one.
   **Fix direction:** add a `@media (max-width: 760px)` (or whatever
   matches the existing hero breakpoint at `static/app.css:3327`) rule
   that switches `.lp-hero-rotator` to `flex-direction: column` (or
   `display: block`) so the lead text and the rotating word stack
   vertically instead of competing for horizontal space. Check the
   `.lp-hero-rotator-words::before` pseudo-element (`static/app.css:1696`)
   too — it may be positioning/sizing assumptions tied to the row layout.
   **Verify:** at 375-390px width, the rendered lead text should not wrap
   mid-phrase, and the rotating word should read as a continuation of the
   sentence, not a disconnected fragment. Screenshot at both the widest
   rotator word ("to finally get fluent") and the narrowest ("work
   emails") to make sure the layout doesn't jump/reflow oddly as the
   rotation cycles (`static/app.css:1714+`, `:nth-child` animation
   delays).

## Not filed (checked, came back clean)

- Mobile hamburger menu (`#menu-dropdown` full-screen nav) — content,
  spacing, and close button all correct at 375/390px. The left-edge
  sliver visible in screenshots is the tooling artifact described above,
  not a real bug — see "How these were found."
- `/app` (the tool page) — header does NOT use the absolute "pill" header
  (that's `body.landing-page`-only), so no overlap there. Ran a real
  lookup end-to-end on mobile (sample text → tap "adventitious" →
  definition panel) and it rendered cleanly: word tokens, action buttons
  (Copy/Collect/Link/Share/Try again), and all definition sections fit
  the viewport with no overflow or collision.
- Pricing cards (Free/Pro) and the Monthly/Family billing tabs — stack
  and wrap correctly at mobile widths, no truncation on "4 SEATS" badge.
- The `.word-token.in-sentence` background highlight that lights up every
  word in the active sentence once you've looked one up — this looked
  like a stuck-hover bug on first glance but is intentional
  (`static/app.css:550`, gives the whole sentence a subtle "this is what
  we're explaining" tint) and isn't mobile-specific — same behavior on
  desktop. Not a bug.
- No JS console errors on landing-page or `/app` load at mobile
  viewport widths.

## Working notes

- Measure, don't just screenshot. This file exists because a screenshot
  alone would have shipped a third "bug" (the sliver) that a real
  `getBoundingClientRect()` check disproved. Screenshots are for
  *finding* candidates; `preview_eval` + `getBoundingClientRect()` /
  `getComputedStyle()` is for *confirming* them before writing them down.
- Test both `/` (landing, `body.landing-page`) and `/app` (tool,
  `body.tool-page`) separately — they share `app.css` but the landing
  page has its own header/hero treatment (`body.landing-page header`,
  `.lp-*` classes) that the tool page doesn't use at all.
- After any fix here: also spot-check the equivalent desktop-width
  layout (≥960px) didn't regress — several of these rules are inside
  `@media (max-width: 760px)` / `900px` / `960px` blocks with layered,
  slightly different breakpoints, easy to fix mobile and break a
  1024px-wide tablet view without noticing.
