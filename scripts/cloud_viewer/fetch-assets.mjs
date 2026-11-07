import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
const here=dirname(fileURLToPath(import.meta.url));
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
export async function verifiedRuntimeAssets({download=false}={}) {
  const manifest=JSON.parse(await readFile(join(here,'runtime-assets.json'),'utf8'));
  const result=[];
  for(const asset of manifest.assets) {
    if(!/^[a-zA-Z0-9._-]+$/.test(asset.cache_name)||asset.destination.includes('..'))throw new Error('Invalid runtime asset path');
    const path=join(here,'node_modules/.cache/viewer',asset.cache_name);
    let bytes;
    try{bytes=await readFile(path);}catch(error){
      if(error.code!=='ENOENT')throw error;
      if(!download)throw new Error('Runtime extension is missing. Run npm run setup in scripts/cloud_viewer first.');
      const response=await fetch(asset.url,{headers:{'User-Agent':'data-publications-viewer','Accept':'application/wasm'}});
      if(!response.ok)throw new Error('Runtime download returned HTTP '+response.status);
      const chunks=[];let length=0;
      for await(const chunk of response.body){
        length+=chunk.length;if(length>asset.size_bytes)throw new Error('Runtime download exceeds pinned size');chunks.push(chunk);
      }
      bytes=Buffer.concat(chunks);
      if(bytes.length!==asset.size_bytes||digest(bytes)!==asset.sha256)throw new Error('Runtime download differs from its checksum pin');
      await mkdir(dirname(path),{recursive:true});await writeFile(path,bytes,{flag:'wx'});
      console.log(JSON.stringify({downloaded:asset.name,bytes:bytes.length}));
    }
    if(bytes.length!==asset.size_bytes||digest(bytes)!==asset.sha256)throw new Error('Cached runtime extension differs from its checksum pin');
    result.push({...asset,path});
  }
  return result;
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  const assets=await verifiedRuntimeAssets({download:true});
  console.log(JSON.stringify({verified_runtime_assets:assets.length}));
}
