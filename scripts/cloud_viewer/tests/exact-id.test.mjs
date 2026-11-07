import test from 'node:test';
import assert from 'node:assert/strict';
import {buildAttributeLookupQuery,supportsExactIdLookup} from '../src/core.js';

const exactLayer={
  id_field:'feature_id',
  lookup_mode:'exact_id',
  fields:['feature_id','width_mean','large_decimal','geom','bbox'],
  geometry_column:'geom',
  decimal_fields:['large_decimal'],
};

test('explicit exact-ID lookup projects every analytic attribute and uses a numeric predicate',()=>{
  assert.equal(supportsExactIdLookup(exactLayer),true);
  const sql=buildAttributeLookupQuery(exactLayer,"https://data.example/global'v1.parquet",42);
  assert.match(sql,/^SELECT "feature_id", "width_mean", CAST\("large_decimal" AS VARCHAR\) AS "large_decimal" FROM read_parquet\('https:\/\/data\.example\/global''v1\.parquet'\)/);
  assert.match(sql,/WHERE "feature_id" = 42 LIMIT 2$/);
  assert.doesNotMatch(sql,/bbox\.xmin|ORDER BY/);
});

test('exact-ID lookup accepts zero and the maximum safe integer without string coercion',()=>{
  for(const id of [0,Number.MAX_SAFE_INTEGER]) {
    const sql=buildAttributeLookupQuery(exactLayer,'source.parquet',id);
    assert.match(sql,new RegExp('WHERE "feature_id" = '+id+' LIMIT 2$'));
  }
  for(const id of ['0','42','9007199254740993',1.5,-1,Number.MAX_SAFE_INTEGER+1,NaN,Infinity,null,42n]) {
    assert.throws(()=>buildAttributeLookupQuery(exactLayer,'source.parquet',id),/exact numeric feature ID/);
  }
});

test('exact-ID mode requires explicit opt-in and a declared feature_id field',()=>{
  assert.equal(supportsExactIdLookup({...exactLayer,lookup_mode:undefined}),false);
  assert.equal(supportsExactIdLookup({...exactLayer,fields:['other']}),false);
  assert.throws(()=>buildAttributeLookupQuery({...exactLayer,fields:['other']},'source.parquet',3),/requires a feature_id field/);
  assert.throws(()=>buildAttributeLookupQuery({...exactLayer,id_field:'OBJECTID'},'source.parquet',3),/requires a feature_id field/);
  assert.throws(()=>buildAttributeLookupQuery({...exactLayer,fields:['width_mean']},'source.parquet',3),/requires a feature_id field/);
});

test('other products retain spatial-bounds plus escaped ID lookup',()=>{
  const layer={
    id_field:'OBJECTID',lookup_mode:'spatial_id',fields:['OBJECTID','name','geom'],geometry_column:'geom',
    covering:{xmin:'bbox.xmin',ymin:'bbox.ymin',xmax:'bbox.xmax',ymax:'bbox.ymax'},
  };
  const sql=buildAttributeLookupQuery(layer,"file'one.parquet","id'7",[5,45,7.5,47.5]);
  assert.match(sql,/read_parquet\('file''one\.parquet'\)/);
  assert.match(sql,/"bbox"\."xmax" >= 5 AND "bbox"\."xmin" <= 7\.5 AND "bbox"\."ymax" >= 45 AND "bbox"\."ymin" <= 47\.5/);
  assert.match(sql,/AND "OBJECTID" = 'id''7' LIMIT 2$/);
  assert.throws(()=>buildAttributeLookupQuery(layer,'source.parquet','id',[170,0,-170,10]),/bounds/);
});
