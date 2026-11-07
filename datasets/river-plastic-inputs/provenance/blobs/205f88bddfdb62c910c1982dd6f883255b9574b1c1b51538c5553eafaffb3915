#!/usr/bin/env python3
"""Inject realistic errors into the real local table; never write altered data."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from check_publication import HERE, MONTHS, evaluate


def replace(table, name, transform):
    field = table.schema.field(name)
    # Widen only the in-memory fault fixture so a units error reaches the checker.
    field = field.with_type(pa.decimal128(38, field.type.scale))
    values = [transform(value) for value in table[name].to_pylist()]
    return table.set_column(table.schema.get_field_index(name), field, pa.array(values, type=field.type))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads((HERE / 'publication-benchmarks.json').read_text())
    table = pq.read_table(args.release / 'river-plastic-inputs/river-plastic-inputs.parquet')
    if evaluate(table, contract)['status'] != 'passed':
        raise SystemExit('Baseline must pass before fault injection')
    results = []

    def detect(label, altered, required_failures):
        report = evaluate(altered, contract)
        failures = {check['id'] for check in report['checks'] if check['status'] == 'failed'}
        if not set(required_failures) <= failures:
            raise AssertionError(f'{label}: expected {required_failures}; detected {sorted(failures)}')
        results.append({'fault': label, 'status': 'detected', 'failed_checks': sorted(failures)})

    scaled = table
    for name in ('i_low', 'i_mid', 'i_high'):
        scaled = replace(scaled, name, lambda x: x * 1000 if x is not None else None)
    detect('Annual tonnes misinterpreted as kilograms', scaled, ['global_lower_annual', 'global_upper_annual'])

    shifted = table
    for index, month in enumerate(MONTHS):
        name = f'i_mid_{month}'
        shifted = shifted.set_column(shifted.schema.get_field_index(name), name,
                                     table[f'i_mid_{MONTHS[(index + 6) % 12]}'])
    detect('Monthly midpoint labels shifted by six months', shifted, ['may_october_midpoint_share'])

    inverted = table.set_column(table.schema.get_field_index('i_low'), 'i_low', table['i_high'])
    detect('Lower uncertainty bound replaced by upper bound', inverted, ['ordered_uncertainty'])

    negative = replace(table, 'runoff_jan', lambda x: -x if x is not None else None)
    detect('Negative runoff introduced', negative, ['nonnegative_estimates'])

    partial = replace(table, 'i_mid', lambda x: Decimal(0) if x is None else x)
    detect('Only midpoint nulls changed to zeros', partial, ['ordered_uncertainty'])

    result = {'status': 'passed', 'scope': 'Five deliberate in-memory faults in a copy of the real local table; release bytes unchanged.', 'checks': results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
