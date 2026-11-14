const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const sw=fs.readFileSync('finished_good_pack_rfid_scan/www/finished-good-pack-rfid-scan-sw.js','utf8');
const updater=fs.readFileSync('finished_good_pack_rfid_scan/templates/includes/client_update.html','utf8').replace(/<\/?script>/g,'').replace('{{ rfid_asset_version | tojson }}','"v1"');
(async()=>{
 const handlers={},data=new Map();let offline=false,skipped=0;
 const key=x=>typeof x==='string'?x:x.url;
 const ctx={URL,Response,Set,Error,self:{location:{origin:'https://example.test'},addEventListener:(n,f)=>handlers[n]=f,skipWaiting:()=>skipped++,clients:{claim(){}}},
 caches:{open:async()=>({match:async x=>data.get(key(x)),put:async(x,r)=>data.set(key(x),r)}),keys:async()=>[],delete:async()=>{}},
 fetch:async()=>{if(offline)throw Error('offline');return new Response('new');}};
 vm.createContext(ctx);vm.runInContext(sw,ctx);
 const url='https://example.test/assets/client.js?v=2';data.set(url,new Response('old'));
 async function request(url,mode='cors'){let result;handlers.fetch({request:{url,method:'GET',mode},respondWith:p=>result=p});return result;}
 assert.equal(await (await request(url)).text(),'new');offline=true;
 assert.equal(await (await request(url)).text(),'new');
 assert.equal((await request('https://example.test/assets/client.js?v=3')).status,503);
 assert.equal(await request('https://example.test/api/method/test'),undefined);
 let installation;handlers.install({waitUntil:p=>installation=p});await assert.rejects(installation);assert.equal(skipped,0);
 const events={},intervals=[],storage=new Map();let reloads=0,view='session-view',online=true;
 const app={dataset:{get view(){return view;}}};
 const page={navigator:{get onLine(){return online;}},document:{hidden:false,getElementById:()=>app,querySelector:()=>null,addEventListener:(n,f)=>events[n]=f},
 window:{isSecureContext:false,location:{reload(){reloads++;}},addEventListener(){},RfidPrepareUpdate:async()=>true},
 sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
 fetch:async()=>({ok:true,json:async()=>({message:{version:'v2'}})}),setInterval:fn=>intervals.push(fn),setTimeout,clearTimeout};
 vm.createContext(page);vm.runInContext(updater,page);events.DOMContentLoaded();await new Promise(setImmediate);
 assert.equal(reloads,0,'Never reload an active scan');
 view='home-view';page.window.RfidPrepareUpdate=async()=>false;intervals[1]();await new Promise(setImmediate);assert.equal(reloads,0);
 page.window.RfidPrepareUpdate=async()=>true;intervals[1]();await new Promise(setImmediate);assert.equal(reloads,1);
 intervals[1]();await new Promise(setImmediate);assert.equal(reloads,1,'No reload loop');
 offline=true;online=false;storage.clear();intervals[1]();await new Promise(setImmediate);assert.equal(reloads,1);
 console.log('Client updates: fresh network, exact offline versions, failed installation, active-scan protection, safe reload and loop guard passed');
})().catch(error=>{console.error(error);process.exit(1);});
