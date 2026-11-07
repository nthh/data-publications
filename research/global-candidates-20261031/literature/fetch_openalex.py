#!/usr/bin/env python3
"""Opt-in, bounded DOI-resolved OpenAlex work capture; never overwrites an existing output."""
import argparse, datetime as dt, json, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
identities=json.loads((HERE/'paper-identities.json').read_text())
DOIS=[]
for p in identities['papers']:
    DOIS.append((p['suggested_id'],'primary',p['paper']['doi']))
    for i,x in enumerate(p.get('related_papers',[])+p.get('related_edition_papers',[]),1):
        DOIS.append((p['suggested_id'],f'related_{i}',x['doi']))
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output',required=True,help='new JSON path; must not already exist')
ap.add_argument('--allow-network',action='store_true',help='required explicit opt-in to send public metadata requests')
args=ap.parse_args()
if not args.allow_network: ap.error('pass --allow-network after reviewing the DOI list')
out=Path(args.output)
if not out.is_absolute(): out=(HERE/out).resolve()
if out.exists(): ap.error(f'refusing to overwrite {out}')
MAX_TOTAL_BYTES=10_000_000
MAX_RESPONSE_BYTES=2_000_000
bytes_received=0
results=[]
for i,(candidate,role,doi) in enumerate(DOIS):
    encoded=urllib.parse.quote(doi,safe='')
    url='https://api.openalex.org/works/https://doi.org/'+encoded
    record={'candidate_id':candidate,'doi_role':role,'doi':doi,'request_url':url,'requested_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':None,'response':None,'error':None}
    req=urllib.request.Request(url,headers={'User-Agent':'folia-global-candidates-literature-review/1.0 (public DOI metadata only)','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as res:
            remaining=MAX_TOTAL_BYTES-bytes_received
            body=res.read(min(MAX_RESPONSE_BYTES,remaining)+1)
            bytes_received+=len(body)
            record['status']=res.status
            if len(body)>MAX_RESPONSE_BYTES or bytes_received>MAX_TOTAL_BYTES:
                record['error']='response exceeded per-work or 10 MB total response guard; body omitted'
            else:
                try: record['response']=json.loads(body)
                except Exception as e: record['error']=f'JSON parse error: {type(e).__name__}: {e}'; record['response_text']=body.decode('utf-8','replace')
    except urllib.error.HTTPError as e:
        body=e.read(65537); record['status']=e.code
        try: record['response']=json.loads(body)
        except Exception: record['response_text']=body.decode('utf-8','replace')
        record['error']=f'HTTPError: {e.code} {e.reason}'
    except Exception as e:
        record['error']=f'{type(e).__name__}: {e}'
    results.append(record)
    if bytes_received>MAX_TOTAL_BYTES:
        break
    if i+1<len(DOIS): time.sleep(0.25)
payload={'schema_version':1,'provider':'OpenAlex public API','captured_at':dt.datetime.now(dt.timezone.utc).isoformat(),'query_count':len(results),'request_plan_count':len(DOIS),'response_bytes_read':bytes_received,'max_response_bytes':MAX_RESPONSE_BYTES,'max_total_response_bytes':MAX_TOTAL_BYTES,'api_key_used':False,'dataset_asset_requests':0,'records':results}
out.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'output':str(out),'requests':len(DOIS),'http_success':sum(isinstance(x['status'],int) and 200<=x['status']<300 for x in results),'unresolved_or_failed':sum(x['response'] is None for x in results)}))
