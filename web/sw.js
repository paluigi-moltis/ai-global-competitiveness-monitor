// Service worker — Network First (per pwa-caching-strategy), with:
// - Range requests and Parquet files bypassing the SW entirely (DuckDB-Wasm
//   uses HTTP Range; SWs handle 206 poorly)
// - meta.json fetched with no-store by the app (double protection)
// - cache version bump invalidates old caches on deploy
const CACHE_NAME = 'ai-monitor-v1';
const APP_SHELL = [
  './', './index.html', './capabilities.html', './adoption.html',
  './css/style.css', './js/common.js', './js/app.js',
  './js/capabilities.js', './js/adoption.js', './manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
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

self.addEventListener('fetch', (event) => {
  const url = event.request.url;

  // Bypass SW for Range requests and Parquet data (DuckDB-Wasm needs 206s)
  if (event.request.headers.has('range') || url.endsWith('.parquet')) {
    return;
  }

  // CDN assets: network first, cache fallback
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
          return networkResponse;
        }
        const responseToCache = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseToCache));
        return networkResponse;
      })
      .catch(() => caches.match(event.request))
  );
});
