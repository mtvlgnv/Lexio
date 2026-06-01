// Lexio service worker — minimal stale-while-revalidate cache for the
// landing-page shell. Conservative on purpose: only the most stable static
// assets are cached, never API responses. Network is always the source of
// truth for /api, /define, /wordbank, /stripe, /family, /recap.

const CACHE_NAME = 'lexio-shell-v2';
const SHELL = [
  '/',
  '/favicon-32.png?v=2',
  '/favicon-180.png?v=2',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        SHELL.map((url) =>
          fetch(url, { cache: 'reload' })
            .then((r) => (r.ok ? cache.put(url, r) : null))
            .catch(() => null)
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-only paths — never cache responses for these.
const BYPASS = [
  /^\/api\//,
  /^\/define\b/,
  /^\/fetch-text\b/,
  /^\/wordbank\b/,
  /^\/stripe\b/,
  /^\/auth\b/,
  /^\/admin\b/,
  /^\/ocr\b/,
  /^\/family\b/,
  /^\/recap\b/,
  /^\/stats\b/,
];

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (BYPASS.some((re) => re.test(url.pathname))) return;

  // HTML documents (navigations) are NETWORK-FIRST: always try to serve the
  // freshest page so a deploy is visible immediately, falling back to cache
  // only when offline. Stale-while-revalidate would leave the page one
  // version behind on every update — that's what we're avoiding here.
  const isDocument = req.mode === 'navigate' || req.destination === 'document';
  if (isDocument) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((c) => c || caches.match('/')))
    );
    return;
  }

  // Stale-while-revalidate for the small static shell only (favicons, etc.).
  event.respondWith(
    caches.match(req).then((cached) => {
      const networkFetch = fetch(req)
        .then((res) => {
          if (res && res.ok && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || networkFetch;
    })
  );
});
