import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {canvasPointToPagePoint,grwlLinePaint,grwlWidthAtZoom,grwlWidthExpression,grwlWidthSampleLayer,grwlWidthSampleRadiusExpression,rawWidthLabel} from '../src/core.js';

function evaluate(expression,properties={},zoom=0) {
  if(!Array.isArray(expression))return expression;
  const [op,...args]=expression;
  if(op==='get')return properties[args[0]];
  if(op==='zoom')return zoom;
  if(op==='to-number'){
    const value=evaluate(args[0],properties,zoom),number=Number(value);
    return value===null||value===undefined||value===''||!Number.isFinite(number)?evaluate(args[1],properties,zoom):number;
  }
  if(op==='*')return evaluate(args[0],properties,zoom)*evaluate(args[1],properties,zoom);
  if(op==='>')return evaluate(args[0],properties,zoom)>evaluate(args[1],properties,zoom);
  if(op==='!=')return evaluate(args[0],properties,zoom)!==evaluate(args[1],properties,zoom);
  if(op==='all')return args.every(value=>evaluate(value,properties,zoom));
  if(op==='case'){
    for(let index=0;index<args.length-1;index+=2)if(evaluate(args[index],properties,zoom))return evaluate(args[index+1],properties,zoom);
    return evaluate(args.at(-1),properties,zoom);
  }
  if(op==='interpolate'){
    const input=evaluate(args[1],properties,zoom),stops=args.slice(2);
    if(input<=stops[0])return evaluate(stops[1],properties,zoom);
    for(let index=2;index<stops.length;index+=2){
      const high=stops[index],highValue=evaluate(stops[index+1],properties,zoom),low=stops[index-2],lowValue=evaluate(stops[index-1],properties,zoom);
      if(input<=high)return lowValue+(highValue-lowValue)*(input-low)/(high-low);
    }
    return evaluate(stops.at(-1),properties,zoom);
  }
  throw new Error('Unsupported expression operator: '+op);
}

test('overview circle diameter equals detail width stroke at zooms 0, 3, 7 and 8',()=>{
  const line=grwlWidthExpression('width_m'),radius=grwlWidthSampleRadiusExpression('width_m');
  for(const width_m of [1,50,200,1000,2500,null])for(const zoom of [0,3,7,8]){
    const properties={width_m},diameter=2*evaluate(radius,properties,zoom),stroke=evaluate(line,properties,zoom);
    assert.ok(Math.abs(diameter-stroke)<1e-10,`width=${width_m}, zoom=${zoom}: diameter ${diameter}, stroke ${stroke}`);
    if(width_m!==1)assert.ok(Math.abs(diameter-grwlWidthAtZoom(width_m,zoom))<1e-10);
  }
  assert.equal(radius[0],'interpolate');
  assert.equal(radius[2][0],'zoom','MapLibre zoom must remain the outer expression input');
});

test('sample radii grow monotonically with valid width and keep unknown values muted and small',()=>{
  const radius=grwlWidthSampleRadiusExpression('width_m');
  for(const zoom of [0,3,7,8]){
    const sizes=[50,200,1000,5000].map(width_m=>evaluate(radius,{width_m},zoom));
    assert.ok(sizes.every((size,index)=>index===0||size>=sizes[index-1]));
    assert.ok(sizes[0]<sizes[1]&&sizes[1]<sizes[2]);
    for(const width_m of [null,0,-4,1])assert.equal(evaluate(radius,{width_m},zoom),evaluate(radius,{width_m:null},zoom));
  }
  assert.equal(rawWidthLabel(1),'Unknown (source sentinel 1)');
  assert.equal(rawWidthLabel(null),'Unknown (null or nonpositive source value)');
});

test('legacy GRWL coverage/detail line paint remains unchanged and coverage fill is retained',async()=>{
  assert.deepEqual(grwlLinePaint('width_mean'),{
    'line-color':'#216d85','line-opacity':['case',['>', ['to-number',['get','width_mean'],0],0],0.82,0.52],
    'line-width':grwlWidthExpression('width_mean'),
  });
  const app=await readFile(new URL('../src/app.js',import.meta.url),'utf8');
  assert.match(app,/if\(overview\)\{\s*map\.addLayer\(\{id:'release-coverage',type:'fill'/);
  assert.match(app,/activeMapLayers=overview\?\['release-coverage','release-lines'\]:\['release-lines'\]/);
});

test('width sample layer binds the overview source-layer and has no outline stroke',()=>{
  const layer=grwlWidthSampleLayer('release-data',{source_layer:'grwl_width_overview',min_zoom:0},8);
  assert.equal(layer['source-layer'],'grwl_width_overview');
  assert.equal(layer.maxzoom,8);
  assert.deepEqual(layer.paint['circle-radius'],grwlWidthSampleRadiusExpression('width_m'));
  assert.equal(layer.paint['circle-stroke-width'],undefined);
  assert.equal(layer.paint['circle-stroke-color'],undefined);
});

test('map canvas click coordinates include the canvas offset within the page',()=>{
  assert.deepEqual(canvasPointToPagePoint({left:312,top:84},{x:127,y:260}),{x:439,y:344});
  assert.throws(()=>canvasPointToPagePoint({left:NaN,top:0},{x:1,y:1}),/Invalid map canvas point/);
});
