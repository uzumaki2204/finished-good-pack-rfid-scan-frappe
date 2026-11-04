/* Same-origin tablet shell only. API and SOAP data are never service-worker cached. */
const CACHE = 'finished-good-pack-rfid-scan-v6';
const PAGE = '/finished-good-pack-rfid-scan';
const ASSETS = [
  PAGE,
  '/assets/finished_good_pack_rfid_scan/rfid/i18n.js',
  '/assets/finished_good_pack_rfid_scan/rfid/offline-store.js',
  '/assets/finished_good_pack_rfid_scan/rfid/client.js',
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('finished-good-pack-rfid-scan-') && key !== CACHE).map(key => caches.delete(key)))),
    self.clients.claim(),
  ]));
});
self.addEventListener('message', event => {
  if (event.data?.type !== 'CACHE_SHELL' || !Array.isArray(event.data.assets)) return;
  const assets = event.data.assets.filter(value => {
    try { const url = new URL(value, self.location.origin); return url.origin === self.location.origin && url.pathname.startsWith('/assets/'); }
    catch { return false; }
  });
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(assets)));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate' && url.pathname === PAGE) {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok) caches.open(CACHE).then(cache => cache.put(PAGE, response.clone()));
      return response;
    }).catch(() => caches.match(PAGE)));
    return;
  }
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(caches.match(event.request, { ignoreSearch: true }).then(cached => cached || fetch(event.request).then(response => {
      if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
      return response;
    })));
  }
});
