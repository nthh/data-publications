import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol, PMTiles } from 'pmtiles';
import * as duckdb from '@duckdb/duckdb-wasm';
import {formatBytes,decodeWKB,buildQuery,objectURL,jsonValue,graticule,quoteIdentifier,quoteValue,previewFields,attributeProjection,grwlLinePaint,GRWL_WIDTH_LEGEND,grwlWidthAtZoom,formatMeanWidth,rawWidthLabel,sourceBounds,sourceProperties,supportsExactIdLookup,buildAttributeLookupQuery} from './core.js';
import './style.css';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const names = {'grwl':'GRWL summary (errors)','grwl-raw':'GRWL raw observations','river-plastic-inputs':'River-plastic inputs','hydrolakes':'HydroLAKES','free-flowing-rivers':'Free-Flowing Rivers','lakeatlas':'LakeATLAS','gdw':'Global Dam Watch','swot_prior_lake_database':'SWOT Prior Lake'};
const state = {config:null,dataset:null,layer:null,phase:'starting',error:null,feature_count:0,capped:false,query:null,bbox:null,bytes:0,ranges:0,requests:0,generation:0,selected:null};
const trafficByURL = new Map();
let map, protocol, dataSource=null, activeMapLayers=[], queryBusy=false, pendingQuery=false, queryTimer, databasePromise;
let renderedFeatures=[];
let activeRegion=null;
performance.setResourceTimingBufferSize(4096);
performance.addEventListener('resourcetimingbufferfull',()=>performance.clearResourceTimings());
const session=crypto.randomUUID();
const channel=new BroadcastChannel('dataset-viewer-'+session);
function observeTraffic(entries) {
  if(!state.config)return;
  for(const entry of entries) {
    if(!entry.name?.startsWith(state.config.object_origin+'/'))continue;
    const current=trafficByURL.get(entry.name)||{bytes:0,ranges:0,requests:0};
    current.bytes+=entry.transferSize===0?0:(entry.encodedBodySize||0);
    current.ranges+=entry.responseStatus===206?1:0;current.requests++;
    trafficByURL.set(entry.name,current);
  }
  const total=[...trafficByURL.values()].reduce((x,y)=>({bytes:x.bytes+y.bytes,ranges:x.ranges+y.ranges,requests:x.requests+y.requests}),{bytes:0,ranges:0,requests:0});
  Object.assign(state,total);
  $('transfer-bytes').textContent=formatBytes(total.bytes);
  $('range-reads').textContent=total.ranges.toLocaleString()+' partial reads';
}
channel.onmessage=event=>observeTraffic(event.data);
new PerformanceObserver(list=>observeTraffic(list.getEntries().map(x=>x.toJSON()))).observe({type:'resource',buffered:true});
function status(phase,text,error=null) {
  state.phase=phase;state.error=error;
  $('map-status').textContent=text;
  $('load-view').disabled=!state.layer || state.layer.format!=='geoparquet' || phase==='loading';
  const message=phase==='error'||phase==='unavailable'||phase==='zoom';
  $('map-message').hidden=!message;
  $('map-message').classList.toggle('error',phase==='error');
  $('map-message').textContent=message?text:'';
}
function isGrwlDataset(){return state.dataset?.id==='grwl'||state.dataset?.id==='grwl-raw';}
function widthFieldForLayer(layer=state.layer){
  if(layer?.width_field&&(!layer.fields||layer.fields.includes(layer.width_field)))return layer.width_field;
  if(layer?.fields?.includes('width_mean')||state.dataset?.id==='grwl')return 'width_mean';
  return null;
}
function renderDatasetList() {
  $('dataset-list').replaceChildren();
  for(const dataset of state.config.datasets) {
    const button=document.createElement('button');button.className='dataset-button'+(dataset.state==='prepared'?'':' unavailable');
    button.dataset.dataset=dataset.id;button.setAttribute('aria-pressed',String(state.dataset?.id===dataset.id));
    const symbol=document.createElement('span');symbol.className='dataset-symbol';symbol.textContent=dataset.state!=='prepared'?'○':dataset.id.includes('lake')?'◒':dataset.id==='river-plastic-inputs'?'⠿':'≈';symbol.setAttribute('aria-hidden','true');
    const text=document.createElement('span'),title=document.createElement('span'),sub=document.createElement('span');
    title.className='dataset-label';title.textContent=names[dataset.id]||dataset.title;
    sub.className='dataset-subtitle';sub.textContent=dataset.state==='prepared'?(dataset.id==='grwl'?'Historical · known errors':dataset.id==='grwl-raw'?'Local preview · PMTiles':dataset.layers.some(x=>x.format==='pmtiles')?'PMTiles · display':'GeoParquet · analytic'):'Release unavailable';
    text.append(title,sub);button.append(symbol,text);button.addEventListener('click',()=>selectDataset(dataset.id));$('dataset-list').append(button);
  }
}
function renderInfo() {
  const dataset=state.dataset,layer=state.layer;
  $('active-title').textContent=names[dataset.id]||dataset.title;
  $('dataset-summary').textContent=dataset.summary||dataset.title;
  $('release-code').textContent=dataset.release||'Not built';
  $('file-size').textContent=layer?formatBytes(layer.size_bytes)+(layer.row_count?' · '+Number(layer.row_count).toLocaleString()+' rows':''):'—';
  $('load-view').hidden=!layer||layer.format!=='geoparquet';
  $('format-tag').textContent=layer?(layer.format==='pmtiles'?'PMTiles display derivative':'GeoParquet analytic data'):'—';
  $('credit').textContent=dataset.attribution||'Producer attribution is retained in the release package.';
  $('license').textContent=dataset.license||'See the release license and producer documentation.';
  const gee=dataset.gee||{};
  $('gee-label').textContent=gee.status==='passed_with_documented_geometry_difference'?'GEE compared · geometry differs':gee.status==='not_run_version_mismatch'?'GEE not compared · edition differs':'GEE not compared';
  $('gee-note').textContent=gee.summary||'No data comparison is recorded for this release.';
  $('file-url').value=layer?objectURL(state.config.object_origin,layer.object_path):'';
  $('file-hash').textContent=layer?.sha256||'—';$('copy-url').disabled=!layer;
  $('layer-switch').replaceChildren();
  if(dataset.layers.length>1) for(const candidate of dataset.layers) {
    const b=document.createElement('button');b.textContent=candidate.geometry_type==='point'?'Pour points':'Polygons';b.dataset.layer=candidate.id;b.setAttribute('aria-pressed',String(candidate.id===layer?.id));
    b.addEventListener('click',()=>selectLayer(candidate.id));$('layer-switch').append(b);
  }
  $('display-note').textContent=!layer?'No converted files are available for this dataset.':dataset.id==='grwl-raw'&&layer.format==='pmtiles'?(layer.overview?'Observation coverage at zooms 0–7; individual widths from zoom 8. Coverage cells are not riverbanks.':'Detailed river-width observations appear from zoom 8. Gaps remain; mapped segments are not joined.'):layer.format==='pmtiles'?'Generalized display tiles. Visible tile features can include fragments; use GeoParquet for analysis.':'Bounding-box selection · up to '+state.config.max_features.toLocaleString()+' features per view · screen geometry is 2D; source files stay unchanged.';
  const widthField=widthFieldForLayer(layer),rawWidth=widthField==='width_m';
  $('grwl-width-legend').hidden=!isGrwlDataset()||!widthField;
  $('grwl-width-title').textContent=rawWidth?'Observation width':'Mean channel width';
  $('grwl-width-legend').setAttribute('aria-label',rawWidth?'GRWL observation width legend':'GRWL mean width legend');
  $('grwl-width-note').textContent=rawWidth?'A value of 1 marks an unknown width. Strokes are exaggerated for legibility; gaps are shown as mapped.':'Widths above 1,000 m use the capped symbol. Strokes are exaggerated for legibility; they do not show literal riverbanks. Unknown widths use a thin muted stroke.';
  $('width-summary').hidden=!isGrwlDataset()||!state.selected||!widthField;
  $('width-label').textContent=rawWidth?'Observation width':'Mean channel width';
  updateGrwlLegend();
}
function clearData() {
  for(const id of activeMapLayers)if(map.getLayer(id))map.removeLayer(id);
  activeMapLayers=[];if(dataSource&&map.getSource(dataSource))map.removeSource(dataSource);dataSource=null;renderedFeatures=[];
  state.feature_count=0;state.capped=false;state.selected=null;$('feature-panel').hidden=true;
}
function addVisualLayers(source,kind,sourceLayer) {
  const ref={source,...(sourceLayer?{'source-layer':sourceLayer}:{})};
  if(kind==='polygon') {
    map.addLayer({id:'release-fill',type:'fill',...ref,paint:{'fill-color':'#428da4','fill-opacity':0.42}});
    map.addLayer({id:'release-outline',type:'line',...ref,paint:{'line-color':'#216d85','line-width':1,'line-opacity':0.8}});
    activeMapLayers=['release-fill','release-outline'];
  } else if(kind==='point') {
    const radius=state.dataset.id==='river-plastic-inputs'?['interpolate',['linear'],['log10',['+',1,['max',0,['coalesce',['get','i_mid'],0]]]],0,2,5,8]:4;
    map.addLayer({id:'release-points',type:'circle',...ref,paint:{'circle-color':'#216d85','circle-opacity':0.75,'circle-radius':radius,'circle-stroke-width':0.6,'circle-stroke-color':'#eff7f7'}});
    activeMapLayers=['release-points'];
  } else {
    const widthField=isGrwlDataset()?widthFieldForLayer():null;
    const paint=widthField?grwlLinePaint(widthField):{'line-color':'#216d85','line-opacity':0.8,'line-width':['interpolate',['linear'],['zoom'],0,0.45,8,1.2,13,2]};
    const overview=state.layer?.overview;
    if(overview){
      map.addLayer({id:'release-coverage',type:'fill',source,'source-layer':overview.source_layer,minzoom:0,maxzoom:state.layer.detail_min_zoom,
        paint:{'fill-color':'#216d85','fill-opacity':0.76,'fill-antialias':false}});
    }
    map.addLayer({id:'release-lines',type:'line',...ref,...(overview?{minzoom:state.layer.detail_min_zoom}:{}),paint});
    activeMapLayers=overview?['release-coverage','release-lines']:['release-lines'];
  }
}
function currentBounds() {
  const b=map.getBounds();
  return [Math.max(-180,b.getWest()),Math.max(-85,b.getSouth()),Math.min(180,b.getEast()),Math.min(85,b.getNorth())];
}
function setRegion(id) {
  const region=state.config.regions.find(x=>x.id===id);if(!region)return;
  activeRegion=id;
  for(const b of $('region-list').children)b.setAttribute('aria-pressed',String(b.dataset.region===id));
  map.fitBounds([[region.bbox[0],region.bbox[1]],[region.bbox[2],region.bbox[3]]],{padding:36,duration:0,maxZoom:12});
}
function chooseDefaultRegion(layer) {
  const requested=params.get('region');
  if(requested&&state.config.regions.some(x=>x.id===requested))return requested;
  if(layer?.default_region&&state.config.regions.some(x=>x.id===layer.default_region))return layer.default_region;
  return layer?.format==='geoparquet'?'southwest_europe':'global';
}
function updateCameraConstraint() {
  // Coverage must remain viewable at zoom 0 even when the canvas is wider
  // than one world tile. Keep a single world and permit the surrounding margin.
  map.setTransformConstrain(state.layer?.overview ? (center,zoom)=>({
    center:new maplibregl.LngLat(Math.max(-180,Math.min(180,center.lng)),Math.max(-85.0511287798066,Math.min(85.0511287798066,center.lat))),
    zoom:Math.max(map.getMinZoom(),Math.min(map.getMaxZoom(),zoom)),
  }) : null);
}
function selectDataset(id, layerID=null) {
  const dataset=state.config.datasets.find(x=>x.id===id);if(!dataset)return;
  state.generation++;clearTimeout(queryTimer);pendingQuery=false;clearData();state.dataset=dataset;state.layer=dataset.layers.find(x=>x.id===layerID)||dataset.layers[0]||null;
  updateCameraConstraint();renderDatasetList();renderInfo();
  if(!state.layer) {status('unavailable',dataset.unavailable_reason||'The source has not been converted into a local release.');return;}
  setRegion(chooseDefaultRegion(state.layer));
  loadLayer();
}
function selectLayer(id) {
  const candidate=state.dataset.layers.find(x=>x.id===id);if(!candidate)return;
  state.generation++;clearTimeout(queryTimer);pendingQuery=false;clearData();state.layer=candidate;updateCameraConstraint();renderInfo();loadLayer();
}
async function loadLayer() {
  const layer=state.layer;dataSource='release-data';
  if(layer.format==='pmtiles') {
    status('loading','Reading display tiles over HTTP…');
    const url=objectURL(state.config.object_origin,layer.object_path);protocol.add(new PMTiles(url));
    map.addSource(dataSource,{type:'vector',url:'pmtiles://'+url,...(Number.isFinite(layer.min_zoom)?{minzoom:layer.min_zoom}:{}),...(Number.isFinite(layer.max_zoom)?{maxzoom:layer.max_zoom}:{})});
    addVisualLayers(dataSource,layer.geometry_type,layer.source_layer);
  } else {
    map.addSource(dataSource,{type:'geojson',data:{type:'FeatureCollection',features:[]},maxzoom:14,tolerance:0.4});
    addVisualLayers(dataSource,layer.geometry_type);scheduleQuery();
  }
}
async function database() {
  if(!databasePromise)databasePromise=(async()=>{
    const worker=new Worker('/parquet.worker.js?session='+session);
    const db=new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING),worker);
    state.engine_step='instantiate';await db.instantiate('/vendor/duckdb-eh.wasm');
    state.engine_step='open';await db.open({maximumThreads:1,filesystem:{allowFullHTTPReads:false,forceFullHTTPReads:false,reliableHeadRequests:true}});
    state.engine_step='connect';const conn=await db.connect();
    state.engine_step='memory limit';await conn.query("SET memory_limit='384MB'");
    state.engine_step='load parquet extension';
    await conn.query('INSTALL parquet FROM '+quoteValue(location.origin+'/vendor/extensions'));
    await conn.query('LOAD parquet');
    state.engine_step='ready';
    return {db,conn,registered:new Set()};
  })();
  return databasePromise;
}
function scheduleQuery() {
  if(state.layer?.format!=='geoparquet')return;
  clearTimeout(queryTimer);queryTimer=setTimeout(loadViewport,350);
}
async function loadViewport() {
  if(state.layer?.format!=='geoparquet')return;
  if(queryBusy){pendingQuery=true;return;}
  const bbox=currentBounds();
  if(bbox[2]-bbox[0]>30||bbox[3]-bbox[1]>25){
    map.getSource(dataSource)?.setData({type:'FeatureCollection',features:[]});renderedFeatures=[];state.feature_count=0;$('feature-panel').hidden=true;
    status('zoom','Zoom in or choose a regional view to read a bounded part of this file.');return;
  }
  queryBusy=true;pendingQuery=false;const generation=state.generation,layer=state.layer;state.bbox=bbox;status('loading','Reading GeoParquet ranges in your browser…');
  const started=performance.now();
  try{
    const {db,conn,registered}=await database();
    const url=objectURL(state.config.object_origin,layer.object_path),filename=objectURL(state.config.object_origin,layer.object_path);
    state.engine_step='register HTTP file';if(!registered.has(filename)){await db.registerFileURL(filename,url,duckdb.DuckDBDataProtocol.HTTP,true);state.registered_files=await db.globFiles('*');
      const registeredFile=state.registered_files.find(file=>file.fileName===filename);
      if(!registeredFile||(registeredFile.allowFullHttpReads===true||registeredFile.forceFullHttpReads===true))throw new Error('The browser reader is not configured for partial HTTP reads');
      registered.add(filename);}
    const sql=buildQuery(layer,filename,bbox,state.config.max_features);state.query=sql;
    state.engine_step='query';const table=await conn.query(sql);
    if(generation!==state.generation)return;
    const rows=table.toArray(),capped=rows.length>state.config.max_features;
    const features=[];
    for(const row of rows.slice(0,state.config.max_features)){
      const raw=typeof row.toJSON==='function'?row.toJSON():{...row};
      const bytes=raw[layer.geometry_column];delete raw[layer.geometry_column];
      if(!bytes)continue;
      const geometry=decodeWKB(bytes);if(!geometry)continue;
      const properties=jsonValue(raw),id=String(properties[layer.id_field]);
      features.push({type:'Feature',id,properties,geometry});
    }
    renderedFeatures=features;state.feature_count=features.length;state.capped=capped;state.data_bbox=bbox;
    map.getSource(dataSource).setData({type:'FeatureCollection',features});
    const seconds=((performance.now()-started)/1000).toFixed(1);
    status('ready',features.length.toLocaleString()+(capped?' features shown · display limit reached':' bbox matches loaded')+' · '+seconds+' s');
    if(!features.length){$('map-message').hidden=false;$('map-message').textContent='No matching features here. Pan the map or choose another region.';}
  }catch(error){
    if(generation===state.generation)status('error','Could not read this file: '+error.message,error.message);
  }finally{
    queryBusy=false;
    if(pendingQuery&&state.layer?.format==='geoparquet'){pendingQuery=false;scheduleQuery();}
  }
}
function showProperties(properties, all=false) {
  $('properties').replaceChildren();
  for(const [key,value] of Object.entries(properties)){
    const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value===null?'null':typeof value==='object'?JSON.stringify(value):String(value);
    if(value===null)dd.className='null-value';$('properties').append(dt,dd);
  }
  $('feature-note').textContent=all?'All source attributes for this ID.':state.layer.format==='pmtiles'?'Properties from the displayed tile.':'Preview attributes. More columns can be read for this feature.';
}
function inspectFeature(feature) {
  if(!feature)return;
  if(feature.sourceLayer===state.layer?.overview?.source_layer){status('ready','Observation coverage · zoom to level 8 for individual widths and source attributes.');return;}
  const properties=sourceProperties(feature,state.layer),id=feature.id??properties[state.layer?.id_field];
  const p=properties;
  const bbox=state.layer?.format==='pmtiles'?sourceBounds(p):state.data_bbox;
  for(const key of ['_src_xmin','_src_ymin','_src_xmax','_src_ymax'])delete p[key];
  state.selected={id,properties,bbox};$('feature-title').textContent=id===undefined?'Feature':'Feature '+id;$('feature-panel').hidden=false;
  const widthField=widthFieldForLayer(),rawWidth=widthField==='width_m';
  $('width-summary').hidden=!isGrwlDataset()||!widthField;
  $('width-label').textContent=rawWidth?'Observation width':'Mean channel width';
  if(widthField)$('width-value').textContent=rawWidth?rawWidthLabel(properties[widthField]):formatMeanWidth(properties[widthField]);
  showProperties(properties);$('load-attributes').hidden=state.layer.format!=='geoparquet';$('load-attributes').disabled=false;$('load-attributes').textContent='Load all attributes';
  $('load-attributes').hidden=!canLoadAttributes(state.layer);
}
function canLoadAttributes(layer){return layer?.format==='geoparquet'||Boolean(layer?.analytic?.object_path&&layer.analytic?.fields&&(layer.analytic?.covering||supportsExactIdLookup(layer.analytic)));}
function belowDisplayMinZoom(){return state.layer?.format==='pmtiles'&&Number.isFinite(state.layer.min_zoom)&&map.getZoom()<state.layer.min_zoom;}
function showDisplayZoomStatus(){
  if(!belowDisplayMinZoom())return false;
  status('zoom','Zoom to level '+state.layer.min_zoom+' or closer to see detailed observations.');
  return true;
}
async function loadAllAttributes() {
  if(!state.selected||!canLoadAttributes(state.layer)||queryBusy)return;
  const generation=state.generation,displayLayer=state.layer,layer=displayLayer.format==='pmtiles'?displayLayer.analytic:displayLayer,id=state.selected.properties[displayLayer.id_field||layer.id_field];
  if(!supportsExactIdLookup(layer)&&!state.selected.bbox){$('feature-note').textContent='Could not locate this feature in the analytical source.';return;}
  $('load-attributes').disabled=true;$('load-attributes').textContent='Reading attributes…';queryBusy=true;
  try{
    const {db,conn,registered}=await database(),filename=objectURL(state.config.object_origin,layer.object_path);
    if(!registered.has(filename)){
      state.engine_step='register analytic HTTP file';
      await db.registerFileURL(filename,filename,duckdb.DuckDBDataProtocol.HTTP,true);
      const registeredFile=(await db.globFiles('*')).find(file=>file.fileName===filename);
      if(!registeredFile||(registeredFile.allowFullHttpReads===true||registeredFile.forceFullHttpReads===true))throw new Error('The analytical file is not configured for partial HTTP reads');
      registered.add(filename);
    }
    const table=await conn.query(buildAttributeLookupQuery(layer,filename,id,state.selected.bbox));
    if(generation!==state.generation)return;
    const rows=table.toArray();if(rows.length!==1)throw new Error(rows.length?'Feature lookup matched more than one source row':'Feature ID was not found in the analytical source');const row=rows[0];
    showProperties(jsonValue(row.toJSON()),true);$('load-attributes').hidden=true;
  }catch(error){if(generation!==state.generation)return;$('feature-note').textContent='Could not load attributes: '+error.message;$('load-attributes').disabled=false;$('load-attributes').textContent='Retry attributes';}
  finally{queryBusy=false;if(pendingQuery){pendingQuery=false;scheduleQuery();}}
}
async function start() {
  const response=await fetch('/viewer-config.json');if(!response.ok)throw new Error('Viewer configuration is unavailable');
  state.config=await response.json();
  const origin=params.get('objects')||state.config.object_origin;
  objectURL(origin,'/nthh/check');state.config.object_origin=new URL(origin).origin;
  $('object-origin').value=state.config.object_origin;
  $('connection-label').textContent=['127.0.0.1','localhost','[::1]'].includes(new URL(origin).hostname)?'Local object storage':'Remote object storage';
  $('ready-count').textContent=state.config.datasets.filter(x=>x.state==='prepared').length+' viewable';
  maplibregl.setWorkerCount(1);maplibregl.setWorkerUrl('/vendor/maplibre-gl-worker.mjs');protocol=new Protocol();maplibregl.addProtocol('pmtiles',protocol.tile);
  map=new maplibregl.Map({container:'map',center:[10,20],zoom:1,renderWorldCopies:false,attributionControl:false,style:{version:8,sources:{land:{type:'geojson',data:'/land.geojson'},grid:{type:'geojson',data:graticule()}},layers:[{id:'water',type:'background',paint:{'background-color':'#eef4f5'}},{id:'land',type:'fill',source:'land',paint:{'fill-color':'#e2e9e6'}},{id:'coast',type:'line',source:'land',paint:{'line-color':'#c1ceca','line-width':0.7}},{id:'grid',type:'line',source:'grid',paint:{'line-color':'#98b0b4','line-width':0.5,'line-opacity':0.24}}]}});
  map.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');map.addControl(new maplibregl.ScaleControl({maxWidth:110}),'bottom-left');map.addControl(new maplibregl.AttributionControl({compact:false,customAttribution:'Geographic context: Natural Earth · local release preview'}));
  for(const region of state.config.regions){
    const button=document.createElement('button');button.textContent=region.label;button.dataset.region=region.id;button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>setRegion(region.id));$('region-list').append(button);
  }
  map.on('moveend',()=>{const c=map.getCenter();$('map-coordinates').textContent=c.lng.toFixed(2)+'°, '+c.lat.toFixed(2)+'° · z'+map.getZoom().toFixed(1);scheduleQuery();});
  map.on('zoom',()=>{updateGrwlLegend();if(state.phase!=='loading'&&state.phase!=='error')showDisplayZoomStatus();});
  map.on('idle',()=>{
    if(state.layer?.format!=='pmtiles'||state.phase==='error'||!activeMapLayers.length)return;
    if(showDisplayZoomStatus())return;
    const visible=map.queryRenderedFeatures(undefined,{layers:activeMapLayers});state.feature_count=visible.length;
    status('ready',visible.length.toLocaleString()+' visible tile features · '+(state.layer.overview&&map.getZoom()<state.layer.detail_min_zoom?'observation coverage; zoom for widths':'display derivative'));
  });
  map.on('error',event=>{
    if(state.phase==='starting'||event.sourceId==='release-data'||event.error?.message?.includes('pmtiles'))status('error','Could not load the layer: '+event.error.message,event.error.message);
  });
  map.on('click',event=>{if(!activeMapLayers.length)return;const feature=map.queryRenderedFeatures(event.point,{layers:activeMapLayers})[0];if(feature?.sourceLayer===state.layer?.overview?.source_layer){map.jumpTo({center:event.lngLat,zoom:state.layer.detail_min_zoom});return;}inspectFeature(feature);});
  map.on('mousemove',event=>{map.getCanvas().style.cursor=activeMapLayers.length&&map.queryRenderedFeatures(event.point,{layers:activeMapLayers}).length?'pointer':'';});
  $('load-view').addEventListener('click',loadViewport);$('close-feature').addEventListener('click',()=>{$('feature-panel').hidden=true;});
  $('load-attributes').addEventListener('click',loadAllAttributes);
  $('copy-url').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('file-url').value);$('copy-url').textContent='Copied';setTimeout(()=>$('copy-url').textContent='Copy URL',1500);}catch{$('file-url').focus();$('file-url').select();}});
  $('apply-origin').addEventListener('click',()=>{try{objectURL($('object-origin').value,'/nthh/check');const url=new URL(location.href);url.searchParams.set('objects',$('object-origin').value);location.href=url;}catch(error){$('connection-error').textContent=error.message;}});
  window.viewer={
    getState:()=>({...state,dataset:state.dataset?.id,layer:state.layer?.id,config:undefined,selected:state.selected?{id:state.selected.id}:null,traffic:[...trafficByURL.entries()]}),
    selectDataset,selectLayer,setRegion,loadViewport,
    setView:(center,zoom)=>map.jumpTo({center,zoom}),
    getZoom:()=>map.getZoom(),
    getCenter:()=>{const center=map.getCenter();return [center.lng,center.lat];},
    getRenderedLayerNames:()=>[...new Set(map.queryRenderedFeatures(undefined,{layers:activeMapLayers}).map(f=>f.sourceLayer))],
    focusBounds:bbox=>map.fitBounds([[bbox[0],bbox[1]],[bbox[2],bbox[3]]],{padding:36,duration:0,maxZoom:12}),
    inspectFirstFeature:()=>inspectFeature(renderedFeatures[0]||map.queryRenderedFeatures(undefined,{layers:activeMapLayers})[0]),
    loadAllAttributes,
    inspectFeatureById:id=>{
      const feature=map.queryRenderedFeatures(undefined,{layers:activeMapLayers}).find(candidate=>candidate.id===id);
      if(!feature)throw new Error('Requested source feature is not rendered: '+id);
      inspectFeature(feature);
    },
    getActiveLineWidthExpression:()=>map.getPaintProperty('release-lines','line-width')||null,
    switchFirstLayer:()=>{const candidate=state.dataset?.layers[0];if(candidate)selectLayer(candidate.id);},
  };
  await new Promise(resolve=>map.once('load',resolve));
  const legend=$('grwl-width-legend').querySelector('.width-legend-items');
  for(const item of GRWL_WIDTH_LEGEND){const sample=document.createElement('div');sample.className='width-legend-item';const line=document.createElement('i');line.className='width-legend-line';line.dataset.metres=String(item.metres);const label=document.createElement('span');label.textContent=item.metres===1000?'≥1,000 m':item.metres+' m';sample.append(line,label);legend.append(sample);}
  updateGrwlLegend();
  selectDataset(params.get('dataset')||state.config.datasets.find(x=>x.state==='prepared').id,params.get('layer'));
}
function updateGrwlLegend(){
  if(!map)return;
  const zoom=map.getZoom();
  $('grwl-width-legend').hidden=!isGrwlDataset()||!widthFieldForLayer()||Boolean(state.layer?.overview&&zoom<state.layer.detail_min_zoom);
  for(const line of document.querySelectorAll('.width-legend-line'))line.style.height=grwlWidthAtZoom(Number(line.dataset.metres),zoom)+'px';
}
start().catch(error=>{status('error',error.message,error.message);console.error(error);});
