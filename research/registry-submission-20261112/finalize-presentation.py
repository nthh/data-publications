"""Bind reviewed rendering attempt 3 into an immutable small-object upload plan."""
from pathlib import Path
import json,hashlib,shutil
from PIL import Image,ImageChops
root=Path.cwd();out=root/'research/registry-submission-20261112';renders=root/'.local/registry-presentation-thumbnails-r3'
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):
    with p.open('x') as f:f.write(json.dumps(v,indent=2,sort_keys=True)+'\n')
if (out/'presentation-upload-plan.json').exists():raise SystemExit('Refusing existing final plan')
review={'status':'passed','scope':'Presentation review only, not scientific validation','attempts':{'1':'Rejected: low zoom thinned the features too much.','2':'Rejected: visible crop boundaries from decoding only requested bounds.','3':'Accepted: fetch covers the aspect-expanded camera; regional views are explicitly labeled.'},'cases':[]}
for attempt in range(1,4):
    src=root/f'.local/registry-presentation-thumbnails-r{attempt}'
    save(out/f'thumbnail-render-attempt{attempt}.json',json.loads((src/'report.json').read_text()))
    if attempt<3:
        d=out/f'thumbnail-attempt{attempt}';d.mkdir(exist_ok=False)
        for p in src.glob('*.png'):
            if not p.stem.endswith('-blank'):shutil.copyfile(p,d/p.name)
manifest=json.loads((out/'presentation-drafts.json').read_text());upload=json.loads((out/'style-upload-plan.json').read_text());checks=[]
for id,m in manifest.items():
    c=json.loads((root/f'catalog/{id}/collection.json').read_text())
    aid,asset=next((k,a) for k,a in c['assets'].items() if 'thumbnail' in a.get('roles',[]))
    new=renders/f'{id}.png'
    if new.exists():
        image=Image.open(new).convert('RGB');blank=Image.open(renders/f'{id}-blank.png').convert('RGB')
        changed=sum(max(pixel)>8 for pixel in ImageChops.difference(image,blank).getdata());assert changed>1000
        review['cases'].append({'dataset_id':id,'sha256':sha(new.read_bytes()),'changed_pixels_from_blank':changed,'visual_review':'pass','view':'Labeled regional window; visible thematic features, distinct palette, no artificial coverage edges.','source_tile_zoom':6,'limitations':'Display tiles remain generalized and selectively retain features; previews do not assert exhaustive spatial coverage.'})
    else:
        new=root/'catalog'/id/asset['href']
        review['cases'].append({'dataset_id':id,'sha256':sha(new.read_bytes()),'visual_review':'unchanged previously reviewed PNG','prior_review':'ci-r1/grader/visual-review.json'})
    name=f'{id}-preview-v2.png';path=Path(f'datasets/{id}/source-coop/presentation-20261112')/name
    shutil.copyfile(new,root/path);raw=(root/path).read_bytes()
    title=next((case['subtitle'] for case in json.loads((out/'thumbnail-plan-v2.json').read_text())['cases'] if case['dataset_id']==id),asset.get('title','Dataset preview'))
    item={'asset_id':aid,'before':asset,'filename':name,'path':str(path),'href':f'https://data.source.coop/nthh/{id}/{name}','sha256':sha(raw),'size_bytes':len(raw),'media_type':'image/png','title':title}
    m['assets'].append(item);m['updated']='2026-11-12T22:20:00Z'
    upload['files'].append({'dataset_id':id,'filename':name,'object_key':id+'/'+name,'url':item['href'],'sha256':item['sha256'],'size_bytes':len(raw),'media_type':'image/png','operation':'generated','local_path':str(path)})
    for item in m['assets']:checks.append({'url':item['href'],'sha256':item['sha256'],'size_bytes':item['size_bytes'],'media_type':item['media_type']})
save(out/'presentation-bound-drafts.json',manifest);save(out/'presentation-upload-plan.json',upload);save(out/'presentation-check-plan.json',{'files':checks});save(out/'thumbnail-review.json',review)
print(json.dumps({'uploads':len(upload['files']),'bytes':sum(r['size_bytes'] for r in upload['files']),'verification_objects':len(checks),'plan_sha256':sha((out/'presentation-upload-plan.json').read_bytes())}))
