// Reproduce these two views without modifying the live viewer or its source data.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const option=(key,fallback)=>{const i=process.argv.indexOf('--'+key);return i<0?fallback:process.argv[i+1];};
const here=fileURLToPath(new URL('.',import.meta.url));
const {chromium}=await import(pathToFileURL(resolve(option('playwright',join(here,'../../scripts/cloud_viewer/node_modules/playwright-core/index.mjs')))));
const url=option('url','http://127.0.0.1:8910/');
const out=resolve(option('out',join(here,'browser')));
const criteriaBytes=await readFile(join(here,'followup-criteria.json'));
const criteria=JSON.parse(criteriaBytes);
const config=await (await fetch(new URL('/viewer-config.json',url))).json();
const layer=config.datasets.find(d=>d.id==='grwl').layers[0];
const report={schema_version:1,recorded_at:new Date().toISOString(),criteria_sha256:createHash('sha256').update(criteriaBytes).digest('hex'),
  scope:'Unchanged live app; test-browser-only viewer-config interception adds frozen regions. Local range reads only.',
  source_layer:layer,cases:[]};
await mkdir(out,{recursive:false});
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-background-networking','--no-first-run']});
try{
 for(const region of criteria.browser_regions){
  const context=await browser.newContext({viewport:{width:1500,height:1050},deviceScaleFactor:1});
  const page=await context.newPage();
  const errors=[],requests=[],pending=[];let bytes=0;
  const entry={region,errors,requests,status:'running'};
  await context.route('**/*',async route=>{
   const request=route.request(),address=new URL(request.url());
   if(!['http:','https:'].includes(address.protocol))return route.continue();
   if(address.hostname!=='127.0.0.1'){errors.push('External request refused: '+address.href);return route.abort();}
   if(address.pathname==='/viewer-config.json')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...config,regions:[...config.regions,...criteria.browser_regions]})});
   if(address.origin===config.object_origin&&request.method()==='GET'&&(!request.headers()['range']||bytes>128*1024*1024)){errors.push('Non-range or over-budget read refused');return route.abort();}
   return route.continue();
  });
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{
   if(!response.url().startsWith(config.object_origin+'/')||response.request().method()!=='GET')return;
   pending.push((async()=>{const headers=await response.allHeaders();const n=Number(headers['content-length']||0);bytes+=n;requests.push({url:response.url(),status:response.status(),range:response.request().headers()['range'],content_range:headers['content-range'],bytes:n,cors:headers['access-control-allow-origin']});await response.finished();})());
  });
  try{
   await page.goto(new URL('?dataset=grwl&region='+region.id,url).href,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>window.viewer?.getState().phase==='ready'&&window.viewer.getState().feature_count>0,{},{timeout:60000});
   await page.evaluate(id=>window.viewer.inspectFeatureById(id),region.feature_id);
   await page.locator('#feature-panel').waitFor({state:'visible'});
   entry.viewer=await page.evaluate(()=>window.viewer.getState());
   entry.tile_properties=await page.locator('#properties').innerText();
   await page.evaluate(()=>window.viewer.loadAllAttributes());
   entry.analytic_properties=await page.locator('#properties').innerText();
   entry.analytic_note=await page.locator('#feature-note').innerText();
   if(!entry.analytic_note.startsWith('All source attributes'))throw new Error('Analytic lookup incomplete');
   await page.screenshot({path:join(out,'feature-'+region.feature_id+'.png'),fullPage:true});
   await Promise.all(pending);
   if(errors.length||!requests.length||requests.some(r=>r.status!==206||!r.content_range||r.cors!=='*')||bytes>128*1024*1024)throw new Error('Local range/network checks failed');
   entry.status='passed';
  }catch(error){entry.status='failed';entry.failure=error.message;await page.screenshot({path:join(out,'failure-'+region.feature_id+'.png'),fullPage:true});}
  entry.response_body_bytes=bytes;report.cases.push(entry);
  console.log(JSON.stringify({id:region.feature_id,status:entry.status,bytes,selected:entry.viewer?.selected,failure:entry.failure}));
  await context.close();
 }
 report.browser_version=browser.version();
 report.status=report.cases.every(c=>c.status==='passed')?'passed':'failed';
 await writeFile(join(out,'browser-evidence.json'),JSON.stringify(report,null,2)+'\n');
}finally{await browser.close();}
if(report.status!=='passed')process.exitCode=1;
