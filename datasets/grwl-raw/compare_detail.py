#!/usr/bin/env python3
"""Exhaustively compare detail MVT semantics using raw UPB protobuf.

Ignores metadata and dictionary ordering; preserves value types, integer
geometry commands, IDs and multiplicity. Independent of the native repacker.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
import gzip
import hashlib
import importlib.metadata
import json
import math
import mmap
from pathlib import Path
import struct
import time

from google.protobuf.internal import api_implementation
from mapbox_vector_tile.Mapbox import vector_tile_pb2
from pmtiles.reader import all_tiles
from pmtiles.tile import Compression, TileType, deserialize_header, zxy_to_tileid

DROP = frozenset(('_src_xmin', '_src_ymin', '_src_xmax', '_src_ymax'))
KEEP = frozenset(('width_m', 'width_valid'))
ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / 'research/grwl-multiscale-20261103/criteria.json'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def descriptor(path):
    return {'path': str(Path(path).resolve()), 'bytes': Path(path).stat().st_size, 'sha256': sha256(path)}


def typed_value(value):
    fields = value.ListFields()
    if len(fields) != 1:
        raise ValueError('MVT value must contain exactly one typed value')
    field, result = fields[0]
    if field.name in ('float_value', 'double_value'):
        if not math.isfinite(result):
            raise ValueError('Nonfinite MVT value')
        result = struct.pack('!f' if field.name == 'float_value' else '!d', result)
    return field.name, result


def signature(raw, *, source):
    tile = vector_tile_pb2.tile()
    tile.ParseFromString(raw)
    if not tile.IsInitialized() or len(tile.layers) != 1:
        raise ValueError('Detail tile must have exactly one initialized layer')
    layer = tile.layers[0]
    if layer.name != 'grwl_raw' or layer.extent != 4096 or layer.version != 2:
        raise ValueError('Unexpected detail layer, extent or MVT version')
    if len(set(layer.keys)) != len(layer.keys):
        raise ValueError('Duplicate MVT key dictionary entries')
    allowed = KEEP | DROP if source else KEEP
    if set(layer.keys) - allowed:
        raise ValueError('Unexpected MVT property dictionary')
    values = [typed_value(value) for value in layer.values]
    features = Counter()
    for feature in layer.features:
        if not feature.HasField('id') or feature.type != 2 or not feature.geometry:
            raise ValueError('Missing feature ID, wrong geometry type or empty geometry')
        if len(feature.tags) % 2:
            raise ValueError('Odd MVT tag count')
        props = {}
        for index in range(0, len(feature.tags), 2):
            ki, vi = feature.tags[index:index + 2]
            if ki >= len(layer.keys) or vi >= len(values):
                raise ValueError('MVT tag index out of range')
            key = layer.keys[ki]
            if key in props:
                raise ValueError('Duplicate property on MVT feature')
            props[key] = values[vi]
        if 'width_valid' not in props or props['width_valid'][0] != 'bool_value':
            raise ValueError('width_valid must exist as MVT boolean')
        if 'width_m' in props and props['width_m'][0] not in ('int_value', 'uint_value', 'sint_value'):
            raise ValueError('width_m must be an integer when present')
        if source and (set(props) & DROP) != DROP:
            raise ValueError('Source feature missing a provenance bbox attribute')
        retained = tuple(sorted((key, value) for key, value in props.items() if key in KEEP))
        features[(feature.id, feature.type, tuple(feature.geometry), retained)] += 1
    return layer.version, layer.extent, features


@contextmanager
def archive_tiles(path):
    with Path(path).open('rb') as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
            get = lambda offset, length: mapping[offset:offset + length]
            header = deserialize_header(get(0, 127))
            if header['tile_type'] != TileType.MVT or header['tile_compression'] not in (Compression.NONE, Compression.GZIP):
                raise ValueError('Expected gzip or uncompressed MVT PMTiles')
            def tiles():
                previous = -1
                count = 0
                for xyz, data in all_tiles(get):
                    tileid = zxy_to_tileid(*xyz)
                    if tileid <= previous:
                        raise ValueError('Duplicate or unordered PMTiles tile coordinate')
                    previous = tileid
                    count += 1
                    yield xyz, data, header['tile_compression']
                if count != header['addressed_tiles_count']:
                    raise ValueError('PMTiles addressed tile count disagrees with directory')
            yield tiles()


def decoded(data, compression):
    return gzip.decompress(data) if compression == Compression.GZIP else data


def detail_tiles(iterator, *, candidate, allow_overview, stats):
    for xyz, data, compression in iterator:
        zoom = xyz[0]
        if 8 <= zoom <= 12:
            yield xyz, data, compression
        elif candidate and allow_overview and 0 <= zoom <= 7:
            tile = vector_tile_pb2.tile()
            tile.ParseFromString(decoded(data, compression))
            if not tile.IsInitialized() or len(tile.layers) != 1 or tile.layers[0].name != 'grwl_overview' or tile.layers[0].extent != 4096:
                raise ValueError('Unexpected layer/extent at overview zoom')
            stats['overview_tiles'] += 1
        else:
            raise ValueError(f'Unexpected tile zoom {xyz}')


def compare(source, candidate, *, allow_overview=False, maximum_tile_bytes=1048576, progress_every=10000):
    if api_implementation.Type() != 'upb':
        raise ValueError('Use locked protobuf UPB environment for exhaustive comparison')
    stats = {'detail_tiles': 0, 'detail_features': 0, 'overview_tiles': 0,
             'maximum_gzip_tile_bytes': 0, 'detail_tiles_over_byte_limit': 0, 'by_zoom': {}}
    sentinel = object()
    with archive_tiles(source) as old, archive_tiles(candidate) as new:
        left = iter(detail_tiles(old, candidate=False, allow_overview=False, stats=stats))
        right = iter(detail_tiles(new, candidate=True, allow_overview=allow_overview, stats=stats))
        while True:
            a, b = next(left, sentinel), next(right, sentinel)
            if a is sentinel and b is sentinel:
                break
            if a is sentinel or b is sentinel or a[0] != b[0]:
                raise ValueError(f'Detail tile coordinate mismatch: {None if a is sentinel else a[0]} / {None if b is sentinel else b[0]}')
            sa = signature(decoded(a[1], a[2]), source=True)
            sb = signature(decoded(b[1], b[2]), source=False)
            if sa != sb:
                raise ValueError(f'Detail semantics differ at {a[0]}')
            length = len(b[1]) if b[2] == Compression.GZIP else len(gzip.compress(b[1], mtime=0))
            stats['maximum_gzip_tile_bytes'] = max(length, stats['maximum_gzip_tile_bytes'])
            stats['detail_tiles_over_byte_limit'] += int(length > maximum_tile_bytes)
            stats['detail_tiles'] += 1
            stats['detail_features'] += sum(sa[2].values())
            zoom = str(a[0][0])
            stats['by_zoom'][zoom] = stats['by_zoom'].get(zoom, 0) + 1
            if progress_every and stats['detail_tiles'] % progress_every == 0:
                print(json.dumps({'progress': stats}), flush=True)
    if not stats['detail_tiles']:
        raise ValueError('No detail tiles compared')
    return stats


def run(source, candidate, report, *, source_sha256, candidate_sha256=None,
        allow_overview=False, criteria_path=CRITERIA):
    if Path(report).exists():
        raise FileExistsError('Refusing to overwrite immutable comparison report')
    started = time.monotonic()
    result = {'schema_version': 1, 'status': 'failed', 'semantic_preservation': False,
              'source': descriptor(source), 'candidate': descriptor(candidate),
              'comparator': descriptor(Path(__file__)), 'criteria': descriptor(criteria_path),
              'protobuf_implementation': api_implementation.Type(),
              'packages': {n: importlib.metadata.version(n) for n in ('pmtiles', 'mapbox-vector-tile', 'protobuf')}}
    error = None
    try:
        if result['source']['sha256'] != source_sha256:
            raise ValueError('Source archive differs from sealed checksum')
        if candidate_sha256 and result['candidate']['sha256'] != candidate_sha256:
            raise ValueError('Candidate archive differs from expected checksum')
        limit = json.loads(Path(criteria_path).read_text())['detail']['maximum_gzip_tile_bytes']
        result['counts'] = compare(source, candidate, allow_overview=allow_overview, maximum_tile_bytes=limit)
        if sha256(source) != result['source']['sha256'] or sha256(candidate) != result['candidate']['sha256']:
            raise ValueError('Archive changed during comparison')
        result['semantic_preservation'] = True
        result['tile_byte_gate'] = result['counts']['detail_tiles_over_byte_limit'] == 0
        result['status'] = 'passed' if result['tile_byte_gate'] else 'failed'
        if not result['tile_byte_gate']:
            raise ValueError('Detail tile byte limit exceeded (semantic preservation passed)')
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
        error = exc
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    Path(report).parent.mkdir(parents=True, exist_ok=True)
    with Path(report).open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    if error:
        raise error
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--candidate-sha256')
    parser.add_argument('--allow-overview', action='store_true')
    parser.add_argument('--criteria', type=Path, default=CRITERIA)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.candidate, args.report, source_sha256=args.source_sha256,
        candidate_sha256=args.candidate_sha256, allow_overview=args.allow_overview,
        criteria_path=args.criteria), sort_keys=True))


if __name__ == '__main__':
    main()
