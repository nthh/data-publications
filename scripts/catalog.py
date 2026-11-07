#!/usr/bin/env python3
"""Validate the frozen community intake and explicit producer/official additions."""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import json
from collections import Counter
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit
import yaml
import candidate_discovery
import dataset_availability
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / 'intake.json'
SCHEMA = ROOT / 'schemas/dataset.schema.json'
RECORDS = ROOT / 'datasets'
AUDIT = ROOT / 'research/gee-community-audit-20261029'
CITATIONS = ROOT / 'research/citations'
PILOT_ID = 'river-plastic-inputs'
PILOT_FAMILY = 'plastic'
RELATED_START = '<!-- related-datasets:start -->'
RELATED_END = '<!-- related-datasets:end -->'


def canonical_id(value: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', value))


def record_paths(root: Path = ROOT) -> list[Path]:
    return sorted((root / 'datasets').glob('*/dataset.yaml'))


def load_records(root: Path = ROOT) -> dict[str, dict]:
    result = {}
    for path in record_paths(root):
        record = yaml.safe_load(path.read_text())
        if not isinstance(record, dict):
            raise ValueError(f'Invalid dataset record: {path}')
        record_id = record.get('id')
        family_key = record.get('audit', {}).get('family_key')
        expected_path_id = PILOT_ID if family_key == PILOT_FAMILY else record_id
        if (not canonical_id(str(record_id)) or path.parent.name != expected_path_id
                or (family_key == PILOT_FAMILY and record_id != PILOT_ID)
                or (record_id == PILOT_ID and family_key != PILOT_FAMILY)):
            raise ValueError(f'Invalid ID/path mapping: {path.relative_to(root)}')
        if record_id in result:
            raise ValueError(f'Duplicate dataset ID: {record_id}')
        result[record_id] = record
    return result


def validate_related(record: dict, records: dict[str, dict]) -> None:
    seen = set()
    for related in record.get('related_datasets', []):
        if related['id'] in seen:
            raise ValueError(f"Duplicate related dataset ID: {record['id']}/{related['id']}")
        seen.add(related['id'])
        target = related.get('record_id')
        if target is not None and (target not in records or target == record['id']):
            raise ValueError(f"Invalid related record_id: {record['id']}/{target}")
        urls = [related['url'], *(item['url'] for item in related['evidence'])]
        for url in urls:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or any(c.isspace() for c in url):
                raise ValueError(f"Invalid related dataset URL: {record['id']}/{related['id']}")


def validate(root: Path = ROOT) -> dict:
    intake = json.loads((root / 'intake.json').read_text())
    audit_dir = root / intake['audit_directory']
    for name, expected in intake['input_sha256'].items():
        actual = hashlib.sha256((audit_dir / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Pinned audit input changed: {name}')
    family_rows = json.loads((audit_dir / 'families.json').read_text())
    families = {row['slug']: row for row in family_rows}
    if len(families) != len(family_rows):
        raise ValueError('Duplicate pinned family key')
    with (audit_dir / 'crosswalk.csv').open(newline='') as stream:
        crosswalk_rows = list(csv.DictReader(stream))
    crosswalk = {row['catalog_slug']: row for row in crosswalk_rows}
    if len(crosswalk) != len(crosswalk_rows):
        raise ValueError('Duplicate pinned crosswalk family key')
    records = load_records(root)
    schema = json.loads((root / 'schemas/dataset.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    rankings_path = intake['citation_snapshot']['rankings_path']
    ranking_rows = json.loads((root / rankings_path).read_text())
    rankings = {row['slug']: row for row in ranking_rows}
    if len(rankings) != len(ranking_rows):
        raise ValueError('Duplicate citation family key')
    familykeys = []
    supplemental = 0
    decisions, queues = Counter(), Counter()
    for record_id, record in records.items():
        validator.validate(record)
        validate_related(record, records)
        if 'intake' in record:
            supplemental += 1
            reference = urlsplit(record['intake']['reference_url'])
            if reference.scheme not in ('https', 'http') or not reference.netloc or any(c.isspace() for c in record['intake']['reference_url']):
                raise ValueError(f'Invalid intake reference URL: {record_id}')
            related = record['intake'].get('related_family')
            if related is not None and related not in families:
                raise ValueError(f'Unknown related intake family: {related}')
            decisions[record['triage']['decision']] += 1
            continue
        family_key = record['audit']['family_key']
        familykeys.append(family_key)
        if family_key not in families or family_key not in crosswalk:
            raise ValueError(f'Unknown audit family key: {family_key}')
        family, row = families[family_key], crosswalk[family_key]
        if record['community_url'] != family['url']:
            raise ValueError(f'Community URL mismatch: {record_id}')
        audit = record['audit']
        if audit['unique_gee_asset_count'] != len(set(family['asset_ids'])):
            raise ValueError(f'Asset count mismatch: {record_id}')
        for field, column in (('folia_registry_ids', 'registry_ids'), ('source_coop_urls', 'source_coop_urls'), ('external_native_urls', 'external_native_urls')):
            expected = [part.strip() for part in row[column].split(';') if part.strip()]
            if audit[field] != expected:
                raise ValueError(f'Pinned audit evidence mismatch: {record_id}/{field}')
        queue = 'review_source_coop_counterpart' if row['source_coop_status'] == 'hosted_counterpart' else 'review_external_native_counterpart' if row['external_native_status'] == 'documented_counterpart' else 'research_original_source'
        if audit['initial_queue'] != queue:
            raise ValueError(f'Initial queue mismatch: {record_id}')
        queues[queue] += 1
        decisions[record['triage']['decision']] += 1
        expected = rankings.get(family_key)
        if not expected:
            raise ValueError(f'Missing citation family: {family_key}')
        observed = record.get('review', {}).get('citation_assessment', {})
        for field in ('geographic_scope', 'paper_count_status', 'max_paper_citations', 'max_data_doi_citations', 'top_paper_doi', 'top_paper_openalex_id', 'citation_scope'):
            if observed.get(field) != expected.get(field):
                raise ValueError(f'Citation snapshot mismatch: {record_id}/{field}')
        snap = intake['citation_snapshot']
        for field in ('as_of', 'provider'):
            if observed.get(field) != snap[field]:
                raise ValueError(f'Citation metadata mismatch: {record_id}/{field}')
        if observed.get('evidence_path') != rankings_path or observed.get('evidence_key') != family_key:
            raise ValueError(f'Citation evidence link mismatch: {record_id}')
    if len(records) - supplemental != intake['family_count'] or len(set(familykeys)) != len(familykeys) or set(familykeys) != set(families):
        raise ValueError('Dataset records do not cover every pinned family exactly once')
    if set(rankings) != set(families):
        raise ValueError('Citation snapshot does not cover exactly the frozen family population')
    if dict(queues) != intake['initial_queues']:
        raise ValueError('Initial queue totals differ from intake snapshot')
    candidate_discovery.validate_discovery(root, records)
    dataset_availability.validate_availability(root, records)
    return {'records_checked': len(records), 'supplemental_records_checked': supplemental, 'family_keys_checked': len(familykeys), 'citations_checked': len(rankings), 'decisions': dict(sorted(decisions.items()))}


def render_index(root: Path = ROOT) -> str:
    records = load_records(root)
    rows = []
    for dataset_id, record in sorted(records.items()):
        publication = record.get('publication') or {}
        row = {'id': dataset_id, 'record_path': f'datasets/{dataset_id}/dataset.yaml',
               'title': record['title'], 'community_url': record.get('community_url'),
               'family_key': record.get('audit', {}).get('family_key'), 'decision': record['triage']['decision'],
               'priority': record['triage']['priority'],
               'publication_status': publication.get('status', 'candidate')}
        if 'intake' in record:
            row['intake'] = record['intake']
        if record.get('discovery'):
            row['discovery'] = record['discovery']
        if record.get('review', {}).get('availability'):
            row['availability'] = record['review']['availability']
            row['availability_summary'] = dataset_availability.summary(root, record)
        if record.get('review', {}).get('publication_readiness'):
            row['publication_readiness'] = record['review']['publication_readiness']
        if publication.get('source_coop'):
            row['source_coop'] = publication['source_coop']
        if record.get('related_datasets'):
            row['related_datasets'] = record['related_datasets']
        citation = record.get('review', {}).get('citation_assessment')
        if citation:
            row['citation'] = {key: citation.get(key) for key in ('geographic_scope', 'paper_count_status', 'max_paper_citations', 'max_data_doi_citations', 'top_paper_doi', 'citation_scope')}
        rows.append(row)
    return json.dumps({'schema_version': 1, 'datasets': rows}, ensure_ascii=False, indent=2) + '\n'


def check_index(root: Path = ROOT) -> None:
    index_path = root / 'index.json'
    if not index_path.exists() or index_path.read_text() != render_index(root):
        raise ValueError('index.json is stale; run scripts/catalog.py')


def markdown_text(value: str) -> str:
    # Treat record prose as text, including embedded Markdown punctuation/HTML.
    value = html.escape(' '.join(value.split()), quote=False)
    return re.sub(r'([\\`*_\[\]])', r'\\\1', value)


def markdown_link(title: str, url: str) -> str:
    return f'[{markdown_text(title)}](<{quote(url, safe=":/?#[]@!$&()*+,;=%~-._")}>)'


def render_related(record: dict) -> str:
    related = record.get('related_datasets', [])
    if not related:
        return ''
    lines = [RELATED_START, '', '## Related datasets', '',
             'Generated from `related_datasets` in [dataset.yaml](dataset.yaml). '
             'These references describe alternatives and complementary uses; '
             'they do not add datasets to the processing queue. '
             'The comparisons are based on the cited documentation, not an equivalence or accuracy benchmark.', '']
    labels = {'alternative': 'Alternative', 'complement': 'Complement',
              'source': 'Upstream source', 'derived_product': 'Derived product'}
    for item in related:
        lines.extend([f"### {markdown_link(item['title'], item['url'])}", '',
                      f"- **Relationship:** {labels[item['relationship']]}. {markdown_text(item['use_case'])}"])
        if item.get('record_id'):
            lines.append(f"- **Local record:** [dataset.yaml](../{item['record_id']}/dataset.yaml)")
        coverage = [item[key] for key in ('spatial_coverage', 'resolution', 'temporal_coverage') if item.get(key)]
        if coverage:
            lines.append(f"- **Coverage:** {markdown_text('; '.join(coverage))}")
        if item.get('formats'):
            lines.append(f"- **Formats:** {markdown_text(', '.join(item['formats']))}")
        if item.get('access'):
            lines.append(f"- **Access:** {markdown_text(item['access'])}")
        lines.append(f"- **Comparison:** {markdown_text(item['comparison'])}")
        sources = ', '.join(markdown_link(source['title'], source['url']) for source in item['evidence'])
        lines.extend([f"- **Reviewed:** {item['reviewed_on']}. **Sources:** {sources}.", ''])
    return '\n'.join([*lines, RELATED_END])


def related_readme_updates(root: Path = ROOT) -> dict[Path, str]:
    """Plan generated blocks before writing, preserving all surrounding prose."""
    updates = {}
    for record_id, record in load_records(root).items():
        path = root / 'datasets' / record_id / 'README.md'
        current = path.read_text() if path.exists() else ''
        start_count, end_count = current.count(RELATED_START), current.count(RELATED_END)
        if (start_count, end_count) not in ((0, 0), (1, 1)):
            raise ValueError(f'Malformed related dataset markers: {path.relative_to(root)}')
        block = render_related(record)
        if start_count:
            start = current.index(RELATED_START)
            end = current.index(RELATED_END)
            if end < start:
                raise ValueError(f'Malformed related dataset markers: {path.relative_to(root)}')
            expected = current[:start] + block + current[end + len(RELATED_END):]
        elif block:
            prefix = current or f"# {markdown_text(record['title'])}\n"
            separator = '' if prefix.endswith('\n\n') else '\n' if prefix.endswith('\n') else '\n\n'
            expected = prefix + separator + block + '\n'
        else:
            continue
        if current != expected:
            updates[path] = expected
    return updates


def check_related_readmes(root: Path = ROOT) -> None:
    stale = related_readme_updates(root)
    if stale:
        paths = ', '.join(str(path.relative_to(root)) for path in stale)
        raise ValueError(f'Related dataset README section is stale: {paths}; run scripts/catalog.py --write')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='validate and require index.json, candidate views and related README sections to be current')
    mode.add_argument('--write', action='store_true', help='validate and generate index.json, candidate views and related README sections')
    args = parser.parse_args()
    report = validate()
    index_path = ROOT / 'index.json'
    expected = render_index()
    readme_updates = related_readme_updates()
    if args.check:
        check_index()
        check_related_readmes()
        candidate_discovery.check_views(ROOT, load_records())
        dataset_availability.check_views(ROOT, load_records())
    else:
        index_path.write_text(expected)
        generated_views = candidate_discovery.render_views(load_records(), ROOT)
        generated_views.update(dataset_availability.render_views(ROOT, load_records()))
        for name, contents in generated_views.items():
            (ROOT / name).write_text(contents)
        for path, contents in readme_updates.items():
            path.write_text(contents)
    print(json.dumps(report, indent=2))
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, AssertionError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
