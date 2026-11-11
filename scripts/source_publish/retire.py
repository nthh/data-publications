#!/usr/bin/env python3
"""Check or execute a separately frozen Source retirement plan.

Deletion is deliberately separate from catalog generation and publication.
The default is an offline dry run. --live checks the deployed cutover; --execute
additionally removes only exact, unchanged inventoried keys and saves receipts.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flat_publication import _repo_file
from source_retirement import checked_key
from support_publication import assert_no_legacy_urls
from upload import ALLOWED_PRODUCTS, S3Session

BASE = 'https://data.source.coop/nthh/'
PAGES = 'https://nthh.github.io/data-publications/'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def pinned(root, pin):
    raw = _repo_file(root, pin['path'], 'retirement input').read_bytes()
    if sha(raw) != pin['sha256']:
        raise ValueError('Retirement input checksum differs: ' + pin['path'])
    return json.loads(raw)

def get(url, size):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(size + 1)
            if len(data) != size:
                raise ValueError('Remote length differs: ' + url)
            return data
        except OSError:
            if attempt == 2:
                raise

def validate_retention(root, retention, revision):
    if retention.get('bucket') != 'nthh' or retention.get('endpoint') != 'https://data.source.coop':
        raise ValueError('Wrong retirement destination')
    rows = retention['objects']
    if not rows or len(rows) != len({o['key'] for o in rows}):
        raise ValueError('Empty or duplicate retirement objects')
    checked = set()
    for obj in rows:
        checked_key(obj['key'], ALLOWED_PRODUCTS)
        target = obj['retained']
        if target['kind'] == 'git':
            path = _repo_file(root, target['path'], 'retained bytes')
            stored = path.read_bytes()
            if sha(stored) != target['stored_sha256'] or len(stored) != target['stored_size_bytes']:
                raise ValueError('Stored Git retention bytes differ')
            if target['path'] not in checked:
                committed = subprocess.check_output(['git', 'show', revision + ':' + target['path']], cwd=root)
                if committed != stored:
                    raise ValueError('Retention commit lacks the retained bytes')
                checked.add(target['path'])
            if target['encoding'] not in ('identity', 'gzip'):
                raise ValueError('Unsupported archive encoding')
            data = gzip.decompress(stored) if target['encoding'] == 'gzip' else stored
            if sha(data) != obj['sha256'] or len(data) != obj['size_bytes']:
                raise ValueError('Retained bytes differ from old source')
        elif target['kind'] in ('flat', 'flat_document'):
            product = obj['key'].split('/')[0]
            u = urlsplit(target['url'])
            prefix = BASE + product + '/'
            if (not target['url'].startswith(prefix) or '/' in target['url'][len(prefix):]
                    or u.query or u.fragment or not target['url'][len(prefix):]):
                raise ValueError('Retained object is not a flat same-product URL')
            if target.get('operation', 'copy') == 'copy' and (target['sha256'] != obj['sha256'] or target['size_bytes'] != obj['size_bytes']):
                raise ValueError('Copy does not preserve source bytes')
        else:
            raise ValueError('Unsupported retention target')
    return rows

def check_inventory(client, rows, deleted):
    remaining = {o['key']: o for o in rows if o['key'] not in deleted}
    seen = {}
    prefixes = sorted({o['key'].split('/')[0] + '/' + o['key'].split('/')[1] + '/' for o in rows})
    # Include empty display prefixes as well, so all ten product prefixes are checked.
    prefixes = sorted({p + '/' + folder + '/' for p in {o['key'].split('/')[0] for o in rows} for folder in ('releases', 'display')})
    for prefix in prefixes:
        for page in client.get_paginator('list_objects_v2').paginate(Bucket='nthh', Prefix=prefix):
            for obj in page.get('Contents', []):
                seen[obj['Key']] = obj
    if set(seen) != set(remaining):
        raise ValueError('Old prefix inventory changed; no unplanned or missing keys are permitted')
    for key, obj in remaining.items():
        remote = seen[key]
        if remote['ETag'] != obj['etag'] or remote['Size'] != obj['size_bytes']:
            raise ValueError('Old object ETag or length changed: ' + key)

def check_live_catalog(catalog_plan, prefixes):
    if catalog_plan.get('destination') != 'github-pages://nthh/data-publications/':
        raise ValueError('Unexpected catalog destination')
    support = []
    for row in catalog_plan['files']:
        url = row['target_url']
        if not url.startswith(PAGES) or row['size_bytes'] > 2 * 1024 * 1024:
            raise ValueError('Unexpected catalog URL or size')
        raw = get(url, row['size_bytes'])
        if sha(raw) != row['sha256']:
            raise ValueError('Live catalog differs from the staged cutover: ' + url)
        if url.endswith(('.json', '.md')):
            assert_no_legacy_urls(raw.decode(), prefixes)
        if url.endswith('/collection.json'):
            collection = json.loads(raw)
            for asset in collection['assets'].values():
                if asset.get('href', '').startswith('https://raw.githubusercontent.com/nthh/data-publications/'):
                    support.append(asset)
    for asset in support:
        if sha(get(asset['href'], asset['file:size'])) != asset['file:checksum'][4:]:
            raise ValueError('Live Git support bytes differ')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--credential-helper', type=Path, default=Path('/Users/nathan/.cargo/bin/source-coop'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    raw = args.plan.read_bytes()
    if sha(raw) != args.expected_plan_sha256:
        raise ValueError('Execution plan checksum differs')
    execution = json.loads(raw)
    retention = pinned(root, execution['retention_plan'])
    inventory = pinned(root, retention['inventory'])
    if [{k: o[k] for k in ('key', 'etag', 'size_bytes', 'last_modified')} for o in retention['objects']] != inventory['objects']:
        raise ValueError('Retention objects differ from frozen inventory')
    rows = validate_retention(root, retention, execution['git_revision'])
    flat_plan = pinned(root, retention['flat_plan'])
    flat_sources = {o.get('source_href'): o for o in flat_plan['files']}
    for row in rows:
        if row['retained']['kind'] != 'flat':
            continue
        original = flat_sources.get(BASE + row['key'])
        if (not original or original['source_sha256'] != row['sha256'] or original['source_size_bytes'] != row['size_bytes']
                or any(row['retained'][k] != original[k] for k in ('url', 'sha256', 'size_bytes', 'operation'))):
            raise ValueError('Flat replacement differs from verified migration mapping')
    proofs = {}
    for pin in execution['destination_receipts']:
        receipt = pinned(root, pin)
        objects = receipt.get('objects', [receipt])
        for item in objects:
            if item.get('status') == 'verified' and item.get('etag'):
                proofs[item['object_key']] = item
    for row in rows:
        target = row['retained']
        if target['kind'] != 'git':
            key = target['url'][len(BASE):]
            proof = proofs.get(key, {})
            if proof.get('sha256') != target['sha256'] or proof.get('size_bytes') != target['size_bytes']:
                raise ValueError('Missing full-byte destination verification')
    catalog_plan = pinned(root, execution['catalog_plan'])
    readme_plan = pinned(root, execution['readme_plan'])
    browser = pinned(root, execution['browser_report'])
    if browser.get('status') != 'passed' or len(browser.get('cases', [])) != 7 or any(x.get('status') != 'passed' for x in browser['cases']):
        raise ValueError('Seven live flat-style checks must pass')
    if args.output.exists():
        if not args.resume:
            raise ValueError('Receipt already exists; use an explicit resume')
        result = json.loads(args.output.read_bytes())
        if result['execution_plan_sha256'] != args.expected_plan_sha256:
            raise ValueError('Resume plan differs')
    else:
        result = {'schema_version': 1, 'execution_plan_sha256': args.expected_plan_sha256, 'status': 'prepared', 'deleted': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    save()
    if not (args.live or args.execute):
        result.update(objects=len(rows), bytes=sum(o['size_bytes'] for o in rows), scope='offline verification only')
        save(); print(json.dumps({k: v for k, v in result.items() if k != 'deleted'})); return
    try:
        remote_main = subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/heads/main'], cwd=root, text=True).split()[0]
        subprocess.run(['git', 'merge-base', '--is-ancestor', execution['git_revision'], remote_main], cwd=root, check=True)
        prefixes = [BASE + p + '/' + f + '/' for p in ALLOWED_PRODUCTS for f in ('releases', 'display')]
        check_live_catalog(catalog_plan, prefixes)
        for row in readme_plan['mutable_metadata']:
            raw = get(row['raw_url_proposed'], row['size_bytes'])
            if sha(raw) != row['sha256']:
                raise ValueError('Source README differs from cutover plan')
            assert_no_legacy_urls(raw.decode(), prefixes)
        for key, proof in proofs.items():
            with urllib.request.urlopen(urllib.request.Request(BASE + key, method='HEAD'), timeout=30) as response:
                if response.headers.get('ETag') != proof['etag'] or int(response.headers['Content-Length']) != proof['size_bytes']:
                    raise ValueError('Verified destination changed: ' + key)
        client = S3Session(args.credential_helper).client()
        deleted = set(result['deleted'])
        if not deleted <= {o['key'] for o in rows}:
            raise ValueError('Resume contains unplanned deletes')
        check_inventory(client, rows, deleted)
        result.update(status='preflight_passed', checked_at=datetime.now(timezone.utc).isoformat(), remote_main=remote_main)
        save()
        if args.execute:
            result['status'] = 'deleting'; save()
            for obj in rows:
                if obj['key'] in deleted:
                    continue
                head = client.head_object(Bucket='nthh', Key=obj['key'])
                if head['ETag'] != obj['etag'] or head['ContentLength'] != obj['size_bytes']:
                    raise ValueError('Object changed after preflight')
                client.delete_object(Bucket='nthh', Key=obj['key'], IfMatch=obj['etag'])
                result['deleted'].append(obj['key']); deleted.add(obj['key']); save()
            check_inventory(client, rows, deleted)
            result.update(status='complete', completed_at=datetime.now(timezone.utc).isoformat())
            save()
        print(json.dumps({'status': result['status'], 'deleted': len(result['deleted'])}))
    except Exception as exc:
        result.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        save(); raise

if __name__ == '__main__':
    main()
