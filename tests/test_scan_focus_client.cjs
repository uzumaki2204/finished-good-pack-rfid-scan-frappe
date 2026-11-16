const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync('finished_good_pack_rfid_scan/public/rfid/client.js', 'utf8');
const code = 'let scanMetrics=null,scanMetricFrame=null,manualScanScrollY=null;'
  + source.slice(source.indexOf('  const boxKey ='), source.indexOf('  const renderCompletionProgress ='))
  + '\nglobalThis.focusRfid=focusRfidInput;globalThis.resizeScan=onScanViewportResize;'
  + 'globalThis.setManualScroll=value=>{manualScanScrollY=value;};';

const frames = [], focusCalls = [], elements = new Map();
const ctx = {
  state: {session: {sessionStatus: 'Active'}, scanPaused: false, refreshing: false, completing: false, completionPending: false},
  document: {hidden: false, body: {}, activeElement: null},
  window: {scrollX: 0, scrollY: 40, innerHeight: 800, visualViewport: {height: 500, offsetTop: 0},
    requestAnimationFrame: fn => frames.push(fn), scrollTo(x, y) {this.scrollX = x; this.scrollY = y;}},
  $: id => {
    if (!elements.has(id)) elements.set(id, {hidden: id === 'item-detail-modal', open: false, style: {},
      focus(options) {focusCalls.push(options); ctx.document.activeElement = this; ctx.window.scrollY = 120;}});
    return elements.get(id);
  },
};
vm.createContext(ctx);
vm.runInContext(code, ctx);
ctx.document.activeElement = ctx.document.body;
ctx.focusRfid();
assert.equal(focusCalls.length, 1);
assert.equal(focusCalls[0].preventScroll, true);
assert.equal(ctx.window.scrollY, 40);
ctx.state.scanPaused = true;
ctx.document.activeElement = ctx.document.body;
ctx.focusRfid();
assert.equal(focusCalls.length, 1);
ctx.state.scanPaused = false;
ctx.document.activeElement = ctx.$('rfid-input');
ctx.setManualScroll(40);
ctx.resizeScan();
assert.equal(ctx.$('scan-dock').style.bottom, '300px');
ctx.window.scrollY = 120;
frames.shift()();
assert.equal(ctx.window.scrollY, 40);
console.log('Scan focus: guarded focus, scroll preservation and keyboard viewport offset passed');
