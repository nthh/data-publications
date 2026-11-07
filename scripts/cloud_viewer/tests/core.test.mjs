import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeWKB,buildQuery,objectURL,jsonValue,previewFields,attributeProjection,verifyRangeResponse,grwlBaseWidth,grwlWidthAtZoom,grwlWidthExpression,grwlLinePaint,GRWL_WIDTH_LEGEND,formatMeanWidth,rawWidthLabel,sourceBounds,sourceProperties,resourceTimingBytes} from '../src/core.js';

test('Resource timing distinguishes hidden cross-origin size from a measured zero',()=>{
  assert.deepEqual(resourceTimingBytes({responseStatus:0,transferSize:0,encodedBodySize:0}),{bytes:0,redacted:true});
  assert.deepEqual(resourceTimingBytes({responseStatus:206,transferSize:0,encodedBodySize:0}),{bytes:0,redacted:true});
  assert.deepEqual(resourceTimingBytes({responseStatus:undefined,transferSize:undefined,encodedBodySize:undefined}),{bytes:0,redacted:true});
  assert.deepEqual(resourceTimingBytes({responseStatus:200,transferSize:0,encodedBodySize:0}),{bytes:0,redacted:false});
  assert.deepEqual(resourceTimingBytes({responseStatus:206,transferSize:512,encodedBodySize:256}),{bytes:256,redacted:false});
});

function point(x,y,little=true,type=1,extra=[]) {
  const buffer=new ArrayBuffer(5+8*(2+extra.length));const v=new DataView(buffer);
  v.setUint8(0,little?1:0);v.setUint32(1,type,little);
  [x,y,...extra].forEach((n,i)=>v.setFloat64(5+i*8,n,little));return new Uint8Array(buffer);
}
test('WKB preserves coordinates across endian and drops only screen Z/M ordinates',()=>{
  for(const little of [true,false])assert.deepEqual(decodeWKB(point(-73.5,40.25,little)),{type:'Point',coordinates:[-73.5,40.25]});
  assert.deepEqual(decodeWKB(point(1,2,true,3001,[8,9])),{type:'Point',coordinates:[1,2]});
  assert.equal(decodeWKB(point(NaN,NaN)),null);
});
test('MultiPoint decodes members and malformed/truncated data is rejected',()=>{
  const a=point(1,2),b=point(3,4,false);const bytes=new Uint8Array(9+a.length+b.length);const v=new DataView(bytes.buffer);
  v.setUint8(0,1);v.setUint32(1,4,true);v.setUint32(5,2,true);bytes.set(a,9);bytes.set(b,9+a.length);
  assert.deepEqual(decodeWKB(bytes),{type:'MultiPoint',coordinates:[[1,2],[3,4]]});
  assert.throws(()=>decodeWKB(a.slice(0,10)),/Truncated/);
  assert.throws(()=>decodeWKB(new Uint8Array([...a,0])),/trailing/);
  const wrong=new Uint8Array(a);wrong[0]=7;assert.throws(()=>decodeWKB(wrong),/byte order/);
});
test('BBox query is bounded, deterministic and safely quotes all identifiers',()=>{
  const layer={id_field:'OBJECTID',fields:['OBJECTID','Lake_name'],geometry_column:'geom"x',covering:{xmin:'bbox.xmin',ymin:'bbox.ymin',xmax:'bbox.xmax',ymax:'bbox.ymax'}};
  const sql=buildQuery(layer,"file'one.parquet",[5,45,7.5,47.5],1500);
  assert.match(sql,/read_parquet\('file''one.parquet'\)/);assert.match(sql,/"geom""x"/);
  assert.match(sql,/"bbox"\."xmax" >= 5/);assert.match(sql,/ORDER BY "OBJECTID" LIMIT 1501$/);
  assert.throws(()=>buildQuery(layer,'x',[170,0,-170,10]),/bounds/);
  assert.throws(()=>buildQuery(layer,'x',[0,0,1,1],-1),/limit/);
});
test('Object origins support deployment without credentials or path injection',()=>{
  assert.equal(objectURL('https://data.source.coop','/nthh/lakeatlas/x.parquet'),'https://data.source.coop/nthh/lakeatlas/x.parquet');
  for(const origin of ['file:///tmp','https://user:pass@example.com','https://example.com/base/'])assert.throws(()=>objectURL(origin,'/nthh/x'));
  assert.throws(()=>objectURL('http://127.0.0.1:8911','/nthh/../secret'));
});
test('Attribute conversion retains exact large integer IDs and nulls',()=>{
  assert.deepEqual(jsonValue({id:9007199254740993n,value:null}),{id:'9007199254740993',value:null});
});

test('All-attribute projection casts only declared decimal fields and quotes identifiers exactly',()=>{
  const projection=attributeProjection({fields:['OBJECTID','width_mean','mean"width','bbox','geom'],geometry_column:'geom',decimal_fields:['width_mean','mean"width']});
  assert.equal(projection,'"OBJECTID", CAST("width_mean" AS VARCHAR) AS "width_mean", CAST("mean""width" AS VARCHAR) AS "mean""width"');
  assert.equal(attributeProjection({fields:['id','amount'],decimal_fields:[]}),'"id", "amount"');
});

