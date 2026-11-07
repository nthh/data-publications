import { chromium } from 'playwright-core';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { verifyRangeResponse } from './src/core.js';
import { grwlWidthAtZoom } from './src/core.js';

function option(name,fallback=null){const index=process.argv.indexOf('--'+name);return index<0?fallback:process.argv[index+1];}
const url=option('url');
const output=resolve(option('out'));
const scope=option('scope','global');
if(!url||!option('out'))throw new Error('Usage: node width-overview-browser-check.mjs --url http://127.0.0.1:8916/ --out NEW_OUTPUT_DIRECTORY [--scope global|pilot|synthetic] [--chrome PATH]');
if(!['global','pilot','synthetic'].includes(scope))throw new Error('--scope must be global, pilot, or synthetic');
await mkdir(output,{recursive:false});
const baseURL=new URL(url), localHosts=new Set(['127.0.0.1','localhost','[::1]']);
if(!['http:','https:'].includes(baseURL.protocol)||!localHosts.has(baseURL.hostname))throw new Error('--url must use a local HTTP(S) host');
const configResponse=await fetch(new URL('/viewer-config.json',baseURL));
if(!configResponse.ok)throw new Error('Could not read local viewer-config.json');
const config=await configResponse.json();
const dataset=config.datasets.find(candidate=>candidate.id==='grwl-raw'&&candidate.state==='prepared');
const layer=dataset?.layers.find(candidate=>candidate.overview?.mode==='width_samples');
if(!layer)throw new Error('Runtime configuration has no prepared GRWL width_samples layer');
const sourceLayer=layer.overview.source_layer;
const buildResponse=await fetch(new URL('/build.json',baseURL));
const buildBytes=buildResponse.ok?new Uint8Array(await buildResponse.arrayBuffer()):null;
const build=buildBytes?JSON.parse(new TextDecoder().decode(buildBytes)):null;
const fixedViews=[
  ...Array.from({length:13},(_,zoom)=>({name:'mississippi',center:[-90,35.51628964037926],zoom})),
  ...[0,3,7,8].map(zoom=>({name:'amazon',center:[-60,-3],zoom})),
  ...[3,7,8].map(zoom=>({name:'dateline',center:[-179.99965,71.197295],zoom})),
];
const views=scope==='pilot'?fixedViews.filter(view=>view.name==='mississippi'):fixedViews;
const maxBytes=32*1024*1024;
const report={schema_version:1,started_at:new Date().toISOString(),status:'running',scope:scope==='pilot'?'regional-pilot-only-mississippi-z0-to-z12':scope==='synthetic'?'synthetic-only-not-production-acceptance':'fixed-global-mississippi-amazon-dateline',fixture_scope:scope==='synthetic'?'synthetic-only-not-production-acceptance':undefined,transfer_ceiling_bytes:maxBytes,viewer_build_sha256:buildBytes?createHash('sha256').update(buildBytes).digest('hex'):null,app_js_sha256:build?.files?.['app.js']?.sha256??null,archive_sha256:layer.sha256??null,source_sha256:layer.analytic?.sha256??dataset.source_sha256??null,source_pins:dataset.source_pins??layer.source_pins??config.source_pins??{source_sha256:layer.analytic?.sha256??dataset.source_sha256??null},cases:[]};
const browser=await chromium.launch({executablePath:option('chrome','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-background-networking','--no-first-run']});
function rangeLength(value){const match=/^bytes=(\d+)-(\d+)$/.exec(value||'');return match?Number(match[2])-Number(match[1])+1:null;}
function evaluateExpression(expression,properties,zoom){
  if(!Array.isArray(expression))return expression;
  const [operator,...args]=expression;
  if(operator==='get')return properties[args[0]];
  if(operator==='zoom')return zoom;
  if(operator==='to-number'){
    const value=evaluateExpression(args[0],properties,zoom),number=Number(value);
    return value===null||value===undefined||value===''||!Number.isFinite(number)?evaluateExpression(args[1],properties,zoom):number;
  }
  if(operator==='*')return evaluateExpression(args[0],properties,zoom)*evaluateExpression(args[1],properties,zoom);
  if(operator==='>')return evaluateExpression(args[0],properties,zoom)>evaluateExpression(args[1],properties,zoom);
  if(operator==='!=')return evaluateExpression(args[0],properties,zoom)!==evaluateExpression(args[1],properties,zoom);
  if(operator==='==')return evaluateExpression(args[0],properties,zoom)===evaluateExpression(args[1],properties,zoom);
  if(operator==='all')return args.every(value=>evaluateExpression(value,properties,zoom));
  if(operator==='case'){
    for(let index=0;index<args.length-1;index+=2)if(evaluateExpression(args[index],properties,zoom))return evaluateExpression(args[index+1],properties,zoom);
    return evaluateExpression(args.at(-1),properties,zoom);
  }
  if(operator==='interpolate'){
    const input=evaluateExpression(args[1],properties,zoom),stops=args.slice(2);
    if(input<=stops[0])return evaluateExpression(stops[1],properties,zoom);
    for(let index=2;index<stops.length;index+=2){
      const high=stops[index],highValue=evaluateExpression(stops[index+1],properties,zoom),low=stops[index-2],lowValue=evaluateExpression(stops[index-1],properties,zoom);
      if(input<=high)return lowValue+(highValue-lowValue)*(input-low)/(high-low);
    }
    return evaluateExpression(stops.at(-1),properties,zoom);
  }
  throw new Error('Unsupported MapLibre style expression: '+operator);
}
try{
  for(const view of views){
    const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
    const page=await context.newPage(),requests=[],pageErrors=[],externalRequests=[],pending=[];
    const objectSizes=new Map([[new URL(layer.object_path,config.object_origin).href,layer.size_bytes]]);
    if(layer.analytic?.object_path)objectSizes.set(new URL(layer.analytic.object_path,config.object_origin).href,layer.analytic.size_bytes);
    let transferredBytes=0,requestedBytes=0;
    await context.route('**/*',async route=>{
      const request=route.request(),href=request.url();
      if(!href.startsWith('http:')&&!href.startsWith('https:'))return route.continue();
      const host=new URL(href).hostname;
      if(!localHosts.has(host)){externalRequests.push(href);return route.abort();}
      if(href.startsWith(config.object_origin+'/')&&request.method()==='GET'){
        const length=rangeLength(request.headers()['range']);
        if(length===null){pageErrors.push('Unbounded object request refused: '+href);return route.abort();}
        if(requestedBytes+length>maxBytes){pageErrors.push('Cold-case byte ceiling exceeded before request: '+href);return route.abort();}
        requestedBytes+=length;
      }
      return route.continue();
    });
    page.on('pageerror',error=>pageErrors.push(error.message));
    page.on('response',response=>{
      if(response.status()>=400)pageErrors.push('HTTP '+response.status()+' '+response.url());
      if(!response.url().startsWith(config.object_origin+'/'))return;
      const pendingResponse=(async()=>{
        const headers=await response.allHeaders(),request=response.request();
        const entry={url:response.url(),method:request.method(),status:response.status(),range:request.headers()['range']||null,content_range:headers['content-range']||null,content_length:Number(headers['content-length']||0),cors:headers['access-control-allow-origin']||null,object_size_bytes:objectSizes.get(response.url())};
        try{
          const body=await response.body();entry.body_bytes=body.byteLength;
          if(entry.method==='GET')transferredBytes+=entry.body_bytes;
          const failure=await response.finished();entry.completed=!failure;if(failure)entry.failure=String(failure);
        }catch(error){entry.completed=false;entry.failure=error.message;}
        requests.push(entry);
      })();pending.push(pendingResponse);
    });
    const target=new URL(url);target.searchParams.set('dataset','grwl-raw');target.searchParams.set('layer',layer.id);
    const entry={view:view.name,requested_zoom:view.zoom,requested_center:view.center,dataset_id:dataset.id,layer_id:layer.id,source_layer:sourceLayer,archive_sha256:layer.sha256,source_pins:report.source_pins,status:'running'};
    try{
      await page.goto(target.href,{waitUntil:'domcontentloaded',timeout:30000});
      await page.waitForFunction(()=>window.viewer&&window.viewer.getState().phase!=='starting',{},{timeout:30000});
      await page.evaluate(({center,zoom})=>window.viewer.setView(center,zoom),view);
      await page.evaluate(()=>window.viewer.waitForStableMapRender());
      await page.waitForFunction(()=>{
        const state=window.viewer.getState();return state.phase==='ready'||state.phase==='error';
      },{},{timeout:30000});
      const state=await page.evaluate(()=>window.viewer.getState());
      entry.actual_zoom=await page.evaluate(()=>window.viewer.getZoom());entry.actual_center=await page.evaluate(()=>window.viewer.getCenter());
      if(Math.abs(entry.actual_zoom-view.zoom)>1e-6)throw new Error('Map zoom differs from requested fixed view');
      const longitudeDelta=Math.abs(((entry.actual_center[0]-view.center[0]+540)%360)-180);
      if(longitudeDelta>1e-6||Math.abs(entry.actual_center[1]-view.center[1])>1e-6)throw new Error('Map center differs from requested fixed view');
      entry.viewer_state={phase:state.phase,feature_count:state.feature_count,error:state.error};
      if(state.phase!=='ready'||state.feature_count<1)throw new Error(state.error||'Stable map has no visible tile features');
      const layerNames=await page.evaluate(()=>window.viewer.getActiveStyleLayerNames());entry.style_layers=layerNames;
      const rendered=await page.evaluate(()=>window.viewer.getRenderedLayerNames());entry.rendered_source_layers=rendered;
      const paint=await page.evaluate(()=>window.viewer.getWidthSamplePaint());entry.width_sample_paint=paint;
      if(!(await page.locator('#grwl-width-legend').isVisible()))throw new Error('GRWL width legend is not visible');
      if(await page.locator('.width-legend-item').count()!==3)throw new Error('Width legend does not contain all three capped width references');
      if(!(await page.locator('#display-note').innerText()).includes('Selected observations; widest measured width per screen-scale cell'))throw new Error('Honest selected-observation label is missing');
      entry.legend_widths=await page.locator('.width-legend-line').evaluateAll(lines=>lines.map(line=>({metres:Number(line.dataset.metres),pixels:parseFloat(line.style.height)})));
      if(entry.legend_widths.length!==3||!(entry.legend_widths[0].pixels<entry.legend_widths[1].pixels&&entry.legend_widths[1].pixels<entry.legend_widths[2].pixels))throw new Error('Legend widths are not monotonically increasing from 50 m to 1,000 m');
      if(layerNames.includes('release-coverage'))throw new Error('Coverage-only fill layer is present in the width overview');
      const paintText=JSON.stringify(paint);
      for(const field of ['width_m','width_valid'])if(!paintText.includes(field))throw new Error('Overview style does not use '+field);
      const detail=view.zoom>=layer.detail_min_zoom;
      if(detail?(!layerNames.includes('release-lines')||layerNames.includes('release-width-samples')):(!layerNames.includes('release-width-samples')||layerNames.includes('release-lines')))throw new Error('Unexpected overview/detail style layer at zoom '+view.zoom);
      const expectedSourceLayer=detail?layer.source_layer:sourceLayer;
      if(!rendered.includes(expectedSourceLayer))throw new Error('Expected source layer is not rendered at zoom '+view.zoom);
      entry.legend_visible=true;entry.expected_layer=detail?'release-lines':'release-width-samples';
      const sample=detail?null:await page.evaluate(()=>window.viewer.getFirstRenderedWidthSample());
      if(!detail){
        if(!sample||!Number.isSafeInteger(sample.featureID)||sample.sourceLayer!==sourceLayer)throw new Error('Rendered overview sample has no exact MVT feature ID or source layer');
        entry.sample={featureID:sample.featureID,properties:sample.properties,geometry:sample.geometry,sourceLayer:sample.sourceLayer,screenPoint:sample.screenPoint,pagePoint:sample.pagePoint};
        const radius=evaluateExpression(paint.radius,sample.properties,entry.actual_zoom);
        const expectedWidth=sample.properties.width_m===1?0:sample.properties.width_m;
        const expectedDiameter=grwlWidthAtZoom(expectedWidth,entry.actual_zoom);
        entry.sample.diameter_px=radius*2;entry.sample.expected_diameter_px=expectedDiameter;
        if(Math.abs(entry.sample.diameter_px-expectedDiameter)>1e-9)throw new Error('Rendered sample circle diameter differs from its width stroke scale');
      }
      if(view.name==='mississippi'&&view.zoom===7){
        if(!Number.isFinite(sample.pagePoint?.x)||!Number.isFinite(sample.pagePoint?.y))throw new Error('Rendered sample has no page-relative click target');
        await page.mouse.click(sample.pagePoint.x,sample.pagePoint.y);
        await page.waitForFunction(id=>window.viewer.getState().selected?.id===id,sample.featureID,{timeout:10000});
        entry.click_zoom=await page.evaluate(()=>window.viewer.getZoom());
        if(Math.abs(entry.click_zoom-7)>1e-9)throw new Error('Selecting an overview sample incorrectly zoomed to detail');
        await page.locator('#feature-panel').waitFor({state:'visible'});
        await page.evaluate(()=>window.viewer.loadAllAttributes());
        await page.waitForFunction(()=>document.querySelector('#feature-note')?.textContent.startsWith('All source attributes'),{},{timeout:30000});
        const result=await page.evaluate(()=>({note:document.querySelector('#feature-note').textContent,properties:Object.fromEntries([...document.querySelectorAll('#properties dt')].map(node=>[node.textContent,node.nextElementSibling.textContent])),count:document.querySelectorAll('#properties dd').length}));
        const sourceFeatureID=Number(result.properties.feature_id);
        if(!Number.isSafeInteger(sourceFeatureID)||sourceFeatureID!==sample.featureID)throw new Error('Exact-ID source feature_id differs from the clicked MVT feature ID');
        entry.exact_id_lookup={featureID:sample.featureID,source_feature_id:sourceFeatureID,attribute_count:result.count,note:result.note,
          displayed_width:result.properties.width_m??null,overview_width:sample.properties.width_m??null,
          source_width_valid:result.properties.width_valid==='true',overview_width_valid:sample.properties.width_valid};
        const expected=layer.analytic?.fields?.filter(field=>field!==layer.analytic.geometry_column&&field!=='bbox').length;
        if(expected!==undefined&&result.count!==expected)throw new Error('Exact-ID lookup did not return every analytic source attribute');
        const width=sample.properties.width_m;
        const sourceWidth=result.properties.width_m==='null'?null:Number(result.properties.width_m);
        if(result.properties.width_valid!=='true'&&result.properties.width_valid!=='false')throw new Error('Exact-ID lookup returned an invalid width_valid value');
        if((result.properties.width_valid==='true')!==sample.properties.width_valid)throw new Error('Exact-ID source width_valid differs from selected overview width_valid');
        if(width!==undefined&&width!==null&&sourceWidth!==Number(width))throw new Error('Exact-ID source width differs from selected overview width');
        if((width===undefined||width===null)&&sample.properties.width_valid===false&&sourceWidth!==null&&sourceWidth>0&&sourceWidth!==1)throw new Error('Unknown overview sample resolved to a measured source width');
        if(!result.note.startsWith('All source attributes'))throw new Error('Overview feature did not resolve to all source attributes');
      }
      await page.screenshot({path:join(output,view.name+'-z'+view.zoom+'.png'),fullPage:true});
      await Promise.all(pending);
      const gets=requests.filter(request=>request.method==='GET');
      if(!gets.length||gets.some(response=>response.status!==206||!response.content_range||response.cors!=='*'||!response.completed))throw new Error('Object GETs did not complete as CORS-enabled HTTP 206 ranges');
      for(const response of gets){if(!response.object_size_bytes)throw new Error('Range request targeted an untracked object');verifyRangeResponse(response.range,response.content_range,response.body_bytes,response.object_size_bytes);if(response.content_length!==response.body_bytes)throw new Error('HTTP content-length differs from the received range body');}
      if(view.name==='mississippi'&&view.zoom===7&&layer.analytic?.object_path){
        const analyticURL=new URL(layer.analytic.object_path,config.object_origin).href;
        if(!gets.some(response=>response.url===analyticURL))throw new Error('Exact-ID lookup did not read the analytic source object');
      }
      if(transferredBytes>maxBytes)throw new Error('Cold-case byte ceiling exceeded');
      if(pageErrors.length||externalRequests.length)throw new Error('Browser or network errors were recorded');
      entry.transferred_bytes=transferredBytes;entry.requests=requests;entry.page_errors=pageErrors;entry.external_requests=externalRequests;entry.status='passed';
    }catch(error){entry.status='failed';entry.failure=error.message;entry.transferred_bytes=transferredBytes;entry.requests=requests;entry.page_errors=pageErrors;entry.external_requests=externalRequests;try{await page.screenshot({path:join(output,view.name+'-z'+view.zoom+'-failure.png'),fullPage:true});}catch{}}
    await Promise.allSettled(pending);report.cases.push(entry);
    await writeFile(join(output,'width-overview-validation.json'),JSON.stringify(report,null,2)+'\n');
    await context.close();
    console.log(JSON.stringify({view:view.name,zoom:view.zoom,status:entry.status,features:entry.viewer_state?.feature_count,transferred_bytes:entry.transferred_bytes,failure:entry.failure}));
  }
  report.status=report.cases.length===views.length&&report.cases.every(entry=>entry.status==='passed')?'passed':'failed';
  report.finished_at=new Date().toISOString();report.browser_version=browser.version();
  await writeFile(join(output,'width-overview-validation.json'),JSON.stringify(report,null,2)+'\n');
}finally{await browser.close();}
if(report.status!=='passed')process.exitCode=1;
