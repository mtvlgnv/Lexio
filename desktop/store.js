/**
 * Minimal local persistence for Lexio Glance — onboarding state, auth,
 * recent lookups, settings. No electron-store dependency: this data is
 * tiny and written rarely (once at first launch, once on sign-in, once on
 * a settings change), so a plain synchronous JSON file is simpler than
 * pulling in a library for it.
 */
const { app } = require('electron');
const fs = require('fs');
const path = require('path');

const DEFAULTS = {
  onboardingComplete: false,
  onboardingAppVersion: 0,              // bumped when onboarding content changes
  auth: null,                          // { token, user } once signed in
  recentLookups: [],                   // { word, at } — newest first (Hub, later)
  lookupDays: {},                      // { 'YYYY-MM-DD': count } — local streak/stats material
  settings: { launchAtLogin: false, doubleTapKey: 'ctrl', shareAnonymousStats: true },
  // B4/P1-5 Phase 1.5: the Home-tab profile-interview card is shown once
  // after real usage (5 saves or 15 lookups) — this flag makes "dismiss"
  // mean "never shown again", whether the user answered or skipped it.
  profileInterviewDismissed: false,
  // B15: random anonymous id for the desktop analytics (lib/analytics.js)
  // — generated once on first capture, never a machine identifier.
  analyticsId: null,
};

function storePath() {
  return path.join(app.getPath('userData'), 'lexio-store.json');
}

let cache = null;

function load() {
  if (cache) return cache;
  try {
    const raw = fs.readFileSync(storePath(), 'utf8');
    cache = { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    cache = { ...DEFAULTS };
  }
  return cache;
}

function persist() {
  try {
    fs.mkdirSync(path.dirname(storePath()), { recursive: true });
    fs.writeFileSync(storePath(), JSON.stringify(cache, null, 2));
  } catch (err) {
    console.error('[store] failed to persist:', err);
  }
}

function get() {
  return load();
}

// Shallow merge — callers pass only the top-level keys they're changing.
function set(patch) {
  load();
  cache = { ...cache, ...patch };
  persist();
  return cache;
}

module.exports = { get, set };
