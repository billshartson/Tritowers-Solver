// Pinned public codec; only code is fetched. The photo stays in this worker.
importScripts('https://cdn.jsdelivr.net/npm/heic-to@1.5.2/dist/iife/heic-to.js');
self.onmessage=async({data})=>{
  let bitmap;
  try{
    // Bitmap conversion avoids the library's DOM-canvas encoder in worker scope.
    bitmap=await HeicTo({blob:data,type:'bitmap'});
    if(bitmap.width*bitmap.height>150000000)throw new Error('pixel_limit');
    const scale=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
    const canvas=new OffscreenCanvas(Math.max(1,Math.round(bitmap.width*scale)),Math.max(1,Math.round(bitmap.height*scale)));
    canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);
    const blob=await canvas.convertToBlob({type:'image/jpeg',quality:0.94});
    self.postMessage({ok:true,blob});
  }catch(e){self.postMessage({ok:false})}
  finally{bitmap?.close()}
};
