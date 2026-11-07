#!/usr/bin/env python3
"""Render the reviewed top-30 download/format study without network access."""
import argparse
import copy
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'research/top30-download-audit-20261030'


def read(name):
    return json.loads((STUDY / name).read_text())


def markdown(value):
    return str(value).replace('|', '/').replace('\n', ' ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    groups = read('top30-input.json')
    frozen = json.loads((ROOT / 'research/catalog-citations-20261030/groups-combined-all.json').read_text())[:30]
    assert [g['id'] for g in groups] == [g['id'] for g in frozen]
    reviews = [r for shard in 'abc' for r in read(f'review-{shard}.json')]
    assert sorted(r['rank'] for r in reviews) == list(range(1, 31))
    rows = {r['rank']: copy.deepcopy(r) for r in reviews}
    for correction in read('parent-corrections.json'):
        row = rows[correction['rank']]
        row.update(correction['replace'])
        row.setdefault('parent_review', []).append(correction['reason'])
    presentations = {r['rank']: r for r in read('presentation.json')}
    assert set(presentations) == set(rows)
    for rank, group in enumerate(groups, 1):
        row = rows[rank]
        row.update(work_id=group['id'], citations=group['max_paper_citations'],
                   catalogs=group['catalogs'], catalog_entries=group['entries'])
        row['catalog_membership'] = ('Both' if len(group['catalogs']) == 2 else
                                     'Community' if group['catalogs'] == ['community'] else 'Official')
        row['presentation'] = presentations[rank]
        d = row['download_size']
        assert d['status'] in {'measured', 'publisher_stated', 'bounded_estimate', 'calculated_uncompressed', 'unknown'}
        assert d['scope'] and d['basis'] and row['selected_scope']
        assert d.get('bytes') is None or (type(d['bytes']) is int and d['bytes'] > 0)
        if d['status'] == 'unknown':
            assert d.get('bytes') is None
        assert row['native_formats'] and row['desired_formats'] and row['sources']
        assert all(s['url'].startswith(('https://', 'http://')) and s['supports'] for s in row['sources'])
        assert set(group['catalogs']) == {e['catalog'] for e in group['entries']}
    result = [rows[i] for i in range(1, 31)]
    membership = dict(Counter(r['catalog_membership'] for r in result))
    assert membership == {'Official': 22, 'Both': 4, 'Community': 4}
    files = {}
    def put_json(name, obj):
        files[name] = json.dumps(obj, indent=2, ensure_ascii=False) + '\n'
    put_json('inventory.json', result)
    fields = ['rank','dataset','catalog','citations','download_size','download_scope','size_evidence_type',
              'exact_measured_bytes','source_formats','desired_formats','existing_cloud_native','caveats','source_urls']
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in result:
        d = row['download_size']
        writer.writerow({'rank':row['rank'],'dataset':row['presentation']['name'],
            'catalog':row['catalog_membership'],'citations':row['citations'],
            'download_size':d['display'],'download_scope':row['selected_scope'],
            'size_evidence_type':d['status'],
            'exact_measured_bytes':d.get('bytes') if d['status']=='measured' else None,
            'source_formats':'; '.join(row['native_formats']),
            'desired_formats':'; '.join(row['desired_formats']),
            'existing_cloud_native':row.get('existing_cloud_native','Not verified'),
            'caveats':' | '.join(row.get('caveats',[])),
            'source_urls':' | '.join(s['url'] for s in row['sources'])})
    files['top30.csv'] = output.getvalue()
    lines = ['# Top 30: catalog membership, download size and formats','',
        'Research date: 2026-10-30. Ranking is the frozen combined official/community paper-citation ranking, including deprecated entries. Counts do not establish conversion priority.','',
        '**22 official only · 4 community only · 4 in both catalogs.** Membership follows the reviewed citation groups. A shared paper can describe different products or versions; it does not prove identical assets.','',
        'Download size always applies to the stated scope. Static releases are sized globally where possible; time series identify product, variables and period. Approximate figures use producer totals, rounded listing sums or average-file-size estimates. Exact bytes are distinguished in the CSV. Publisher MB units are retained in detailed evidence; rounded GB summaries are planning approximations. Unknown is not zero.','',
        'Desired formats are recommendations for a future publication: COG for spatial raster maps, Zarr for time series and multidimensional grids, GeoParquet for vectors, and optional PMTiles for display. Existing cloud-native distributions may only need a registry reference. Converted output size requires a measured pilot.','',
        '| # | Dataset | Catalog | Download size / selected scope | Source format | Desired output |',
        '|---:|---|---|---|---|---|']
    for row in result:
        p = row['presentation']
        lines.append(f'| {row["rank"]} | [{markdown(p["name"])}](#dataset-{row["rank"]}) | {row["catalog_membership"]} | {markdown(p["size"])} — {markdown(p["scope"])} | {markdown(p["source"])} | {markdown(p["output"])} |')
    lines += ['', 'NCEP/NCAR entries are deprecated in the official snapshot. Several “Both” groups contain different versions or resolutions; see their detail records.','',
        '## Sources and scope details','']
    for row in result:
        p = row['presentation']; d = row['download_size']
        lines += [f'<a id="dataset-{row["rank"]}"></a>',f'### {row["rank"]}. {p["name"]}','',
            f'**Catalog:** {row["catalog_membership"]}. **Citation count:** {row["citations"]:,}.','',
            '**Scope:** ' + row['selected_scope'],'',
            '**Download amount:** ' + d['display'] + f' (`{d["status"]}`).','',
            '**Evidence:** ' + d['basis'],'',
            '**Source formats:** ' + '; '.join(row['native_formats']) + '.','',
            '**Desired formats:** ' + '; '.join(row['desired_formats']) + '. ' + row.get('rationale',''),'',
            '**Existing access:** ' + row.get('existing_cloud_native','Not verified').rstrip('.') + '.','']
        for caveat in row.get('caveats',[]):
            lines += ['- ' + caveat]
        if row.get('caveats'): lines += ['']
        if row.get('alternative_sizes'):
            lines += ['Other explicitly scoped amounts:','']
            for a in row['alternative_sizes']:
                lines += ['- ' + a['display'] + ' — ' + a['scope'] + ' ' + a['basis']]
            lines += ['']
        lines += ['Catalog entries: ' + '; '.join(f'[{markdown(e["catalog_id"])}]({quote(e["url"],safe=":/?=&%#")})' for e in row['catalog_entries']) + '.','', 'Primary sources:','']
        for i, source in enumerate(row['sources'],1):
            lines += [f'- [{i}]({quote(source["url"],safe=":/?=&%#")}) — {source["supports"]}']
        lines += ['']
    lines += ['## Reproduce and review','',
        'The three review shards retain initial source assessments; `parent-corrections.json` applies the final review. `evidence-*` holds metadata receipts and research notes. `review-findings.json` preserves failed checks and unresolved questions. `inventory.json` and `top30.csv` contain all 30 rows.','',
        '```sh','python3 scripts/report_download_audit.py --check','```','',
        'This command uses only committed files and the Python standard library. It performs no network requests. To refresh sizes, start a new dated study, retrieve producer metadata again, review scope and units, then regenerate; do not overwrite this snapshot.','',
        'Format references: [COG](https://guide.cloudnativegeo.org/cloud-optimized-geotiffs/intro.html), [Zarr](https://guide.cloudnativegeo.org/zarr/intro.html), [GeoParquet](https://geoparquet.org/), [PMTiles](https://docs.protomaps.com/pmtiles/). PMTiles is an optional display derivative; analytic geometry and attributes remain in GeoParquet.','',
        'No dataset bodies, GEE exports, conversions, uploads or registry submissions were performed. A separate rights and exact-version review precedes publication.','']
    files['README.md'] = '\n'.join(lines)
    input_paths = [STUDY / x for x in ['methodology.json','top30-input.json','review-a.json','review-b.json','review-c.json','parent-corrections.json','presentation.json','review-findings.json']]
    input_paths += sorted(f for f in STUDY.glob('evidence-*/*') if f.is_file())
    input_paths += [Path(__file__).resolve(), ROOT/'research/catalog-citations-20261030/groups-combined-all.json']
    put_json('input-manifest.json',{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in input_paths})
    for name, text in files.items():
        path = STUDY / name
        if args.check:
            assert path.read_text() == text, 'Stale output: ' + name
        else:
            path.write_text(text)
    print(json.dumps({'rows':30,'membership':membership,'size_evidence':dict(Counter(r['download_size']['status'] for r in result)),
                      'outputs':len(files),'result':'byte-identical' if args.check else 'generated'}))

if __name__ == '__main__':
    main()
