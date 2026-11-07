import { chromium } from 'playwright-core';
import { createHash } from 'node:crypto';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { verifyRangeResponse } from './src/core.js';

const option=(name,defaultValue)=>{const i=process.argv.indexOf('--'+name);return i<0?defaultValue:process.argv[i+1];};
const origin=option('url','http://127.0.0.1:8912');
const output=resolve(option('out','.local/raw-browser-check'));
const controlsPath=resolve(option('controls','research/grwl-raw-release-20261102/browser-controls.json'));
const controlsBytes=await readFile(controlsPath),controls=JSON.parse(controlsBytes.toString('utf8'));
const controlsHash=createHash('sha256').update(controlsBytes).digest('hex');
const config=await (await fetch(origin+'/viewer-config.json')).json();
const viewerBuildBytes=Buffer.from(await (await fetch(origin+'/build.json')).arrayBuffer());
const viewerBuildHash=createHash('sha256').update(viewerBuildBytes).digest('hex');
const dataset=config.datasets.find(d=>d.id==='grwl-raw'),layer=dataset?.layers?.[0];
if(!layer?.analytic||!Array.isArray(controls.cases)||!controls.cases.length)throw new Error('Raw layer or controls.cases is missing');
if(controls.source_sha256&&controls.source_sha256!==layer.analytic.sha256)throw new Error('Browser controls source_sha256 does not match runtime analytical object');
await mkdir(output,{recursive:false});
const CEILING=controls.browser_limits?.bytes_per_case||134217728;
const objects=new Map([[layer.object_path,layer],[layer.analytic.object_path,layer.analytic]]);
const report={schema_version:2,status:'running',scope:'Local Chrome source lookup, rendering and bounded HTTP range/CORS checks; no remote publication or GEE claim',
 inputs:{viewer_build_sha256:viewerBuildHash,controls:{path:controlsPath,sha256:controlsHash},source_manifest_sha256:controls.source_manifest_sha256||null,
  source_validation_sha256:controls.source_validation_sha256||null,browser_policy_sha256:controls.browser_policy_sha256||null,
  source:{object_path:layer.analytic.object_path,sha256:layer.analytic.sha256,size_bytes:layer.analytic.size_bytes},
  pmtiles:{object_path:layer.object_path,sha256:layer.sha256,size_bytes:layer.size_bytes}},
 transfer_policy:{bytes_per_case:CEILING,enforced:true,aggregate_requested_range_bytes:true,aggregate_response_body_bytes:true},cases:[],errors:[]};
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-background-networking','--no-first-run']});
try{
 for(const control of controls.cases){
  const caseId=String(control.case_id??`summary-${control.summary_reference_id}`),contextRegion=control.context_region??`grwl_${control.summary_reference_id}`;
  const context=await browser.newContext({viewport:{width:1500,height:1050},locale:'en-US'}),page=await context.newPage();
  const requests=[],pending=[],errors=[];let requestedBytes=0,responseBytes=0;
  await context.route('**/*',route=>{
   const req=route.request(),href=req.url();
   if(!href.startsWith('http:')&&!href.startsWith('https:'))return route.continue();
   if(new URL(href).hostname!=='127.0.0.1'){errors.push('Unexpected external request '+href);return route.abort();}
   const url=new URL(href),asset=objects.get(url.pathname);
   if(url.origin===config.object_origin&&req.method()==='GET'){
    const range=req.headers()['range'];const match=/^bytes=(\d+)-(\d+)$/.exec(range||'');
    if(!asset||!match){errors.push('Object GET lacked a known object or single bounded byte range');return route.abort();}
    const start=Number(match[1]),end=Number(match[2]),length=end-start+1;
    if(!Number.isSafeInteger(length)||length<1||end>=asset.size_bytes||requestedBytes+length>CEILING){errors.push('Requested object range exceeded the per-case transfer ceiling or object bounds');return route.abort();}
    requestedBytes+=length;
   }
   return route.continue();
  });
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{
   const url=new URL(response.url()),asset=objects.get(url.pathname);
   if(url.origin!==config.object_origin||!asset)return;
   pending.push((async()=>{
    const headers=await response.allHeaders(),req=response.request(),method=req.method(),range=req.headers()['range']||null;
    const entry={object_path:url.pathname,object_size_bytes:asset.size_bytes,method,range,status:response.status(),content_range:headers['content-range']||null,
     content_length:Number(headers['content-length']||0),body_bytes:0,cors:headers['access-control-allow-origin']||null,completed:false};
    try{entry.body_bytes=method==='GET'?(await response.body()).byteLength:entry.content_length;entry.completed=!(await response.finished());}
    catch(error){entry.body_error=error.message;}
    if(method==='GET')responseBytes+=entry.body_bytes;
    requests.push(entry);
   })());
  });
  const id=Number(control.feature_id),entry={case_id:caseId,kind:control.kind||'pilot',summary_reference_id:control.summary_reference_id??null,
   window_id:control.window_id??null,source_tile:control.source_tile,source_row:control.source_row,feature_id:id,
   context_region:contextRegion,context_bbox:control.context_bbox??null,detail_bbox:control.detail_bbox,status:'running'};
  try{
   await page.goto(origin+'/?dataset=grwl-raw&region='+encodeURIComponent(contextRegion),{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>window.viewer&&(window.viewer.getState().phase==='error'||window.viewer.getState().phase==='ready'&&window.viewer.getState().feature_count>0),{},{timeout:60000});
   const state=await page.evaluate(()=>window.viewer.getState());if(state.phase!=='ready')throw new Error(state.error||'Raw map did not render');
   if(control.context_bbox){
    await page.evaluate(bbox=>window.viewer.focusBounds(bbox),control.context_bbox);
    await page.waitForLoadState('networkidle',{timeout:30000});
    await page.waitForFunction(()=>{const s=window.viewer?.getState(),text=document.querySelector('#map-status')?.textContent||'';
     return s&&(s.phase==='zoom'||s.phase==='ready'&&text.includes('visible tile features'));},{},{timeout:30000});
    const contextState=await page.evaluate(()=>window.viewer.getState());
    entry.context_phase=contextState.phase;
    entry.context_rendered_features=contextState.phase==='ready'?contextState.feature_count:null;
    entry.context_map_status=await page.locator('#map-status').innerText();
    entry.context_map_coordinates=await page.locator('#map-coordinates').innerText();
    const coordinateMatch=/(-?\d+(?:\.\d+)?)°[,]\s*(-?\d+(?:\.\d+)?)°/.exec(entry.context_map_coordinates);
    const expectedCenter=[(control.context_bbox[0]+control.context_bbox[2])/2,(control.context_bbox[1]+control.context_bbox[3])/2];
    if(!coordinateMatch||Math.abs(Number(coordinateMatch[1])-expectedCenter[0])>0.05||Math.abs(Number(coordinateMatch[2])-expectedCenter[1])>0.05)
     throw new Error('Context map did not move to the source-derived regional bounds');
   }
   await page.screenshot({path:join(output,`context-${caseId}.png`),fullPage:true});
   await page.evaluate(bbox=>window.viewer.focusBounds(bbox),control.detail_bbox);
   await page.waitForLoadState('networkidle',{timeout:30000});
   await page.waitForFunction(()=>window.viewer?.getState().phase==='ready'&&(document.querySelector('#map-status')?.textContent||'').includes('visible tile features'),{},{timeout:30000});
   const detailState=await page.evaluate(()=>window.viewer.getState());
   entry.detail_rendered_features=detailState.feature_count;entry.detail_map_status=await page.locator('#map-status').innerText();
   await page.waitForFunction(featureId=>{try{window.viewer.inspectFeatureById(featureId);return true;}catch{return false;}},id,{timeout:30000});
   entry.detail_feature_inspected=true;
   const expression=await page.evaluate(()=>window.viewer.getActiveLineWidthExpression());
   if(!JSON.stringify(expression).includes('width_m')||JSON.stringify(expression).includes('width_mean'))throw new Error('Raw paint does not use observation width');
   const props=()=>page.locator('#properties').evaluate(el=>Object.fromEntries([...el.querySelectorAll('dt')].map(dt=>[dt.textContent,dt.nextElementSibling.textContent])));
   entry.tile_attributes=await props();entry.width_label=await page.locator('#width-summary').innerText();
   if(!entry.width_label.startsWith('Observation width'))throw new Error('Incorrect width label');
   if(entry.tile_attributes.width_m==='1'&&!entry.width_label.includes('Unknown'))throw new Error('Missing-width sentinel displayed as a measurement');
   await page.evaluate(()=>window.viewer.loadAllAttributes());
   if(!(await page.locator('#feature-note').innerText()).startsWith('All source attributes'))throw new Error('Analytical lookup failed');
   entry.analytic_attributes=await props();
   if(entry.analytic_attributes.source_tile!==control.source_tile||Number(entry.analytic_attributes.source_row)!==Number(control.source_row)||Number(entry.analytic_attributes.feature_id)!==id)throw new Error('Analytical source identity differs');
   if(entry.tile_attributes.width_m!==entry.analytic_attributes.width_m)throw new Error('Tile width differs from analytic width');
   if(Object.keys(entry.analytic_attributes).length!==layer.analytic.fields.length)throw new Error('Source attribute fields omitted');
   entry.analytic_attribute_field_count=Object.keys(entry.analytic_attributes).length;
   if(control.expected_analytic_attributes){
    const expected=control.expected_analytic_attributes,actual=entry.analytic_attributes;
    entry.analytic_attributes_checked=Object.keys(expected).length;
    entry.attribute_mismatches=Object.entries(expected).filter(([key,value])=>actual[key]!==value).map(([key,value])=>({field:key,expected:value,actual:actual[key]??null}));
    if(entry.attribute_mismatches.length)throw new Error('Exact analytical attribute values differ: '+entry.attribute_mismatches.map(x=>x.field).join(', '));
   }
   if(control.expected_width){
    entry.expected_width=control.expected_width;
    if(entry.analytic_attributes.width_m!==String(control.expected_width.width_m??'null'))throw new Error('Expected width value differs');
    if(entry.width_label!==control.expected_width.label)throw new Error('Expected width label differs');
    entry.tile_width={width_m:entry.tile_attributes.width_m??null,
     width_valid:entry.tile_attributes.width_valid===undefined?null:entry.tile_attributes.width_valid==='true',label:entry.width_label};
    entry.width_checked=entry.tile_width.width_m===String(control.expected_width.width_m??'null')&&
     entry.tile_width.width_valid===control.expected_width.width_valid&&
     entry.tile_width.label===control.expected_width.label;
    if(!entry.width_checked)throw new Error('Rendered tile width properties or label differ from frozen expectation');
   }
   await page.screenshot({path:join(output,`detail-${caseId}.png`),fullPage:true});
   entry.raw_rendered_features=entry.detail_rendered_features;
   await Promise.all(pending);
   const gets=requests.filter(r=>r.method==='GET');
   if(!gets.length||gets.some(r=>r.status!==206||r.cors!=='*'||!r.completed||!r.range))throw new Error('Cross-origin partial reads failed');
   for(const r of gets){const asset=objects.get(r.object_path);verifyRangeResponse(r.range,r.content_range,r.body_bytes,asset.size_bytes);}
   if(requestedBytes>CEILING||responseBytes>CEILING)throw new Error('Per-case requested or transferred bytes exceeded ceiling');
   if(errors.length)throw new Error(errors.join('; '));
   entry.requests=requests;entry.requested_range_bytes=requestedBytes;entry.response_body_bytes=responseBytes;entry.transfer_ceiling_bytes=CEILING;entry.status='passed';
  }catch(error){await Promise.allSettled(pending);entry.status='failed';entry.error=error.message;entry.requests=requests;entry.requested_range_bytes=requestedBytes;entry.response_body_bytes=responseBytes;report.errors.push(`${caseId}: ${error.message}`);}
  report.cases.push(entry);await context.close();
 }
 report.status=report.errors.length?'failed':'passed';
}finally{await browser.close();await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({status:report.status,cases:report.cases.length,errors:report.errors}));
if(report.status!=='passed')process.exitCode=1;