test('GRWL width symbols are data-driven, distinct at one zoom, and explicit for unknown widths',()=>{
  const fifty=grwlBaseWidth(50),twoHundred=grwlBaseWidth(200),thousand=grwlBaseWidth(1000),unknown=grwlBaseWidth(null);
  assert.ok(fifty<twoHundred&&twoHundred<thousand);
  assert.equal(fifty,1.6);assert.equal(twoHundred,2.7);assert.equal(thousand,6.2);assert.equal(unknown,0.9);
  assert.deepEqual(GRWL_WIDTH_LEGEND.map(x=>x.metres),[50,200,1000]);
  assert.ok(grwlWidthAtZoom(50,12)>grwlWidthAtZoom(50,8));assert.ok(grwlWidthAtZoom(200,8)>grwlWidthAtZoom(50,8));
  const paint=grwlLinePaint(),encoded=JSON.stringify(paint);
  assert.match(encoded,/"width_mean"/);assert.match(encoded,/50/);assert.match(encoded,/200/);assert.match(encoded,/1000/);
  assert.match(encoded,/0\.9/);assert.match(encoded,/0\.52/);
  const expression=grwlWidthExpression();assert.equal(expression[0],'interpolate');assert.equal(expression[2][0],'zoom');
  assert.equal(formatMeanWidth(50),'50 m');assert.equal(formatMeanWidth(1),'1 m');assert.equal(formatMeanWidth(0),'Unknown (null or nonpositive source value)');assert.equal(formatMeanWidth(null),'Unknown (null or nonpositive source value)');
  assert.equal(rawWidthLabel(50),'50 m');assert.equal(rawWidthLabel(1),'Unknown (source sentinel 1)');assert.equal(rawWidthLabel(0),'Unknown (null or nonpositive source value)');assert.equal(rawWidthLabel(null),'Unknown (null or nonpositive source value)');
  const rawPaint=JSON.stringify(grwlLinePaint('width_m')),rawExpression=JSON.stringify(grwlWidthExpression('width_m'));
  assert.match(rawPaint,/"width_m"/);assert.match(rawExpression,/"width_m"/);
  assert.match(rawPaint,/\["!=",\["to-number",\["get","width_m"\],0\],1\]/);
  assert.doesNotMatch(encoded,/\["!=",\["to-number",\["get","width_mean"\]/);
});
test('PMTiles attribute lookup uses producer source bounds, not quantized tile geometry',()=>{
  assert.deepEqual(sourceBounds({_src_xmin:10,_src_ymin:20,_src_xmax:10,_src_ymax:20}),[9.9999999,19.9999999,10.0000001,20.0000001]);
  assert.deepEqual(sourceBounds({_src_xmin:1,_src_ymin:2,_src_xmax:3,_src_ymax:4}),[1,2,3,4]);
  assert.equal(sourceBounds({_src_xmin:null,_src_ymin:2,_src_xmax:3,_src_ymax:4}),null);
});

test('Browser-observed byte ranges must match request, object size and body length',()=>{
  assert.equal(verifyRangeResponse('bytes=10-29','bytes 10-29/100',20,100),true);
  assert.equal(verifyRangeResponse('bytes=-8','bytes 92-99/100',8,100),true);
  assert.equal(verifyRangeResponse('bytes=92-200','bytes 92-99/100',8,100),true);
  for(const [range,content,length,size] of [['bytes=10-29','bytes 0-19/100',20,100],['bytes=10-29','bytes 10-29/100',19,100],['bytes=10-29','bytes 10-29/200',20,100],['bytes=-0','bytes 0-99/100',100,100]])assert.throws(()=>verifyRangeResponse(range,content,length,size));
});

// Fixed OGC WKB fixtures, independent of the decoder and viewer query paths.
test('LineString and Polygon fixtures preserve vertices and closed rings',()=>{
  const line=Buffer.from('01020000000200000000000000000000000000000000000000000000000000f03f0000000000000040','hex');
  const polygon=Buffer.from('0103000000010000000400000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000004000000000000000000000000000000000','hex');
  assert.deepEqual(decodeWKB(line),{type:'LineString',coordinates:[[0,0],[1,2]]});
  assert.deepEqual(decodeWKB(polygon),{type:'Polygon',coordinates:[[[0,0],[2,0],[0,2],[0,0]]]});
});

test('Explicit MVT ID representation preserves source identity and rejects conflicts',()=>{
  const layer={id_field:'Hylak_id',id_encoding:'mvt_feature_id'};
  assert.deepEqual(sourceProperties({id:66,properties:{Lake_area:12}},layer),{Lake_area:12,Hylak_id:66});
  assert.throws(()=>sourceProperties({id:66,properties:{Hylak_id:67}},layer),/conflicts/);
  assert.throws(()=>sourceProperties({id:9007199254740993,properties:{}},layer),/Invalid exact/);
  assert.deepEqual(sourceProperties({id:66,properties:{}},{id_field:'Hylak_id'}),{});
});
