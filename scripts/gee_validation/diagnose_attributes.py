#!/usr/bin/env python3
"""Summarize observed attribute differences without changing strict comparisons."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare
from provenance import verify_provenance


NUMERIC_KINDS = {'integer', 'float64', 'float32', 'decimal'}
SUPPORTED = {'hydrolakes', 'lakeatlas-polygons', 'lakeatlas-points', 'free-flowing-rivers'}


def local_number(value, type_name):
    if compare.type_kind(type_name) not in NUMERIC_KINDS or isinstance(value, bool) or value is None:
        return None
    try:
        n = compare.source_decimal(value) if compare.type_kind(type_name) == 'decimal' else float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if n is not None and math.isfinite(n) else None


def gee_number(value):
    n = compare.number(value)
    if n is None:
        return None
    n = float(n)
    return n if math.isfinite(n) else None


def precision_hypothesis(dataset, local, gee, local_n):
    result = {'tested': False, 'match': None, 'bound': None, 'exception': None}
    if local_n is None or gee is None:
        result['exception'] = 'not_finite_numeric_pair'
        return result
    if dataset == 'free-flowing-rivers':
        result['tested'] = True
        rounded = float(format(local_n, '.12g'))
        result.update(match=gee == rounded, rounded_local_12_significant=rounded)
        return result
    if dataset in {'lakeatlas-polygons', 'lakeatlas-points'}:
        result['tested'] = True
        if local_n == 0:
            result['exception'] = 'six_significant_digit_bound_undefined_for_zero'
            return result
        decimal_bound = 0.5 * (10.0 ** (math.floor(math.log10(abs(local_n))) - 5))
        serialization_allowance = 2 * max(compare.ulp(local_n), compare.ulp(gee))
        result.update(bound=decimal_bound, serialization_allowance=serialization_allowance, effective_bound=decimal_bound + serialization_allowance)
        result['match'] = abs(local_n - gee) <= result['effective_bound']
        return result
    return result


def string_patterns(local, gee):
    return {
        'null_to_empty': local is None and gee == '',
        'empty_to_null': local == '' and gee is None,
        'whitespace_only_difference': isinstance(local, str) and isinstance(gee, str) and local != gee and local.strip() == gee.strip(),
    }


def diagnose_field(field_name, meta, observations, dataset):
    """Analyze (local_id, local_value, gee_value, property_present) rows."""
    stats = Counter()
    exceptions = Counter()
    numeric_rows = 0
    numeric_mismatches = []
    pattern_examples = defaultdict(list)
    absolute_max = None
    relative_max = None
    precision_tested = 0
    precision_matches = 0
    precision_exceptions = Counter()
    hypothesis_cases = []
    precision_outliers = []
    for local_id, local, gee, property_present in observations:
        if not property_present and local is not None:
            stats['missing_required_property'] += 1
            stats['mismatch'] += 1
            exceptions['missing_nonnull_property'] += 1
            continue
        equal, kind, reason = compare.compare_value(local, gee, meta.get('type', ''))
        stats[kind] += 1
        if not property_present and local is None:
            stats['absent_property_null_equivalence'] += 1
        pats = string_patterns(local, gee)
        for label, found in pats.items():
            if found:
                exceptions[label] += 1
                if len(pattern_examples[label]) < 5:
                    pattern_examples[label].append({'local_id': local_id, 'local': local, 'gee': gee})
        if not equal:
            exceptions[f'strict_reason:{reason}'] += 1
        typ = compare.type_kind(meta.get('type', ''))
        if typ not in NUMERIC_KINDS:
            if local is None or gee is None:
                if local != gee:
                    exceptions['null_value_mismatch'] += 1
                    if len(pattern_examples['null_value_mismatch']) < 5:
                        pattern_examples['null_value_mismatch'].append({'local_id': local_id, 'local': local, 'gee': gee})
            elif isinstance(local, str) and not isinstance(gee, str):
                exceptions['string_to_nonstring_mismatch'] += 1
                if len(pattern_examples['string_to_nonstring_mismatch']) < 5:
                    pattern_examples['string_to_nonstring_mismatch'].append({'local_id': local_id, 'local': local, 'gee': gee})
            elif isinstance(gee, str) and not isinstance(local, str):
                exceptions['nonstring_to_string_mismatch'] += 1
                if len(pattern_examples['nonstring_to_string_mismatch']) < 5:
                    pattern_examples['nonstring_to_string_mismatch'].append({'local_id': local_id, 'local': local, 'gee': gee})
            continue
        local_n = local_number(local, meta.get('type', ''))
        gee_n = gee_number(gee)
        if local is None or gee is None:
            if local != gee:
                exceptions['numeric_null_mismatch'] += 1
            continue
        if local_n is None or gee_n is None:
            exceptions['numeric_value_not_json_number_or_finite'] += 1
            continue
        numeric_rows += 1
        absolute = abs(local_n - gee_n)
        relative = absolute / abs(local_n) if local_n != 0 else None
        absolute_max = absolute if absolute_max is None else max(absolute_max, absolute)
        if relative is not None:
            relative_max = relative if relative_max is None else max(relative_max, relative)
        elif absolute:
            exceptions['relative_error_undefined_local_zero'] += 1
        if not equal:
            hypothesis = precision_hypothesis(dataset, local, gee_n, local_n)
            if hypothesis['tested']:
                precision_tested += 1
                precision_matches += bool(hypothesis['match'])
                case = {'local_id': local_id, 'local': local, 'gee': gee, 'absolute_error': absolute, 'hypothesis': hypothesis}
                if dataset == 'free-flowing-rivers':
                    hypothesis_cases.append(case)
                elif dataset.startswith('lakeatlas-') and hypothesis['match'] is False:
                    precision_outliers.append(case)
            if hypothesis['exception']:
                precision_exceptions[hypothesis['exception']] += 1
            numeric_mismatches.append({
                'local_id': local_id, 'local': local, 'gee': gee,
                'absolute_error': absolute, 'relative_error': relative,
                'strict_reason': reason, 'precision_hypothesis': hypothesis,
            })
    numeric_mismatches.sort(key=lambda r: (r['absolute_error'], str(r['local_id'])), reverse=True)
    return {
        'role': meta.get('role'),
        'type': meta.get('type'),
        'observations': len(observations),
        'counts': {k: stats[k] for k in ('exact', 'representational', 'mismatch')},
        'missing_required_property': stats['missing_required_property'],
        'absent_property_null_equivalence': stats['absent_property_null_equivalence'],
        'numeric': {
            'valid_numeric_pairs': numeric_rows,
            'mismatch_pairs': len(numeric_mismatches),
            'maximum_absolute_error': absolute_max,
            'maximum_relative_error': relative_max,
            'relative_error_undefined_count': exceptions['relative_error_undefined_local_zero'],
            'precision_hypothesis': {
                'kind': '12_significant_digit_rounding' if dataset == 'free-flowing-rivers' else '6_significant_digit_decimal_bound' if dataset.startswith('lakeatlas-') else 'not_applicable',
                'tested_mismatch_pairs': precision_tested,
                'compatible_mismatch_pairs': precision_matches,
                'compatibility_is_observation_not_causal_proof_or_tolerance': True,
                'exceptions': dict(precision_exceptions),
                'ffr_case_results': hypothesis_cases if dataset == 'free-flowing-rivers' else [],
                'lakeatlas_outliers': precision_outliers if dataset.startswith('lakeatlas-') else [],
            },
            'largest_absolute_error_examples': numeric_mismatches[:5],
        },
        'string_null_and_type_patterns': dict(exceptions),
        'string_null_type_mismatch_examples': dict(pattern_examples),
    }


def index_features(sample, payloads):
    dataset = sample['dataset_id']
    id_field = 'Hylak_id' if dataset in {'hydrolakes', 'lakeatlas-polygons', 'lakeatlas-points'} else 'GOID'
    indexed = defaultdict(list)
    malformed = 0
    for qid, pages in payloads.items():
        if not qid.startswith(f'{dataset}-features-'):
            continue
        for _, payload in pages:
            for feature in payload.get('features', []):
                props = feature.get('properties', {})
                name = compare.resolve_field(id_field, {'gee_aliases': [id_field]}, props)
                if name is None:
                    malformed += 1
                    continue
                indexed[str(props[name])].append(feature)
    return indexed, malformed, id_field


def build_diagnostic(sample_path, capture_dir, plan_path, report_path=None):
    criteria_path = ROOT / 'research/gee-release-validation-20261106/criteria.json'
    followup_path = ROOT / 'research/gee-release-validation-20261106/followup-criteria.json'
    sample = compare.read_json(sample_path)
    plan = compare.read_json(plan_path)
    criteria = compare.read_json(criteria_path)
    followup = compare.read_json(followup_path)
    dataset = sample.get('dataset_id')
    if dataset not in SUPPORTED:
        raise ValueError(f'Attribute diagnostic supports only {sorted(SUPPORTED)}; got {dataset!r}')
    capture_issues, payloads, _ = compare.verify_capture(sample_path, sample, capture_dir, plan_path, plan, criteria_path, criteria)
    provenance = verify_provenance(sample_path, capture_dir, plan_path)
    parent_criteria_bound = followup.get('parent_criteria_sha256') == compare.sha(criteria_path)
    own_script_sha = compare.sha(Path(__file__).resolve())
    lock_sha = compare.sha(Path(__file__).with_name('uv.lock'))
    try:
        git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        tracked_changes = subprocess.check_output(['git', 'status', '--porcelain', '--', 'scripts/gee_validation/diagnose_attributes.py', 'scripts/gee_validation/uv.lock', 'research/gee-release-validation-20261106/followup-criteria.json'], cwd=ROOT, text=True).strip()
    except Exception:
        git_commit, tracked_changes = None, 'git-unavailable'
    # Preserve strict comparison as its own status. Diagnostic findings never change it.
    strict = compare.build_report(sample_path, sample, capture_dir, plan_path, plan, criteria_path, criteria)
    indexed, malformed_features, id_field = index_features(sample, payloads)
    observations = defaultdict(list)
    missing_ids = []
    duplicate_ids = []
    for row in sample.get('features', []):
        local_id = str(row.get('local_id'))
        hits = indexed.get(local_id, [])
        if not hits:
            missing_ids.append(local_id)
            props = {}
            feature_present = False
        elif len(hits) > 1:
            duplicate_ids.append(local_id)
            props = hits[0].get('properties', {})
            feature_present = True
        else:
            props = hits[0].get('properties', {})
            feature_present = True
        for field_name, meta in sample['fields'].items():
            if meta.get('role') not in {'source', 'geometry_derived'}:
                continue
            key = compare.resolve_field(field_name, meta, props) if feature_present else None
            present = key is not None
            local = row.get('properties', {}).get(field_name)
            gee = props.get(key) if present else None
            observations[field_name].append((local_id, local, gee, present))

    field_summary = {'source_scientific_attributes': {}, 'geometry_derived_attributes': {}}
    for field_name, meta in sample['fields'].items():
        role = meta.get('role')
        if role not in {'source', 'geometry_derived'}:
            continue
        group = 'geometry_derived_attributes' if role == 'geometry_derived' else 'source_scientific_attributes'
        field_summary[group][field_name] = diagnose_field(field_name, meta, observations[field_name], dataset)

    alternate = None
    if dataset == 'free-flowing-rivers':
        field_name = 'ERO_YLD_TON'
        meta = sample['fields'].get(field_name)
        if meta is not None:
            alt_observations = []
            for row in sample.get('features', []):
                lid = str(row.get('local_id'))
                hits = indexed.get(lid, [])
                props = hits[0].get('properties', {}) if hits else {}
                alt_key = compare.resolve_field('ERO_YLD_TO', {'gee_aliases': []}, props) if hits else None
                alt_observations.append((lid, row.get('properties', {}).get(field_name), props.get(alt_key) if alt_key else None, alt_key is not None))
            alternate = {
                'source_field': field_name,
                'candidate_gee_field': 'ERO_YLD_TO',
                'explicit_analysis_only_alias_added': False,
                'original_strict_field_result_preserved': field_summary['source_scientific_attributes'][field_name],
                'candidate_mapping_diagnostic': diagnose_field(field_name, meta, alt_observations, dataset),
                'classification': 'observed candidate compatibility only; no causal proof, tolerance change, or strict-pass relabeling',
            }

    return {
        'schema_version': 1,
        'diagnostic_only': True,
        'dataset_id': dataset,
        'status': 'diagnostic_complete' if not capture_issues and provenance.get('status') == 'passed' and parent_criteria_bound and not tracked_changes else 'diagnostic_inputs_unverified',
        'interpretation': 'Observed compatibility patterns are descriptive only; they do not prove causes, establish new tolerances, change aliases, or turn strict failures into passes.',
        'strict_comparison': {'status': strict.get('status'), 'attribute_pass': strict.get('attributes', {}).get('pass'), 'geometry_pass': strict.get('geometry', {}).get('strict_passed'), 'status_unchanged_by_diagnostic': True},
        'provenance': {'capture_issues': capture_issues, 'independent_verification': provenance, 'sample_sha256': compare.sha(sample_path), 'plan_sha256': compare.sha(plan_path), 'criteria_sha256': compare.sha(criteria_path), 'followup_criteria_sha256': compare.sha(followup_path), 'followup_parent_criteria_bound': parent_criteria_bound, 'diagnostic_script_sha256': own_script_sha, 'environment_lock_sha256': lock_sha, 'git_commit': git_commit, 'diagnostic_script_lock_criteria_worktree_changes': tracked_changes},
        'matching': {'identifier_field': id_field, 'requested_rows': len(sample.get('features', [])), 'missing_ids': missing_ids, 'duplicate_ids': duplicate_ids, 'malformed_gee_features_missing_identifier': malformed_features},
        'attributes': field_summary,
        'explicit_ffr_candidate_mapping': alternate,
        'geometry_derived_fields_are_separate': True,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sample', required=True, type=Path)
    ap.add_argument('--capture', required=True, type=Path)
    ap.add_argument('--plan', required=True, type=Path)
    ap.add_argument('--report', required=True, type=Path)
    args = ap.parse_args(argv)
    if args.report.exists():
        ap.error(f'refusing to overwrite existing report: {args.report}')
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--', 'scripts/gee_validation/diagnose_attributes.py', 'scripts/gee_validation/uv.lock', 'research/gee-release-validation-20261106/followup-criteria.json'], cwd=ROOT, text=True).strip()
    if dirty:
        ap.error('commit diagnostic script, environment lock, and frozen follow-up criteria before evaluating captures')
    report = build_diagnostic(args.sample, args.capture, args.plan, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'dataset_id': report['dataset_id'], 'strict_comparison': report['strict_comparison']['status'], 'report': str(args.report)}))
    return 0 if report['status'] == 'diagnostic_complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
