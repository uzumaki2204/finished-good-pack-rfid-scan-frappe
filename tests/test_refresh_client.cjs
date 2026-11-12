const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('finished_good_pack_rfid_scan/public/rfid/client.js','utf8');
const code = source.slice(source.indexOf('  const hasCartonMismatch'), source.indexOf('  const init = async')) + '\nglobalThis.refresh = refreshSession;';
function setup(response, failStorage=false) {
  const booking = {bookingId:'B',planVersion:'old',headerPlannedCartonCount:2,headerActualCartonCount:1,items:[{finishedGoodPackDetailId:'I',rfid:'R'}]};
  const state = {device:{id:'D'},session:{sessionId:'S',sessionStatus:'Active',preloadedBookings:[booking]}};
  const elements = new Map();
  const ctx = { state, navigator:{onLine:true}, document:{hidden:false,activeElement:null},
    $:id=>{if(!elements.has(id)) elements.set(id,{hidden:id==='item-detail-modal',value:'',open:false});return elements.get(id);},
    api:async()=>typeof response==='function'?response(ctx):response,
    scanQueue:Promise.resolve(),renderScanMode(){},lockCompletionNavigation(){},
    store:{put:async(t,s)=>{if(failStorage)throw Error('disk full');ctx.saved=structuredClone(s);}},
    renderSession:async()=>{ctx.renders++;},notice(){},explain(){ctx.errors++;},
    window:{scrollX:0,scrollY:12,scrollTo(){}},renders:0,errors:0,Map,Set,
  };
  vm.createContext(ctx);vm.runInContext(code,ctx);return ctx;
}
const patch={baseVersion:'old',patch:{metadata:{bookingId:'B',planVersion:'new',plannedBoxCount:3},remove:['I'],upsert:[{finishedGoodPackDetailId:'J',rfid:'NEW'}]}};
(async()=>{
  let c=setup({hasChanges:false});await c.refresh({automatic:true});assert.equal(c.renders,0);assert.equal(c.saved,undefined);
  c=setup(patch);await c.refresh();assert.equal(c.state.session.preloadedBookings[0].items[0].rfid,'NEW');assert.equal(c.saved.preloadedBookings[0].planVersion,'new');assert.equal(c.renders,1);
  c=setup(patch,true);await c.refresh();assert.equal(c.state.session.preloadedBookings[0].planVersion,'old');assert.equal(c.renders,0);assert.equal(c.errors,1);
  c=setup(ctx=>{ctx.state.session.sessionStatus='Completed';return patch;});await c.refresh();assert.equal(c.saved,undefined);
  c=setup(ctx=>{ctx.state.session={sessionId:'OTHER',sessionStatus:'Active'};return patch;});await c.refresh();assert.equal(c.saved,undefined);
  c=setup(patch);c.$('rfid-input').value='typing';await c.refresh();assert.equal(c.saved,undefined);
  let release;c=setup(()=>new Promise(r=>release=r));const first=c.refresh();assert.equal(c.state.refreshing,undefined);assert.equal(c.state.refreshRequest,true);await c.refresh();release({});await first;
  c=setup(patch);c.navigator.onLine=false;await c.refresh();assert.equal(c.saved,undefined);
  c=setup(patch);c.state.completing=true;await c.refresh();assert.equal(c.saved,undefined);
  console.log('9 client refresh scenarios passed');
})().catch(e=>{console.error(e);process.exit(1)});
