const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('finished_good_pack_rfid_scan/public/rfid/client.js','utf8');
const code=source.slice(source.indexOf('  let syncingScans ='),source.indexOf('  const addScan ='))+'\nglobalThis.sync=syncScans;';
function setup(n=1){
 const rows=Array.from({length:n},(_,i)=>({bookingId:'B',finishedGoodPackDetailId:String(i)}));
 const calls=[],status={textContent:''};
 const ctx={state:{session:{sessionId:'S',sessionStatus:'Active'}},navigator:{onLine:true},document:{getElementById:()=>status},store:{scans:async()=>rows},api:async(...args)=>calls.push(args)};
 vm.createContext(ctx);vm.runInContext(code,ctx);return {ctx,calls,status,rows};
}
(async()=>{
 let {ctx,calls,status,rows}=setup(101);
 await ctx.sync();assert.equal(calls[0][1].scans.length,100);
 await ctx.sync();assert.equal(calls[1][1].scans.length,1);
 await ctx.sync();assert.equal(calls.length,2);assert.equal(rows.length,101);
 ({ctx,calls,status}=setup());ctx.api=async()=>{throw Error('lost response');};
 await ctx.sync();assert.match(status.textContent,/Chưa đồng bộ/);
 ctx.api=async(...args)=>calls.push(args);await ctx.sync();assert.equal(calls.length,1);
 ({ctx,calls}=setup());ctx.navigator.onLine=false;await ctx.sync();assert.equal(calls.length,0);
 ctx.navigator.onLine=true;ctx.state.completing=true;await ctx.sync();assert.equal(calls.length,0);
 ctx.state.completing=false;await Promise.all([ctx.sync(),ctx.sync()]);assert.equal(calls.length,1);
 ({ctx,calls}=setup());let release;ctx.api=()=>new Promise(resolve=>release=resolve);
 const pending=ctx.sync();await new Promise(resolve=>setImmediate(resolve));
 ctx.state.session=null;release({});await pending;
 const mergeCode=source.slice(source.indexOf('  const scansForSession ='),source.indexOf('  const scansForSession =')+source.slice(source.indexOf('  const scansForSession =')).indexOf('\n  };')+5)+'\nglobalThis.read=scansForSession;';
 ctx.state.session={sessionId:'S',scannedItems:[{bookingId:'B',finishedGoodPackDetailId:'0',rfid:'saved'}]};
 vm.runInContext(mergeCode,ctx);const merged=await ctx.read();assert.equal(merged.length,1);assert.equal(merged[0].rfid,'saved');
 ({ctx,calls}=setup());ctx.state.session.readOnly=true;await ctx.sync();assert.equal(calls.length,0);
 console.log('Scan sync: batching, retry, offline, completion guard, concurrency, navigation and server recovery passed');
})().catch(error=>{console.error(error);process.exit(1);});
