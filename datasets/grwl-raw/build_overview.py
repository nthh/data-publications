#!/usr/bin/env python3
"""Create a repeatable, source-derived GRWL observation-coverage overview (z0–7).

Cells are closed in continuous spherical Web Mercator. X is periodic; Y is
bounded. These polygons indicate source observation coverage, not riverbanks.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import time
import numpy as np
import pyarrow.parquet as pq
import shapely
from mapbox_vector_tile.Mapbox import vector_tile_pb2 as mvt
from pmtiles.writer import Writer
from pmtiles.tile import Compression, TileType, Entry, zxy_to_tileid

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT/'research/grwl-multiscale-20261103/criteria.json'
CELLS = 512
EXTENT = 4096
MAX_ZOOM = 7
LAYER = 'grwl_overview'
LAT_LIMIT = math.degrees(math.atan(math.sinh(math.pi)))


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False)+'\n')


def guard(task_root, start=False):
    limits = json.loads(CRITERIA.read_text())['resources']
    free = shutil.disk_usage(task_root).free
    floor = limits['minimum_start_free_gib' if start else 'minimum_running_free_gib']*2**30
    used = sum(p.stat().st_size for p in task_root.rglob('*') if p.is_file() and not p.is_symlink())
    if free < floor or used > limits['maximum_new_artifacts_gib']*2**30:
        raise RuntimeError(f'Resource guard: free={free}, task_bytes={used}, floor={floor}')
    return {'free_bytes':free, 'task_bytes':used}


def project_segments(geometries, grid_size):
    """Extract successive vertices WITHIN parts; unwrap each crossing separately."""
    parts = shapely.get_parts(geometries)
    if np.any(shapely.get_type_id(parts) != 1):
        raise ValueError('Overview accepts only LineString or MultiLineString parts')
    xy, part = shapely.get_coordinates(parts, return_index=True)
    if not len(xy):
        return np.empty((0,4), dtype=np.float64)
    if not np.isfinite(xy).all() or np.any(np.abs(xy[:,0]) > 180) or np.any(np.abs(xy[:,1]) > 90):
        raise ValueError('Invalid source longitude/latitude')
    x = (xy[:,0]+180)/360*grid_size
    y = (1-np.arcsinh(np.tan(np.deg2rad(np.clip(xy[:,1],-LAT_LIMIT,LAT_LIMIT))))/np.pi)/2*grid_size
    y = np.clip(y, 0, grid_size)
    keep = part[:-1] == part[1:]
    result = np.column_stack((x[:-1][keep],y[:-1][keep],x[1:][keep],y[1:][keep]))
    dx = result[:,2]-result[:,0]
    result[:,2] = np.where(dx > grid_size/2,result[:,2]-grid_size,
                         np.where(dx < -grid_size/2,result[:,2]+grid_size,result[:,2]))
    return result


def intersects_cell(segments, cx, cy):
    """Vectorized closed slab test; division by zero has explicit semantics."""
    enter = np.zeros(len(segments))
    leave = np.ones(len(segments))
    possible = np.ones(len(segments),dtype=bool)
    for axis, lower in ((0,cx),(1,cy)):
        a = segments[:,axis]
        delta = segments[:,axis+2]-a
        parallel = delta == 0
        possible &= ~parallel | ((a >= lower) & (a <= lower+1))
        t0 = np.divide(lower-a,delta,out=np.full(len(a),-np.inf),where=~parallel)
        t1 = np.divide(lower+1-a,delta,out=np.full(len(a),np.inf),where=~parallel)
        enter = np.maximum(enter,np.minimum(t0,t1))
        leave = np.minimum(leave,np.maximum(t0,t1))
    return possible & (enter <= leave)


def _long_cells(segment, n):
    """Bound candidate work by x strips, not a potentially world-sized bbox."""
    x0,y0,x1,y1 = map(float,segment)
    cells=[]
    for x in range(math.ceil(min(x0,x1))-1,math.floor(max(x0,x1))+1):
        if x0 == x1:
            lo,hi=min(y0,y1),max(y0,y1)
        else:
            a,b=sorted(((x-x0)/(x1-x0),(x+1-x0)/(x1-x0)))
            a,b=max(0,a),min(1,b)
            if a>b:
                continue
            lo,hi=sorted((y0+a*(y1-y0),y0+b*(y1-y0)))
        # Original segment/cell slab test decides candidates, not rounded strip intersections.
        ys=np.arange(max(0,math.ceil(np.nextafter(lo,-np.inf))-1),min(n-1,math.floor(np.nextafter(hi,np.inf)))+1,dtype=np.int64)
        ss=np.repeat(np.asarray(segment)[None,:],len(ys),axis=0)
        good=intersects_cell(ss,np.full(len(ys),x),ys)
        cells.extend((ys[good]*n+(x%n)).tolist())
    return np.asarray(cells,dtype=np.uint64)


def cells_for_segments(segments, grid_size):
    """Return unique row-major cell indices for closed, periodic source segments."""
    segments=np.asarray(segments,dtype=np.float64).reshape(-1,4)
    if not np.isfinite(segments).all():
        raise ValueError('Nonfinite projected segment')
    if len(segments)==0:
        return np.empty(0,dtype=np.uint64)
    lower=np.ceil(np.minimum(segments[:,:2],segments[:,2:])).astype(np.int64)-1
    upper=np.floor(np.maximum(segments[:,:2],segments[:,2:])).astype(np.int64)
    span=upper-lower+1
    normal=np.prod(span,axis=1)<=16
    found=[]
    s=segments[normal]; low=lower[normal]; size=span[normal]
    if len(s):
        for dx in range(int(size[:,0].max())):
            for dy in range(int(size[:,1].max())):
                cx=low[:,0]+dx;cy=low[:,1]+dy
                candidate=(dx<size[:,0])&(dy<size[:,1])&(cy>=0)&(cy<grid_size)
                indices=np.flatnonzero(candidate)
                hit=indices[intersects_cell(s[indices],cx[indices],cy[indices])]
                found.append((cy[hit].astype(np.uint64)*grid_size+(cx[hit]%grid_size).astype(np.uint64)))
    for segment in segments[~normal]:
        found.append(_long_cells(segment,grid_size))
    return np.unique(np.concatenate(found)) if found else np.empty(0,dtype=np.uint64)


def mark_cells(mask, cells):
    np.bitwise_or.at(mask,cells//8,np.left_shift(np.uint8(1),(cells%8).astype(np.uint8)))


def downsample(packed, n):
    """Exact OR of each 2x2 cell block, little-endian bits within each byte."""
    rows=np.asarray(packed).reshape(n,n//8)
    paired=rows[0::2] | rows[1::2]
    lut=np.array([sum(bool(v&(3<<(2*k)))<<k for k in range(4)) for v in range(256)],dtype=np.uint8)
    return (lut[paired[:,0::2]] | (lut[paired[:,1::2]]<<4)).reshape(-1)


def tile_mask(packed,n,x,y):
    rows=np.asarray(packed).reshape(n,n//8)
    block=rows[y*CELLS:(y+1)*CELLS,x*(CELLS//8):(x+1)*(CELLS//8)]
    return np.unpackbits(block,axis=1,bitorder='little')


def zigzag(v):
    return (v<<1)^(v>>31)


def encode_tile(mask):
    """Each horizontal occupied run is its own clockwise valid rectangle."""
    tile=mvt.tile();layer=tile.layers.add();layer.name=LAYER;layer.version=2;layer.extent=EXTENT
    runs=np.diff(np.pad(mask.astype(np.int8),((0,0),(1,1))),axis=1)
    yy,xx=np.where(runs==1);ey,ex=np.where(runs==-1)
    if not np.array_equal(yy,ey):
        raise AssertionError('Unpaired occupancy runs')
    scale=EXTENT//CELLS
    for y,x,xend in zip(yy,xx,ex,strict=True):
        x,y,xend=int(x)*scale,int(y)*scale,int(xend)*scale
        width=xend-x
        feature=layer.features.add();feature.type=3
        feature.geometry.extend([9,zigzag(x),zigzag(y),26,zigzag(width),0,0,zigzag(scale),zigzag(-width),0,15])
    return gzip.compress(tile.SerializeToString(deterministic=True),compresslevel=6,mtime=0),len(xx)


class ExactWriter(Writer):
    """No hash-only deduplication: avoid Python Writer's unchecked hash collision."""
    def write_tile(self,tileid,data):
        if self.tile_entries and tileid<=self.tile_entries[-1].tile_id:
            raise ValueError('Tiles must be written once, in increasing ID order')
        self.tile_f.write(data)
        self.tile_entries.append(Entry(tileid,self.offset,len(data),1))
        self.hash_to_offset[tileid]=self.offset
        self.offset+=len(data);self.addressed_tiles+=1


