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
- ~~Save button did nothing after the first lookup ever rendered~~ —
  updateSaveBtn() did `btn.onclick = null`, which permanently detaches an
  element from its inline `onclick="..."` HTML attribute; every click
  since app launch called nothing. Fixed with a plain state flag instead
  of touching `.onclick` (2026-07-09). **Lesson: a real `.click()` +
  state-diff test caught this; DOM-presence checks alone did not.**

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
2. ~~def-actions row overflow~~ ✅ DONE 2026-07-10 — split into two rows
   (Save/Copy/New lookup, then language select right-aligned below).
   Room for P1-4's "Think deeper" button in row 1.
3. ~~Two different loading layouts~~ ✅ DONE 2026-07-10 — unified into one
   `renderLoading()` component (title + optional thumb + skeleton lines)
   used by both text- and image-mode lookups. Also fixed a real bug found
   along the way: `lexioImageInput()`'s loading text used `--text-secondary`,
   a CSS variable that doesn't exist in tokens.css — it was silently
   falling back to the default color.

## P1 — makes it feel unfinished

4. ~~Word Bank rows: no hover state, low delete affordance~~ ✅ DONE
   2026-07-10 — row hover background, delete × fades in on hover/focus.
5. ~~Stat cards are typographically flat~~ ✅ DONE 2026-07-10 — streak
   card (both Home and Account) gets accent border/background + a 🔥
   when the streak is ≥2 days.
6. ~~Sidebar footer tip is cramped~~ ✅ DONE 2026-07-10 — added top
   padding and line-height.
7. **Onboarding permission step density** (observed). Two status rows +
   two buttons + stale-hint paragraph is a wall. Restructure to match the
   Hub Settings pattern: one row per permission with a trailing button,
   and reveal the troubleshooting hint only after a failed poll cycle.
8. **Panel gradient header vs. content hierarchy** (observed in captures).
   The traffic-light-style header bar with the wordmark eats vertical
   space in a 580px panel. Consider collapsing it to a slim drag handle
   once a definition is showing.

## P2 — polish

9. ~~Capture thumbnail corners/borders~~ AUDITED 2026-07-10, already
   consistent — nested elements (thumbnails, buttons) use 6-8px,
   containers use 12px, a coherent scale. No change needed.
10. ~~Focus states / keyboard affordances~~ ✅ DONE 2026-07-10 — DOM
    tab order already matched the intended priority; added visible
    accent-at-40% focus rings (browser defaults were invisible against
    the panel's warm surfaces).
11. ~~Pill tooltip copy~~ ✅ DONE 2026-07-10 — now says "Click: open
    panel · Double-tap ⌃: define the word at your pointer".
12. **Marketing site: hero rotator + trust badges are English-only** on
    localized UIs (static/index.html hardcodes them; the i18n pass
    covered `data-i18n` keys only). Either i18n-ify the rotator items or
    accept EN as deliberate.
13. ~~App icon in the Dock~~ N/A 2026-07-10 — the Dock icon was removed
    entirely (see the P0 regression fix in ROADMAP.md: having one broke
    setVisibleOnAllWorkspaces across Spaces/full-screen apps). No Dock
    icon means nothing to audit here anymore.

14. ~~Dead legacy Electron entry points still shipped~~ ✅ DONE
    2026-07-10 — confirmed `main-app.js` was unsigned (`identity: null`,
    never notarized) and untouched since April; the live site's download
    modal offers only Lexio Glance now (the "two download options" era
    ended). Deleted `main.js`, `main-app.js`, `electron-builder-app.json`,
    `scripts/after-sign.js`, and the now-orphaned `start-app`/`dist-app`
    npm scripts.

## Working notes

- Verify visually, not just via DOM: the `.hidden` bug shipped past DOM
  checks and was caught only by a pixel capture. Use the lexio-ocr
  binary spawned from bash (it sees real pixels, and excludes nothing
  when run without --exclude-window) to screenshot Electron windows.
- After any compact.html change: `bash desktop/scripts/sync-compact.sh`.
