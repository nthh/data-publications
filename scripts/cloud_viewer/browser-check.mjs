import { verifyRangeResponse } from './src/core.js';
import { chromium } from 'playwright-core';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';

function option(name,fallback=null){const i=process.argv.indexOf('--'+name);return i<0?fallback:process.argv[i+1];}
function displayedNumber(value){const match=String(value).replaceAll(',','').match(/[+-]?(?:\d+\.?\d*|\.\d+)/);return match?Number(match[0]):NaN;}
const url=option('url','http://127.0.0.1:8910/');
const output=resolve(option('out'));
await mkdir(output,{recursive:false});
const config=await (await fetch(new URL('/viewer-config.json',url))).json();
const datasetFilter=option('dataset');
const regionalByDataset={'grwl':'north_america','river-plastic-inputs':'atlantic_coast','hydrolakes':'north_america','free-flowing-rivers':'north_america','lakeatlas':'north_america'};
const cases=config.datasets.filter(x=>x.state==='prepared'&&(!datasetFilter||datasetFilter===x.id)).flatMap(dataset=>dataset.layers.flatMap(layer=>['global',regionalByDataset[dataset.id]||'north_america',...(dataset.id==='grwl'?['dateline']:[])].map(region=>({dataset,layer,region}))));
const report={schema_version:1,started_at:new Date().toISOString(),status:'running',scope:'Installed Chrome, fresh browser context for every layer, direct cross-origin object reads; local hosting only.',transfer_ceiling_bytes:128*1024*1024,cases:[]};
const browser=await chromium.launch({executablePath:option('chrome','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader','--disable-background-networking','--no-first-run']});
try{
  for(const {dataset,layer,region} of cases){
    const context=await browser.newContext({viewport:{width:1500,height:1050},deviceScaleFactor:1});
    const page=await context.newPage(),requests=[],errors=[],external=[],pending=[];
    let declaredBytes=0;
    const objectSizes=new Map();
    for(const candidate of dataset.layers){objectSizes.set(new URL(candidate.object_path,config.object_origin).href,candidate.size_bytes);if(candidate.analytic?.object_path)objectSizes.set(new URL(candidate.analytic.object_path,config.object_origin).href,candidate.analytic.size_bytes);}
    await context.route('**/*',route=>{
      const request=route.request(),href=request.url();
      if(!href.startsWith('http:')&&!href.startsWith('https:'))return route.continue();
      if(new URL(href).hostname!=='127.0.0.1'){external.push(href);return route.abort();}
      if(href.startsWith(config.object_origin+'/')&&request.method()==='GET'){
        if(!request.headers()['range']){errors.push('Whole-file GET refused by evaluation guard: '+href);return route.abort();}
        if(declaredBytes>report.transfer_ceiling_bytes){errors.push('Transfer ceiling exceeded');return route.abort();}
      }
      return route.continue();
    });
    page.on('pageerror',error=>errors.push(error.message));
    page.on('response',response=>{
      if(response.status()>=400)errors.push('HTTP '+response.status()+' '+response.url());
      if(!response.url().startsWith(config.object_origin+'/'))return;
      const promise=(async()=>{
        const headers=await response.allHeaders(),method=response.request().method();
        const entry={url:response.url(),method,status:response.status(),range:response.request().headers()['range']||null,content_range:headers['content-range']||null,content_length:Number(headers['content-length']||0),cors:headers['access-control-allow-origin']||null,object_size_bytes:objectSizes.get(response.url())};
        if(method==='GET')declaredBytes+=entry.content_length;
        const failure=await response.finished();entry.completed=!failure;if(failure)entry.failure=String(failure);
        requests.push(entry);
      })();pending.push(promise);
    });
    const target=new URL(url);target.searchParams.set('dataset',dataset.id);target.searchParams.set('layer',layer.id);target.searchParams.set('region',region);
    const entry={dataset_id:dataset.id,layer_id:layer.id,format:layer.format,source_sha256:layer.sha256,source_size_bytes:layer.size_bytes,region,region_bbox:config.regions.find(candidate=>candidate.id===region).bbox,status:'running'};
    try{
      await page.goto(target.href,{waitUntil:'domcontentloaded',timeout:30000});
      await page.waitForFunction(()=>window.viewer&&(window.viewer.getState().phase==='error'||window.viewer.getState().phase==='ready'&&window.viewer.getState().feature_count>0),{},{timeout:60000});
      entry.viewer=await page.evaluate(()=>window.viewer.getState());
      if(entry.viewer.phase!=='ready'||entry.viewer.feature_count<=0)throw new Error(entry.viewer.error||'No visible data');
      if(dataset.id==='grwl'&&region==='dateline'){
        await page.evaluate(()=>window.viewer.inspectFeatureById(28938));
        entry.inspected_source_id=28938;
      }else await page.evaluate(()=>window.viewer.inspectFirstFeature());
      await page.locator('#feature-panel').waitFor({state:'visible'});
      entry.inspected_property_count=await page.locator('#properties dd').count();
      if(!entry.inspected_property_count)throw new Error('Feature properties unavailable');
      if(dataset.id==='grwl'){
        const widthExpression=await page.evaluate(()=>window.viewer.getActiveLineWidthExpression());
        entry.active_width_expression=widthExpression;
        if(!JSON.stringify(widthExpression).includes('width_mean'))throw new Error('Active GRWL line paint does not use width_mean');
        if(await page.locator('#grwl-width-legend').isHidden())throw new Error('GRWL width legend is not visible');
        if(await page.locator('.width-legend-item').count()!==3)throw new Error('GRWL legend does not show the three measured-width symbols');
        entry.clicked_mean_width=await page.locator('#width-summary').innerText();
        entry.tile_mean_width=displayedNumber(await page.evaluate(()=>{
          const label=[...document.querySelectorAll('#properties dt')].find(node=>node.textContent==='width_mean');
          return label?.nextElementSibling?.textContent??null;
        }));
        if(!Number.isFinite(entry.tile_mean_width))throw new Error('GRWL tile width summary is not numeric');
      }
      entry.initial_view_body_bytes=declaredBytes;
      if(layer.format==='geoparquet'||layer.analytic?.object_path){
        await page.evaluate(()=>window.viewer.loadAllAttributes());
        entry.all_attributes_note=await page.locator('#feature-note').innerText();
        entry.all_attribute_count=await page.locator('#properties dd').count();
        if(!entry.all_attributes_note.startsWith('All source attributes')||entry.all_attribute_count<entry.inspected_property_count)throw new Error('All-attributes inspection failed');
        if(layer.analytic?.fields){
          const expected=layer.analytic.fields.filter(field=>field!==layer.analytic.geometry_column&&field!=='bbox').length;
          entry.expected_source_attribute_count=expected;
          if(entry.all_attribute_count!==expected)throw new Error('All-attributes lookup did not return every declared source field');
        }
        if(dataset.id==='grwl'){
          const displayed=await page.evaluate(()=>{
            const label=[...document.querySelectorAll('#properties dt')].find(node=>node.textContent==='width_mean');
            return label?.nextElementSibling?.textContent??null;
          });
          entry.analytic_mean_width=displayedNumber(displayed);
          entry.decimal_width_matches=Number.isFinite(entry.analytic_mean_width)&&Math.abs(entry.analytic_mean_width-entry.tile_mean_width)<1e-9;
          if(!entry.decimal_width_matches)throw new Error('GRWL all-attributes width_mean differs from the displayed tile width');
          if(region==='dateline'&&entry.inspected_source_id===28938&&entry.analytic_mean_width!==97)throw new Error('GRWL dateline source 28938 width_mean is not 97 m');
        }
      }
      if(dataset.id==='lakeatlas'&&dataset.layers.length>1){
        const other=dataset.layers.find(candidate=>candidate.id!==layer.id);
        await page.evaluate(id=>window.viewer.selectLayer(id),other.id);
        await page.waitForFunction(()=>window.viewer.getState().phase==='ready'&&window.viewer.getState().feature_count>0,{},{timeout:60000});
        await page.evaluate(()=>window.viewer.inspectFirstFeature());
        await page.locator('#feature-panel').waitFor({state:'visible'});
        await page.evaluate(()=>window.viewer.loadAllAttributes());
        const switchNote=await page.locator('#feature-note').innerText(),switchCount=await page.locator('#properties dd').count();
        if(!switchNote.startsWith('All source attributes')||switchCount!==other.analytic.fields.filter(field=>field!==other.analytic.geometry_column&&field!=='bbox').length)throw new Error('Layer switch click and all-attributes lookup failed');
        entry.layer_switch_lookup_passed=true;
      }
      await page.screenshot({path:join(output,layer.id+'-'+region+'.png'),fullPage:true});
      await Promise.all(pending);
      const gets=requests.filter(x=>x.method==='GET');
      if(!gets.length||gets.some(x=>x.status!==206||!x.content_range||x.cors!=='*'||!x.completed))throw new Error('Data GETs did not all complete as cross-origin 206 range responses');
      for(const response of gets){if(!response.object_size_bytes)throw new Error('Range request targeted an untracked object');verifyRangeResponse(response.range,response.content_range,response.content_length,response.object_size_bytes);}
      if(declaredBytes>report.transfer_ceiling_bytes)throw new Error('Transfer ceiling exceeded');
      if(layer.format==='geoparquet'&&declaredBytes>=layer.size_bytes)throw new Error('Analytical object was not read partially');
      if(layer.analytic?.object_path){const analyticGets=gets.filter(response=>response.url===new URL(layer.analytic.object_path,config.object_origin).href);if(!analyticGets.length)throw new Error('Analytic attribute lookup did not read its GeoParquet object');if(analyticGets.reduce((sum,response)=>sum+response.content_length,0)>=layer.analytic.size_bytes)throw new Error('Analytic attributes required a full-object read');}
      if(errors.length||external.length)throw new Error('Browser/network errors were recorded');
      await page.waitForFunction(expected=>window.viewer.getState().bytes===expected,declaredBytes,{timeout:5000});
      entry.ui_bytes_after_inspection=(await page.evaluate(()=>window.viewer.getState())).bytes;
      if(layer.format==='geoparquet'){
        await page.evaluate(()=>window.viewer.setRegion('global'));
        await page.waitForFunction(()=>window.viewer.getState().phase==='zoom'&&window.viewer.getState().feature_count===0,{},{timeout:5000});
        entry.wide_view_guard_passed=true;
      }
      if(dataset.id==='grwl'){
        for(const id of ['gdw','swot_prior_lake_database']){
          await page.evaluate(id=>window.viewer.selectDataset(id),id);
          const candidate=await page.evaluate(()=>window.viewer.getState());
          if(candidate.phase!=='unavailable'||candidate.feature_count!==0)throw new Error('Unbuilt dataset did not show its unavailable state');
        }
        entry.unavailable_datasets_checked=true;
      }
      entry.status='passed';
    }catch(error){entry.status='failed';entry.failure=error.message;try{entry.viewer=await page.evaluate(()=>window.viewer?.getState());await page.screenshot({path:join(output,layer.id+'-'+region+'-failure.png'),fullPage:true});}catch{}}
    await Promise.allSettled(pending);
    entry.requests=requests;entry.response_body_bytes=declaredBytes;entry.page_errors=errors;entry.external_requests=external;
    report.cases.push(entry);await context.close();
    await writeFile(join(output,'browser-validation.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({dataset_id:dataset.id,layer_id:layer.id,region,status:entry.status,features:entry.viewer?.feature_count,body_bytes:declaredBytes,requests:requests.length,failure:entry.failure}));
  }
  report.status=report.cases.length>0&&report.cases.every(x=>x.status==='passed')?'passed':'failed';
  report.finished_at=new Date().toISOString();report.browser_version=browser.version();
  await writeFile(join(output,'browser-validation.json'),JSON.stringify(report,null,2)+'\n');
}finally{await browser.close();}
if(report.status!=='passed')process.exitCode=1;
