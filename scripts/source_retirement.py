#!/usr/bin/env python3
"""Prepare an exact Source prefix retirement plan; never delete while preparing.

Derive old/new mappings from verified flat manifests, retain other bytes by
checksum in Git, and keep producer PDFs as flat Source companions. The remote
inventory is an explicit input, not a list of prefixes to delete recursively.
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
from urllib.parse import urlsplit, quote, urljoin
import yaml
import urllib.request

BASE = 'https://data.source.coop/nthh/'
ROOT = Path(__file__).resolve().parents[1]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f'Refusing to replace frozen output: {path}')
    path.write_bytes(data)
    return sha(data)

def checked_key(key, products):
    parts = key.split('/')
    if (len(parts) < 4 or parts[0] not in products or parts[1] not in ('releases', 'display')
            or any(p in ('', '.', '..') for p in parts) or '\\' in key):
        raise ValueError(f'Out-of-scope old key: {key}')
    return key

def tracked_by_hash(root):
    result = {}
    for name in subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0'):
        p = root / name
        if not name or not p.is_file() or p.is_symlink():
            continue
        result.setdefault(sha(p.read_bytes()), []).append(name)
    return result

def prepare(root, inventory_path, flat_path, output):
    inventory = json.loads(inventory_path.read_bytes())
    flat = json.loads(flat_path.read_bytes())
    assert inventory['bucket'] == flat['bucket'] == 'nthh'
    products = {x['dataset_id'] for x in flat['files']}
    old_to_flat = {}
    for item in flat['files']:
        href = item.get('source_href') or ''
        if href.startswith(BASE):
            old_to_flat[href[len(BASE):]] = item
    by_hash = tracked_by_hash(root)
    cache = root / '.local/source-retirement-cache'
    cache.mkdir(parents=True, exist_ok=True)
    rows = inventory['objects']
    if len({o['key'] for o in rows}) != len(rows):
        raise ValueError('Duplicate source object keys')
    for obj in rows:
        checked_key(obj['key'], products)
    def retain(obj):
        key = obj['key']
        old = dict(obj)
        mapped = old_to_flat.get(key)
        if mapped is not None:
            if obj['size_bytes'] != mapped['source_size_bytes']:
                raise ValueError(f'Source size changed: {key}')
            old['sha256'] = mapped['source_sha256']
            old['retained'] = {'kind': 'flat', 'url': mapped['url'], 'sha256': mapped['sha256'],
                               'size_bytes': mapped['size_bytes'], 'operation': mapped['operation']}
            return old
        if obj['size_bytes'] > 60_000_000 or (key.endswith(('.parquet', '.pmtiles')) and obj['size_bytes'] > 4096):
            raise ValueError(f'Unmapped bulk object: {key}')
        cache_path = cache / sha(key.encode())
        if cache_path.exists():
            data = cache_path.read_bytes()
        else:
            request = urllib.request.Request(BASE + quote(key, safe='/'), headers={'If-Match': obj['etag']})
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=90) as response:
                        if response.headers.get('ETag') != obj['etag']:
                            raise ValueError(f'Source ETag changed: {key}')
                        data = response.read(obj['size_bytes'] + 1)
                    break
                except OSError:
                    if attempt == 2:
                        raise
            if len(data) != obj['size_bytes']:
                raise ValueError(f'Source length changed: {key}')
            cache_path.write_bytes(data)
        digest = sha(data)
        old['sha256'] = digest
        if key.endswith('.pdf'):
            filename = key.rsplit('/', 1)[1]
            target = f"{key.split('/')[0]}/{filename}"
            old['retained'] = {'kind': 'flat_document', 'url': BASE + target,
                               'object_key': target, 'size_bytes': len(data), 'sha256': digest}
        else:
            matches = by_hash.get(digest, [])
            product = key.split('/')[0]
            # Prefer a producer/release filename over a duplicate research blob.
            matches.sort(key=lambda p: (not p.startswith('datasets/' + product + '/'), Path(p).name != Path(key).name, len(p), p))
            if matches:
                path = root / matches[0]
                stored = data
                encoding = 'identity'
            else:
                suffix = Path(key).suffix or '.txt'
                if suffix == '.pmtiles':
                    suffix = '.pmtiles.fixture'  # two tiny, pre-existing test controls
                encoding = 'gzip' if len(data) > 1_000_000 else 'identity'
                stored = gzip.compress(data, mtime=0) if encoding == 'gzip' else data
                path = output / 'archive' / (digest + suffix + ('.gz' if encoding == 'gzip' else ''))
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and path.read_bytes() != stored:
                    raise ValueError(f'Archive collision: {path}')
                path.write_bytes(stored)
            old['retained'] = {'kind': 'git', 'path': path.relative_to(root).as_posix(),
                               'encoding': encoding, 'stored_sha256': sha(stored), 'stored_size_bytes': len(stored),
                               'sha256': digest, 'size_bytes': len(data)}
        return old
    with ThreadPoolExecutor(max_workers=4) as pool:
        retained = list(pool.map(retain, rows))
    plan = {'schema_version': 1, 'bucket': 'nthh', 'endpoint': 'https://data.source.coop',
            'inventory': {'path': inventory_path.relative_to(root).as_posix(), 'sha256': sha(inventory_path.read_bytes())},
            'flat_plan': {'path': flat_path.relative_to(root).as_posix(), 'sha256': sha(flat_path.read_bytes())},
            'objects': retained}
    dump(output / 'retention-plan.json', plan)
    copies = []
    for obj in retained:
        t = obj['retained']
        if t['kind'] == 'flat_document':
            copies.append({'dataset_id': obj['key'].split('/')[0], 'filename': t['object_key'].split('/')[1],
                           'object_key': t['object_key'], 'url': t['url'], 'operation': 'copy',
                           'sha256': obj['sha256'], 'size_bytes': obj['size_bytes'],
                           'source_key': obj['key'], 'source_href': BASE + obj['key'],
                           'source_sha256': obj['sha256'], 'source_size_bytes': obj['size_bytes'],
                           'media_type': 'application/pdf'})
    dump(output / 'document-copy-plan.json', {'schema_version': 1, 'bucket': 'nthh',
         'endpoint': 'https://data.source.coop', 'layout_id': 'support-20261111',
         'scope': 'Flat producer documents; exact copies only.', 'files': copies})
    print(json.dumps({'objects': len(retained), 'bytes': sum(o['size_bytes'] for o in retained),
                      'new_archive_files': len(list((output / 'archive').glob('*'))),
                      'producer_documents': len(copies)}))

def prepare_support(root, output, revision, receipt_path):
    if not __import__('re').fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Use an exact committed retention revision')
    plan_path = output / 'retention-plan.json'
    plan = json.loads(plan_path.read_bytes())
    receipt = json.loads(receipt_path.read_bytes())
    if receipt.get('status') != 'complete':
        raise ValueError('Producer document copies must be verified first')
    sources = {BASE + row['key']: row for row in plan['objects']}
    checked = set()
    for row in plan['objects']:
        target = row['retained']
        if target['kind'] != 'git' or target['path'] in checked:
            continue
        data = subprocess.check_output(['git', 'show', revision + ':' + target['path']], cwd=root)
        if sha(data) != target['stored_sha256']:
            raise ValueError('Git retention commit does not contain the exact bytes')
        checked.add(target['path'])
    total = 0
    for product in sorted({row['key'].split('/')[0] for row in plan['objects']}):
        record_path = root / 'datasets' / product / 'dataset.yaml'
        record = yaml.safe_load(record_path.read_text())
        pub = record['publication']
        source = pub['source_coop']
        snapshot_path = root / pub['catalog']['snapshot_path']
        snapshot = json.loads(snapshot_path.read_bytes())
        collection_path = snapshot['collection_path']
        collection = json.loads((snapshot_path.parent / 'files' / collection_path).read_bytes())
        base = urljoin(pub['catalog']['package_base_url'], collection_path)
        files = []
        for aid, asset in collection['assets'].items():
            href = urljoin(base, asset['href'])
            old = sources.get(href)
            if old is None or old['retained']['kind'] not in ('git', 'flat_document'):
                continue
            if any(role in asset.get('roles', []) for role in ('data', 'visual', 'style', 'thumbnail')):
                continue
            if asset.get('file:checksum') != '1220' + old['sha256'] or asset.get('file:size') != old['size_bytes']:
                raise ValueError('Support source disagrees with the immutable collection')
            target = dict(old['retained'])
            if target['kind'] == 'git':
                target['url'] = 'https://raw.githubusercontent.com/nthh/data-publications/' + revision + '/' + quote(target['path'], safe='/')
            files.append({'asset_id': aid, 'source_href': href, 'sha256': old['sha256'],
                          'size_bytes': old['size_bytes'], 'media_type': asset['type'],
                          'roles': asset['roles'], 'title': asset['title'], 'retained': target})
        manifest = {'schema_version': 1, 'dataset_id': product, 'owner': source['owner'],
                    'product_id': source['product_id'], 'source_release': pub['release'],
                    'git_revision': revision, 'retention_plan': {'path': plan_path.relative_to(root).as_posix(), 'sha256': sha(plan_path.read_bytes())},
                    'document_receipt': {'path': receipt_path.relative_to(root).as_posix(), 'sha256': sha(receipt_path.read_bytes())},
                    'files': sorted(files, key=lambda x: x['asset_id'])}
        path = root / 'datasets' / product / 'source-coop' / 'support-20261111.json'
        digest = dump(path, manifest)
        pin = {'manifest_path': path.relative_to(root).as_posix(), 'manifest_sha256': digest}
        if source.get('support_layout') is not None:
            if source['support_layout'] != pin:
                raise ValueError('Existing support pin differs; publish a new revision')
        else:
            text = record_path.read_text()
            marker = '  source_coop:\n'
            if text.count(marker) != 1:
                raise ValueError('Ambiguous canonical source_coop section')
            text = text.replace(marker, marker + '    support_layout:\n      manifest_path: ' + pin['manifest_path'] + '\n      manifest_sha256: ' + digest + '\n')
            record_path.write_text(text)
        total += len(files)
    print(json.dumps({'support_assets': total, 'git_revision': revision, 'checked_retained_git_files': len(checked)}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory', required=True, type=Path)
    p.add_argument('--flat-plan', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--support-revision')
    p.add_argument('--document-receipt', type=Path)
    args = p.parse_args()
    if args.support_revision:
        if not args.document_receipt:
            p.error('--support-revision requires --document-receipt')
        prepare_support(ROOT, ROOT / args.output, args.support_revision, ROOT / args.document_receipt)
    else:
        prepare(ROOT, ROOT / args.inventory, ROOT / args.flat_plan, ROOT / args.output)

if __name__ == '__main__':
    main()
