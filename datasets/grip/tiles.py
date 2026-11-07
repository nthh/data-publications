"""Exhaustive PMTiles ID/attribute audit plus declared deterministic geometry samples."""
from collections import Counter,defaultdict
import gzip
import hashlib
import heapq
import json
import math
import mmap
from pathlib import Path
import subprocess
import duckdb
import mapbox_vector_tile
from mapbox_vector_tile.Mapbox import vector_tile_pb2
import numpy as np
import pyarrow.parquet as pq
import shapely
from pmtiles.reader import Reader,all_tiles
from pmtiles.tile import Compression

def require(ok,message):
    if not ok: raise ValueError(message)

def value(v):
    present=v.ListFields()
    require(len(present)==1,'Ambiguous MVT value')
    return present[0][1]

def project(geometry,z,x,y,extent):
    def transform(coords):
        lon,lat=coords[:,0],coords[:,1]
        return np.column_stack((((lon+180)/360*2**z-x)*extent,
          ((1-np.arcsinh(np.tan(np.radians(lat)))/math.pi)/2*2**z-y)*extent))
    return shapely.transform(geometry,transform)

def geometry_error(original,observed,z,x,y,extent):
    target=project(original,z,x,y,extent)
    points=shapely.get_coordinates(observed)
    # Vertices and segment midpoints check both quantization and shortcuts from simplification.
    mids=[]
    for part in shapely.get_parts(observed):
        c=shapely.get_coordinates(part)
        if len(c)>1: mids.append((c[:-1]+c[1:])/2)
    if mids: points=np.vstack([points,*mids])
    require(len(points)>0,'Empty displayed line')
    require(np.isfinite(points).all(),'Nonfinite tile geometry')
    require((points>=-extent*5/256-1).all() and (points<=extent*(1+5/256)+1).all(),'Tile geometry outside declared clip buffer')
    distances=shapely.distance(shapely.points(points),target)
    # A source road close to the dateline may be wrapped into the adjacent world copy.
    if x in (0,2**z-1):
        for shift in (-extent*2**z,extent*2**z):
            moved=shapely.transform(target,lambda c:c+np.array([shift,0]))
            distances=np.minimum(distances,shapely.distance(shapely.points(points),moved))
    return float(np.max(distances))

