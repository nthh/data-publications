"""Build portable STAC 1.1 and Portolan v0.2 metadata plus a deterministic PNG preview."""
from __future__ import annotations
import hashlib,json,struct,zlib
from pathlib import Path
import shapely
from dataset_config import load_config
HERE=Path(__file__).resolve().parent
C=load_config()
DOI='https://doi.org/'+C['source_doi']
CITE='Allen, G. H. & Pavelsky, T. M. (2018). Global extent of rivers and streams. Science, 361(6402), 585–588. https://doi.org/10.1126/science.aat0636'
def write(path,obj): Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def asset(path,base,media,roles,title):
 return {'href':path.relative_to(base).as_posix(),'type':media,'roles':roles,'title':title,'file:size':path.stat().st_size,'file:checksum':'1220'+hashlib.sha256(path.read_bytes()).hexdigest()}
def png_chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
def thumbnail(path,table):
 width,height=1000,500;background=(245,248,249);ink=(26,112,135);pixels=bytearray(background*(width*height))
 def draw(x0,y0,x1,y1):
  dx=abs(x1-x0);sx=1 if x0<x1 else -1;dy=-abs(y1-y0);sy=1 if y0<y1 else -1;err=dx+dy
  while True:
   if 0<=x0<width and 0<=y0<height:
    i=(y0*width+x0)*3;pixels[i:i+3]=bytes(ink)
   if x0==x1 and y0==y1:break
   e2=2*err
   if e2>=dy:err+=dy;x0+=sx
   if e2<=dx:err+=dx;y0+=sy
 def xy(lon,lat):return (round((float(lon)+180)/360*(width-1)),round((90-float(lat))/180*(height-1)))
 for raw in table['geometry'].to_pylist():
  geom=shapely.from_wkb(raw)
  for part in geom.geoms:
   coords=part.coords
   # Drawing every second original vertex keeps a crisp overview and avoids analysis claims.
   selected=list(coords[::2])
   if selected and selected[-1]!=coords[-1]:selected.append(coords[-1])
   for a,b in zip(selected,selected[1:]):draw(*xy(*a),*xy(*b))
 rows=b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
 image=b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+png_chunk(b'IDAT',zlib.compress(rows,9))+png_chunk(b'IEND',b'')
 Path(path).write_bytes(image)
