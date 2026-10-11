const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sleep=()=>new Promise(resolve=>setImmediate(resolve));
async function drain(predicate){for(let i=0;i<100;i++){await sleep();if(predicate())return}throw new Error('async work did not finish')}

function bridge(){
  const storage=new Map(),games=new Map(),calls=[],workers=[];let onSend=()=>{};
  class Worker{
    constructor(){workers.push(this)}
    terminate(){}
    postMessage(message){
      calls.push(message);onSend(message);
      if(message.cancel!==undefined)return;
      setImmediate(()=>{
        const {id,route,body}=message;let result;
        if(route==='/api/new'){
          if(!games.has(body.sid))games.set(body.sid,{stock:body.stock,applied:new Set()});
          result={ok:true,sid:body.sid,stock:games.get(body.sid).stock};
        }else{
          const game=games.get(body.sid);
          if(!game)result={ok:false,gone:true};
          else{
            if(body.op==='draw'&&!game.applied.has(body.req_id)){game.stock--;game.applied.add(body.req_id)}
            result={ok:true,stock:game.stock};
          }
        }
        this.onmessage({data:{id,ok:true,json:JSON.stringify(result)}});
      });
    }
  }
  const context={Worker,URL,Response,DOMException,AbortController,Map,Set,Promise,
    location:{href:'https://example.test/',origin:'https://example.test'},sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,val)=>storage.set(key,val)},
    window:{fetch:()=>{throw new Error('unexpected external request')}}};
  vm.runInNewContext(fs.readFileSync('web/tt-bridge.js','utf8'),context);
  const log={n:{sid:'saved',stock:5,req_id:'new'},ops:[{sid:'saved',op:'draw',rank:'2',req_id:'old-1'},{sid:'saved',op:'draw',rank:'3',req_id:'old-2'}],seen:['old-1','old-2']};
  storage.set('tt_log_saved',JSON.stringify(log));
  const act=(op,req_id,signal)=>context.window.fetch('/api/act',{body:JSON.stringify({sid:'saved',op,req_id}),signal}).then(r=>r.json());
  return {storage,games,calls,act,setOnSend:fn=>onSend=fn};
}

async function testConcurrentRestore(){
  const h=bridge();
  const [state,draw]=await Promise.all([h.act('state','state'),h.act('draw','draw')]);
  assert.equal(state.stock,3);assert.equal(draw.stock,2);
  assert.equal(h.calls.filter(c=>c.route==='/api/new').length,1);
  const journal=JSON.parse(h.storage.get('tt_log_saved'));
  assert.equal(journal.ops.length,3);assert.equal(journal.ops[2].req_id,'draw');
  await h.act('draw','draw');assert.equal(h.games.get('saved').stock,2);
  assert.equal(JSON.parse(h.storage.get('tt_log_saved')).ops.length,3);
}
async function testAbortDoesNotLeavePartialReplay(){
  const h=bridge(),controller=new AbortController();let aborted=false;
  h.setOnSend(message=>{if(message.body?.req_id==='old-1'&&!aborted){aborted=true;controller.abort()}});
  const cancelled=h.act('state','cancelled',controller.signal);
  const restored=h.act('state','after-abort');
  await assert.rejects(cancelled,error=>error.name==='AbortError');
  assert.equal((await restored).stock,3);
  assert.equal(h.calls.filter(c=>c.route==='/api/new').length,1);
}
async function testAbortNotifiesWorker(){
  const h=bridge(),controller=new AbortController();
  h.games.set('saved',{stock:5,applied:new Set()});
  h.setOnSend(message=>{if(message.body?.req_id==='abort-flight')queueMicrotask(()=>controller.abort())});
  await assert.rejects(h.act('state','abort-flight',controller.signal),error=>error.name==='AbortError');
  assert.ok(h.calls.some(c=>c.cancel!==undefined));
}

async function worker(){
  const messages=[],recognitions=[],loads=[];let resolveLoad;
  const py={unpackArchive(){},globals:{set(){}},FS:{writeFile(){},unlink(){}},
    runPython(source){if(source.includes('api_photo'))recognitions.push(source);return '{}'},
    loadPackage(){const promise=new Promise((resolve,reject)=>{resolveLoad={resolve,reject}});loads.push(resolveLoad);return promise}};
  const context={loadPyodide:async()=>py,fetch:async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)}),Uint8Array,
    self:{postMessage:message=>messages.push(message)},Promise,Set};
  const source=fs.readFileSync('web/pw.js','utf8').replace(/^import .*\n/m,'');
  vm.runInNewContext(source,context);
  await drain(()=>loads.length===1);
  return {messages,recognitions,loads,send:data=>context.self.onmessage({data})};
}
async function testWorkerDropsCancelledAndSupersededPhotos(){
  const h=await worker();
  h.send({id:1,route:'/api/photo',bytes:new ArrayBuffer(1)});
  await sleep(); // first photo is waiting for preloaded vision
  h.send({cancel:1});
  h.send({id:2,route:'/api/photo',bytes:new ArrayBuffer(1)});
  h.send({id:3,route:'/api/photo',bytes:new ArrayBuffer(1)});
  h.loads[0].resolve();
  await drain(()=>h.messages.length===3);
  assert.equal(h.recognitions.length,1);
  assert.equal(h.messages.find(m=>m.id===1).ok,false);
  assert.equal(h.messages.find(m=>m.id===2).ok,false);
  assert.equal(h.messages.find(m=>m.id===3).ok,true);
}
async function testWorkerRetriesFailedPreload(){
  const h=await worker();
  h.loads[0].reject(new Error('temporary network error'));await sleep();
  h.send({id:1,route:'/api/photo',bytes:new ArrayBuffer(1)});
  await drain(()=>h.loads.length===2);
  h.loads[1].resolve();await drain(()=>h.messages.length===1);
  assert.equal(h.messages[0].ok,true);assert.equal(h.recognitions.length,1);
}
(async()=>{
  await testConcurrentRestore();await testAbortDoesNotLeavePartialReplay();await testAbortNotifiesWorker();
  await testWorkerDropsCancelledAndSupersededPhotos();await testWorkerRetriesFailedPreload();
  process.stdout.write('5 browser transport regression scenarios passed\n');
})().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1});
