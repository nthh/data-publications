#!/usr/bin/env python3
"""Exercise the production raw builder against frozen synthetic dateline controls."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from test_grwl_raw_conversion import _attrs, _write_tile


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    source=args.output/'source';source.mkdir()
    cases=[
      {'name':'eastward crossing','width_m':90,'parts':[[(179.999,0),(-179.999,.0001)]]},
      {'name':'westward crossing and unknown width','width_m':1,'parts':[[(-179.999,.1),(179.999,.1001)]]},
      {'name':'east tiny tail','width_m':200,'parts':[[(179.999,.2),(-179.9999999,.2001)]]},
      {'name':'west tiny tail','width_m':500,'parts':[[(-179.999,.3),(179.9999999,.3001)]]},
      {'name':'separate same-segment record A','width_m':50,'parts':[[(10,0),(10.001,0)]]},
      {'name':'separate same-segment record B and multipart','width_m':1000,'parts':[[(10.01,0),(10.011,0)],[(10.02,0),(10.021,0)]]},
    ]
    _write_tile(source,'AA01',[{'parts':c['parts'],'attrs':_attrs(segmentID=7,width_m=c['width_m'])} for c in cases])
    (args.output/'controls.json').write_text(json.dumps({'purpose':'synthetic regression controls, not producer records','cases':cases},indent=2)+'\n')
    convert=module('raw_convert',ROOT/'datasets/grwl-raw/convert.py')
    validate=module('raw_validate',ROOT/'datasets/grwl-raw/validate.py')
    builder=module('raw_display',ROOT/'datasets/grwl-raw/build_display.py')
    oracle=module('raw_oracle',ROOT/'datasets/grwl-raw/validate_display.py')
    analytical=args.output/'analytical';convert.convert(source,['AA01'],analytical)
    fidelity=args.output/'source-fidelity.json'
    if validate.validate(source,None,analytical/'grwl-raw.parquet',analytical/'manifest.json',fidelity)['status']!='passed':
        raise RuntimeError('Synthetic source conversion failed')
    display=args.output/'display'
    builder.build(analytical/'grwl-raw.parquet',analytical/'manifest.json',fidelity,display,args.output)
    report=oracle.validate(analytical/'grwl-raw.parquet',analytical/'manifest.json',fidelity,
                          display/'assets/grwl-raw.pmtiles',args.output/'display-validation.json')
    if report['status']!='passed':raise RuntimeError('Native dateline/part controls failed')
    print(json.dumps({'status':report['status'],'native_source_ids':report['maxzoom_unique_ids'],'geometry_samples_passed':report['geometry_samples_passed']}))


if __name__=='__main__':main()
