#!/usr/bin/env python3
"""Opt-in bounded public OpenAlex lookups for the catalog comparison.

Use --identities for count-blind title lookups, or --counts after reference review.
Responses and exact URLs/times are saved; reruns reuse completed requests.
No credentials, account creation, paid allowance or full-text downloads.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'research/catalog-citations-20261030'
FIELDS = 'id,doi,title,type,publication_year,publication_date'


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def request(params):
    url = 'https://api.openalex.org/works?' + urllib.parse.urlencode(params)
    name = hashlib.sha256(url.encode()).hexdigest() + '.json'
    path = HERE / 'responses' / name
    if path.exists():
        return json.loads(path.read_text())
    existing = list((HERE / 'responses').glob('*.json')) if (HERE / 'responses').exists() else []
    searches = sum('search=' in json.loads(p.read_text())['request_url'] for p in existing)
    assert (searches < 60 if 'search' in params else len(existing) - searches < 100), 'Committed request cap reached'
    receipt = {'request_url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(), 'response_path':'responses/' + name}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'data-publications-citation-audit/1.0'}), timeout=60) as r:
            body = r.read(10_000_001)
            assert len(body) <= 10_000_000
            receipt.update(status=r.status, response_sha256=hashlib.sha256(body).hexdigest(), response=json.loads(body))
    except urllib.error.HTTPError as exc:
        body = exc.read()
        receipt.update(status=exc.code,error=body.decode(errors='replace'))
    except Exception as exc:
        receipt.update(status='error',error=str(exc))
    if 'response' in receipt:
        receipt['response_normalized_sha256'] = hashlib.sha256(json.dumps(receipt['response'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    save(path,receipt)
    print(f"OpenAlex {receipt['status']}: {params.get('filter',params.get('search',''))[:100]}",flush=True)
    if receipt['status'] in [401,403,429]:
        raise RuntimeError('Public allowance/auth response; stop, do not create an account or incur paid usage')
    time.sleep(.15)
    return receipt


def reviews():
    return [g for p in sorted(HERE.glob('review-[abc].json')) for g in json.loads(p.read_text())]


def identities():
    queries = sorted({t['title'] for g in reviews() for t in g.get('unresolved_titles',[])})
    if (HERE / 'title-queries.json').exists():
        queries = json.loads((HERE / 'title-queries.json').read_text())
    assert len(queries) <= 60, 'Select a declared bounded batch in title-queries.json; remaining references stay unresolved'
    captures = {}
    for title in queries:
        captures[title] = request({'search':title,'corpus':'all','per_page':5,'select':FIELDS})
    save(HERE / 'identity-searches.json',captures)


def counts():
    official = reviews()
    assert official, 'Reference review must precede scoring'
    dois = {d.lower() for g in official for k in ['paper_dois','data_dois'] for d in g[k]}
    corrections = json.loads((HERE / 'reference-corrections.json').read_text()) if (HERE / 'reference-corrections.json').exists() else []
    dois |= {d.lower() for g in corrections for k in ['add_paper_dois','add_data_dois'] for d in g.get(k,[])}
    old = json.loads((ROOT / 'research/citations/openalex-dois.json').read_text())
    dois |= set(old)
    community = json.loads((ROOT / 'research/citations/rankings.json').read_text())
    ids = {p['work']['id'].split('/')[-1] for row in community for kind in ['papers','data_dois'] for p in row[kind]}
    matches = json.loads((HERE / 'title-matches.json').read_text()) if (HERE / 'title-matches.json').exists() else []
    ids |= {m['work_id'].split('/')[-1] for m in matches}
    observations = {}
    by_id = json.loads((HERE / 'openalex-works.json').read_text()) if (HERE / 'openalex-works.json').exists() else {}
    # Work IDs first ensure the already reviewed community identities are refreshed.
    for field, values in [('openalex',sorted(ids)),('doi',sorted(dois))]:
        for start in range(0,len(values),40):
            batch = values[start:start+40]
            capture = request({'filter':field + ':' + '|'.join(batch),'corpus':'all','per_page':100,'select':FIELDS + ',cited_by_count,counts_by_year'})
            results = capture.get('response',{}).get('results',[])
            for work in results:
                assert isinstance(work.get('cited_by_count'),int) and work['cited_by_count'] >= 0
                # First observation in the common window is canonical for all views.
                by_id.setdefault(work['id'], {'work':work,'retrieved_at':capture['retrieved_at'],'response_path':capture['response_path']})
            if field == 'doi':
                returned = {w['doi'].removeprefix('https://doi.org/').lower():w['id'] for w in results if w.get('doi')}
                for doi in batch:
                    observations[doi] = {'status':'matched' if doi in returned else ('not_found' if capture['status']==200 else 'error'),
                                         'work_id':returned.get(doi), 'response_path':capture['response_path']}
    save(HERE / 'openalex-works.json', dict(sorted(by_id.items())))
    save(HERE / 'doi-resolution.json', dict(sorted(observations.items())))
    print(json.dumps({'works':len(by_id),'doi_queries':len(dois),'id_queries':len(ids),'doi_matched':sum(v['status']=='matched' for v in observations.values())}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--identities',action='store_true');p.add_argument('--counts',action='store_true')
    args=p.parse_args()
    if args.identities: identities()
    if args.counts: counts()
    if not (args.identities or args.counts): p.error('Choose an explicit network phase')

if __name__=='__main__':main()
