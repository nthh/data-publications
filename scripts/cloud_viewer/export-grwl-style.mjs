import { grwlLinePaint, GRWL_WIDTH_LEGEND } from './src/core.js';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output=resolve(root,'datasets/grwl/styles/width-v1.json');
const style={version:8,name:'GRWL mean channel width',metadata:{
  'data-publications:width-field':'width_mean','data-publications:width-unit':'m',
  'data-publications:legend':GRWL_WIDTH_LEGEND,
  'data-publications:notice':'Widths are cartographic symbols exaggerated for legibility; not literal riverbanks. Symbol width is capped at 1000 m. Nonpositive/missing values use a muted fallback stroke.',
  'data-publications:storage-path':'metadata/grwl-width-v1/style.json',
},sources:{data:{type:'vector',url:'../../releases/summary-v01.02-local-r1/grwl/grwl-display.pmtiles',attribution:'Allen and Pavelsky (2018), CC BY 4.0; independently maintained display style'}},layers:[{id:'grwl-width',type:'line',source:'data','source-layer':'grwl',paint:grwlLinePaint()}]};
const bytes=JSON.stringify(style,null,2)+'\n';
if(process.argv.includes('--check')){if(await readFile(output,'utf8')!==bytes)throw new Error('GRWL width-v1 style differs from its generator');}
else {await mkdir(dirname(output),{recursive:true});await writeFile(output,bytes,{flag:'wx'});}
console.log('GRWL width-v1 style '+(process.argv.includes('--check')?'verified':'written'));
