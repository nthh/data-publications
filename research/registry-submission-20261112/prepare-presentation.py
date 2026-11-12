"""Prepare catalog-only styles and a bounded thumbnail rendering plan, offline.

Run from the repository root before adding presentation pins. The input catalog
must still have its verified flat-data bindings and original presentation assets.
Hosting receipts are produced separately; this script cannot authorize publishing.
"""
from pathlib import Path
import hashlib
import json

ROOT=Path.cwd()
OUT=ROOT/'research/registry-submission-20261112'
def sha(b): return hashlib.sha256(b).hexdigest()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def paint(field,stops,missing='#8a9295'):
    return ['case',['all',['has',field],['!=',['get',field],None],['>=',['to-number',['get',field],-1],0]],['interpolate',['linear'],['get',field],*stops],missing]

cases=[]; manifests={}; uploads=[]
baseplan=json.loads((ROOT/'research/catalog-presentation-20261107/plan.json').read_text())
for id in ('free-flowing-rivers','grwl-raw','hydrolakes','lakeatlas','river-plastic-inputs'):
    collection=json.loads((ROOT/f'catalog/{id}/collection.json').read_text())
    flat=json.loads((ROOT/f'datasets/{id}/source-coop/flat-20261111/manifest.json').read_text())
    directory=ROOT/f'datasets/{id}/source-coop/presentation-20261112'
    directory.mkdir(parents=True,exist_ok=True)
    manifest={'schema_version':1,'dataset_id':id,'release':flat['source_release'],'assets':[]}
    for aid,asset in collection['assets'].items():
        if 'style' not in asset.get('roles',[]): continue
        original=next(f for f in flat['files'] if f.get('asset_id')==aid)
        style=json.loads((ROOT/original['local_path']).read_text())
        name=original['filename']; local=Path(original['local_path']); title=asset['title']
        legend=None
        if id=='free-flowing-rivers':
            color=paint('CSI',[0,'#b64819',50,'#edb15d',95,'#48a787',100,'#006a59'])
            for layer in style['layers']:
                layer['paint']['line-color']=color
                layer['paint']['line-opacity']=0.9
            legend={'label':'Connectivity status index (%)','stops':[['0','#b64819'],['50','#edb15d'],['95','#48a787'],['100','#006a59']]}
            title='River connectivity (CSI, 0–100%)'
        elif id=='hydrolakes':
            color=paint('Lake_area',[0,'#7dbccc',10,'#418fb6',100,'#22609b',1000,'#15366c',10000,'#171f49'])
            for layer in style['layers']:
                layer['paint'].update({'fill-color':color,'fill-opacity':0.95,'fill-outline-color':'#325f83'})
            legend={'label':'Lake surface area (km²)','stops':[['<10','#7dbccc'],['100','#22609b'],['1,000','#15366c'],['≥10,000','#171f49']]}
            title='Lake polygons by surface area (km²)'
        elif id=='lakeatlas':
            color=paint('Lake_area',[0,'#d2a46a',10,'#ac6b3c',100,'#824129',1000,'#571c2b',10000,'#2c0a25'])
            for layer in style['layers']:
                if layer['type']=='fill':layer['paint'].update({'fill-color':color,'fill-opacity':0.9,'fill-outline-color':'#814b41'})
                else:
                    layer['paint'].update({'circle-color':color,'circle-radius':['interpolate',['linear'],['zoom'],0,['interpolate',['linear'],['get','Lake_area'],0,0.6,100,1.4,1000,2.5],8,['interpolate',['linear'],['get','Lake_area'],0,2,100,4,1000,7]],'circle-stroke-color':'#fff7ed','circle-stroke-width':0.3})
            legend={'label':'Lake area at pour point (km²)' if 'points' in name else 'Lake surface area (km²)','stops':[['<10','#d2a46a'],['100','#824129'],['1,000','#571c2b'],['≥10,000','#2c0a25']]}
            title=('Lake pour points' if 'points' in name else 'Lake polygons')+' by lake surface area (km²)'
        if legend:
            style['name']=title
            style.setdefault('metadata',{})['data-publications:legend']=legend
            style['metadata']['data-publications:notice']='Generalized display geometry. Use the GeoParquet and producer field definitions for analysis. Grey indicates unavailable values.'
            name=name.removesuffix('.style.json')+'-presentation-v2.style.json'
            local=directory.relative_to(ROOT)/name
            save(ROOT/local,style)
        raw=(ROOT/local).read_bytes()
        entry={'asset_id':aid,'before':asset,'filename':name,'path':str(local),'href':f'https://data.source.coop/nthh/{id}/{name}','sha256':sha(raw),'size_bytes':len(raw),'media_type':asset['type'],'title':title}
        manifest['assets'].append(entry)
        if legend:
            uploads.append({'dataset_id':id,'filename':name,'object_key':id+'/'+name,'url':entry['href'],'sha256':entry['sha256'],'size_bytes':len(raw),'media_type':asset['type'],'operation':'generated','local_path':str(local)})
            default='default' in asset['roles']
            # A pour-point window distinguishes LakeATLAS from the global polygon card.
            preview=(id!='lakeatlas' and default) or (id=='lakeatlas' and 'points' in name)
            if preview:
                tileurl=style['sources']['data']['url'].removeprefix('pmtiles://')
                tile=next(a for a in collection['assets'].values() if a['href']==tileurl)
                case=next(c.copy() for c in baseplan['cases'] if c['dataset_id']==id)
                case.update(style_path=str(local),style_sha256=sha(raw),pmtiles={'url':tileurl,'size_bytes':tile['file:size'],'sha256':tile['file:checksum'][4:]},legend=legend)
                if id=='lakeatlas':case.update(bounds=[[2,53],[33,72]],subtitle='Pour points sized by lake area · Northern Europe · v1.0')
                cases.append(case)
    manifests[id]=manifest
save(OUT/'presentation-drafts.json',manifests)
save(OUT/'style-upload-plan.json',{'schema_version':1,'endpoint':'https://data.source.coop','bucket':'nthh','files':uploads})
baseplan['cases']=cases
save(OUT/'thumbnail-plan-v2.json',baseplan)
print(json.dumps({'style_objects':len(uploads),'thumbnail_cases':len(cases),'style_bytes':sum(i['size_bytes'] for i in uploads)}))
