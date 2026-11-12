"""Verified presentation assets and field semantics for generated catalog metadata.

The immutable analytical releases remain the source of asset identity. This
optional overlay can replace styles/thumbnails and fill missing descriptions;
it cannot replace data, PMTiles, column names, or types.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import re
from flat_publication import _asset_sha, _read_json, _repo_file, _sha256, _pin_sha


def pinned_json(root, pin, label):
    value, data = _read_json(root, pin['path'], label)
    if _sha256(data) != _pin_sha(pin['sha256'], label):
        raise ValueError(f'{label} checksum differs')
    return value


def load_presentation(root: Path, record: dict) -> dict | None:
    pin = record.get('publication', {}).get('catalog', {}).get('presentation')
    if pin is None:
        return None
    manifest = pinned_json(root, pin, 'presentation manifest')
    source = record['publication']['source_coop']
    if (manifest.get('schema_version') != 1 or manifest.get('dataset_id') != record['id']
            or manifest.get('release') != record['publication']['release']):
        raise ValueError('Presentation identity differs')
    receipt = pinned_json(root, manifest['hosting'], 'presentation hosting evidence')
    if receipt.get('status') != 'complete':
        raise ValueError('Presentation hosting verification is incomplete')
    verified = {item['url']: item for item in receipt['objects']}
    seen = set()
    for item in manifest['assets']:
        aid = item['asset_id']
        if aid in seen:
            raise ValueError('Duplicate presentation asset')
        seen.add(aid)
        name = item['filename']
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*', name):
            raise ValueError('Presentation must use flat filenames')
        url = f"https://data.source.coop/{source['owner']}/{source['product_id']}/{name}"
        content = _repo_file(root, item['path'], 'presentation asset').read_bytes()
        sha = _pin_sha(item['sha256'], 'presentation asset')
        if item['href'] != url or len(content) != item['size_bytes'] or _sha256(content) != sha:
            raise ValueError('Presentation bytes or destination differ')
        proof = verified.get(url, {})
        if (proof.get('status') != 'verified' or proof.get('sha256') != sha
                or proof.get('size_bytes') != len(content) or not proof.get('cors_passed')):
            raise ValueError('Presentation lacks exact anonymous hosting and CORS verification')
        if item['media_type'] == 'image/png':
            if not content.startswith(b'\x89PNG\r\n\x1a\n') or not name.endswith('.png'):
                raise ValueError('Invalid presentation PNG')
        elif item['media_type'] == 'application/vnd.mapbox.style+json':
            style = json.loads(content)
            if style.get('version') != 8 or not style.get('layers') or not name.endswith('.json'):
                raise ValueError('Invalid presentation style')
        else:
            raise ValueError('Only styles and thumbnails may be presented')
        if len(content) > 10_000_000:
            raise ValueError('Presentation asset exceeds metadata size limit')
    return manifest


def apply_presentation(root, record, collection, tree):
    manifest = load_presentation(root, record)
    if manifest is None:
        return
    assets = collection['assets']
    rewrites, remove = {}, []
    pmtiles = {a['href'] for a in assets.values() if a.get('type') == 'application/vnd.pmtiles'}
    for item in manifest['assets']:
        aid = item['asset_id']
        asset = assets.get(aid)
        if not asset or not set(asset.get('roles', [])) & {'style', 'thumbnail'}:
            raise ValueError('Presentation cannot replace analytic or map data')
        if asset != item['before']:
            raise ValueError(f'Presentation source asset identity differs: {aid}')
        original = asset['href']
        if 'style' in asset['roles']:
            content = _repo_file(root, item['path'], 'presentation style').read_bytes()
            style = json.loads(content)
            sources = style.get('sources', {})
            if not sources or any(s.get('type') != 'vector' or s.get('url', '').removeprefix('pmtiles://') not in pmtiles for s in sources.values()):
                raise ValueError('Presentation style must use the existing PMTiles assets')
            for layer in style['layers']:
                if layer.get('type') == 'background' and 'source' not in layer:
                    continue
                if layer.get('source') not in sources:
                    raise ValueError('Presentation layer uses an unbound source')
        elif item['media_type'] != 'image/png':
            raise ValueError('Thumbnail must stay an image')
        asset.update(href=item['href'], type=item['media_type'], title=item['title'])
        asset['file:checksum'] = '1220' + item['sha256']
        asset['file:size'] = item['size_bytes']
        rewrites[original] = item['href']
        if not original.startswith('https://'):
            remove.append(f"{record['id']}/{original.removeprefix('./')}")
    for link in collection['links']:
        if link.get('href') in rewrites:
            link['href'] = rewrites[link['href']]
    for path in remove:
        tree.pop(path, None)
    if manifest.get('updated'):
        updated = datetime.fromisoformat(manifest['updated'].replace('Z', '+00:00'))
        original = datetime.fromisoformat(collection['updated'].replace('Z', '+00:00'))
        if updated < original:
            raise ValueError('Presentation metadata cannot predate the release metadata')
        collection['updated'] = manifest['updated']


def apply_field_semantics(root, record, collection):
    pin = record.get('publication', {}).get('catalog', {}).get('field_semantics')
    if pin is None:
        return
    semantics = pinned_json(root, pin, 'field semantics')
    for aid, binding in semantics['bound_assets'].items():
        if _asset_sha(collection['assets'][aid], aid) != binding['sha256']:
            raise ValueError('Field semantics analytical asset binding differs')
    for column in collection.get('table:columns', []):
        aid, name = column['asset'], column['name']
        if aid not in semantics['bound_assets']:
            raise ValueError('Field semantics omits an analytical asset')
        definition = semantics['assets'][aid]['fields'].get(name, {}).get('definition')
        if not definition:
            raise ValueError(f'Field semantics lacks definition: {aid}.{name}')
        if column.get('description') and column['description'] != definition:
            raise ValueError('Field enrichment cannot silently replace an existing description')
        column['description'] = definition
        unit = semantics['assets'][aid]['fields'][name].get('units_as_published')
        if unit and 'unit' not in column:
            column['unit'] = unit


def render_agents(record, draft):
    lines = [f"# {record['title']}: query guidance", '', draft['temporal_note'], '',
             'Use the following dataset-specific constraints when choosing records, interpreting values, or making comparisons:', '']
    lines.extend('- ' + note for note in draft['limitations'])
    lines.extend(['', '[Field dictionaries, runnable queries and source citations](README.md).',
                  '[Shared catalog conventions](../AGENTS.md).', ''])
    return '\n'.join(lines)
