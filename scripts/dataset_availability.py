"""Validate and render the reviewed, bounded dataset availability view."""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote, urlsplit

from record_locations import record_path


def _https(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == 'https' and bool(parsed.hostname) and
                parsed.username is None and parsed.password is None and
                not any(c.isspace() for c in value))
    except ValueError:
        return False


def _safe_file(root: Path, relative: str, *, limit: int | None = None) -> Path:
    """Resolve a repository-relative regular file without traversing symlinks."""
    rel = PurePosixPath(relative)
    if not relative or rel.is_absolute() or '..' in rel.parts or '\\' in relative:
        raise ValueError(f'Unsafe evidence path: {relative}')
    path = root
    for part in rel.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Symlink evidence path: {relative}')
    if not path.is_file():
        raise ValueError(f'Missing evidence file: {relative}')
    if limit is not None and path.stat().st_size >= limit:
        raise ValueError(f'Evidence file is not smaller than {limit} bytes: {relative}')
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified_evidence(root: Path, item: dict) -> Path:
    path = _safe_file(root, item['path'], limit=10_000_000)
    if not re.fullmatch(r'[0-9a-f]{64}', item['sha256']) or _sha(path) != item['sha256']:
        raise ValueError(f"Availability evidence checksum mismatch: {item['path']}")
    try:
        value = json.loads(path.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Availability evidence must be valid JSON: {item["path"]}') from exc
    candidates = value.get('candidates') if isinstance(value, dict) else None
    if not isinstance(candidates, list):
        raise ValueError(f'Availability evidence is missing a candidates list: {item["path"]}')
    matches = [row for row in candidates if isinstance(row, dict)
               and item['key'] in (row.get('evidence_key'), row.get('suggested_id'))]
    if len(matches) != 1:
        raise ValueError(f"Availability evidence key must occur exactly once: {item['path']}#{item['key']}")
    return path


def _manifest_assets(root: Path, availability: dict) -> list[dict] | None:
    manifest = availability.get('output_manifest')
    if manifest is None:
        return None
    path = _safe_file(root, manifest['path'], limit=10_000_000)
    if not re.fullmatch(r'[0-9a-f]{64}', manifest['sha256']) or _sha(path) != manifest['sha256']:
        raise ValueError(f"Output manifest checksum mismatch: {manifest['path']}")
    data = json.loads(path.read_text())
    raw = data.get('assets') if isinstance(data, dict) else None
    if isinstance(raw, list):
        assets = raw
    elif isinstance(raw, dict):
        assets = [dict(value, href=key) for key, value in raw.items() if isinstance(value, dict)]
        if len(assets) != len(raw):
            raise ValueError(f'Invalid legacy output assets: {manifest["path"]}')
    else:
        raise ValueError(f'Invalid output manifest assets: {manifest["path"]}')
    seen = set()
    selected = []
    for asset in assets:
        href = asset.get('href')
        size = asset.get('size_bytes')
        if not isinstance(href, str) or not href or href in seen:
            raise ValueError(f'Invalid or duplicate output asset path: {href}')
        seen.add(href)
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f'Invalid output asset size: {href}')
        # Package bundles, docs, and all other files are intentionally omitted.
        suffix = PurePosixPath(urlsplit(href).path).suffix.lower()
        if suffix not in ('.parquet', '.pmtiles'):
            continue
        if suffix == '.parquet' and size == 0:
            raise ValueError(f'Analytic Parquet asset must have positive size: {href}')
        selected.append({'href': href, 'size_bytes': size,
                         'media_type': asset.get('media_type'),
                         'kind': 'analytic' if suffix == '.parquet' else 'display'})
    if not any(asset['kind'] == 'analytic' for asset in selected):
        raise ValueError(f'Output manifest has no analytic Parquet assets: {manifest["path"]}')
    return selected


def _sizes(root: Path, availability: dict) -> tuple[list[dict] | None, int | None, int | None]:
    assets = _manifest_assets(root, availability)
    if assets is None:
        return None, None, None
    analytic = sum(a['size_bytes'] for a in assets if a['kind'] == 'analytic')
    display = sum(a['size_bytes'] for a in assets if a['kind'] == 'display')
    return assets, analytic, display


