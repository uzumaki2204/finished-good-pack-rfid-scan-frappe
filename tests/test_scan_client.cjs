const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('finished_good_pack_rfid_scan/public/rfid/client.js','utf8');
const code=source.slice(source.indexOf('  let scanLookupSession ='),source.indexOf('  const clearScannerCommitTimer ='))+'\nglobalThis.enqueue=enqueueScan;';
function setup(){
 const scans=[],notices=[],timers=[];
 const ctx={window:{setTimeout:fn=>{timers.push(fn);return timers.length;}},state:{session:{sessionId:'S',sessionStatus:'Active',preloadedBookings:[{bookingId:'B',items:[{finishedGoodPackDetailId:'I',rfid:'ABC123',orderNo:'PO',doNo:'DO',dispPackNum:'0001'}]}]}},scanQueue:Promise.resolve(),normalizedRfid:v=>String(v||'').trim().toUpperCase(),scansForSession:async()=>scans.map(x=>x.payload),store:{put:async(t,row)=>scans.push(row)},notice:k=>notices.push(k),renderSession:async()=>{},$:()=>({value:'',focus(){}}),Date};
 vm.createContext(ctx);vm.runInContext(code,ctx);ctx.flush=async()=>{while(timers.length)await timers.shift()();};return {ctx,scans,notices};
}
(async()=>{
 let {ctx,scans,notices}=setup();
 await Promise.all([ctx.enqueue('abc123'),ctx.enqueue('ABC123')]);assert.equal(scans.length,1);assert.equal(notices.length,0);assert.equal(scans[0].payload.finishedGoodPackDetailId,'I');assert.ok(scans[0].payload.scannedAtUtc.endsWith('Z'));
 await ctx.enqueue('UNKNOWN');assert.equal(scans.length,1);assert.equal(notices.length,0);
 ctx.state.completing=true;await ctx.enqueue('ABC123');assert.equal(scans.length,1);
 ctx.state.completing=false;ctx.state.session.sessionStatus='Completed';await ctx.enqueue('ABC123');assert.equal(scans.length,1);
 ({ctx,scans,notices}=setup());ctx.store.put=async()=>{throw Error('disk full')};await ctx.enqueue('ABC123');assert.equal(scans.length,0);assert.equal(notices.at(-1),'error.offline_storage');
 ({ctx,scans,notices}=setup());ctx.state.session.readOnly=true;await ctx.enqueue('ABC123');assert.equal(scans.length,0);
 ({ctx,scans,notices}=setup());let renders=0;ctx.renderSession=async()=>renders++;
 await Promise.all(Array.from({length:300},(_,i)=>ctx.enqueue(i%3 ? 'OUTSIDE-'+i : 'ABC123')));
 assert.equal(scans.length,1);assert.equal(renders,0);await ctx.flush();assert.equal(renders,1);assert.equal(notices.length,0);
 ({ctx,scans,notices}=setup());ctx.state.session.preloadedBookings[0].items.push({...ctx.state.session.preloadedBookings[0].items[0],finishedGoodPackDetailId:'I2'});
 await ctx.enqueue('ABC123');assert.equal(scans.length,0);assert.equal(notices.at(-1),'error.scan_ambiguous_in_plan');
 ({ctx,scans,notices}=setup());
 let reads=0,writes=0,normalizations=0;const normalize=ctx.normalizedRfid;
 ctx.normalizedRfid=v=>{normalizations++;return normalize(v);};
 ctx.state.session.preloadedBookings[0].items=Array.from({length:13000},(_,i)=>({finishedGoodPackDetailId:'I'+i,rfid:'VALID'+i}));
 ctx.scansForSession=async()=>{reads++;return scans.map(x=>x.payload);};
 ctx.store.put=async(t,row)=>{writes++;scans.push(row);};
 await ctx.enqueue('WARMUP-OUTSIDE');normalizations=0;
 const started=performance.now();const tasks=[];
 for(let i=0;i<100000;i++) {tasks.push(ctx.enqueue('OUTSIDE'+i));if(i%100===0)tasks.push(ctx.enqueue('VALID'+(i/100)));}
 await Promise.all(tasks);
 assert.equal(scans.length,1000);assert.equal(writes,1000);assert.equal(reads,1);assert.equal(notices.length,0);
 assert.ok(normalizations<110000,'Lookup must not rescan the plan for every tag');
 console.log(`100,000 outside + 1,000 valid / 13,000 plan: ${(performance.now()-started).toFixed(1)} ms, ${reads} scan read, ${writes} writes`);
 // Replacing the plan invalidates both the lookup and the restored scan cache.
 ctx.state.session={...ctx.state.session,preloadedBookings:[{bookingId:'B',items:[{finishedGoodPackDetailId:'NEW',rfid:'NEW'}]}]};
 await ctx.enqueue('VALID5000');await ctx.enqueue('NEW');assert.equal(scans.length,1001);
 // A failed write is not marked as saved; the same tag can be retried.
 ({ctx,scans,notices}=setup());const put=ctx.store.put;ctx.store.put=async()=>{throw Error('disk');};
 await ctx.enqueue('ABC123');ctx.store.put=put;await ctx.enqueue('ABC123');assert.equal(scans.length,1);
 // Split batched scanner input rather than concatenating separate RFID values.
 ({ctx,scans,notices}=setup());const elements=new Map();
 ctx.$=id=>{if(!elements.has(id))elements.set(id,{value:'',hidden:id==='item-detail-modal',open:false});return elements.get(id);};
 ctx.window.clearTimeout=()=>{};ctx.scannerCommitTimer=null;ctx.lastFocusedRfidKeyAt=0;ctx.focusedRfidKeyBurst=0;ctx.SCAN_COMMIT_DELAY_MS=60;
 vm.runInContext(source.slice(source.indexOf('  const clearScannerCommitTimer ='),source.indexOf('  const shouldCaptureScannerKeys ='))+'\nglobalThis.append=appendScannerText;',ctx);
 ctx.append('OUTSIDE\r\nABC123\tOUTSIDE2\nABC123\n');await ctx.scanQueue;
 assert.equal(scans.length,1);assert.equal(notices.length,0);assert.equal(ctx.$('rfid-input').value,'');
 console.log('Client scan queue: valid scan, duplicate, unknown RFID, completion guard and storage failure passed');
})().catch(e=>{console.error(e);process.exit(1)});
