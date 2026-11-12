"""Verify small public presentation objects by full hash, range and browser CORS.

No credentials. Usage: python verify-presentation.py --plan PLAN --output NEW_FILE
The plan contains ONLY styles and PNGs with exact hashes and byte lengths.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request

ORIGIN='https://browser.portolan-sdi.org'
EXPOSE={'content-type','content-length','content-range','accept-ranges','etag'}
ALLOW={'range','if-match','if-modified-since','if-none-match','if-unmodified-since'}

def words(value):return {s.strip().lower() for s in value.split(',')}
def request(url,method='GET',headers=None):
    return urllib.request.urlopen(urllib.request.Request(url,method=method,headers={'Origin':ORIGIN,**(headers or {})}),timeout=30)
def check(item):
    result={k:item[k] for k in ('url','sha256','size_bytes')}
    result['status']='failed'
    try:
        if not item['url'].startswith('https://data.source.coop/nthh/') or not 0<item['size_bytes']<10_000_000:
            raise ValueError('Not a bounded presentation object')
        with request(item['url']) as r:
            content=r.read(item['size_bytes']+1)
            if r.status!=200 or len(content)!=item['size_bytes'] or hashlib.sha256(content).hexdigest()!=item['sha256']:
                raise ValueError('Anonymous bytes differ')
            if r.headers.get('access-control-allow-origin') not in ('*',ORIGIN): raise ValueError('GET lacks origin')
            exposed=words(r.headers.get('access-control-expose-headers',''))
            if '*' not in exposed and not EXPOSE<=exposed:raise ValueError('GET lacks exposed headers')
            result['expose_headers']=sorted(exposed)
        with request(item['url'],'HEAD') as r:
            if r.status!=200 or int(r.headers.get('content-length',-1))!=item['size_bytes'] or r.headers.get_content_type()!=item['media_type']:
                raise ValueError('HEAD identity differs')
            result['etag']=r.headers.get('etag')
        start=max(0,len(content)-32)
        with request(item['url'],headers={'Range':f'bytes={start}-{len(content)-1}'}) as r:
            ranged=r.read(33)
            if r.status!=206 or r.headers.get('content-range')!=f'bytes {start}-{len(content)-1}/{len(content)}' or ranged!=content[start:]:
                raise ValueError('Range response differs')
        with request(item['url'],'OPTIONS',{'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':', '.join(sorted(ALLOW))}) as r:
            methods=words(r.headers.get('access-control-allow-methods','')); headers=words(r.headers.get('access-control-allow-headers',''))
            if r.status not in (200,204) or r.headers.get('access-control-allow-origin') not in ('*',ORIGIN):raise ValueError('Preflight origin fails')
            if '*' not in methods and not {'get','head'}<=methods:raise ValueError('Preflight methods fail')
            if '*' not in headers and not ALLOW<=headers:raise ValueError('Preflight headers fail')
            result.update(allow_methods=sorted(methods),allow_headers=sorted(headers))
        result.update(status='verified',cors_passed=True,checksum_method='full_anonymous_readback_sha256')
    except Exception as exc:result['error']=str(exc)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():raise SystemExit('Refusing existing report')
    raw=args.plan.read_bytes();plan=json.loads(raw)
    with ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(check,plan['files']))
    report={'schema_version':1,'status':'complete' if all(o['status']=='verified' for o in objects) else 'failed','plan_sha256':hashlib.sha256(raw).hexdigest(),'checked_at':datetime.now(timezone.utc).isoformat(),'objects':objects}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'objects':len(objects),'failed':[o for o in objects if o['status']!='verified']}))
    raise SystemExit(0 if report['status']=='complete' else 1)