def validate_availability(root: Path, records: dict) -> None:
    ranks: dict[str, list[int]] = {}
    for record_id, record in records.items():
        block = record.get('review', {}).get('availability')
        if not block:
            continue
        download = block['download']
        precision, size = download['precision'], download['bytes']
        if precision == 'unknown' and (size is not None or download['reported_size'] is not None):
            raise ValueError(f'Unknown source size must retain null bytes and reported_size: {record_id}')
        if precision == 'exact' and (not isinstance(size, int) or size <= 0):
            raise ValueError(f'Exact source size must be positive bytes: {record_id}')
        if precision == 'rounded' and size is None and not download['reported_size']:
            raise ValueError(f'Rounded source size needs bytes or a reported size: {record_id}')
        size_key = block.get('source_size_key')
        if size_key is not None and record.get('source', {}).get(size_key) != size:
            raise ValueError(f'Source size key mismatch: {record_id}/{size_key}')
        shortlist = block['shortlist_id']
        ranks.setdefault(shortlist, []).append(block['rank'])
        services = [location['service_id'] for location in block['locations']]
        if len(services) != len(set(services)):
            raise ValueError(f'Duplicate availability service ID: {record_id}')
        for location in block['locations']:
            if any(not _https(url) for url in location['urls']):
                raise ValueError(f'Availability URLs must be credential-free HTTPS: {record_id}/{location["service_id"]}')
            if location['platform'] == 'external' and location['asset_ids']:
                raise ValueError(f'External availability location has asset IDs: {record_id}/{location["service_id"]}')
            if location['platform'] == 'gee':
                if location['service_id'] != 'earth_engine' or not location['asset_ids'] or len(set(location['asset_ids'])) != len(location['asset_ids']):
                    raise ValueError(f'Invalid GEE availability assets: {record_id}')
        for evidence in block['evidence']:
            _verified_evidence(root, evidence)
        _sizes(root, block)
    for shortlist, values in ranks.items():
        if len(values) != len(set(values)) or sorted(values) != list(range(1, len(values) + 1)):
            raise ValueError(f'Availability ranks must be unique and contiguous for {shortlist}')


def _display_size(value: int | None, precision: str, reported: str | None) -> str:
    if value is None:
        return reported if reported else ('Unknown' if precision == 'unknown' else 'Not reported')
    unit, amount = ('GB', value / 1_000_000_000) if value >= 1_000_000_000 else ('MB', value / 1_000_000)
    formatted = f'{amount:.2f}'.rstrip('0').rstrip('.')
    return ('~' if precision == 'rounded' else '') + f'{formatted} {unit}'


def summary(root: Path, record: dict) -> dict:
    block = record.get('review', {}).get('availability')
    if not block:
        return {}
    locations = block['locations']
    external = [item for item in locations if item['platform'] == 'external']
    gee = [item for item in locations if item['platform'] == 'gee']
    _, analytic, display = _sizes(root, block)
    download = block['download']
    return {
        'shortlist_id': block['shortlist_id'], 'shortlist_rank': block['rank'],
        'source_download_bytes': download['bytes'], 'source_size_precision': download['precision'],
        'source_size_display': _display_size(download['bytes'], download['precision'], download['reported_size']),
        'external_locations': len(external),
        'external_matching_locations': sum(x['relationship'] == 'matching_scope' for x in external),
        'gee_locations': len(gee),
        'gee_matching_locations': sum(x['relationship'] == 'matching_scope' for x in gee),
        'gee_asset_count': sum(len(x['asset_ids']) for x in gee),
        'prepared_analytic_bytes': analytic, 'prepared_display_bytes': display,
        'prepared_data_bytes': None if analytic is None else analytic + (display or 0),
    }


def _md(value: str) -> str:
    return html.escape(' '.join(str(value).split()), quote=False).replace('|', r'\|').replace('`', r'\`')


def _link(label: str, url: str) -> str:
    safe = quote(url, safe=':/?#[]@!$&()*+,;=%~-._')
    return f'[{_md(label)}](<{safe}>)'


