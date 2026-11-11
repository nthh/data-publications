"""Relocate checksum-bound supporting assets without changing frozen releases."""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from flat_publication import _asset_sha, _read_json, _repo_file, _sha256, _pin_sha, _relpath

REPOSITORY = 'https://github.com/nthh/data-publications'
RAW_REPOSITORY = 'https://raw.githubusercontent.com/nthh/data-publications'

def load_support_layout(root: Path, record: dict) -> dict | None:
    source = (record.get('publication') or {}).get('source_coop') or {}
    pin = source.get('support_layout')
    if pin is None:
        return None
    if source.get('flat_layout') is None:
        raise ValueError('Support relocation requires verified flat data')
    manifest, data = _read_json(root, pin['manifest_path'], 'support manifest')
    if _sha256(data) != _pin_sha(pin['manifest_sha256'], 'support manifest'):
        raise ValueError('Support manifest hash mismatch')
    if (manifest.get('schema_version') != 1 or manifest.get('dataset_id') != record['id']
            or manifest.get('owner') != source['owner'] or manifest.get('product_id') != source['product_id']
            or manifest.get('source_release') != record['publication']['release']):
        raise ValueError('Support manifest identity mismatch')
    revision = manifest.get('git_revision', '')
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Support Git revision must be a commit SHA')
    receipt_pin = manifest.get('document_receipt')
    receipts = {}
    if receipt_pin:
        receipt, receipt_data = _read_json(root, receipt_pin['path'], 'support document receipt')
        if _sha256(receipt_data) != receipt_pin['sha256'] or receipt.get('status') != 'complete':
            raise ValueError('Support document receipt is not verified')
        receipts = {r['url']: r for r in receipt['objects'] if r.get('status') == 'verified'}
    seen = set()
    for item in manifest.get('files', []):
        aid = item['asset_id']
        if aid in seen:
            raise ValueError('Duplicate support asset mapping')
        seen.add(aid)
        _pin_sha(item['sha256'], 'support asset')
        target = item['retained']
        if target['kind'] == 'git':
            rel = _relpath(target['path'], 'retained support file')
            content = _repo_file(root, rel, 'retained support file').read_bytes()
            url = RAW_REPOSITORY + '/' + revision + '/' + quote(rel, safe='/')
            if target.get('encoding') != 'identity' or target.get('url') != url:
                raise ValueError('Support Git URL or encoding differs')
            if len(content) != item['size_bytes'] or _sha256(content) != item['sha256']:
                raise ValueError('Retained support bytes changed')
        elif target['kind'] == 'flat_document':
            name = target['object_key'].split('/')
            if len(name) != 2 or name[0] != source['product_id'] or not name[1].endswith('.pdf'):
                raise ValueError('Support document must be a flat PDF in the same product')
            url = f"https://data.source.coop/{source['owner']}/{target['object_key']}"
            receipt = receipts.get(url, {})
            if (target['url'] != url or receipt.get('sha256') != item['sha256']
                    or receipt.get('size_bytes') != item['size_bytes']):
                raise ValueError('Support document lacks exact hosted verification')
        else:
            raise ValueError('Unsupported support retention kind')
        if target.get('sha256') != item['sha256'] or target.get('size_bytes') != item['size_bytes']:
            raise ValueError('Support relocation must preserve bytes')
    return manifest

def apply_support_layout(root: Path, record: dict, collection: dict) -> dict | None:
    manifest = load_support_layout(root, record)
    if manifest is None:
        return None
    assets = collection['assets']
    mapped = set()
    old_to_new = {}
    for item in manifest['files']:
        aid = item['asset_id']
        asset = assets.get(aid)
        if not asset or asset.get('href') != item['source_href']:
            raise ValueError(f'Support source href differs: {aid}')
        if (_asset_sha(asset, aid) != item['sha256'] or asset.get('file:size') != item['size_bytes']
                or asset.get('type') != item['media_type'] or asset.get('roles') != item['roles']
                or asset.get('title') != item['title']):
            raise ValueError(f'Support asset identity changed: {aid}')
        asset['href'] = item['retained']['url']
        old_to_new[item['source_href']] = asset['href']
        mapped.add(aid)
    for link in collection.get('links', []):
        if link.get('href') in old_to_new:
            link['href'] = old_to_new[link['href']]
    prefixes = legacy_prefixes(record)
    assert_no_legacy_urls(collection, prefixes)
    return manifest

def legacy_prefixes(record):
    source = record['publication']['source_coop']
    base = f"https://data.source.coop/{source['owner']}/{source['product_id']}/"
    return [base + 'releases/', base + 'display/']

def assert_no_legacy_urls(value, prefixes):
    # Only generated consumer metadata is passed here, never historical reports.
    if isinstance(value, str):
        if any(prefix in value for prefix in prefixes):
            raise ValueError('Generated catalog still references a retired Source prefix')
    elif isinstance(value, list):
        for child in value:
            assert_no_legacy_urls(child, prefixes)
    elif isinstance(value, dict):
        for child in value.values():
            assert_no_legacy_urls(child, prefixes)
