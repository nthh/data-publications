#!/usr/bin/env python3
"""Capture public GEE STAC metadata only; no GEE API or asset requests.

Network is opt-in (--fetch). --normalize reconstructs reviewed input from cached
raw responses. Full responses are ignored; normalized citation evidence is Git-backed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'research/catalog-citations-20261030'
CACHE = ROOT / '.local/catalog-citations-20261030'
ROOT_URL = 'https://storage.googleapis.com/earthengine-stac/catalog/catalog.json'


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def norm_doi(value):
    value = html.unescape(urllib.parse.unquote(value)).strip()
    value = re.sub(r'\\+([<>_()])', r'\1', value)
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value, flags=re.I)
    return value.rstrip('.,').lower()


def extract_dois(text):
    """Preserve balanced DOI parentheses and internal AMS angle brackets/semicolon."""
    text = html.unescape(re.sub(r'\\+([<>_()])', r'\1', str(text)))
    found = set()
    for match in re.finditer(r'10\.\d{4,9}/', text, re.I):
        chars, stack = [], []
        for ch in text[match.start():]:
            if ch.isspace() or ch in '\"{}':
                break
            if ch in '([':
                stack.append(ch)
            elif ch in ')]':
                opener = '(' if ch == ')' else '['
                if not stack or stack[-1] != opener:
                    break
                stack.pop()
            chars.append(ch)
        value = ''.join(chars).rstrip('.,')
        if value.endswith('>') and '<' not in value:
            value = value[:-1]
        value = norm_doi(value)
        if value:
            found.add(value)
    return sorted(found)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def fetch_one(url):
    assert url.startswith('https://storage.googleapis.com/earthengine-stac/catalog/'), url
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'data-publications-citation-audit/1.0'}), timeout=40) as response:
                body = response.read(5_000_001)
                assert len(body) <= 5_000_000, 'Document exceeds cap'
                obj = json.loads(body)
                digest = hashlib.sha256(body).hexdigest()
                (CACHE / 'raw').mkdir(parents=True, exist_ok=True)
                (CACHE / 'raw' / (digest + '.json')).write_bytes(body)
                return obj, {'url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(), 'status':response.status, 'bytes':len(body), 'sha256':digest}
        except Exception as exc:
            error = str(exc)
            time.sleep(attempt + 1)
    return None, {'url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(), 'status':'error', 'error':error}


def crawl():
    pending, seen, receipts = {ROOT_URL}, set(), []
    total_bytes = 0
    while pending:
        batch = sorted(pending - seen)
        pending = set()
        assert len(seen) + len(batch) <= 3000, 'Document cap'
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch_one, u):u for u in batch}
            for future in as_completed(futures):
                obj, receipt = future.result()
                seen.add(receipt['url']); receipts.append(receipt)
                total_bytes += receipt.get('bytes', 0)
                assert total_bytes <= 120_000_000, 'Metadata byte cap'
                if obj and obj.get('type') == 'Catalog':
                    for link in obj.get('links', []):
                        if link.get('rel') == 'child':
                            pending.add(urllib.parse.urljoin(receipt['url'], link['href']))
        print(f'Captured {len(receipts)} metadata documents / {total_bytes} bytes; next {len(pending - seen)}', flush=True)
    save(STUDY / 'catalog-fetch.json', sorted(receipts, key=lambda r:r['url']))
    if any(r['status'] == 'error' for r in receipts):
        raise RuntimeError('Incomplete catalog capture; see receipts')


def normalize():
    receipts = json.loads((STUDY / 'catalog-fetch.json').read_text())
    entries = []
    groups = {}
    for receipt in receipts:
        if receipt['status'] != 200:
            continue
        body = (CACHE / 'raw' / (receipt['sha256'] + '.json')).read_bytes()
        assert hashlib.sha256(body).hexdigest() == receipt['sha256']
        obj = json.loads(body)
        if obj.get('type') != 'Collection':
            continue
        citation = {k:obj[k] for k in ['sci:citation','sci:doi','sci:publications'] if k in obj}
        # Empty references share a review group only when provider/title family does.
        key = json.dumps(citation, sort_keys=True)
        group_id = 'refs-' + hashlib.sha256(key.encode()).hexdigest()[:12]
        refs = []
        for field, value in citation.items():
            for doi in sorted({d for text in strings(value) for d in extract_dois(text)}):
                refs.append({'doi':doi, 'field':field})
        entry = {
            'id':obj['id'], 'title':obj.get('title',obj['id']),
            'catalog_url':'https://developers.google.com/earth-engine/datasets/catalog/' + obj['id'].replace('/','_'),
            'stac_url':receipt['url'], 'source_sha256':receipt['sha256'],
            'deprecated':obj.get('deprecated',False), 'gee_status':obj.get('gee:status'),
            'user_uploaded':obj.get('gee:user_uploaded'),
            'description':obj.get('description',''),
            'description_references':extract_dois(obj.get('description','')), 'bbox':obj.get('extent',{}).get('spatial',{}).get('bbox',[]),
            'temporal_extent':obj.get('extent',{}).get('temporal'),
            'providers':obj.get('providers',[]), 'license':obj.get('license'),
            'citation_fields':citation, 'references':refs, 'review_group':group_id,
            'version_links':[l for l in obj.get('links',[]) if l.get('rel') in ['latest-version','predecessor-version','successor-version']],
        }
        entries.append(entry)
        group = groups.setdefault(group_id, {'id':group_id,'citation_fields':citation,'references':refs,'entries':[]})
        group['entries'].append({'id':entry['id'],'title':entry['title'],'bbox':entry['bbox'], 'description':entry['description']})
    entries.sort(key=lambda r:r['id'])
    assert len(entries) == len({r['id'] for r in entries})
    save(STUDY / 'official-entries.json', entries)
    group_list = sorted(groups.values(), key=lambda r:r['id'])
    save(STUDY / 'reference-groups.json', group_list)
    for i, name in enumerate(['a','b','c']):
        save(STUDY / ('review-input-' + name + '.json'), group_list[i::3])
    print(json.dumps({'collections':len(entries),'reference_groups':len(groups),'deprecated':sum(e['deprecated'] for e in entries),'unique_dois':len({r['doi'] for e in entries for r in e['references']})}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--normalize', action='store_true')
    args = parser.parse_args()
    if args.fetch:
        if (STUDY / 'catalog-fetch.json').exists():
            raise FileExistsError('Snapshot already exists; declare a new dated study before refreshing')
        crawl()
    if args.normalize:
        normalize()
    if not (args.fetch or args.normalize):
        parser.error('Choose --fetch and/or --normalize')

if __name__ == '__main__':
    main()
