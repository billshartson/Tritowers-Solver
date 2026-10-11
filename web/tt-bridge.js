// Static app transport. No request is sent to the retired origin, including photos.
(()=>{
  const realFetch=window.fetch.bind(window),pending=new Map(),sessions=new Map(),restoreNeeded=new Set();let worker,n=0;
  function engine(){
    if(!worker){
      worker=new Worker('/pw.js',{type:'module'});
      worker.onmessage=({data})=>{const p=pending.get(data.id);if(!p)return;pending.delete(data.id);p.clean();data.ok?p.resolve(data.json):p.reject(new Error(data.error))};
      worker.onerror=()=>{for(const p of pending.values()){p.clean();p.reject(new Error('The local engine could not start. Reload to try again.'))}pending.clear();worker.terminate();worker=null};
    }
    return worker;
  }
  function call(message,signal){return new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(new DOMException('Cancelled','AbortError'));return}
    const id=++n,abort=()=>{pending.delete(id);signal?.removeEventListener('abort',abort);worker?.postMessage({cancel:id});reject(new DOMException('Cancelled','AbortError'))};
    pending.set(id,{resolve,reject,clean:()=>signal?.removeEventListener('abort',abort)});
    signal?.addEventListener('abort',abort,{once:true});
    try{engine().postMessage({id,...message},message.bytes?[message.bytes]:[])}catch(e){pending.delete(id);signal?.removeEventListener('abort',abort);reject(e)}
  })}
  const jsonResponse=s=>new Response(typeof s==='string'?s:JSON.stringify(s),{headers:{'content-type':'application/json'}});
  const key=sid=>'tt_log_'+sid,mutations=['play','reveal','draw','undo'];
  function saved(sid){try{return JSON.parse(sessionStorage.getItem(key(sid))||'null')}catch(e){return null}}
  function save(sid,value){try{sessionStorage.setItem(key(sid),JSON.stringify(value))}catch(e){/* Play remains usable if storage is full. */}}
  function serial(sid,fn){
    const run=(sessions.get(sid)||Promise.resolve()).then(fn),tail=run.catch(()=>{});
    sessions.set(sid,tail);
    tail.then(()=>{if(sessions.get(sid)===tail)sessions.delete(sid)});
    return run;
  }
  async function action(route,body,signal){
    if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
    const log=saved(body.sid);
    let result=restoreNeeded.has(body.sid)?{gone:true}:JSON.parse(await call({route,body},signal));
    if(result.gone&&log){
      restoreNeeded.add(body.sid);
      // Finish a restoration even if its caller cancels: later actions must
      // never observe a partly replayed game. Stable IDs make replay resumable.
      const restored=JSON.parse(await call({route:'/api/new',body:log.n}));
      if(!restored.ok)throw new Error('Saved game could not be restored');
      for(let i=0;i<log.ops.length;i++){
        const op={...log.ops[i],req_id:log.ops[i].req_id||`restore-${i}`};
        const replay=JSON.parse(await call({route:'/api/act',body:op}));
        if(!replay.ok)throw new Error('Saved game could not be restored');
      }
      restoreNeeded.delete(body.sid);
      result=JSON.parse(await call({route,body},signal));
    }
    const alreadySaved=body.req_id&&((log?.seen||[]).includes(body.req_id)||(log?.ops||[]).some(op=>op.req_id===body.req_id));
    if(result.ok&&log&&mutations.includes(body.op)&&!alreadySaved){
      // Keep every acknowledged action and its ID, including undo, so refresh
      // preserves history and a late retry cannot corrupt the saved journal.
      log.ops.push({...body});
      if(body.req_id)log.seen=[...(log.seen||[]),body.req_id];
      save(body.sid,log);
    }
    return jsonResponse(result);
  }
  window.fetch=async(input,init={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href),route=url.pathname;
    if(url.origin!==location.origin)return realFetch(input,init);
    if(route==='/api/photo'){
      const file=init.body.get('file'),bytes=await file.arrayBuffer();
      return jsonResponse(await call({route,bytes,corners:init.body.get('corners')||''},init.signal));
    }
    if(!['/api/geo','/api/new','/api/act','/api/solve'].includes(route))return realFetch(input,init);
    const body=init.body?JSON.parse(init.body):{};
    if(route==='/api/act')return serial(body.sid,()=>action(route,body,init.signal));
    let result=JSON.parse(await call({route,body},init.signal));
    if(route==='/api/new'&&result.ok&&!saved(result.sid))save(result.sid,{n:{...body,sid:result.sid},ops:[],seen:[]});
    return jsonResponse(result);
  };
  engine(); // warm the engine while the user chooses a photo
})();
