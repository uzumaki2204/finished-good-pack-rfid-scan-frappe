const fs = require('node:fs');
const assert = require('node:assert/strict');

const source = fs.readFileSync('finished_good_pack_rfid_scan/public/rfid/client.js', 'utf8');
const init = source.slice(source.indexOf('  const init = async'), source.indexOf('  window.RfidPrepareUpdate ='));
const complete = source.slice(source.indexOf('  const complete = async'), source.indexOf('  const deleteSession ='));

assert.doesNotMatch(init, /syncScans|sync_scans/, 'Active scanning must not upload in background');
assert.doesNotMatch(source, /const syncScans =/, 'No background upload path should remain');
assert.match(complete, /api\('sync_scans'/, 'Completion must upload scans before finalizing');
console.log('Scan sync: no background upload; completion retains its upload path');