def build_catalog(root,table,schema,bbox,revision):
 folder=root/'grwl';description=('Global River Width from Landsat (GRWL) simplified global river network summary. This is the complete V01.02 summary polyline archive, converted from the producer ZIP. It is a static derived global river network; widths and lengths are producer attributes.')
 rootread=f'''# {C['title']}\n\n{description}\n\nThe analytic [GeoParquet](grwl/README.md) retains all 42,077 source features, ten numeric DBF fields, multipart structure, vertices, nulls and original coordinate values. [catalog.json](catalog.json) is a relative STAC catalog. This is local preparation only; publication remains pending.\n\n## Provenance and license\n\nSource DOI: {DOI}. The pinned file is `GRWL_summaryStats_V01.02.zip`, SHA-256 `{C['source_sha256']}`. Zenodo metadata says V01.01 while the selected archive name is V01.02; this build identifies exact bytes by DOI, filename and checksum. The source release declares CC BY 4.0.\n\n{CITE}\n'''
 (root/'README.md').write_text(rootread)
 guidance='''# Dataset guidance for agents\n\nUse the GeoParquet for analysis. PMTiles and thumbnail are presentation derivatives. Preserve producer IDs, source row identity, null values, numeric precision, all polyline parts and source vertices. The source DOI, version, archive and license are recorded in dataset.yaml and manifest.json. Public hosting and Portolan submission remain pending.\n'''
 (root/'AGENTS.md').write_text(guidance);(folder/'AGENTS.md').write_text(guidance)
 fields='\n'.join(f"| `{x['name']}` | `{x['type']}` | {x['description']} | {x['unit'] or '—'} |" for x in schema)
 (folder/'README.md').write_text(f'''# GRWL summary V01.02\n\n{description}\n\nUse `grwl-summary-v0102.parquet` for analysis. It has 42,077 features, all ten numeric DBF fields, producer `ID` values and one-based unique `source_row`. Numeric fields use fixed-point Arrow decimals matching source values; the storage scale expands where source scientific notation exceeds the nominal DBF scale. DBF asterisks are null. Geometry is WKB MultiLineString, EPSG:4326, retaining each SHP part and source XY vertex in order. Per-row bbox struct and GeoParquet covering metadata permit spatial pruning.\n\n`grwl-display.pmtiles` is a display derivative (PMTiles v3, layer `grwl`, zoom 0–10). At z10 every source row occurs; producer IDs repeat and remain attributes. Line simplification and Web Mercator tile quantization alter display geometry. The SHP header bbox alone overshoots 180 by 1e-10 degrees; all feature vertices are in valid longitude bounds, so the display-only clamp is a no-op. Never use PMTiles or the PNG thumbnail for analysis. The MapLibre style stores a relative PMTiles path. Resolve it against the style URL, register the PMTiles protocol, then prepend `pmtiles://` to the resolved archive URL before loading the style.\n\nThe source has ten numeric fields. Width fields are metres; `nSegPx` is a pixel/segment count; `lakeFlag` is retained as stored; `Shape_Leng` is geodesic length in km per source XML lineage. `OBJECTID` is Esri's generated row number; `ID` is the producer feature identifier and is not unique.\n\n| Field | Arrow type | Meaning | Unit |\n|---|---|---|---|\n{fields}\n\nSource: [Zenodo record](https://zenodo.org/records/18624542), DOI {DOI}, License: CC-BY-4.0. Cite Allen & Pavelsky (2018), DOI 10.1126/science.aat0636. The catalog's GEE asset corresponds to the older label V01.01; no parity is asserted.\n''')
 (folder/'quality.json').exists()
 thumbnail(folder/'thumbnail.png',table)
 styles=folder/'styles';styles.mkdir(exist_ok=True)
 style={'version':8,'name':'GRWL river widths','metadata':{'folia:display_notice':'PMTiles is a display derivative; use GeoParquet for analysis.'},'sources':{'grwl':{'type':'vector','url':'../grwl-display.pmtiles','attribution':'Allen and Pavelsky, CC BY 4.0; conversion by Folia'}},'layers':[{'id':'background','type':'background','paint':{'background-color':'#f5f8f9'}},{'id':'river-network','type':'line','source':'grwl','source-layer':'grwl','paint':{'line-color':'#1a7087','line-opacity':0.72,'line-width':['interpolate',['linear'],['zoom'],0,0.35,10,1.4]}}]}
 write(styles/'grwl.json',style)
 extensions=['https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json','https://stac-extensions.github.io/file/v2.1.0/schema.json','https://stac-extensions.github.io/table/v1.2.0/schema.json','https://stac-extensions.github.io/scientific/v1.0.0/schema.json','https://stac-extensions.github.io/version/v1.2.0/schema.json','https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json']
 links=[{'rel':'root','href':'../catalog.json','type':'application/json'},{'rel':'parent','href':'../catalog.json','type':'application/json'},{'rel':'describedby','href':'README.md','type':'text/markdown'},{'rel':'agents','href':'AGENTS.md','type':'text/markdown'},{'rel':'thumbnail','href':'thumbnail.png','type':'image/png'},{'rel':'license','href':C['license_url'],'type':'text/html'},{'rel':'via','href':DOI,'type':'text/html'},{'rel':'cite-as','href':'https://doi.org/10.1126/science.aat0636','type':'text/html'},{'rel':'pmtiles','href':'grwl-display.pmtiles','type':'application/vnd.pmtiles','pmtiles:layers':['grwl']}]
 providers=[{'name':'Allen and Pavelsky','roles':['producer','licensor'],'url':'https://doi.org/10.1126/science.aat0636'},{'name':'Folia','roles':['processor','host'],'url':'https://folia.sh','description':'Designated host provider for this prepared catalog. Public hosting and Portolan submission are pending.'}]
 stac_bbox=[-180.0,max(-90,bbox[1]),180.0,min(90,bbox[3])]
 collection={'type':'Collection','stac_version':'1.1.0','stac_extensions':extensions,'id':'grwl','title':C['title'],'description':description,'created':'2026-10-30T00:00:00Z','updated':'2026-10-30T00:00:00Z','license':'CC-BY-4.0','version':'summary-v01.02-local-r1','extent':{'spatial':{'bbox':[stac_bbox]},'temporal':{'interval':[[None,None]]}},'providers':providers,'sci:doi':C['source_doi'],'sci:citation':CITE,'keywords':['river','width','global','Landsat','hydrology','GRWL'],'table:columns':[dict((k,v) for k,v in {'name':x['name'],'type':x['type'],'description':x['description'],'unit':x['unit']}.items() if v is not None) for x in schema],'links':links,'assets':{'data':asset(folder/'grwl-summary-v0102.parquet',folder,'application/vnd.apache.parquet',['data'],'Complete analytic GeoParquet'),'tiles':asset(folder/'grwl-display.pmtiles',folder,'application/vnd.pmtiles',['visual'],'Simplified display vector tiles'),'thumbnail':asset(folder/'thumbnail.png',folder,'image/png',['thumbnail'],'Global river network overview'),'style':asset(styles/'grwl.json',folder,'application/vnd.mapbox.style+json',['style','default'],'MapLibre style for the PMTiles display derivative'),'schema':asset(folder/'schema.json',folder,'application/json',['metadata'],'Field dictionary'),'quality':asset(folder/'quality.json',folder,'application/json',['metadata'],'Source structure and null diagnostics'),'source':{'href':C['source_url'],'type':'application/zip','roles':['source'],'title':'Pinned GRWL summary V01.02 ZIP','file:size':C['source_size'],'file:checksum':'1220'+C['source_sha256']},},'portolan:version':'0.2.0','portolan:status':'prepared-local','portolan:revision':revision}
 write(folder/'collection.json',collection)
 root_links=[{'rel':'root','href':'catalog.json','type':'application/json'},{'rel':'child','href':'grwl/collection.json','type':'application/json','title':C['title']},{'rel':'describedby','href':'README.md','type':'text/markdown'},{'rel':'agents','href':'AGENTS.md','type':'text/markdown'},{'rel':'thumbnail','href':'grwl/thumbnail.png','type':'image/png'},{'rel':'license','href':C['license_url'],'type':'text/html'},{'rel':'via','href':DOI,'type':'text/html'}]
 catalog={'type':'Catalog','stac_version':'1.1.0','stac_extensions':[extensions[0]],'id':'folia-grwl','title':C['title'],'description':description,'created':'2026-10-30T00:00:00Z','updated':'2026-10-30T00:00:00Z','links':root_links,'portolan:version':'0.2.0','portolan:status':'prepared-local','portolan:revision':revision}
 write(root/'catalog.json',catalog)
