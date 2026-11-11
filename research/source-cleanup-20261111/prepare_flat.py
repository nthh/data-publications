"""Prepare flat Source objects from the existing verified catalog; never upload."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import struct
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = 'flat-20261111'
UPDATED = '2026-11-11T07:23:02Z'
BASE = 'https://data.source.coop/nthh/'
ASSETS = {
 'free-flowing-rivers': {
  'ffr-reach-network-v1': 'free-flowing-rivers-v1.parquet',
  'ffr-reach-network-v1_fields': 'free-flowing-rivers-v1.fields.json',
  'display_tiles_free-flowing-rivers-1': 'free-flowing-rivers-v1.pmtiles',
  'display_style_free-flowing-rivers-1': 'free-flowing-rivers-v1.style.json'},
 'grwl-raw': {
  'grwl-raw-observations': 'grwl-raw-v01.01.parquet',
  'grwl-raw-observations_fields': 'grwl-raw-v01.01.fields.json',
  'display_tiles_grwl-raw-display': 'grwl-raw-v01.01.pmtiles',
  'display_style_grwl-raw-display': 'grwl-raw-v01.01.style.json'},
 'hydrolakes': {
  'hydrolakes-polygons': 'hydrolakes-polygons-v1.0.parquet',
  'hydrolakes-polygons_fields': 'hydrolakes-polygons-v1.0.fields.json',
  'display_tiles_hydrolakes-1': 'hydrolakes-polygons-v1.0.pmtiles',
  'display_style_hydrolakes-1': 'hydrolakes-polygons-v1.0.style.json'},
 'lakeatlas': {
  'lakeatlas-polygons': 'lakeatlas-polygons-v1.0.parquet',
  'lakeatlas-polygons_fields': 'lakeatlas-polygons-v1.0.fields.json',
  'lakeatlas-pour-points': 'lakeatlas-pour-points-v1.0.parquet',
  'lakeatlas-pour-points_fields': 'lakeatlas-pour-points-v1.0.fields.json',
  'display_tiles_lakeatlas-1': 'lakeatlas-polygons-v1.0.pmtiles',
  'display_style_lakeatlas-1': 'lakeatlas-polygons-v1.0.style.json',
  'display_tiles_lakeatlas-2': 'lakeatlas-pour-points-v1.0.pmtiles',
  'display_style_lakeatlas-2': 'lakeatlas-pour-points-v1.0.style.json'},
 'river-plastic-inputs': {
  'data': 'river-plastic-inputs-figshare-v6.parquet',
  'tiles': 'river-plastic-inputs-figshare-v6.pmtiles',
  'style-annual-input': 'river-plastic-inputs-figshare-v6.style.json',
  'schema': 'river-plastic-inputs-figshare-v6.fields.json',
  'quality': 'river-plastic-inputs-figshare-v6.quality.json'},
}

def sha(data): return hashlib.sha256(data).hexdigest()
def encoded(data): return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()
def write(path, data):
 path.parent.mkdir(parents=True, exist_ok=True)
 if path.exists():
  if path.read_bytes() != data: raise ValueError(f'Existing prepared file differs: {path}')
 else: path.write_bytes(data)

def revise_pmtiles(asset, output, proof_path, attribution):
 # PMTiles v3 has a 127-byte header, with section offsets/lengths as uint64 LE.
 # Only replace JSON metadata and rebase subsequent section offsets. All encoded
 # root/leaf directory and vector-tile payload bytes must remain identical.
 with urllib.request.urlopen(asset['href'], timeout=60) as response:
  before = response.read(asset['file:size']+1)
 if len(before) != asset['file:size'] or sha(before) != asset['file:checksum'][4:]:
  raise ValueError('River-plastic source archive checksum differs')
 if before[:8] != b'PMTiles\x03' or before[97] != 2:
  raise ValueError('Expected PMTiles v3 with gzip internal compression')
 offsets = struct.unpack_from('<8Q', before, 8)
 root_off, root_len, meta_off, meta_len, leaf_off, leaf_len, tile_off, tile_len = offsets
 if not (root_off+root_len <= meta_off and meta_off+meta_len <= leaf_off <= tile_off):
  raise ValueError('Unsupported section order')
 old_metadata = json.loads(gzip.decompress(before[meta_off:meta_off+meta_len]))
 new_metadata = dict(old_metadata)
 new_metadata['attribution'] = attribution
 # The old command string repeats the incorrect credit. Preserve that history
 # in the original archive, without claiming this metadata revision reran it.
 new_metadata.pop('generator_options', None)
 if 'folia' in json.dumps(new_metadata).lower():
  raise ValueError('Additional incorrect attribution requires explicit review')
 metadata_bytes = gzip.compress(json.dumps(new_metadata,separators=(',',':'),ensure_ascii=False).encode(),mtime=0)
 delta = len(metadata_bytes)-meta_len
 after = bytearray(before[:meta_off]+metadata_bytes+before[meta_off+meta_len:])
 struct.pack_into('<Q',after,32,len(metadata_bytes))
 struct.pack_into('<Q',after,40,leaf_off+delta)
 struct.pack_into('<Q',after,56,tile_off+delta)
 sections={}
 for name,off,length,new_off in [('root',root_off,root_len,root_off),('leaf',leaf_off,leaf_len,leaf_off+delta),('tile_data',tile_off,tile_len,tile_off+delta)]:
  a,b=before[off:off+length],after[new_off:new_off+length]
  if bytes(a)!=bytes(b): raise ValueError(f'{name} payload changed')
  sections[name]={'sha256':sha(a),'bytes':len(a),'identical':True}
 header_before=bytearray(before[:127]); header_after=bytearray(after[:127])
 for off in [32,40,56]: header_before[off:off+8]=header_after[off:off+8]
 if header_before!=header_after: raise ValueError('Unapproved PMTiles header change')
 if set(old_metadata)-set(new_metadata) != {'generator_options'} or any(old_metadata[k]!=new_metadata[k] for k in new_metadata if k!='attribution'):
  raise ValueError('Unapproved metadata change')
 write(output,bytes(after))
 proof={'schema_version':1,'status':'passed','operation':'PMTiles attribution metadata correction only',
        'source_sha256':sha(before),'target_sha256':sha(after),'source_size_bytes':len(before),'target_size_bytes':len(after),
        'geometry_payload_unchanged':True,'encoded_sections':sections,'metadata_changed_fields':['attribution','generator_options'], 'generator_options_removed':True,
        'header_changed_fields':['json_metadata_length','leaf_directory_offset','tile_data_offset']}
 write(proof_path,encoded(proof))
 return bytes(after)

def main():
 plan={'schema_version':1,'layout_id':LAYOUT,'endpoint':'https://data.source.coop','bucket':'nthh','files':[],'scope':'Add flat consumer assets; preserve all existing object keys.'}
 for dataset_id,names in ASSETS.items():
  record=yaml.safe_load((ROOT/f'datasets/{dataset_id}/dataset.yaml').read_text())
  publication=record['publication']; config=publication['source_coop']
  collection=json.loads((ROOT/f'catalog/{dataset_id}/collection.json').read_text())
  directory=ROOT/f'datasets/{dataset_id}/source-coop/{LAYOUT}'
  replacements={collection['assets'][key]['href']:BASE+dataset_id+'/'+name for key,name in names.items() if name.endswith('.pmtiles')}
  files=[]
  for asset_id,filename in names.items():
   asset=collection['assets'][asset_id]
   item={'filename':filename,'asset_id':asset_id,'source_href':asset['href'],
         'source_sha256':asset['file:checksum'][4:],'source_size_bytes':asset['file:size'],
         'sha256':asset['file:checksum'][4:],'size_bytes':asset['file:size'],
         'media_type':asset['type'],'roles':asset.get('roles',[]),'title':asset.get('title',filename),'operation':'copy'}
   if 'style' in asset.get('roles',[]):
    original=(ROOT/f'catalog/{dataset_id}'/asset['href']).read_bytes()
    if sha(original)!=item['source_sha256']: raise ValueError('Style binding differs')
    style=json.loads(original)
    for source in style.get('sources',{}).values():
     url=source.get('url')
     if url:
      raw=url.removeprefix('pmtiles://')
      if raw not in replacements: raise ValueError(f'Unmapped style URL: {raw}')
      source['url']='pmtiles://'+replacements[raw]
     if 'folia' in source.get('attribution','').lower(): source['attribution']=config['attribution']+' '+config['license_note']
    data=encoded(style)
    write(directory/filename,data)
    item.update(operation='rewrite_style',sha256=sha(data),size_bytes=len(data),local_path=(directory/filename).relative_to(ROOT).as_posix())
   elif dataset_id=='river-plastic-inputs' and asset_id=='tiles':
    output=ROOT/'.local/source-cleanup-20261111'/filename
    proof_path=directory/'pmtiles-attribution-proof.json'
    data=revise_pmtiles(asset,output,proof_path,config['attribution']+' '+config['license_note'])
    item.update(operation='pmtiles_attribution',sha256=sha(data),size_bytes=len(data),
                transformation_proof={'path':proof_path.relative_to(ROOT).as_posix(),'sha256':sha(proof_path.read_bytes())})
   files.append(item)
  license_text=(f"Dataset license: {collection['license']}\n\n{config['license_note']}\n\nProducer attribution: {config['attribution']}\n\nIndependent format conversion and publication: nthh.\n")
  license_data=license_text.encode()
  write(directory/'LICENSE.txt',license_data)
  files.append({'filename':'LICENSE.txt','asset_id':None,'source_href':None,'sha256':sha(license_data),'size_bytes':len(license_data),'media_type':'text/plain','roles':['license'],'title':'Dataset license and producer attribution','operation':'generated','local_path':(directory/'LICENSE.txt').relative_to(ROOT).as_posix()})
  public_manifest={'schema_version':1,'dataset_id':dataset_id,'source_release':publication['release'],'license':collection['license'],
                   'attribution':config['attribution'],'files':[{k:v for k,v in item.items() if k in ['filename','sha256','size_bytes','roles','source_href']} for item in files],
                   'provenance_url':f'https://github.com/nthh/data-publications/tree/main/datasets/{dataset_id}'}
  data=encoded(public_manifest); name='manifest-20261111.json'; write(directory/name,data)
  files.append({'filename':name,'asset_id':None,'source_href':None,'sha256':sha(data),'size_bytes':len(data),'media_type':'application/json','roles':['metadata'],'title':'Checksums and source provenance','operation':'generated','local_path':(directory/name).relative_to(ROOT).as_posix()})
  manifest={'schema_version':1,'dataset_id':dataset_id,'layout_id':LAYOUT,'updated':UPDATED,'owner':config['owner'],'product_id':config['product_id'],
            'source_release':publication['release'],'files':files}
  write(directory/'manifest.json',encoded(manifest))
  for item in files:
   entry=dict(item,dataset_id=dataset_id,object_key=dataset_id+'/'+item['filename'],url=BASE+dataset_id+'/'+item['filename'])
   if item['operation']=='copy':
    prefix=BASE+dataset_id+'/'
    if not item['source_href'].startswith(prefix): raise ValueError('Source outside dataset product')
    entry['source_key']=dataset_id+'/'+item['source_href'][len(prefix):]
   elif item['operation']=='pmtiles_attribution':
    entry['local_path']=(Path('.local/source-cleanup-20261111')/item['filename']).as_posix()
   plan['files'].append(entry)
 write(ROOT/'research/source-cleanup-20261111/flat-plan.json',encoded(plan))
 print(json.dumps({'files':len(plan['files']),'bytes':sum(r['size_bytes'] for r in plan['files']),'plan_sha256':sha(encoded(plan))}))

if __name__=='__main__': main()
