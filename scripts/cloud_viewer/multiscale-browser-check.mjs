import { chromium } from 'playwright-core';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { verifyRangeResponse } from './src/core.js';

function option(name, fallback) {
  const index=process.argv.indexOf('--'+name);
  return index<0?fallback:process.argv[index+1];
}
const origin=new URL(option('url','http://127.0.0.1:8912')).origin;
const output=resolve(option('out','.local/grwl-multiscale-browser-check'));
const chromePath='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const transferLimit=32*1024*1024;
const localHosts=new Set(['127.0.0.1','localhost','::1','[::1]']);

// Frozen geographic cases: global, Amazon, a known raw-source location, its
// overview-to-detail transition, and a dateline source-derived anchor.
const fixedCases=[
  {id:'global-z0',center:[0,20],zoom:0,mode:'overview'},
  {id:'amazon-z3',center:[-60,-3],zoom:3,mode:'overview'},
  {id:'known-raw-15450-z7',center:[-108,44.8],zoom:7,mode:'overview'},
  {id:'overview-to-detail',center:[-108,44.8],zoom:7,mode:'transition'},
];

const configResponse=await fetch(origin+'/viewer-config.json');
if(!configResponse.ok)throw new Error('Local viewer config returned HTTP '+configResponse.status);
const config=await configResponse.json();
const viewerBuildBytes=Buffer.from(await (await fetch(origin+'/build.json')).arrayBuffer());
const viewerBuildHash=createHash('sha256').update(viewerBuildBytes).digest('hex');
const dataset=config.datasets?.find(candidate=>candidate.id==='grwl-raw');
const layer=dataset?.layers?.find(candidate=>candidate.overview);
if(!layer?.object_path||!layer.overview?.source_layer||layer.detail_min_zoom!==8)
  throw new Error('Runtime GRWL archive lacks the configured overview layer or zoom-8 detail boundary');
if(layer.overview.source_layer!=='grwl_overview')throw new Error('Unexpected GRWL overview source layer');
const objectOrigin=new URL(config.object_origin);
if(!localHosts.has(objectOrigin.hostname))throw new Error('GRWL object origin must be local for this check');

const sourceManifestPath='research/grwl-raw-release-20261102/global-source-validation-r1.json';
const sourceManifestBytes=await readFile(sourceManifestPath);
const sourceManifest=JSON.parse(sourceManifestBytes.toString('utf8'));
if(layer.analytic?.sha256&&sourceManifest.parquet_sha256!==layer.analytic.sha256)
  throw new Error('NR01 source anchor manifest does not match the runtime analytical source');
const nr01=sourceManifest.tiles?.find(candidate=>candidate.tile==='NR01');
const nr01First=nr01?.first_records?.[0];
if(nr01First?.source_tile!=='NR01'||!Array.isArray(nr01First.bbox)||nr01First.bbox.length!==4||!nr01First.bbox.every(Number.isFinite))
  throw new Error('The frozen NR01 first-record anchor is missing from the source manifest');
const datelineCenter=[(nr01First.bbox[0]+nr01First.bbox[2])/2,(nr01First.bbox[1]+nr01First.bbox[3])/2];
if(Math.abs(datelineCenter[0])<170)throw new Error('NR01 first-record anchor is not at the dateline');
const cases=[...fixedCases,{id:'nr01-first-record-z7',center:datelineCenter,zoom:7,mode:'overview',source_tile:'NR01',source_row:nr01First.source_row,feature_id:nr01First.feature_id}];

await mkdir(output,{recursive:false});
const report={schema_version:1,status:'running',started_at:new Date().toISOString(),
  scope:'Local installed-Chrome acceptance of GRWL overview coverage and zoom-8 detail rendering; local HTTP range/CORS only.',
  runtime:{viewer_build_sha256:viewerBuildHash,url:origin,dataset_id:dataset.id,layer_id:layer.id,object_path:layer.object_path,
    sha256:layer.sha256,size_bytes:layer.size_bytes,overview_source_layer:layer.overview.source_layer,
    detail_min_zoom:layer.detail_min_zoom},
  source_anchor:{path:sourceManifestPath,sha256:createHash('sha256').update(sourceManifestBytes).digest('hex'),
    parquet_sha256:sourceManifest.parquet_sha256,tile:'NR01',source_row:nr01First.source_row,feature_id:nr01First.feature_id,
    bbox:nr01First.bbox,center:datelineCenter},
  transfer_policy:{bytes_per_case:transferLimit,enforced:true,requested_range_bytes:true,response_body_bytes:true},
  cases:[],errors:[]};
