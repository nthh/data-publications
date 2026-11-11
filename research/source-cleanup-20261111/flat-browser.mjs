import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const root=process.cwd();
const modules=process.env.FLAT_VIEWER_MODULES || '/Users/nathan/.folia-fleets/source-publication-20261106/tree/scripts/cloud_viewer/node_modules';
const {chromium}=await import(pathToFileURL(path.join(modules,'playwright-core/index.mjs')).href);
const plan=JSON.parse(await readFile('research/source-cleanup-20261111/flat-plan.json','utf8'));
const selected=process.env.FLAT_TEST_DATASETS?.split(',');
const allowed=new Map(plan.files.map(row=>[row.url,row]));
const html=`<!doctype html><html><head><link rel="stylesheet" href="/maplibre/maplibre-gl.css"><style>html,body,#map{margin:0;width:100%;height:100%}</style></head><body><div id="map"></div><script src="/pmtiles.js"></script><script type="module">
import * as maplibre from '/maplibre/maplibre-gl.mjs';
maplibre.setWorkerCount(1); maplibre.setWorkerUrl('/maplibre/maplibre-gl-worker.mjs');
const protocol=new pmtiles.Protocol();maplibre.addProtocol('pmtiles',protocol.tile);
window.start=(style,center,zoom)=>{window.map=new maplibre.Map({container:'map',style,center,zoom,renderWorldCopies:false,attributionControl:false,preserveDrawingBuffer:true});window.errors=[];map.on('error',e=>window.errors.push(String(e.error)));};
window.ready=true;
</script></body></html>`;
const server=createServer(async(req,res)=>{try{
 let bytes,type='application/javascript';
 const route=new URL(req.url,'http://localhost').pathname;
 if(route==='/'){bytes=Buffer.from(html);type='text/html';}
 else if(route==='/pmtiles.js')bytes=await readFile(path.join(modules,'pmtiles/dist/pmtiles.js'));
 else if(/^\/maplibre\/[A-Za-z0-9._-]+$/.test(route)){bytes=await readFile(path.join(modules,'maplibre-gl/dist',path.basename(route)));if(route.endsWith('.css'))type='text/css';}
 else{res.writeHead(404);res.end();return;}
 res.writeHead(200,{'Content-Type':type,'Content-Length':bytes.length});res.end(bytes);
}catch{res.writeHead(500);res.end();}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=`http://127.0.0.1:${server.address().port}`;
const output=process.argv[2] || 'research/source-cleanup-20261111/flat-browser-report.json';
const report={schema_version:1,status:'running',checked_at:new Date().toISOString(),viewer:'MapLibre GL 6.16.0 with PMTiles 4.5.0',selected_datasets:selected||null,scope:'Live flat Source URLs; loopback UI. This is not a Portolan Browser navigation check.',cases:[]};
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-background-networking','--no-first-run']});
let reserved=0;
try{
 for(const style of plan.files.filter(r=>r.operation==='rewrite_style'&&(!selected||selected.includes(r.dataset_id)))){
  const views=style.dataset_id==='grwl-raw'?[{center:[-90,35.51628964037926],zoom:3},{center:[-90,35.51628964037926],zoom:9}]:[{center:style.dataset_id==='river-plastic-inputs'?[-60,-5]:[-86,45],zoom:3}];
  for(const view of views){
   const context=await browser.newContext({viewport:{width:1024,height:768},deviceScaleFactor:1});
   const page=await context.newPage();const errors=[],responses=[],pending=[];
   await context.route('**/*',async route=>{
    const request=route.request(),url=request.url();
    if(url.startsWith(base+'/'))return route.continue();
    const row=allowed.get(url);
    if(!row){errors.push('Unplanned URL: '+url);return route.abort();}
    const method=request.method();if(method==='HEAD'||method==='OPTIONS')return route.continue();
    if(method!=='GET'){errors.push('Unexpected method');return route.abort();}
    let size=row.size_bytes;
    const range=request.headers()['range'];
    if(range){const match=/^bytes=(\d+)-(\d+)$/.exec(range);if(!match){errors.push('Unbounded range');return route.abort();}size=Number(match[2])-Number(match[1])+1;}
    if((row.filename.endsWith('.pmtiles')&&!range)||size>16*1024*1024||reserved+size>512*1024*1024){errors.push('Transfer bound exceeded');return route.abort();}
    reserved+=size;return route.continue();
   });
   page.on('pageerror',e=>errors.push(e.message));
   page.on('response',response=>{if(!allowed.has(response.url()))return;pending.push((async()=>{const h=await response.allHeaders();const method=response.request().method();const range=response.request().headers()['range'];if(response.status()>=400)errors.push('HTTP '+response.status());if(h['access-control-allow-origin']!=='*'&&h['access-control-allow-origin']!==base)errors.push('Missing CORS');if(range&&response.status()!==206)errors.push('Range not honored');responses.push({url:response.url(),method,status:response.status(),range:range||null,content_range:h['content-range']||null,content_length:h['content-length']||null});})());});
   const item={dataset_id:style.dataset_id,style:style.filename,...view,status:'running'};report.cases.push(item);
   try{
    await page.goto(base);await page.waitForFunction(()=>window.ready===true);
    await page.evaluate(args=>window.start(args.style,args.center,args.zoom),{style:style.url,...view});
    await page.waitForFunction(()=>window.map?.loaded()&&window.map.areTilesLoaded()&&window.map.queryRenderedFeatures().length>0,{},{timeout:90000});
    item.features=await page.evaluate(()=>window.map.queryRenderedFeatures().length);
    errors.push(...await page.evaluate(()=>window.errors));
    await Promise.all(pending);
    if(errors.length)throw new Error(errors.join('; '));
    const image=await page.screenshot();
    await mkdir('.local/source-cleanup-20261111/browser',{recursive:true});
    const screenshot=`.local/source-cleanup-20261111/browser/${style.filename}-z${view.zoom}.png`;
    await writeFile(screenshot,image);item.screenshot={path:screenshot,sha256:createHash('sha256').update(image).digest('hex')};
    item.status='passed';
   }catch(e){item.status='failed';item.error=e.message;}
   item.responses=responses;item.errors=errors;
   await context.close();await writeFile(output,JSON.stringify(report,null,2)+'\n');
  }
 }
 report.status=report.cases.every(x=>x.status==='passed')?'passed':'failed';report.requested_source_bytes=reserved;
}finally{await browser.close();server.close();await writeFile(output,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({status:report.status,cases:report.cases.length,requested_source_bytes:reserved}));
if(report.status!=='passed')process.exitCode=1;
