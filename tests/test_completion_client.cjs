const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync('finished_good_pack_rfid_scan/public/rfid/client.js', 'utf8');
const code = source.slice(source.indexOf('  const pendingCompletionScans ='), source.indexOf('  const boxStatus ='))
  + source.slice(source.indexOf('  const complete = async'), source.indexOf('  const deleteSession ='))
  + '\nglobalThis.finish = complete;';

function setup() {
  const scans = Array.from({length: 1200}, (_, i) => ({bookingId: 'B', finishedGoodPackDetailId: String(i), rfid: `TAG${i}`}));
  const calls = [], cache = [], elements = new Map(), acknowledged = new Map([['S', new Set(['B|2', 'B|3'])]]);
  const session = {sessionId: 'S', sessionStatus: 'Active', preloadedBookings: [{bookingId: 'B'}],
    scannedItems: scans.slice(0, 2)};
  const ctx = {
    state: {session, completing: true, completionPending: false}, navigator: {onLine: true},
    window: {RfidPhotos: {prepareCompletion: async () => true}}, scanAcknowledgements: acknowledged,
    scansForSession: async () => scans, normalizedRfid: value => String(value || '').toUpperCase(),
    api: async (operation, payload) => {calls.push({operation, payload});
      return operation === 'complete' ? {sessionId: 'S', sessionStatus: 'Completed', totalScannedCount: scans.length} : {};},
    store: {clearScans: async () => {}, put: async (_type, row) => cache.push(row), remove: async () => {}},
    $: id => {if (!elements.has(id)) elements.set(id, {disabled: false, value: id === 'completion-vehicle' ? '51A' : id === 'completion-driver' ? 'Driver' : ''}); return elements.get(id);},
    value: id => ctx.$(id).value, renderCompletionProgress: () => {}, lockCompletionNavigation: () => {},
    loadHome: async () => {}, resetSessionNavigation: () => {}, notice: () => {}, explain: error => {throw error;},
    formatCount: value => String(value),
  };
  vm.createContext(ctx); vm.runInContext(code, ctx);
  return {ctx, calls, cache, scans, acknowledged};
}

(async () => {
  let {ctx, calls, cache, scans, acknowledged} = setup();
  await ctx.finish();
  const batches = calls.filter(call => call.operation === 'sync_scans');
  assert.deepEqual(batches.map(call => call.payload.scans.length), [500, 500, 196]);
  assert.equal(calls.at(-1).operation, 'complete');
  assert.equal(calls.at(-1).payload.scans.length, 0);
  assert.equal(calls.at(-1).payload.compactResult, true);
  assert.equal(acknowledged.get('S').size, 1198);
  assert.equal(cache[0].preloadedBookings[0].bookingId, 'B');
  assert.equal(cache[0].scannedItems.length, scans.length);
  assert.equal(cache[0].sessionStatus, 'Completed');

  ({ctx, calls, acknowledged} = setup());
  let sent = 0;
  const api = ctx.api;
  ctx.api = async (...args) => {
    if (args[0] === 'sync_scans' && ++sent === 2) throw Error('network');
    return api(...args);
  };
  ctx.explain = () => {};
  await ctx.finish();
  assert.equal(calls.filter(call => call.operation === 'sync_scans').length, 1);
  assert.equal(calls.filter(call => call.operation === 'complete').length, 0);
  assert.equal(acknowledged.get('S').size, 502);
  ctx.api = api;
  await ctx.finish();
  assert.equal(calls.filter(call => call.operation === 'complete').length, 1);
  assert.deepEqual(calls.filter(call => call.operation === 'sync_scans').map(call => call.payload.scans.length), [500, 500, 196]);

  ({ctx, calls} = setup());
  const completedApi = ctx.api;
  ctx.api = async (operation, payload) => {
    if (operation === 'sync_scans') throw {code: 'error.session_inactive'};
    return completedApi(operation, payload);
  };
  await ctx.finish();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].operation, 'complete');
  console.log('Completion: sends only pending scans in batches, finalizes once, and retries without duplicates');
})().catch(error => {console.error(error); process.exit(1);});
