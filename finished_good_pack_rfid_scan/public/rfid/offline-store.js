(() => {
  'use strict';
  const NAME = 'finished-good-rfid-v1';
  const open = () => new Promise((resolve, reject) => {
    const request = indexedDB.open(NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore('sessions', { keyPath: 'sessionId' });
      db.createObjectStore('scans', { keyPath: 'key' });
      db.createObjectStore('meta');
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const transaction = async (table, mode, action) => {
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(table, mode);
        const request = action(tx.objectStore(table));
        let result;
        request.onsuccess = () => { result = request.result; };
        request.onerror = () => reject(request.error);
        tx.oncomplete = () => resolve(result);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    } finally { db.close(); }
  };
  const put = (table, value, key) => transaction(table, 'readwrite', store => key === undefined ? store.put(value) : store.put(value, key));
  const get = (table, key) => transaction(table, 'readonly', store => store.get(key));
  const all = table => transaction(table, 'readonly', store => store.getAll());
  const remove = (table, key) => transaction(table, 'readwrite', store => store.delete(key));
  const scans = async sessionId => (await all('scans')).filter(scan => scan.sessionId === sessionId).map(scan => scan.payload);
  const clearScans = async sessionId => {
    const rows = await all('scans');
    for (const row of rows.filter(scan => scan.sessionId === sessionId)) await remove('scans', row.key);
  };
  window.RfidOffline = { put, get, all, remove, scans, clearScans };
})();
