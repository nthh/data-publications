#!/usr/bin/env python3
"""Build citation tables from pinned references and observed OpenAlex metadata.

No network calls. --check verifies generated artifacts without changing files.
"""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'research' / 'citations'


def norm(doi):
    return doi.lower().removeprefix('https://doi.org/').removeprefix('http://doi.org/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    methodology = json.loads((HERE / 'methodology.json').read_text())
    candidates = {r['slug']: r for r in json.loads((HERE / 'candidates.json').read_text())}
    reviews = [r for p in sorted(HERE.glob('review-*.json')) for r in json.loads(p.read_text())]
    assert len(reviews) == len(candidates) == 363
    assert len({r['slug'] for r in reviews}) == len(reviews)
    assert {r['slug'] for r in reviews} == set(candidates)
    observations = json.loads((HERE / 'openalex-dois.json').read_text())
    searches = json.loads((HERE / 'title-searches.json').read_text())
    title_review = json.loads((HERE / 'title-review.json').read_text())
    parent = json.loads((HERE / 'parent-review.json').read_text())
    availability_path = ROOT / 'research' / 'availability' / 'availability-review.json'
    availability = json.loads(availability_path.read_text()) if availability_path.exists() else {}
    by_doi = {d: {'work': o['work'], 'retrieved_at': o['retrieved_at'],
                  'evidence_path': o['response_path'], 'match_method': 'doi'}
              for d, o in observations.items() if o['status'] == 'matched'}
    by_family_title = {}
    for match in title_review['matches']:
        capture = searches[match['query_title']]
        work = next(w for w in capture['results'] if w['id'] == match['work_id'])
        value = {'work': work, 'retrieved_at': capture['retrieved_at'],
                 'evidence_path': 'title-searches.json', 'match_method': 'reviewed_title'}
        by_family_title.setdefault(match['slug'], []).append(value)
        if work.get('doi'):
            by_doi.setdefault(norm(work['doi']), value)
    output = []
    for review in reviews:
        slug = review['slug']
        candidate = candidates[slug]
        intake = yaml.safe_load((ROOT / 'datasets' / ('river-plastic-inputs' if slug == 'plastic' else slug) / 'dataset.yaml').read_text())
        correction = parent.get(slug, {})
        paper_dois = sorted(set(review['paper_dois'] + correction.get('add_paper_dois', [])) - set(correction.get('remove_paper_dois', [])))
        papers = [by_doi[d] for d in paper_dois if d in by_doi]
        papers += by_family_title.get(slug, [])
        papers = list({p['work']['id']: p for p in papers}.values())
        data_dois = sorted(set(review['data_dois'] + correction.get('add_data_dois', [])) - set(correction.get('remove_data_dois', [])))
        data = [by_doi[d] for d in data_dois if d in by_doi]
        data = list({d['work']['id']: d for d in data}.values())
        assert not ({p['work']['id'] for p in papers} & {d['work']['id'] for d in data}), f'Mixed paper/data roles: {slug}'
        assert all(p['work']['type'] != 'dataset' for p in papers), f'Data release classified as paper: {slug}'
        papers.sort(key=lambda p: (-p['work']['cited_by_count'], p['work']['id']))
        data.sort(key=lambda p: (-p['work']['cited_by_count'], p['work']['id']))
        for observed in papers + data:
            assert isinstance(observed['work']['cited_by_count'], int)
            assert observed['work']['cited_by_count'] >= 0
        title_matches = {m['query_title'] for m in title_review['matches'] if m['slug'] == slug}
        unresolved_titles = [t['title'] for t in review['unresolved_paper_titles'] + correction.get('add_unresolved_paper_titles', []) if t['title'] not in title_matches]
        missing_papers = [d for d in paper_dois if d not in by_doi]
        missing_data = [d for d in data_dois if d not in by_doi]
        top = papers[0]['work'] if papers else {}
        top_data = data[0]['work'] if data else {}
        scope = correction.get('geographic_scope', review['geographic_scope'])
        assert scope in ('global', 'regional', 'mixed', 'unclear')
        status = ('partial' if missing_papers or unresolved_titles else 'matched') if papers else 'unknown'
        score = top.get('cited_by_count')
        routing = availability.get(slug, {}).get('route', intake['audit']['initial_queue'])
        row = {
            'slug': slug, 'title': candidate['title'], 'community_url': candidate['community_url'],
            'geographic_scope': scope, 'scope_note': correction.get('scope_note', review['scope_note']),
            'paper_count_status': status, 'max_paper_citations': score,
            'top_paper_title': top.get('title'), 'top_paper_doi': top.get('doi'),
            'top_paper_openalex_id': top.get('id'), 'top_paper_year': top.get('publication_year'),
            'top_paper_citations_2025': next((x['cited_by_count'] for x in top.get('counts_by_year', []) if x['year'] == 2025), None),
            'top_paper_citations_2026_ytd': next((x['cited_by_count'] for x in top.get('counts_by_year', []) if x['year'] == 2026), None),
            'citation_scope': correction.get('citation_scope', 'associated_dataset_publication'),
            'citation_scope_note': correction.get('note'),
            'max_data_doi_citations': top_data.get('cited_by_count'),
            'top_data_doi': top_data.get('doi'),
            'papers': papers, 'data_dois': data,
            'unmatched_paper_dois': missing_papers, 'unmatched_data_dois': missing_data,
            'unresolved_paper_titles': unresolved_titles,
            'folia_registry_ids': intake['audit']['folia_registry_ids'],
            'initial_source_coop_urls': intake['audit']['source_coop_urls'],
            'initial_native_urls': intake['audit']['external_native_urls'],
            'publication_route': routing,
            'availability_review': availability.get(slug),
        }
        output.append(row)
    output.sort(key=lambda r: (r['max_paper_citations'] is None, -(r['max_paper_citations'] or 0), r['slug']))
    global_rows = [r for r in output if r['geographic_scope'] == 'global']
    # A separate data-DOI table keeps data-only works visible without adding unlike counts.
    data_rows = sorted([r for r in output if r['max_data_doi_citations'] is not None],
                       key=lambda r: (-r['max_data_doi_citations'], r['slug']))
    fields = ['rank', 'slug', 'title', 'geographic_scope', 'paper_count_status', 'max_paper_citations',
              'top_paper_year', 'top_paper_title', 'top_paper_doi', 'top_paper_openalex_id',
              'top_paper_citations_2025', 'top_paper_citations_2026_ytd',
              'citation_scope', 'citation_scope_note', 'max_data_doi_citations', 'top_data_doi',
              'publication_route', 'community_url']
    def table(rows, score_key='max_paper_citations'):
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fields, lineterminator='\n')
        writer.writeheader()
        rank, previous_score = 0, None
        for position, row in enumerate(rows, start=1):
            if row[score_key] is not None and row[score_key] != previous_score:
                rank = position
                previous_score = row[score_key]
            writer.writerow({k: (rank if row[score_key] is not None else '') if k == 'rank' else row.get(k) for k in fields})
        return stream.getvalue()
    times = [o['retrieved_at'] for o in observations.values()] + [o['retrieved_at'] for o in searches.values()]
    summary = {
        'as_of': methodology['as_of'], 'as_of_timezone': methodology.get('as_of_timezone', 'UTC'), 'provider': 'OpenAlex', 'metric': 'Maximum cited_by_count among associated dataset papers; never a sum.',
        'families': len(output), 'families_with_paper_count': sum(r['max_paper_citations'] is not None for r in output),
        'families_with_data_doi_count': len(data_rows),
        'families_with_any_count': sum(r['max_paper_citations'] is not None or r['max_data_doi_citations'] is not None for r in output),
        'families_without_any_count': sum(r['max_paper_citations'] is None and r['max_data_doi_citations'] is None for r in output),
        'global_families': len(global_rows), 'global_families_with_paper_count': sum(r['max_paper_citations'] is not None for r in global_rows),
        'scope_counts': dict(Counter(r['geographic_scope'] for r in output)),
        'paper_match_status_counts': dict(Counter(r['paper_count_status'] for r in output)),
        'doi_observations': len(observations), 'title_queries': len(searches),
        'retrieval_started_utc': min(times), 'retrieval_ended_utc': max(times),
        'limitations': ['Paper citations proxy scholarly attention; they do not measure dataset users or exact-release citations.',
                       'Base-family citations are explicitly marked for derived variants such as daily MERRA-2 and TerraClimate futures.',
                       'A missing or unindexed reference remains unknown, never zero. Rankings cover resolved references only.',
                       'Multiple papers and data DOIs can share citing works; counts are reported separately and never summed.',
                       'Total citation counts favor older papers; recent counts and publication years are contextual fields.',
                       'Existing-host routing is a separate availability review; lack of a known host is not proof conversion is required.'],
    }
    files = {'rankings.json': json.dumps(output, indent=2) + '\n',
             'ranking-all.csv': table(output), 'ranking-global.csv': table(global_rows),
             'ranking-data-dois.csv': table(data_rows, 'max_data_doi_citations'),
             'summary.json': json.dumps(summary, indent=2) + '\n'}
    for name, content in files.items():
        path = HERE / name
        if args.check:
            assert path.read_text() == content, f'Stale generated output: {name}'
        else:
            path.write_text(content)
    print(json.dumps(summary, indent=2))
    print('Global leaders:')
    for row in global_rows[:15]:
        print(row['slug'], row['max_paper_citations'], row['top_paper_doi'], row['citation_scope'])


if __name__ == '__main__':
    main()
