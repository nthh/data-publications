#!/usr/bin/env python3
"""Freeze deterministic global raw-GRWL browser controls from verified local inputs."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

import pyarrow.dataset as ds
import pyarrow.parquet as pq


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def display(value) -> str:
    if value is None:
        return 'null'
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def bounds(bbox: dict, pad: float) -> list[float]:
    return [max(-180.0, float(bbox['xmin']) - pad),
            max(-90.0, float(bbox['ymin']) - pad),
            min(180.0, float(bbox['xmax']) + pad),
            min(90.0, float(bbox['ymax']) + pad)]


def exact_row(dataset, tile: str, row: int, fields: list[str]) -> dict:
    table = dataset.to_table(columns=fields, filter=(ds.field('source_tile') == tile) &
                             (ds.field('source_row') == row))
    if table.num_rows != 1:
        raise ValueError(f'Expected one analytic row for {tile}/{row}, found {table.num_rows}')
    return {name: table[name][0].as_py() for name in fields}


def make_case(dataset, control: dict, fields: list[str], kind: str, context: str,
              detail_bbox: list[float], window_id: str | None = None,
              context_bbox: list[float] | None = None) -> dict:
    values = exact_row(dataset, control['source_tile'], int(control['source_row']), fields)
    fid = int(values['feature_id'])
    if kind == 'global' and fid != int(control['feature_id']):
        raise ValueError('Longest-part fidelity feature ID differs from analytic row')
    width = values['width_m']
    width_suffix = ('Unknown (source sentinel 1)' if width == 1 else
                    'Unknown (null or nonpositive source value)' if width is None or width <= 0 else
                    f'{width:,} m')
    return {
        'case_id': (f"global-{window_id}" if window_id else f"known-summary-{control['summary_reference_id']}"),
        'kind': kind,
        **({'summary_reference_id': int(control['summary_reference_id'])} if window_id is None else {}),
        **({'window_id': window_id, 'longest_part_m': float(control['length_m']),
            'source_part_bbox': control['bbox']} if window_id else {}),
        'context_region': context,
        **({'context_bbox': [float(v) for v in context_bbox]} if context_bbox else {}),
        'source_tile': control['source_tile'],
        'source_row': int(control['source_row']),
        'feature_id': fid,
        'detail_bbox': [float(v) for v in detail_bbox],
        'expected_analytic_attributes': {name: display(values[name]) for name in fields},
        'expected_width': {
            'width_m': width,
            'width_valid': bool(values['width_valid']),
            'label': 'Observation width · ' + width_suffix
        }
    }


def generate(validation_path: Path, manifest_path: Path, parquet_path: Path,
             output_path: Path, policy_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError(f'Refusing to overwrite existing controls: {output_path}')
    policy = json.loads(policy_path.read_text())
    validation = json.loads(validation_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    hashes = {'source_sha256': digest(parquet_path), 'source_manifest_sha256': digest(manifest_path),
              'source_validation_sha256': digest(validation_path), 'browser_policy_sha256': digest(policy_path)}
    if validation.get('status') != 'passed':
        raise ValueError('Source validation report is not passed')
    if validation.get('manifest_sha256') != hashes['source_manifest_sha256']:
        raise ValueError('Validation report is not bound to this manifest')
    if validation.get('parquet_sha256') != hashes['source_sha256'] or manifest.get('parquet_sha256') != hashes['source_sha256']:
        raise ValueError('Validation/manifest is not bound to these Parquet bytes')
    if validation.get('sample_policy', {}).get('kind') != policy['source_selection']['sample_policy']:
        raise ValueError('Validation report does not use the frozen global sample policy')
    tiles = validation.get('tiles')
    manifest_tiles = manifest.get('tiles')
    if not isinstance(tiles, list) or not isinstance(manifest_tiles, list) or len(tiles) != len(manifest_tiles):
        raise ValueError('Validation and manifest tile inventories differ')
    checked_tiles = []
    for evidence, declared in zip(tiles, manifest_tiles):
        if evidence.get('tile') != declared.get('tile') or evidence.get('source_rows') != declared.get('records') or evidence.get('parts') != declared.get('parts'):
            raise ValueError(f"Source-fidelity tile counts differ from manifest at {evidence.get('tile')}")
        if evidence.get('parts', 0) < evidence.get('source_rows', 0):
            raise ValueError(f"Invalid part/record counts for {evidence.get('tile')}")
        checked_tiles.append(evidence)
    expected_rows = validation.get('progress', {}).get('source_rows')
    if expected_rows != manifest.get('rows'):
        raise ValueError('Global source row count differs from conversion manifest')

    selection = policy['source_selection']
    candidates = []
    for evidence in checked_tiles:
        longest = evidence.get('longest_parts')
        if not isinstance(longest, list) or len(longest) != min(selection['longest_parts_per_tile'], evidence['parts']):
            raise ValueError(f"Incomplete longest-part controls for {evidence['tile']}")
        for item in longest:
            if item.get('source_tile') != evidence['tile']:
                raise ValueError('Longest-part sample tile identity mismatch')
            candidates.append(item)
    cases = []
    fields = list(policy['analytic_fields'])
    parquet = pq.ParquetFile(parquet_path)
    if not set(fields).issubset(parquet.schema_arrow.names):
        raise ValueError('Analytic Parquet lacks one or more expected fields')
    dataset = ds.dataset(parquet_path, format='parquet')
    known_seen = set()
    for item in policy['known_error_cases']:
        key = (item['source_tile'], int(item['source_row']))
        if key in known_seen:
            raise ValueError('Duplicate known-error source ID in policy')
        known_seen.add(key)
        cases.append(make_case(dataset, item, fields, 'known_error', f"grwl_{item['summary_reference_id']}", item['detail_bbox']))

    for window in policy['global_controls']:
        west, south, east, north = window['bbox']
        eligible = [item for item in candidates
                    if float(item.get('length_m', 0)) >= selection['minimum_part_length_m']
                    and len(item.get('bbox', [])) == 4
                    and west <= float(item['bbox'][0]) <= float(item['bbox'][2]) <= east
                    and south <= float(item['bbox'][1]) <= float(item['bbox'][3]) <= north]
        eligible.sort(key=lambda item: (item['source_tile'], int(item['source_row']), int(item.get('part', 0))))
        if not eligible:
            raise ValueError(f"No eligible longest source part in frozen window {window['window_id']}")
        chosen = eligible[0]
        if (chosen['source_tile'], int(chosen['source_row'])) in known_seen:
            raise ValueError('Global control duplicates a known-error source ID')
        detail = bounds(dict(zip(('xmin', 'ymin', 'xmax', 'ymax'), chosen['bbox'])), selection['detail_padding_degrees'])
        context_bbox = bounds(dict(zip(('xmin', 'ymin', 'xmax', 'ymax'), chosen['bbox'])),
                              selection['context_padding_degrees'])
        cases.append(make_case(dataset, chosen, fields, 'global', selection['context_region'], detail,
                               window['window_id'], context_bbox))
    result = {
        'schema_version': 1,
        'status': 'frozen_controls',
        'scope': 'Source-derived browser lookup controls; no PMTiles result was inspected during selection.',
        **hashes,
        'browser_limits': policy['browser_limits'],
        'source_rows': expected_rows,
        'case_count': len(cases),
        'cases': cases
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-validation', required=True, type=Path)
    parser.add_argument('--source-manifest', required=True, type=Path)
    parser.add_argument('--parquet', required=True, type=Path)
    parser.add_argument('--policy', type=Path, default=Path(__file__).with_name('global-browser-policy.json'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = generate(args.source_validation, args.source_manifest, args.parquet, args.output, args.policy)
    print(json.dumps({'status': result['status'], 'case_count': result['case_count'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
