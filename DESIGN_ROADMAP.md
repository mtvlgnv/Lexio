# Lexio Glance — Design Roadmap (ASAP fixes)

Started 2026-07-09. Companion to ROADMAP.md — this file tracks *design*
debt: visual bugs, inconsistencies, and polish the product needs soon.
Items marked **observed** were seen in real captures/screenshots; items
marked **audit** are suspected and need a look before fixing. Keep this
list honest: add a screenshot path or a file:line when adding items.

Design system ground truth: `desktop/tokens.css` (oklch palette — accent
was softened from chroma 0.22 to 0.13 terracotta on 2026-07-09; keep new
UI in that register), Fraunces for display type, DM Sans for UI.

## Fixed already (for context on the bar we're setting)

- ~~Vivid neon accent~~ → muted terracotta across both themes (2026-07-09).
- ~~home.html missing `.hidden` class~~ — signed-in AND signed-out account
  states rendered simultaneously (2026-07-09).
- ~~Empty-state ornament showed ⌘ while the trigger text said ⌃~~ — glyph
  now mirrors the configured trigger (compact.html, 2026-07-09).
- ~~Pill click captured a screenshot of the pill itself~~ — click now opens
  the manual panel; lookups belong to the double-tap (2026-07-09).

## P0 — actively hurting

1. **Dark-mode audit of every new surface** (audit). tokens.css has a full
   dark palette, but home.html, the def-capture thumbnail border, the
   lang-select, and the onboarding permission rows were built and verified
   in light mode only. Check `prefers-color-scheme: dark` +
   `.dark-theme` for: contrast of `.plan-chip`, `.stat` cards, `#lang-select`
   text, capture-thumb border, Home hint-cards. The panel's webview gets
   theme from pill.html's `matchMedia` — home.html has no equivalent wiring
   for its `dark-theme`/`light-theme` root classes (check whether it relies
   purely on the media query — the `:root:not(.light-theme)` rule should
   cover it, but verify visually).
2. **def-actions row overflow** (observed risk, compact.html:~408). The row
   now holds Save + Copy + New lookup + the language select — at 460px
   panel width with a long language name it's tight, and P1-4's "Think
   deeper" button will not fit. Design a two-row layout or an overflow
   menu BEFORE adding the next button.
3. **Two different loading layouts** (observed). Text lookups show a bare
   skeleton with the word as title; screen lookups show "Asking Lexio…" +
   capture thumb + skeleton. Unify into one loading component (the image
   variant is the better one — adopt its structure everywhere).

## P1 — makes it feel unfinished

4. **Word Bank rows: no hover state, low delete affordance** (observed,
   home.html `.wb-entry`). Add row hover background; make the × appear on
   hover (macOS-native pattern) instead of always-visible.
5. **Stat cards are typographically flat** (observed). The three Home/
   Account cards are identical boxes; the primary stat (streak) deserves
   visual priority — consider the accent color or a small flame/dot only
   on the streak card when it's alive (≥2 days).
6. **Sidebar footer tip is cramped** (observed, home.html `.side-foot`).
   The "Point at a word · double-tap ⌃" line wraps awkwardly at min window
   width. Give it line-height and margin, or fold it into an empty-state-
   only hint.
7. **Onboarding permission step density** (observed). Two status rows +
   two buttons + stale-hint paragraph is a wall. Restructure to match the
   Hub Settings pattern: one row per permission with a trailing button,
   and reveal the troubleshooting hint only after a failed poll cycle.
8. **Panel gradient header vs. content hierarchy** (observed in captures).
   The traffic-light-style header bar with the wordmark eats vertical
   space in a 580px panel. Consider collapsing it to a slim drag handle
   once a definition is showing.

## P2 — polish

9. **Capture thumbnail corners/borders** vs. panel radius consistency
   (8px img inside 12px+ panel sections — pick one radius scale:
   4/8/12).
10. **Focus states / keyboard affordances** (audit): tab order in the
    panel (Save → Copy → New lookup → lang), visible focus rings using
    the accent at 40% — currently browser defaults.
11. **Pill tooltip copy**: still "Click or double-tap ⌃ to open Lexio
    Glance" — click and double-tap now do DIFFERENT things; tooltip
    should say so ("Click: open panel · double-tap ⌃: define word at
    pointer").
12. **Marketing site: hero rotator + trust badges are English-only** on
    localized UIs (static/index.html hardcodes them; the i18n pass
    covered `data-i18n` keys only). Either i18n-ify the rotator items or
    accept EN as deliberate.
13. **App icon in the Dock** (audit): now that the Dock icon is
    intentional, confirm build/icon.icns reads well at 32px (it was
    designed for a menu-bar-only app).

## Working notes

- Verify visually, not just via DOM: the `.hidden` bug shipped past DOM
  checks and was caught only by a pixel capture. Use the lexio-ocr
  binary spawned from bash (it sees real pixels, and excludes nothing
  when run without --exclude-window) to screenshot Electron windows.
- After any compact.html change: `bash desktop/scripts/sync-compact.sh`.
