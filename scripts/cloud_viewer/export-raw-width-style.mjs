import { grwlLinePaint, grwlWidthSampleLayer, GRWL_WIDTH_LEGEND } from './src/core.js';
import { writeFile } from 'node:fs/promises';
const style={version:8,name:'GRWL source widths at every zoom',metadata:{
  'data-publications:width-field':'width_m','data-publications:width-unit':'m',
  'data-publications:legend':GRWL_WIDTH_LEGEND,
  'data-publications:notice':'At zooms 0–7, selected original observations retain the widest valid measured width per screen-scale cell. Detailed source segments appear from zoom 8. Symbols are exaggerated and capped at 1000 m; they are not riverbanks. A source value of 1 denotes unknown width.',
},sources:{data:{type:'vector',url:'../assets/grwl-raw.pmtiles',attribution:'Allen and Pavelsky (2018), GRWL V01.01, CC BY 4.0'}},
layers:[grwlWidthSampleLayer('data',{source_layer:'grwl_width_overview',min_zoom:0},8),
  {id:'release-lines',type:'line',source:'data','source-layer':'grwl_raw',minzoom:8,paint:grwlLinePaint('width_m')}]};
const bytes=JSON.stringify(style,null,2)+'\n';
const index=process.argv.indexOf('--output');
if(index>=0)await writeFile(process.argv[index+1],bytes,{flag:'wx'});
else process.stdout.write(bytes);