def render_views(root: Path, records: dict) -> dict[str, str]:
    rows = []
    for record_id, record in records.items():
        block = record.get('review', {}).get('availability')
        if not block:
            continue
        assets, _, _ = _sizes(root, block)
        row = {'id': record_id, 'record_path': record_path(root, record_id).relative_to(root).as_posix(),
               'title': record.get('title', record_id),
               'decision': record.get('triage', {}).get('decision', 'pending'),
               'publication_status': record.get('publication', {}).get('status', 'candidate'),
               'preparation_stage': record.get('review', {}).get('publication_readiness', {}).get('stage') or record.get('review', {}).get('publication_assessment', {}).get('stage'),
               'availability': block,
               'summary': summary(root, record), 'prepared_assets': assets}
        rows.append(row)
    rows.sort(key=lambda row: (row['summary']['shortlist_id'], row['summary']['shortlist_rank'], row['id']))
    payload = json.dumps({'schema_version': 1, 'datasets': rows}, ensure_ascii=False, indent=2) + '\n'
    fields = ['shortlist_id', 'rank', 'id', 'label', 'scope', 'decision', 'publication_status', 'preparation_stage', 'source_size', 'format',
              'source_download_bytes', 'source_size_precision', 'external_locations',
              'external_matching_locations', 'gee_locations', 'gee_matching_locations',
              'gee_asset_count', 'prepared_analytic_bytes', 'prepared_display_bytes',
              'prepared_data_bytes', 'external_details', 'gee_details']
    csv_rows = []
    md_details = []
    md_lines = ['# Dataset availability shortlist', '',
                'Generated from canonical dataset records. Unknown size is not zero. Counts use distinct distribution services, not URLs. '
                'Older versions count toward total locations but not matching-scope locations. Documentation and request forms do not prove hosting. '
                'Prepared local output is not a public distribution host. Counts reflect the reviewed sources, not an exhaustive inventory; zero GEE matches means none identified. Sizes use decimal MB/GB except an explicitly retained producer label.', '',
                '| Rank | Dataset | Current work | Scope | Source download | Prepared analytic | Prepared display | External services (matching) | GEE services (matching) | GEE assets |',
                '|---:|---|---|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        block, sums = row['availability'], row['summary']
        locations = block['locations']
        external = [x for x in locations if x['platform'] == 'external']
        gee = [x for x in locations if x['platform'] == 'gee']
        external_detail = '; '.join(
            f"{x['label']} ({x['relationship']}): {', '.join(x['urls'])}; {x['note']}" for x in external)
        gee_detail = '; '.join(
            f"{x['label']} ({x['relationship']}): {', '.join(x['urls'])}; "
            f"assets={', '.join(x['asset_ids'])}; {x['note']}" for x in gee)
        csv_rows.append({
            'shortlist_id': block['shortlist_id'], 'rank': block['rank'], 'id': row['id'],
            'label': block['label'], 'scope': block['scope'],
            'decision': row['decision'], 'publication_status': row['publication_status'], 'preparation_stage': row['preparation_stage'],
            'source_size': sums['source_size_display'], 'format': block['download']['format'],
            **{key: sums[key] for key in (
                'source_download_bytes', 'source_size_precision', 'external_locations',
                'external_matching_locations', 'gee_locations', 'gee_matching_locations',
                'gee_asset_count', 'prepared_analytic_bytes', 'prepared_display_bytes',
                'prepared_data_bytes')},
            'external_details': external_detail, 'gee_details': gee_detail,
        })
        amount = lambda n: 'Unknown' if n is None else _display_size(n, 'exact', None)
        md_lines.append(f"| {block['rank']} | **{_md(block['label'])}** | {_md((row['preparation_stage'] or row['decision']).replace('_', ' '))} | {_md(block['scope'])} | "
                        f"{_md(sums['source_size_display'])} | {amount(sums['prepared_analytic_bytes'])} | "
                        f"{amount(sums['prepared_display_bytes'])} | {sums['external_locations']} ({sums['external_matching_locations']}) | "
                        f"{sums['gee_locations']} ({sums['gee_matching_locations']}) | {sums['gee_asset_count']} |")
        md_details.extend(['', f"### {block['rank']}. {_md(block['label'])}", '',
                         f"**Scope:** {_md(block['scope'].rstrip('.'))}. **Geography:** {_md(block['geographic_scope'])}. "
                         f"**Reviewed:** {block['reviewed_on']}. **Download format:** {_md(block['download']['format'])}."])
        if external:
            md_details.append('')
            for item in external:
                urls = ', '.join(_link(item['label'], url) for url in item['urls'])
                md_details.append(f"- External: {urls or _md(item['label'])} — {_md(item['relationship'])}; {_md(item['note'])}")
        for item in gee:
            urls = ', '.join(_link(item['label'], url) for url in item['urls'])
            md_details.append(f"- GEE: {urls or _md(item['label'])} — {_md(item['relationship'])}; "
                              f"{len(item['asset_ids'])} asset(s); {_md(item['note'])}")
        md_details.extend(['', f"Source size basis: {_md(block['download']['basis'])}. {_md(block['download']['note'])}", ''])
    from io import StringIO
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader(); writer.writerows(csv_rows)
    md_lines.extend(['', *md_details, ''])
    return {'SHORTLIST.md': '\n'.join(md_lines).rstrip() + '\n', 'shortlist.json': payload, 'shortlist.csv': stream.getvalue()}


def check_views(root: Path, records: dict) -> None:
    for name, expected in render_views(root, records).items():
        path = root / name
        if not path.is_file() or path.read_text() != expected:
            raise ValueError(f'{name} is stale; regenerate dataset availability views')
