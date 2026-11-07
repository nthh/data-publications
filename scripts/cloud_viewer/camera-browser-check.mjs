import {chromium} from 'playwright-core';
import {createHash} from 'node:crypto';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {verifyRangeResponse} from './src/core.js';
const option=(key,fallback)=>{const i=process.argv.indexOf('--'+key);return i<0?fallback:process.argv[i+1];};
const origin=new URL(option('url','http://127.0.0.1:8916')).origin;
const out=resolve(option('out','.local/camera-browser-check'));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
if(new URL(origin).hostname!=='127.0.0.1')throw new Error('Loopback browser check only');
const config=await(await fetch(origin+'/viewer-config.json')).json();
const build=Buffer.from(await(await fetch(origin+'/build.json')).arrayBuffer());
const objects=new Map(config.datasets.flatMap(dataset=>dataset.layers||[]).map(layer=>[layer.object_path,layer]));
const limit=32*1024*1024;
await mkdir(out,{recursive:false});
const report={schema_version:1,status:'running',scope:'Coverage camera constraint and restoration on dataset switches; local browser acceptance only',
  inputs:{viewer_build_sha256:hash(build),checker_sha256:hash(await readFile(new URL(import.meta.url)))},cases:[],errors:[],requests:[],requested_bytes:0,response_bytes:0,ceiling_bytes:limit};
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,
  args:['--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-background-networking','--no-first-run']});
const pending=[];
try{
  const context=await browser.newContext({viewport:{width:1500,height:1050},deviceScaleFactor:1,locale:'en-US'});
  const page=await context.newPage();
  await context.route('**/*',route=>{
    const request=route.request(),href=request.url();
    if(!/^https?:/.test(href))return route.continue();
    const url=new URL(href);
    if(url.hostname!=='127.0.0.1'){report.errors.push('Nonlocal request '+href);return route.abort();}
    if(url.origin===config.object_origin&&request.method()==='GET'){
      const asset=objects.get(url.pathname),range=/^bytes=(\d+)-(\d+)$/.exec(request.headers().range||'');
      const bytes=range?Number(range[2])-Number(range[1])+1:0;
      if(!asset||!range||bytes<1||Number(range[2])>=asset.size_bytes||report.requested_bytes+bytes>limit){report.errors.push('Invalid or excessive object range');return route.abort();}
      report.requested_bytes+=bytes;
    }
    return route.continue();
  });
  page.on('pageerror',error=>report.errors.push(error.message));
  page.on('response',response=>{
    const url=new URL(response.url()),request=response.request();
    if(url.origin!==config.object_origin||request.method()!=='GET')return;
    pending.push((async()=>{
      const headers=await response.allHeaders(),body=await response.body(),asset=objects.get(url.pathname);
      if(response.status()!==206||headers['access-control-allow-origin']!=='*'||await response.finished())throw new Error('Range response failed');
      verifyRangeResponse(request.headers().range,headers['content-range'],body.byteLength,asset.size_bytes);
      report.response_bytes+=body.byteLength;report.requests.push({path:url.pathname,status:206,bytes:body.byteLength});
    })().catch(error=>report.errors.push(error.message)));
  });
  await page.goto(origin+'/?dataset=grwl-raw&region=global',{waitUntil:'domcontentloaded'});
  for(const item of [{id:'raw-initial',dataset:'grwl-raw',zero:true},{id:'other-default',dataset:'hydrolakes',zero:false},{id:'raw-return',dataset:'grwl-raw',zero:true}]){
    await page.waitForFunction(()=>window.viewer,{},{timeout:60000});
    if(item.id!=='raw-initial')await page.evaluate(id=>window.viewer.selectDataset(id),item.dataset);
    await page.waitForFunction(id=>{const s=window.viewer.getState();return s.dataset===id&&s.phase==='ready'&&s.feature_count>0;},item.dataset,{timeout:60000});
    await page.evaluate(()=>window.viewer.setView([0,20],0));
    await page.waitForLoadState('networkidle',{timeout:30000});
    const actual=await page.evaluate(()=>({dataset:window.viewer.getState().dataset,zoom:window.viewer.getZoom(),center:window.viewer.getCenter(),phase:window.viewer.getState().phase}));
    if(actual.dataset!==item.dataset||actual.phase!=='ready'||(item.zero?Math.abs(actual.zoom)>1e-8:actual.zoom<0.1))throw new Error('Camera constraint switch failed: '+item.id);
    report.cases.push({...item,...actual,status:'passed'});
  }
  await Promise.all(pending);
  if(report.errors.length||!report.requests.length||report.response_bytes>limit)throw new Error('Browser/network regression check failed');
  report.status='passed';
}catch(error){report.status='failed';report.errors.push(error.message);}
finally{await browser.close();await Promise.allSettled(pending);if(report.errors.length)report.status='failed';await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});}
console.log(JSON.stringify({status:report.status,cases:report.cases.length,errors:report.errors}));
if(report.status!=='passed')process.exitCode=1;
