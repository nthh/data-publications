#!/usr/bin/env python3
"""Verify the frozen layout migration; no network, bulk data, or mutations."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from catalog import load_records
from record_locations import record_paths


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((Path(__file__).parent / 'plan.json').read_text())
    base = plan['base_commit']
    moves = plan['candidate_records_to_move']
    for item in moves:
        require(not (ROOT / item['from']).exists(), f"Old record remains: {item['from']}")
        require(digest(ROOT / item['to']) == item['sha256'], f"Moved record changed: {item['id']}")
    retained = plan['conversion_workspaces_retained']
    paths = record_paths(ROOT)
    require(sorted(p.parent.name for p in paths if p.parent.parent.name == 'datasets') == retained,
            'Retained workspace IDs changed')
    require(sorted(p.parent.name for p in paths if p.parent.parent.name == 'candidates') == sorted(i['id'] for i in moves),
            'Candidate IDs changed')
    require(len(paths) == plan['total_records'], 'Record count changed')
    preserved = git('diff', '--name-only', base, '--', *(f'datasets/{i}/' for i in retained)).decode()
    require(not preserved, f'Existing workspace files changed: {preserved}')
    for path, sha256 in plan['catalog_files'].items():
        require(digest(ROOT / path) == sha256, f'Published metadata changed: {path}')
    require({p.relative_to(ROOT).as_posix() for p in (ROOT / 'catalog').rglob('*') if p.is_file()} == set(plan['catalog_files']),
            'Published metadata file set changed')
    for name in ('index.json', 'shortlist.json', 'candidates.csv', 'shortlist.csv'):
        before = git('show', f'{base}:{name}').decode()
        after = (ROOT / name).read_text()
        if name.endswith('.json'):
            left, right = json.loads(before)['datasets'], json.loads(after)['datasets']
        else:
            left, right = list(csv.DictReader(io.StringIO(before))), list(csv.DictReader(io.StringIO(after)))
        for row in right:
            if 'record_path' in row:
                require((ROOT / row['record_path']).is_file(), f'Missing generated record link: {row}')
        for rows in (left, right):
            for row in rows:
                row.pop('record_path', None)
        require(left == right, f'Non-path inventory fields or ordering changed: {name}')
    for name in ('CANDIDATES.md', 'SHORTLIST.md'):
        expected = git('show', f'{base}:{name}').decode()
        for item in moves:
            expected = expected.replace(item['from'], item['to'])
        if name == 'CANDIDATES.md':
            expected = expected.replace('Generated from `datasets/<id>/dataset.yaml`;',
                                        'Generated from `candidates/<id>/dataset.yaml` and `datasets/<id>/dataset.yaml`;')
        require((ROOT / name).read_text() == expected, f'Unexpected generated Markdown changes: {name}')
    allowed = {'research/global-candidates-20261031/citations/check_review.py',
               'research/global-candidates-20261031/reuse/check.py'}
    research_changes = git('diff', '--name-only', base, '--', 'research').decode().splitlines()
    require(all(p in allowed or p.startswith('research/candidate-layout-20261109/') for p in research_changes),
            'Historical research inputs changed')
    stage = args.stage.resolve()
    prior = json.loads((ROOT / 'research/catalog-presentation-20261107/deployment/summary.json').read_text())
    require(digest(stage / 'publish-plan.json') == prior['reviewed_plan_sha256'], 'Staged plan differs from deployed plan')
    staged_plan = json.loads((stage / 'publish-plan.json').read_text())
    for item in staged_plan['files']:
        require(digest(stage / item['path']) == item['sha256'], f"Staged file mismatch: {item['path']}")
    published = sorted(key for key, record in load_records(ROOT).items()
                       if (record.get('publication') or {}).get('status') == 'published')
    require(len(published) == plan['published_collections'], 'Publication count changed')
    print(json.dumps({'status': 'passed', 'base_commit': base, 'unchanged_records': len(paths),
                      'moved_records': len(moves), 'retained_workspaces': len(retained),
                      'inventory_values_and_order': 'unchanged_except_record_paths',
                      'published_ids': published, 'unchanged_catalog_files': len(plan['catalog_files']),
                      'staged_plan_sha256': digest(stage / 'publish-plan.json'),
                      'source_release_and_research_evidence': 'unchanged'}, indent=2))


if __name__ == '__main__':
    main()
