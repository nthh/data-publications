#!/usr/bin/env python3
"""Verify all inventoried historical workflow bytes without the original Git repository."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    entries = blobs = 0
    inventories = list((root/'datasets').glob('*/provenance/index.json'))
    portable = root/'research/history-portability-20261106/index.json'
    if portable.is_file():
        inventories.append(portable)
    for inventory in sorted(inventories):
        data = json.loads(inventory.read_text())
        seen = set()
        for entry in data['files']:
            expected = entry['sha256']
            relative = Path(entry['blob'])
            if relative.as_posix() != 'blobs/'+expected or len(expected) != 64:
                raise ValueError('Invalid content-addressed path')
            path = inventory.parent / relative
            raw = path.read_bytes()
            if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError(f'Historical source changed: {entry["path"]}')
            seen.add(expected); entries += 1
        actual = {path.name for path in (inventory.parent/'blobs').iterdir() if path.is_file()}
        if actual != seen:
            raise ValueError('Uninventoried or missing historical blobs')
        blobs += len(seen)
    if not entries:
        raise ValueError('No historical source inventory found')
    return {'status':'passed','historical_entries':entries,'unique_blobs':blobs}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
