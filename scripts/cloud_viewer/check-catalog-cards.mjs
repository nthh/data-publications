#!/usr/bin/env node
// Preview the real Portolan card UI with local staged metadata; never deploy it.
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, join} from 'node:path';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright-core';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const option = name => {const i=process.argv.indexOf(name);if(i<0||!process.argv[i+1])throw new Error(`Missing ${name}`);return resolve(process.argv[i+1]);};
const stage=option('--stage'), out=option('--out');
const planBytes=await readFile(join(stage,'publish-plan.json')), plan=JSON.parse(planBytes);
const files=new Map();
for(const entry of plan.files){
  if(!entry.path.startsWith('catalog/')||entry.path.split('/').includes('..'))throw new Error('Invalid staged path');
  const bytes=await readFile(join(stage,entry.path));
  if(bytes.length!==entry.size_bytes||sha(bytes)!==entry.sha256)throw new Error('Stage differs from plan');
  files.set(entry.target_url,{bytes,entry});
}
const root=JSON.parse(await readFile(join(stage,'catalog/catalog.json'),'utf8'));
const self=root.links.find(link=>link.rel==='self').href;
const expected=[];
for(const link of root.links.filter(link=>link.rel==='child')){
  const url=new URL(link.href,self).href, file=files.get(url);
  if(!file)throw new Error('Missing staged collection');
  const collection=JSON.parse(file.bytes), thumbnail=Object.values(collection.assets).find(asset=>asset.roles?.includes('thumbnail'));
  expected.push({id:collection.id,title:collection.title,thumbnail:new URL(thumbnail.href,url).href,providers:collection.providers});
}
await mkdir(out,{recursive:false});
const report={schema_version:1,status:'failed',scope:'Official Portolan card UI with local staged metadata intercepted. No deployment, public-host check, or analytical revalidation.',stage_plan_sha256:sha(planBytes),cards:[],served_metadata:[],errors:[]};
let browser;
try{
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  report.browser_version=browser.version();
  const page=await browser.newPage({viewport:{width:1600,height:1200},deviceScaleFactor:1,serviceWorkers:'block'});
  page.on('pageerror',error=>report.errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=route.request().url(), file=files.get(url);
    if(file){
      report.served_metadata.push({url,sha256:file.entry.sha256,size_bytes:file.bytes.length});
      await route.fulfill({status:200,body:file.bytes,headers:{'content-type':url.endsWith('.png')?'image/png':url.endsWith('.json')?'application/json':'text/plain','access-control-allow-origin':'*'}});
    }else if(url.startsWith(new URL('.',self).href)||url.startsWith('https://data.source.coop/')){
      report.errors.push('Unplanned metadata or data request: '+url);await route.abort();
    }else await route.continue();
  });
  const parsed=new URL(self);
  await page.goto(`https://browser.portolan-sdi.org/#/external/${parsed.host}${parsed.pathname}`,{waitUntil:'domcontentloaded',timeout:60000});
  for(const expectedCard of expected){
    const card=page.locator('.catalog-card').filter({has:page.locator('a',{hasText:expectedCard.title})});
    await card.waitFor({state:'visible',timeout:60000});
    await card.scrollIntoViewIfNeeded();
    const image=card.locator('img.thumbnail');
    await page.waitForFunction(src=>[...document.querySelectorAll('.catalog-card img.thumbnail')]
      .some(img=>img.currentSrc===src&&img.complete&&img.naturalWidth>0),expectedCard.thumbnail,{timeout:15000});
    const details=await image.evaluate(img=>({src:img.currentSrc,width:img.naturalWidth,height:img.naturalHeight}));
    if(details.src!==expectedCard.thumbnail||!details.width)throw new Error('Card thumbnail does not match staged catalog');
    report.cards.push({...expectedCard,...details,sha256:files.get(details.src).entry.sha256,status:'loaded'});
  }
  await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:join(out,'catalog-cards.png'),fullPage:true,animations:'disabled'});
  report.screenshot_sha256=sha(await readFile(join(out,'catalog-cards.png')));
  if(report.errors.length)throw new Error('Browser errors occurred');
  report.status='rendered_pending_visual_review';
}catch(error){report.error=error.message;process.exitCode=1;}
finally{await browser?.close();await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');}