def build(source,source_manifest,output,task_root):
    if output.exists():
        raise FileExistsError('Refusing to overwrite overview')
    output.resolve().relative_to(task_root.resolve())
    task_root.mkdir(parents=True,exist_ok=True)
    start_resources=guard(task_root,start=True)
    import sys
    active_lock=Path(sys.prefix).resolve().parent/'uv.lock'
    if sha256(active_lock)!=sha256(ROOT/'scripts/display_tools/uv.lock'):
        raise ValueError('Use the committed display_tools locked environment')
    source_meta=json.loads(source_manifest.read_text())
    source_hash=sha256(source)
    if source_meta['parquet_sha256']!=source_hash:
        raise ValueError('Source manifest hash mismatch')
    output.mkdir(parents=True);(output/'masks').mkdir();(output/'workflow').mkdir()
    for file in (Path(__file__),CRITERIA,ROOT/'scripts/display_tools/uv.lock'):
        shutil.copyfile(file,output/'workflow'/file.name)
    write_json(output/'partial.json',{'status':'building','usable_release':False})
    start=time.monotonic();n=CELLS*(1<<MAX_ZOOM)
    mask=np.memmap(output/'masks'/f'z{MAX_ZOOM}.bin',mode='w+',dtype=np.uint8,shape=(n*n//8,));mask[:]=0
    rows=segments_count=0
    try:
        parquet=pq.ParquetFile(source)
        for index,batch in enumerate(parquet.iter_batches(batch_size=32768,columns=['geometry'],use_threads=False)):
            geometries=shapely.from_wkb(batch['geometry'].to_pylist())
            segments=project_segments(geometries,n)
            mark_cells(mask,cells_for_segments(segments,n))
            rows+=len(batch);segments_count+=len(segments)
            if index%100==0:
                guard(task_root)
                print(json.dumps({'stage':'coverage','rows':rows,'seconds':round(time.monotonic()-start,2)}),flush=True)
        if rows!=source_meta['rows']:
            raise ValueError('Source row count mismatch')
        mask.flush()
        for z in range(MAX_ZOOM-1,-1,-1):
            coarse=downsample(mask,n);n//=2
            coarse.tofile(output/'masks'/f'z{z}.bin')
            mask=np.memmap(output/'masks'/f'z{z}.bin',mode='r',dtype=np.uint8)
        extents=[t['extent'] for t in source_meta['tiles'] if t['extent']]
        bounds=[min(b[0] for b in extents),min(b[1] for b in extents),max(b[2] for b in extents),max(b[3] for b in extents)]
        per_zoom=[]
        with (output/'overview.pmtiles').open('xb') as stream:
            writer=ExactWriter(stream)
            for z in range(MAX_ZOOM+1):
                n=CELLS*(1<<z);mask=np.memmap(output/'masks'/f'z{z}.bin',mode='r',dtype=np.uint8)
                tiles=polygons=occupied=bytes_total=max_bytes=0
                coords=sorted((zxy_to_tileid(z,x,y),x,y) for y in range(1<<z) for x in range(1<<z))
                for tileid,x,y in coords:
                    block=tile_mask(mask,n,x,y)
                    count=int(block.sum())
                    if not count:continue
                    encoded,features=encode_tile(block)
                    writer.write_tile(tileid,encoded);tiles+=1;polygons+=features;occupied+=count
                    bytes_total+=len(encoded);max_bytes=max(max_bytes,len(encoded))
                per_zoom.append({'zoom':z,'tiles':tiles,'polygons':polygons,'occupied_cells':occupied,'tile_bytes':bytes_total,'maximum_tile_bytes':max_bytes})
                guard(task_root);print(json.dumps({'stage':'tiles',**per_zoom[-1]}),flush=True)
            header={'tile_type':TileType.MVT,'tile_compression':Compression.GZIP,
                'min_lon_e7':round(bounds[0]*1e7),'min_lat_e7':round(bounds[1]*1e7),
                'max_lon_e7':round(bounds[2]*1e7),'max_lat_e7':round(bounds[3]*1e7),
                'center_zoom':1,'center_lon_e7':0,'center_lat_e7':0}
            metadata={'name':'GRWL raw observation coverage','description':'Closed cells touched by source observations. Coverage only, not riverbanks or measured width.',
                'attribution':'Allen and Pavelsky (2018), GRWL V01.01; CC BY 4.0',
                'vector_layers':[{'id':LAYER,'minzoom':0,'maxzoom':7,'fields':{},'description':'Source-observation coverage cells'}]}
            writer.finalize(header,metadata)
        report={'status':'built_unvalidated','source_sha256':source_hash,'source_manifest_sha256':sha256(source_manifest),
            'criteria_sha256':sha256(CRITERIA),'rows':rows,'segments':segments_count,'cells_per_tile':CELLS,'extent':EXTENT,
            'seconds':time.monotonic()-start,'per_zoom':per_zoom,'resources_start':start_resources,'resources_end':guard(task_root),
            'packages':{p:importlib.metadata.version(p) for p in ('numpy','pyarrow','shapely','pmtiles','mapbox-vector-tile')},
            'artifacts':{str(p.relative_to(output)):{'size_bytes':p.stat().st_size,'sha256':sha256(p)} for p in sorted(output.rglob('*')) if p.is_file() and p.name!='partial.json'}}
        write_json(output/'build.json',report)
        write_json(output/'partial.json',{'status':'built_unvalidated','usable_release':False})
        return report
    except BaseException as exc:
        write_json(output/'failure.json',{'status':'failed','error':str(exc),'rows':rows,'seconds':time.monotonic()-start})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','source-manifest','output','task-root'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();r=build(a.source,a.source_manifest,a.output,a.task_root)
    print(json.dumps({k:r[k] for k in ('status','rows','segments','seconds')}))
