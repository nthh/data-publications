export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1000) return Math.round(bytes) + ' B';
  const unit = Math.min(Math.floor(Math.log10(bytes) / 3), 3);
  return (bytes / 1000 ** unit).toFixed(unit === 1 ? 0 : 2) + ' ' + ['B','kB','MB','GB'][unit];
}
export function quoteIdentifier(name) {
  if (typeof name !== 'string' || !name || name.includes('\0')) throw new Error('Invalid column name');
  return '"' + name.replaceAll('"', '""') + '"';
}
export function quoteValue(value) {
  return "'" + String(value).replaceAll("'", "''") + "'";
}
export function attributeProjection(layer) {
  const decimalFields=new Set(layer.decimal_fields||[]);
  return layer.fields.filter(name=>name!==layer.geometry_column&&name!=='bbox').map(name=>{
    const identifier=quoteIdentifier(name);
    return decimalFields.has(name)?'CAST('+identifier+' AS VARCHAR) AS '+identifier:identifier;
  }).join(', ');
}
export function validBbox(bbox) {
  if (!Array.isArray(bbox) || bbox.length !== 4 || !bbox.every(Number.isFinite)) throw new Error('Invalid map bounds');
  const [x0,y0,x1,y1] = bbox;
  if (x0 < -180 || x1 > 180 || y0 < -90 || y1 > 90 || x0 >= x1 || y0 >= y1) throw new Error('Map bounds are out of range');
  return bbox;
}
export function previewFields(layer) {
  const wanted = [layer.id_field,'Hylak_id','Lake_name','Lake_area','Country','COUNTRY','CONTINENT','REACH_ID','LENGTH_KM','CSI_D','CSI_FF1','HYRIV_RCH','dis_m3_pyr'];
  const available = new Set(layer.fields || []);
  const fields = [...new Set(wanted.filter(x => x && (available.has(x) || x === layer.id_field)))];
  for (const field of available) {
    if (fields.length >= 14) break;
    if (!fields.includes(field)) fields.push(field);
  }
  return fields.filter(x => x !== layer.geometry_column && x !== 'bbox');
}
const GRWL_WIDTH_STOPS = [[1,1.1],[50,1.6],[200,2.7],[1000,6.2]];
export const GRWL_WIDTH_LEGEND = [50,200,1000].map(metres=>({metres,width:grwlBaseWidth(metres)}));
export function grwlBaseWidth(metres) {
  const value=Number(metres);
  if(!Number.isFinite(value)||value<=0)return 0.9;
  if(value<=GRWL_WIDTH_STOPS[0][0])return GRWL_WIDTH_STOPS[0][1];
  for(let i=1;i<GRWL_WIDTH_STOPS.length;i++){
    const [right,width]=GRWL_WIDTH_STOPS[i],[left,leftWidth]=GRWL_WIDTH_STOPS[i-1];
    if(value<=right)return leftWidth+(width-leftWidth)*(value-left)/(right-left);
  }
  return GRWL_WIDTH_STOPS.at(-1)[1];
}
export function grwlWidthAtZoom(metres, zoom) {
  const z=Math.max(0,Math.min(12,Number(zoom)||0));
  const scale=z<=8?0.65+(z/8)*0.35:1+((z-8)/4)*0.4;
  return grwlBaseWidth(metres)*scale;
}
function grwlWidthValidity(field) {
  const value=['to-number',['get',field],0];
  const positive=['>',value,0];
  return field==='width_m'?['all',positive,['!=',value,1]]:positive;
}
export function grwlWidthExpression(field='width_mean') {
  const value=['to-number',['get',field],0];
  const width=['case',grwlWidthValidity(field),
    ['interpolate',['linear'],value,...GRWL_WIDTH_STOPS.flat()],0.9];
  return ['interpolate',['linear'],['zoom'],0,['*',width,0.65],8,width,12,['*',width,1.4]];
}
export function grwlWidthSampleRadiusExpression(field='width_m') {
  const value=['to-number',['get',field],0];
  const width=['case',grwlWidthValidity(field),
    ['interpolate',['linear'],value,...GRWL_WIDTH_STOPS.flat()],0.9];
  return ['interpolate',['linear'],['zoom'],0,['*',width,0.65/2],8,['*',width,0.5],12,['*',width,1.4/2]];
}
export function grwlWidthSampleLayer(source,overview,detailMinZoom) {
  return {id:'release-width-samples',type:'circle',source,'source-layer':overview.source_layer,
    minzoom:overview.min_zoom??0,maxzoom:detailMinZoom,
    layout:{'circle-sort-key':['case',['==',['get','width_valid'],true],['to-number',['get','width_m'],0],-1]},
    paint:{'circle-radius':grwlWidthSampleRadiusExpression('width_m'),
      'circle-color':['case',['==',['get','width_valid'],true],'#216d85','#71858a'],
      'circle-opacity':['case',['==',['get','width_valid'],true],0.82,0.58]}};
}
export function canvasPointToPagePoint(canvasRect,point) {
  if(!canvasRect||!Number.isFinite(canvasRect.left)||!Number.isFinite(canvasRect.top)||
      !point||!Number.isFinite(point.x)||!Number.isFinite(point.y))throw new Error('Invalid map canvas point');
  return {x:canvasRect.left+point.x,y:canvasRect.top+point.y};
}
export function grwlLinePaint(field='width_mean') {
  return {'line-color':'#216d85','line-opacity':['case',grwlWidthValidity(field),0.82,0.52],'line-width':grwlWidthExpression(field)};
}
export function formatMeanWidth(value) {
  const number=Number(value);
  if(value===null||value===undefined||value===''||!Number.isFinite(number)||number<=0)return 'Unknown (null or nonpositive source value)';
  return new Intl.NumberFormat(undefined,{maximumFractionDigits:1}).format(number)+' m';
}
export function rawWidthLabel(value) {
  const number=Number(value);
  if(number===1)return 'Unknown (source sentinel 1)';
  if(value===null||value===undefined||value===''||!Number.isFinite(number)||number<=0)return 'Unknown (null or nonpositive source value)';
  return new Intl.NumberFormat(undefined,{maximumFractionDigits:1}).format(number)+' m';
}
export function sourceProperties(feature, layer) {
  const properties=jsonValue(feature.properties||{});
  if(layer?.id_encoding==='mvt_feature_id'){
    const id=feature.id;
    if(!Number.isSafeInteger(id)||id<0||!layer.id_field)throw new Error('Invalid exact source ID in MVT feature');
    if(properties[layer.id_field]!==undefined&&properties[layer.id_field]!==id)throw new Error('MVT source ID conflicts with its property');
    properties[layer.id_field]=id;
  }
  return properties;
}
export function sourceBounds(properties) {
  const keys=['_src_xmin','_src_ymin','_src_xmax','_src_ymax'];
  if(!keys.every(key=>properties?.[key]!==null&&properties?.[key]!==undefined&&properties?.[key]!==''&&Number.isFinite(Number(properties[key]))))return null;
  let [xmin,ymin,xmax,ymax]=keys.map(key=>Number(properties[key]));
  if(xmin < -180||xmax>180||ymin < -90||ymax>90||xmin>xmax||ymin>ymax)return null;
  if(xmin===xmax){xmin=Math.max(-180,xmin-1e-7);xmax=Math.min(180,xmax+1e-7);}
  if(ymin===ymax){ymin=Math.max(-90,ymin-1e-7);ymax=Math.min(90,ymax+1e-7);}
  return [xmin,ymin,xmax,ymax];
}
export function buildQuery(layer, filename, bbox, limit=1500) {
  validBbox(bbox);
  if (!Number.isInteger(limit) || limit < 1 || limit > 5000) throw new Error('Invalid display limit');
  const columns = [...previewFields(layer),layer.geometry_column].map(quoteIdentifier).join(', ');
  return 'SELECT ' + columns + ' FROM read_parquet(' + quoteValue(filename) + ') WHERE ' +
    spatialPredicate(layer, bbox) +
    ' ORDER BY ' + quoteIdentifier(layer.id_field) + ' LIMIT ' + (limit + 1);
}
function spatialPredicate(layer, bbox) {
  const cover = layer.covering;
  if (!cover) throw new Error('This file has no spatial covering index');
  const field = key => {
    if (typeof cover[key] !== 'string' || !cover[key]) throw new Error('Invalid spatial covering field');
    return cover[key].split('.').map(quoteIdentifier).join('.');
  };
  return field('xmax') + ' >= ' + bbox[0] + ' AND ' + field('xmin') + ' <= ' + bbox[2] +
    ' AND ' + field('ymax') + ' >= ' + bbox[1] + ' AND ' + field('ymin') + ' <= ' + bbox[3];
}
export function supportsExactIdLookup(layer) {
  return layer?.lookup_mode === 'exact_id' && layer.id_field === 'feature_id' &&
    Array.isArray(layer.fields) && layer.fields.includes('feature_id');
}
export function buildAttributeLookupQuery(layer, filename, id, bbox) {
  const columns = attributeProjection(layer);
  if (!columns) throw new Error('This file has no attribute fields');
  const source = ' FROM read_parquet(' + quoteValue(filename) + ') WHERE ';
  if (layer?.lookup_mode === 'exact_id') {
    if (!supportsExactIdLookup(layer)) throw new Error('Exact ID lookup requires a feature_id field');
    if (typeof id !== 'number' || !Number.isSafeInteger(id) || id < 0) throw new Error('Invalid exact numeric feature ID');
    return 'SELECT ' + columns + source + quoteIdentifier('feature_id') + ' = ' + id + ' LIMIT 2';
  }
  if (!Array.isArray(layer.fields) || !layer.fields.includes(layer.id_field)) throw new Error('ID field is missing from the analytical schema');
  if (typeof id !== 'string' && (typeof id !== 'number' || !Number.isFinite(id))) throw new Error('Invalid feature ID');
  validBbox(bbox);
  return 'SELECT ' + columns + source + spatialPredicate(layer, bbox) + ' AND ' +
    quoteIdentifier(layer.id_field) + ' = ' + quoteValue(id) + ' LIMIT 2';
}
export function objectURL(origin, path) {
  const url = new URL(origin);
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password ||
      url.search || url.hash || !['','/'].includes(url.pathname)) throw new Error('Enter an HTTP(S) object-storage origin');
  if (typeof path !== 'string' || !path.startsWith('/nthh/') || path.includes('..') || path.includes('\\')) throw new Error('Invalid object path');
  return url.origin + path;
}
export function jsonValue(value) {
  if (typeof value === 'bigint') return value.toString();
  if (value instanceof Date) return value.toISOString();
  if (typeof value === 'number' && !Number.isFinite(value)) return null;
  if (Array.isArray(value)) return value.map(jsonValue);
  if (value && typeof value === 'object') {
    if (typeof value.toJSON === 'function') return jsonValue(value.toJSON());
    return Object.fromEntries(Object.entries(value).map(([k,v]) => [k,jsonValue(v)]));
  }
  return value;
}
/* Decode source WKB to two-dimensional screen coordinates. Source bytes stay unchanged. */
export function decodeWKB(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 0;
  function need(length) { if (offset + length > view.byteLength) throw new Error('Truncated WKB geometry'); }
  function geometry(depth=0) {
    if (depth > 32) throw new Error('WKB nesting limit exceeded');
    need(5);
    const order=view.getUint8(offset++); if (order !== 0 && order !== 1) throw new Error('Invalid WKB byte order');
    const little=order===1; const raw=view.getUint32(offset,little); offset+=4;
    let type=raw & 0x1fffffff;
    let z=Boolean(raw & 0x80000000), m=Boolean(raw & 0x40000000);
    if (type >= 3000) { z=true; m=true; type-=3000; }
    else if (type >= 2000) { m=true; type-=2000; }
    else if (type >= 1000) { z=true; type-=1000; }
    if (raw & 0x20000000) { need(4); offset+=4; }
    const dimensions=2+Number(z)+Number(m);
    function count() { need(4); const n=view.getUint32(offset,little);offset+=4;if(n>10000000)throw new Error('Invalid WKB element count');return n; }
    function point() {
      need(8*dimensions);
      const p=[view.getFloat64(offset,little),view.getFloat64(offset+8,little)];offset+=8*dimensions;
      return p;
    }
    function points() { return Array.from({length:count()},point); }
    if(type===1) { const p=point(); return p.every(Number.isFinite) ? {type:'Point',coordinates:p}:null; }
    if(type===2) return {type:'LineString',coordinates:points()};
    if(type===3) return {type:'Polygon',coordinates:Array.from({length:count()},points)};
    if(type>=4 && type<=7) {
      const children=Array.from({length:count()},()=>geometry(depth+1)).filter(Boolean);
      if(type===7)return {type:'GeometryCollection',geometries:children};
      const names={4:'MultiPoint',5:'MultiLineString',6:'MultiPolygon'};
      const childNames={4:'Point',5:'LineString',6:'Polygon'};
      if(children.some(child=>child.type!==childNames[type]))throw new Error('Invalid WKB multi-geometry member');
      return {type:names[type],coordinates:children.map(child=>child.coordinates)};
    }
    throw new Error('Unsupported WKB geometry type '+type);
  }
  const result=geometry();
  if(offset!==view.byteLength)throw new Error('Unexpected trailing WKB bytes');
  return result;
}
export function graticule() {
  const features=[];
  for(let longitude=-180;longitude<=180;longitude+=30)features.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[[longitude,-85],[longitude,85]]}});
  for(let latitude=-75;latitude<=75;latitude+=15)features.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:Array.from({length:73},(_,i)=>[-180+i*5,latitude])}});
  return {type:'FeatureCollection',features};
}

export function verifyRangeResponse(requested, contentRange, length, size) {
  const request=/^bytes=(\d*)-(\d*)$/.exec(requested||'');
  const response=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(contentRange||'');
  if(!request||!response||!Number.isSafeInteger(size)||size<=0)throw new Error('Invalid byte-range response');
  let start,end;
  if(request[1]===''){
    const suffix=Number(request[2]);if(!suffix)throw new Error('Invalid suffix range');
    start=Math.max(0,size-suffix);end=size-1;
  }else{
    start=Number(request[1]);end=request[2]===''?size-1:Math.min(Number(request[2]),size-1);
  }
  if(start<0||start>end||start>=size||Number(response[1])!==start||Number(response[2])!==end||Number(response[3])!==size||length!==end-start+1)throw new Error('Byte-range response differs from the requested interval');
  return true;
}
