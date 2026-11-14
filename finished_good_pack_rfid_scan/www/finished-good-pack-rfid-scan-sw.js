/* Cache only this app shell. API data and IndexedDB are never touched. */
const CACHE = 'finished-good-pack-rfid-scan-v29';
const PAGE = '/finished-good-pack-rfid-scan';
const fresh = url => fetch(url, {cache: 'no-store'});
const assetUrl = value => {
  try {const url = new URL(value, self.location.origin);return url.origin === self.location.origin && url.pathname.startsWith('/assets/') ? url.href : null;}
  catch {return null;}
};
const cacheShell = async (extra = []) => {
  const page = await fresh(PAGE);
  if (!page.ok) throw Error('Shell unavailable');
  const html = await page.clone().text();
  const assets = [...new Set([...extra, ...Array.from(html.matchAll(/(?:src|href)=["']([^"']+)["']/g), m => m[1])].map(assetUrl).filter(Boolean))];
  // Fetch the whole bundle before replacing the offline entry page.
  const responses = await Promise.all(assets.map(async url => {
    const response = await fresh(url);if (!response.ok) throw Error('Asset unavailable');return [url,response];
  }));
  const cache = await caches.open(CACHE);
  await Promise.all(responses.map(([url,response]) => cache.put(url,response)));
  await cache.put(PAGE,page);
};
self.addEventListener('install', event => {event.waitUntil(cacheShell().then(() => self.skipWaiting()));});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('finished-good-pack-rfid-scan-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('message', event => {
  if (event.data?.type === 'CACHE_SHELL' && Array.isArray(event.data.assets)) event.waitUntil(cacheShell(event.data.assets).catch(() => {}));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;
  const navigation = event.request.mode === 'navigate' && url.pathname === PAGE;
  if (!navigation && !url.pathname.startsWith('/assets/')) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(event.request, {cache:'no-store'});
      if (!response.ok) throw Error('Network response unavailable');
      if (!navigation) await cache.put(event.request,response.clone());
      return response;
    } catch {
      // Exact URL, including version: never substitute another release's JS/CSS.
      return await cache.match(navigation ? PAGE : event.request) || new Response('Offline asset unavailable', {status:503});
    }
  })());
});
