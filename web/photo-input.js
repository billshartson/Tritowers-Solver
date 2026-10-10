/* Phone intake shared by the HTTP UI and the static browser build. */
(() => {
  const MAX_BYTES=60*1024*1024, MAX_SIDE=1600, MAX_PIXELS=150000000;
  function fail(code,message){const e=new Error(code);e.code=code;e.userMessage=message;return e}
  function cancelled(signal){if(signal?.aborted)throw new DOMException('Cancelled','AbortError')}
  async function decode(blob){
    if(typeof createImageBitmap==='function'){
      try{return await createImageBitmap(blob,{imageOrientation:'from-image'})}catch(e){}
    }
    const url=URL.createObjectURL(blob);
    try{return await new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(fail('decode_failed','Could not decode this image. Choose another photo.'));im.src=url})}
    finally{URL.revokeObjectURL(url)}
  }
  async function isHeic(file){
    const bytes=new Uint8Array(await file.slice(0,64).arrayBuffer());
    const signature=String.fromCharCode(...bytes);
    return signature.slice(4,8)==='ftyp'&&/heic|heix|hevc|hevx|mif1|msf1/.test(signature.slice(8));
  }
  let decoder;
  async function decodeHeic(file,signal){
    cancelled(signal);
    // A worker keeps software HEIC decoding off the UI thread; photos never leave the browser.
    if(!decoder)decoder='/web/heic-worker.js';
    return await new Promise((resolve,reject)=>{
      const worker=new Worker(decoder),stop=()=>{worker.terminate();signal?.removeEventListener('abort',abort);clearTimeout(timer)};
      const abort=()=>{stop();reject(new DOMException('Cancelled','AbortError'))};
      const timer=setTimeout(()=>{stop();reject(fail('decode_timeout','This HEIC photo took too long to decode. Try a JPEG export.'))},60000);
      signal?.addEventListener('abort',abort,{once:true});
      worker.onmessage=({data})=>{stop();data.ok?resolve(data.blob):reject(fail('heic_decode_failed','Could not decode this HEIC photo. Try exporting it as JPEG.'))};
      worker.onerror=()=>{stop();reject(fail('heic_unavailable','The HEIC decoder could not load. Reconnect and try again, or choose a JPEG export.'))};
      worker.postMessage(file);
    });
  }
  async function normalize(file,{signal}={}){
    cancelled(signal);
    if(!file||!file.size)throw fail('empty_image','Choose a photo first.');
    if(file.size>MAX_BYTES)throw fail('image_too_large','Choose a photo smaller than 60 MB.');
    // Only supported raster formats; SVG and animation are not board captures.
    const head=new Uint8Array(await file.slice(0,16).arrayBuffer());
    const heic=await isHeic(file);cancelled(signal);
    const raster=head[0]===255&&head[1]===216 || head[0]===137&&head[1]===80&&head[2]===78&&head[3]===71 || String.fromCharCode(...head.slice(0,4))==='RIFF'&&String.fromCharCode(...head.slice(8,12))==='WEBP';
    if(!heic&&!raster)throw fail('unsupported_format','Choose a JPEG, PNG, WebP or HEIC photo.');
    let decoded;
    try{decoded=await decode(file)}catch(e){if(!heic)throw e;decoded=await decode(await decodeHeic(file,signal))}
    try{
      cancelled(signal);
      const width=decoded.width||decoded.naturalWidth,height=decoded.height||decoded.naturalHeight;
      if(!width||!height||width*height>MAX_PIXELS)throw fail('pixel_limit','This image exceeds the 150 megapixel limit. Export a smaller copy.');
      const scale=Math.min(1,MAX_SIDE/Math.max(width,height)),canvas=document.createElement('canvas');
      canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
      const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(decoded,0,0,canvas.width,canvas.height);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.94));canvas.width=canvas.height=1;
      cancelled(signal);if(!blob)throw fail('encode_failed','Could not prepare this photo. Try another image.');return blob;
    }finally{decoded.close?.()}
  }
  window.TTPhoto={normalize};
})();