const browser=await chromium.launch({executablePath:chromePath,headless:true,
  args:['--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-background-networking','--no-first-run']});
const objectPath=new URL(layer.object_path,objectOrigin).pathname;
const assets=new Map([[objectPath,layer]]);

function localURL(value) {
  try{return localHosts.has(new URL(value).hostname);}catch{return false;}
}
async function waitForView(page, expectedSource, zoom) {
  await page.waitForFunction(({source,expectedZoom})=>{
    const viewer=window.viewer;
    if(!viewer||viewer.getState().phase==='error')return true;
    const names=viewer.getRenderedLayerNames();
    return Math.abs(viewer.getZoom()-expectedZoom)<0.05&&names.includes(source);
  },{source:expectedSource,expectedZoom:zoom},{timeout:60000});
  const state=await page.evaluate(()=>window.viewer?.getState());
  if(state?.phase==='error')throw new Error(state.error||'Viewer entered error state');
  const actual=await page.evaluate(()=>({zoom:window.viewer.getZoom(),center:window.viewer.getCenter(),layers:window.viewer.getRenderedLayerNames()}));
  if(Math.abs(actual.zoom-zoom)>=0.05||!actual.layers.includes(expectedSource))
    throw new Error(`Expected ${expectedSource} at zoom ${zoom}; got ${actual.layers.join(',')} at ${actual.zoom}`);
  return actual;
}
async function checkOverview(page, entry, item, screenshotPath) {
  const rendered=await waitForView(page,layer.overview.source_layer,item.zoom);
  if(rendered.center.some((value,index)=>Math.abs(value-item.center[index])>1e-8))throw new Error('Overview camera center differs from the frozen source view');
  const legendHidden=await page.locator('#grwl-width-legend').isHidden();
  const status=await page.locator('#map-status').innerText();
  if(!legendHidden)throw new Error('GRWL width legend must be hidden below detail minimum zoom');
  if(!/coverage/i.test(status))throw new Error('Overview status does not identify observation coverage');
  entry.checkpoints.push({view:'overview',center:item.center,actual_center:rendered.center,zoom:rendered.zoom,rendered_layers:rendered.layers,
    width_legend_hidden:legendHidden,map_status:status,screenshot:screenshotPath});
  await page.screenshot({path:join(output,screenshotPath),fullPage:true});
}
async function checkDetail(page, entry, center, screenshotPath) {
  const rendered=await waitForView(page,'grwl_raw',8);
  if(rendered.center.some((value,index)=>Math.abs(value-center[index])>1e-8))throw new Error('Detail camera center differs from the frozen source view');
  const legendHidden=await page.locator('#grwl-width-legend').isHidden();
  const expression=await page.evaluate(()=>window.viewer.getActiveLineWidthExpression());
  if(legendHidden)throw new Error('GRWL width legend must be visible at zoom 8');
  if(!JSON.stringify(expression).includes('width_m')||JSON.stringify(expression).includes('width_mean'))
    throw new Error('Zoom-8 detail line expression does not use width_m');
  entry.checkpoints.push({view:'detail',center,actual_center:rendered.center,zoom:rendered.zoom,rendered_layers:rendered.layers,
    width_legend_hidden:legendHidden,width_expression:expression,screenshot:screenshotPath});
  await page.screenshot({path:join(output,screenshotPath),fullPage:true});
}

