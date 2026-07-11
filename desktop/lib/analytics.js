/**
 * B15: privacy-respecting desktop analytics. Same PostHog EU project the
 * website already uses (static/index.html) — the project API key is a
 * public write-only ingestion key, safe to embed the same way it already
 * is client-side. Main-process only, per design: no renderer ever talks
 * to PostHog directly (compact.html's CSP is connect-src 'self' anyway).
 *
 * distinct_id is a random, anonymous id generated once and stored in
 * store.js — never a machine serial or anything identifying. Every
 * capture call is a no-op if the user has turned off
 * settings.shareAnonymousStats (default true, an honest opt-out, not
 * opt-in-by-dark-pattern).
 */
const crypto = require('crypto');
const { PostHog } = require('posthog-node');
const store = require('../store');

const POSTHOG_KEY = 'phc_ApmyYpyviPs6Cuwakxp6XbYgMo7GkS6UxatRCucEhRGT';
const POSTHOG_HOST = 'https://eu.i.posthog.com';

let client = null;

function ensureClient() {
  if (!client) {
    client = new PostHog(POSTHOG_KEY, { host: POSTHOG_HOST, flushAt: 1, flushInterval: 0 });
  }
  return client;
}

function getOrCreateAnalyticsId() {
  const s = store.get();
  if (s.analyticsId) return s.analyticsId;
  const id = crypto.randomBytes(16).toString('hex');
  store.set({ analyticsId: id });
  return id;
}

function isEnabled() {
  return store.get().settings?.shareAnonymousStats !== false;   // default ON
}

/**
 * event: string; properties: plain object, NEVER lookup content (no
 * words, no context text, no screenshots) — outcome only (e.g. success:
 * true/false).
 */
function capture(event, properties = {}) {
  if (!isEnabled()) return;
  try {
    ensureClient().capture({
      distinctId: getOrCreateAnalyticsId(),
      event,
      properties: { ...properties, app_version: require('../package.json').version },
    });
  } catch (err) {
    console.warn('[analytics] capture failed:', err.message);
  }
}

async function shutdown() {
  if (client) await client.shutdown().catch(() => {});
}

module.exports = { capture, shutdown, isEnabled };