def validate_tiles(root,config,summary):
    root=Path(root); maximum=summary['max_source_fid'];zmax=config['pmtiles_maxzoom']
    require(maximum<50_000_000,'Unexpected source ID extent: review memory budget')
    regions=np.zeros(maximum+1,dtype=np.uint8);classes=np.zeros(maximum+1,dtype=np.int32)
    fid,region,roadtype=config['fid_column'],config['region_field'],config['road_type_field']
    for path in sorted((root/'grip/data').glob('*.parquet')):
        for batch in pq.ParquetFile(path).iter_batches(columns=[fid,region,roadtype],batch_size=65536):
            ids=batch[fid].to_numpy();regions[ids]=batch[region].to_numpy();classes[ids]=batch[roadtype].to_numpy()
    masks=np.zeros(maximum+1,dtype=np.uint16)
    counts=Counter();instances=Counter();reservoir=defaultdict(list);geometry_samples=[]
    path=root/'grip/grip.pmtiles'
    subprocess.run(['pmtiles','verify',str(path)],check=True,capture_output=True,text=True)
    with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as payload:
        require(payload[:8]==b'PMTiles\x03','Expected PMTiles v3')
        get=lambda offset,length:payload[offset:offset+length]
        reader=Reader(get);header=reader.header();meta=reader.metadata()
        require(header['min_zoom']==0 and header['max_zoom']==zmax,'Incorrect tile zoom range')
        require({x['id'] for x in meta['vector_layers']}=={'roads'},'Wrong display layer')
        for (z,x,y),blob in all_tiles(get):
            if header['tile_compression']==Compression.GZIP: blob=gzip.decompress(blob)
            elif header['tile_compression']!=Compression.NONE: raise ValueError('Unsupported compression')
            tile=vector_tile_pb2.tile();tile.ParseFromString(blob)
            require(len(tile.layers)==1 and tile.layers[0].name=='roads','Wrong MVT layer')
            layer=tile.layers[0]
            require(layer.extent==4096,'Undeclared tile resolution')
            ids=np.fromiter((f.id for f in layer.features),dtype=np.int64,count=len(layer.features))
            require(len(ids)>0 and ids.min()>0 and ids.max()<=maximum,'Missing/invalid MVT source ID')
            require((regions[ids]>0).all(),'Tile ID absent from source')
            vals=[value(v) for v in layer.values]
            for feature in layer.features:
                require(feature.type==2,'Non-line display feature')
                props={layer.keys[feature.tags[i]]:vals[feature.tags[i+1]] for i in range(0,len(feature.tags),2)}
                require(props=={region:int(regions[feature.id]),roadtype:int(classes[feature.id])},'Tile source attribute mismatch')
            masks[ids]|=1<<z;counts[z]+=1;instances[z]+=len(ids)
            rank=int.from_bytes(hashlib.sha256(f'{z}/{x}/{y}'.encode()).digest(),'big')
            sample=(-rank,z,x,y)
            if len(reservoir[z])<16: heapq.heappush(reservoir[z],sample)
            elif sample>reservoir[z][0]: heapq.heapreplace(reservoir[z],sample)
            if counts[z]%10000==0: print(f'tiles zoom {z}: {counts[z]:,}',flush=True)
        require(set(counts)==set(range(zmax+1)),'A zoom level is absent')
        for z in sorted(reservoir):
            for _,_,x,y in sorted(reservoir[z]):
                blob=reader.get(z,x,y)
                if header['tile_compression']==Compression.GZIP:blob=gzip.decompress(blob)
                layer=mapbox_vector_tile.decode(blob,default_options={'y_coord_down':True})['roads']
                selected=sorted(layer['features'],key=lambda f:hashlib.sha256(str(f['id']).encode()).digest())[:8]
                for feature in selected:geometry_samples.append((z,x,y,layer['extent'],feature))
    sample_ids=sorted({feature['id'] for *_,feature in geometry_samples})
    with duckdb.connect() as con:
        con.execute('SET threads=2');con.execute("SET memory_limit='1GB'")
        records=con.execute(f'SELECT "{fid}",geometry FROM read_parquet(?) WHERE "{fid}" IN (SELECT unnest(?))',
            [str(root/'grip/data/*.parquet'),sample_ids]).fetchall()
    originals={key:shapely.from_wkb(bytes(blob)) for key,blob in records}
    errors=[]
    for z,x,y,extent,feature in geometry_samples:
        observed=shapely.from_geojson(json.dumps(feature['geometry']))
        error=geometry_error(originals[feature['id']],observed,z,x,y,extent)
        require(error<=4.0,f'Display geometry exceeds 4 tile-unit contract: ID {feature["id"]}, zoom {z}, error {error}')
        errors.append(error)
    coverage={}
    for z in range(zmax+1):
        kept=(masks&(1<<z))!=0
        by_region={str(r):int(np.count_nonzero(kept&(regions==r))) for r in range(1,8)}
        require(all(n>0 for n in by_region.values()),f'Missing geographic region at zoom {z}')
        coverage[str(z)]={'tiles':counts[z],'feature_instances_including_buffer_duplicates':instances[z],
           'unique_source_ids':int(np.count_nonzero(kept)),'unique_ids_by_region':by_region,
           'fraction_of_source_ids':float(np.count_nonzero(kept)/summary['rows'])}
    return {'status':'passed','structure_verified':True,'all_tile_ids_and_attributes_checked':True,
       'coverage_by_zoom':coverage,'geometry_sampling':'16 lowest SHA256(z/x/y) tiles per zoom, up to 8 lowest SHA256(source ID) features per tile; vertices and segment midpoints',
       'geometry_features_checked':len(errors),'maximum_sampled_error_tile_units':max(errors),
       'maximum_allowed_error_tile_units':4.0,'limits':'Complete source preservation is certified only for GeoParquet; geometry distances are sampled, ID/attribute checks exhaustive.'}