try{
  for(const item of cases){
    const context=await browser.newContext({viewport:{width:1500,height:1050},deviceScaleFactor:1,locale:'en-US'});
    const page=await context.newPage(),requests=[],pending=[],errors=[],external=[];
    let requestedBytes=0,responseBytes=0;
    const entry={case_id:item.id,kind:item.mode,center:item.center,zoom:item.zoom,status:'running',checkpoints:[]};
    if(item.source_tile)Object.assign(entry,{source_tile:item.source_tile,source_row:item.source_row,feature_id:item.feature_id});
    await context.route('**/*',route=>{
      const request=route.request(),href=request.url();
      if(!href.startsWith('http:')&&!href.startsWith('https:'))return route.continue();
      if(!localURL(href)){external.push(href);errors.push('Blocked nonlocal network request '+href);return route.abort();}
      const url=new URL(href);
      if(url.origin===objectOrigin.origin&&request.method()==='GET'){
        const asset=assets.get(url.pathname),range=request.headers()['range'];
        const match=/^bytes=(\d+)-(\d+)$/.exec(range||'');
        if(!asset||!match){errors.push('Object GET lacked the known PMTiles object or a single bounded byte range');return route.abort();}
        const start=Number(match[1]),end=Number(match[2]),length=end-start+1;
        if(!Number.isSafeInteger(length)||length<1||end>=asset.size_bytes||requestedBytes+length>transferLimit){
          errors.push('Requested byte range exceeded the object bounds or 32 MiB case ceiling');return route.abort();
        }
        requestedBytes+=length;
      }
      return route.continue();
    });
    page.on('pageerror',error=>errors.push(error.message));
    page.on('response',response=>{
      const url=new URL(response.url()),asset=assets.get(url.pathname);
      if(url.origin!==objectOrigin.origin||!asset)return;
      pending.push((async()=>{
        const headers=await response.allHeaders(),request=response.request(),method=request.method();
        const record={object_path:url.pathname,method,range:request.headers()['range']||null,status:response.status(),
          content_range:headers['content-range']||null,cors:headers['access-control-allow-origin']||null,
          body_bytes:0,completed:false};
        try{
          if(method==='GET')record.body_bytes=(await response.body()).byteLength;
          record.completed=!(await response.finished());
        }catch(error){record.body_error=error.message;}
        if(method==='GET')responseBytes+=record.body_bytes;
        requests.push(record);
      })());
    });
    try{
      const target=new URL('/',origin);target.searchParams.set('dataset','grwl-raw');target.searchParams.set('region','global');
      await page.goto(target.href,{waitUntil:'domcontentloaded',timeout:30000});
      await page.waitForFunction(()=>window.viewer&&(window.viewer.getState().phase==='error'||window.viewer.getState().phase==='ready'),{},{timeout:60000});
      const initial=await page.evaluate(()=>window.viewer?.getState());
      if(initial?.phase!=='ready'||initial.layer!==layer.id)throw new Error(initial?.error||'Global GRWL runtime layer did not become ready');
      await page.evaluate(({center,zoom})=>window.viewer.setView(center,zoom),{center:item.center,zoom:item.zoom});
      if(item.mode==='transition'){
        await checkOverview(page,entry,{...item,zoom:7},`${item.id}-z7.png`);
        await page.evaluate(center=>window.viewer.setView(center,8),item.center);
        await checkDetail(page,entry,item.center,`${item.id}-z8.png`);
      }else{
        await checkOverview(page,entry,item,`${item.id}.png`);
      }
      await Promise.all(pending);
      const gets=requests.filter(record=>record.method==='GET');
      if(!gets.length||gets.some(record=>record.status!==206||record.cors!=='*'||!record.completed||!record.range))
        throw new Error('PMTiles reads did not all complete as CORS-enabled HTTP 206 byte ranges');
      for(const record of gets)verifyRangeResponse(record.range,record.content_range,record.body_bytes,layer.size_bytes);
      if(requestedBytes>transferLimit||responseBytes>transferLimit)throw new Error('Per-case 32 MiB transfer ceiling was exceeded');
      if(errors.length)throw new Error(errors.join('; '));
      entry.requests=requests;entry.requested_range_bytes=requestedBytes;entry.response_body_bytes=responseBytes;
      entry.transfer_ceiling_bytes=transferLimit;entry.status='passed';
    }catch(error){
      await Promise.allSettled(pending);
      entry.status='failed';entry.error=error.message;entry.requests=requests;
      entry.requested_range_bytes=requestedBytes;entry.response_body_bytes=responseBytes;
      entry.external_requests=external;report.errors.push(`${item.id}: ${error.message}`);
      try{await page.screenshot({path:join(output,`${item.id}-failure.png`),fullPage:true});}catch{}
    }
    report.cases.push(entry);
    await context.close();
    await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({case_id:item.id,status:entry.status,requests:requests.length,
      requested_range_bytes:requestedBytes,response_body_bytes:responseBytes,error:entry.error}));
  }
  report.status=report.cases.length===cases.length&&report.cases.every(item=>item.status==='passed')?'passed':'failed';
  report.finished_at=new Date().toISOString();
}finally{
  await browser.close();
  await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
}
console.log(JSON.stringify({status:report.status,cases:report.cases.length,errors:report.errors}));
if(report.status!=='passed')process.exitCode=1;
