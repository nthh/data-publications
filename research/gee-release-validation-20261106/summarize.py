#!/usr/bin/env python3
"""Regenerate the review snapshot from retained reports, offline (stdlib only)."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LAYERS = ['hydrolakes', 'lakeatlas-polygons', 'lakeatlas-points', 'free-flowing-rivers', 'grwl-raw']


def read(path):
    return json.loads((HERE / path).read_text())


def reference(path):
    p = HERE / path
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}


def max_distance(result):
    return result.get('max_vertex_displacement_m') or result.get('hausdorff_m') or 0


def make_summary():
    layers = []
    for layer in LAYERS:
        cpath = f'comparisons-r1/{layer}.json'
        c = read(cpath)
        assert c['capture_validation']['pass'] and c['provenance']['independent_verification']['status'] == 'passed'
        assert c['count']['pass'] and c['identity']['missing_sample_count'] == 0
        entry = {'layer_id': layer, 'dataset_id': 'lakeatlas' if layer.startswith('lakeatlas-') else layer,
                 'status': 'completed_sampled_with_documented_differences', 'strict_status': c['status'],
                 'count': c['count'], 'identity': c['identity'], 'sample_context': c['sample_context'],
                 'capture_integrity': 'passed', 'source_and_historical_git_provenance': 'passed',
                 'strict_geometry': {k: c['geometry'][k] for k in ['strict_pass', 'strict_fail']},
                 'comparison_report': reference(cpath)}
        apath = f'attribute-diagnostics-r1/{layer}.json'
        if (HERE / apath).exists():
            a = read(apath)
            assert a['status'] == 'diagnostic_complete'
            assert a['provenance']['sample_sha256'] == c['provenance']['sample_sha256']
            counts = Counter()
            fields = a['attributes']['source_scientific_attributes']
            for f in fields.values(): counts.update(f['counts'])
            entry['attributes'] = {'scientific_field_count': len(fields), 'counts': dict(counts),
                'mismatching_fields': [k for k, f in fields.items() if f['counts']['mismatch']],
                'missing_required_properties': sum(f['missing_required_property'] for f in fields.values()),
                'geometry_derived_fields_excluded_from_these_counts': list(a['attributes']['geometry_derived_attributes']),
                'diagnostic_report': reference(apath)}
            if layer.startswith('lakeatlas-'):
                hypotheses = [f['numeric']['precision_hypothesis'] for f in fields.values()]
                outliers = [dict(field=k, **x) for k,f in fields.items() for x in f['numeric']['precision_hypothesis']['lakeatlas_outliers']]
                entry['attributes']['six_significant_digit_diagnostic'] = {
                    'mismatches_tested': sum(h['tested_mismatch_pairs'] for h in hypotheses),
                    'compatible': sum(h['compatible_mismatch_pairs'] for h in hypotheses),
                    'outliers': len(outliers),
                    'outlier_fields': sorted({x['field'] for x in outliers}),
                    'outliers_with_integral_gee_value': sum(float(x['gee']).is_integer() for x in outliers),
                    'outliers_equal_nearest_source_integer': sum(x['gee'] == round(x['local']) for x in outliers),
                    'maximum_outlier_absolute_difference': max(x['absolute_error'] for x in outliers),
                    'largest_relative_difference_example': max(outliers,key=lambda x:x['absolute_error']/abs(x['local'])),
                    'interpretation': 'Posthoc descriptive integer counts; not a new tolerance or proof of the ingestion method. Six exceptions across both layers differ from nearest-integer rounding of the retained source value.'}
            if layer == 'free-flowing-rivers':
                hyps = [f['numeric']['precision_hypothesis'] for f in fields.values()]
                alias = a['explicit_ffr_candidate_mapping']['candidate_mapping_diagnostic']
                exceptional = [x for h in hyps for x in h['ffr_case_results'] if not x['hypothesis']['match']]
                entry['attributes']['twelve_significant_digit_diagnostic'] = {
                    'original_mapped_mismatches_tested': sum(h['tested_mismatch_pairs'] for h in hyps),
                    'original_mapped_compatible': sum(h['compatible_mismatch_pairs'] for h in hyps),
                    'remaining_cases': len(exceptional),
                    'remaining_max_absolute_difference': max(x['absolute_error'] for x in exceptional),
                    'explicit_erosion_alias': {'source': 'ERO_YLD_TON', 'gee': 'ERO_YLD_TO',
                        'counts': alias['counts'], 'rounding_compatible': alias['numeric']['precision_hypothesis']['compatible_mismatch_pairs'],
                        'maximum_absolute_difference': alias['numeric']['maximum_absolute_error'],
                        'definition_url': 'https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers'},
                    'interpretation': 'Alias diagnostic is separate; the original missing-field and numerical failures remain.'}
        else:
            entry['attributes'] = c['attributes']
        g = c['geometry']
        passed = g['diagnostic_pass']
        max_passed = max([max_distance(x) for x in g['results'] if x.get('diagnostic_pass')] or [0])
        geometry = {'initial_diagnostic_within_one_meter': passed, 'followup_cases': 0,
                    'within_one_meter_across_mixed_diagnostics': passed, 'over_one_meter': g['diagnostic_fail'],
                    'incomplete': g['diagnostic_incomplete'], 'maximum_observed_diagnostic_m': max_passed,
                    'interpretation': 'Aligned WGS84 vertices or discrete locally projected distances; not a continuous Hausdorff certificate, strict parity pass or exhaustive check.'}
        gpath = f'geometry-diagnostics-r2/{layer}.json'
        if (HERE / gpath).exists():
            followup = read(gpath)
            assert followup['comparison_sha256'] == reference(cpath)['sha256']
            assert followup['cases'] == g['diagnostic_fail'] + g['diagnostic_incomplete']
            geometry.update(followup_cases=followup['cases'],
                within_one_meter_across_mixed_diagnostics=passed+followup['discrete_within_one_meter'],
                over_one_meter=followup['discrete_over_one_meter'], incomplete=followup['incomplete'],
                maximum_observed_diagnostic_m=max(max_passed, followup['maximum_sampled_distance_m']),
                above_one_meter_cases=[{'local_id': x['local_id'], 'maximum_sampled_distance_m': x['maximum_sampled_distance_m']} for x in followup['results'] if x.get('discrete_within_one_meter') is False],
                followup_report=reference(gpath))
        assert geometry['incomplete'] == 0
        entry['geometry_diagnostics'] = geometry
        layers.append(entry)

    plastic = read('plastic-replay-r1/diagnostic.json')
    before = read('count-metadata/river-plastic-refresh-r1/river-plastic-inputs-before-001.json')
    after = read('count-metadata/river-plastic-refresh-r1/river-plastic-inputs-after-001.json')
    count = read('count-metadata/river-plastic-refresh-r1/river-plastic-inputs-count-001.json')['result']
    assert before == after == plastic['provenance']['asset_metadata']
    assert count == plastic['source_rows'] == plastic['gee_features']
    layers.insert(0, {'layer_id': 'river-plastic-inputs', 'dataset_id': 'river-plastic-inputs',
        'status': 'completed_historical_exhaustive_replay_with_fresh_metadata_and_count',
        'strict_status': 'failed_geometry_parity', 'count': {'local_row_count': count, 'gee_synchronous_count': count, 'pass': True},
        'features_refetched_in_this_review': False, 'metadata_unchanged_since_original_capture': True,
        'capture_scope': 'Offline replay of the 2026-10-30 full capture, with 2026-11-06 metadata/count refresh only.',
        'attributes': {k: plastic[k] for k in ['scientific_fields','attribute_cells_compared','exact_numeric_matches','null_matches','mismatch_counts']},
        'identity': {k: plastic[k] for k in ['uniquely_matched_points','coincident_groups_verified','coincident_records_verified','source_records_verified']},
        'geometry_diagnostics': {'within_one_meter': count, 'maximum_observed_diagnostic_m': plastic['geodesic_displacement_meters']['maximum']},
        'strict_report': reference('plastic-replay-r1/strict.json'), 'diagnostic_report': reference('plastic-replay-r1/diagnostic.json')})
    files = sorted(p for p in HERE.rglob('*.json') if p.name not in {'summary.json','verification.json'})
    return {'schema_version': 1, 'as_of': '2026-11-06', 'datasets_reviewed': 5, 'analytical_layers': 6,
        'status': 'comparisons_complete_with_documented_differences', 'all_strict_gee_parity_passed': False,
        'source_data_modified': False, 'products_published': False,
        'scope': 'Global counts, 512–522 systematic source-selected observations in each large layer, and historical exhaustive river-plastic replay. Neither counts nor samples establish exhaustive present-day GEE parity or independent scientific accuracy.',
        'layers': layers, 'lake_spike_trace': reference('lake-spike-traces-r1.json'),
        'grwl_global_selected_key_inventory': reference('grwl-key-inventory-r1.json'),
        'grwl_primary_license_review': reference('zenodo-metadata/review.json'),
        'generator': reference('summarize.py'), 'evidence': [reference(p.relative_to(HERE)) for p in files]}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true')
    a=ap.parse_args();expected=json.dumps(make_summary(),indent=2,ensure_ascii=False,allow_nan=False)+'\n';path=HERE/'summary.json'
    if a.write: path.write_text(expected)
    elif not path.exists() or path.read_text()!=expected: raise SystemExit('GEE review summary is stale; run --write.')
    print('GEE review summary: six layers, five datasets; retained strict differences, no publication.')


if __name__=='__main__': main()
