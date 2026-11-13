const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('finished_good_pack_rfid_scan/public/rfid/client.js','utf8');
const code=source.slice(source.indexOf('  const addScan ='),source.indexOf('  const clearScannerCommitTimer ='))+'\nglobalThis.enqueue=enqueueScan;';
function setup(){
 const scans=[],notices=[];
 const ctx={state:{session:{sessionId:'S',sessionStatus:'Active',preloadedBookings:[{bookingId:'B',items:[{finishedGoodPackDetailId:'I',rfid:'ABC123',orderNo:'PO',doNo:'DO',dispPackNum:'0001'}]}]}},scanQueue:Promise.resolve(),normalizedRfid:v=>String(v||'').trim().toUpperCase(),scansForSession:async()=>scans.map(x=>x.payload),store:{put:async(t,row)=>scans.push(row)},notice:k=>notices.push(k),renderSession:async()=>{},$:()=>({value:'',focus(){}}),Date};
 vm.createContext(ctx);vm.runInContext(code,ctx);return {ctx,scans,notices};
}
(async()=>{
 let {ctx,scans,notices}=setup();
 await Promise.all([ctx.enqueue('abc123'),ctx.enqueue('ABC123')]);assert.equal(scans.length,1);assert.ok(notices.includes('error.scan_duplicate'));assert.equal(scans[0].payload.finishedGoodPackDetailId,'I');assert.ok(scans[0].payload.scannedAtUtc.endsWith('Z'));
 await ctx.enqueue('UNKNOWN');assert.equal(scans.length,1);assert.equal(notices.at(-1),'error.scan_not_in_plan');
 ctx.state.completing=true;await ctx.enqueue('ABC123');assert.equal(scans.length,1);
 ctx.state.completing=false;ctx.state.session.sessionStatus='Completed';await ctx.enqueue('ABC123');assert.equal(scans.length,1);
 ({ctx,scans,notices}=setup());ctx.store.put=async()=>{throw Error('disk full')};await ctx.enqueue('ABC123');assert.equal(scans.length,0);assert.equal(notices.at(-1),'error.offline_storage');
 ({ctx,scans,notices}=setup());ctx.state.session.readOnly=true;await ctx.enqueue('ABC123');assert.equal(scans.length,0);
 console.log('Client scan queue: valid scan, duplicate, unknown RFID, completion guard and storage failure passed');
})().catch(e=>{console.error(e);process.exit(1)});
