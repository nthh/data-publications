#!/usr/bin/env python3
"""Reproduce retained strict failures from a clean checkout and existing local cache."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'research/gee-release-validation-20261106'
LAYERS = ['hydrolakes','lakeatlas-polygons','lakeatlas-points','free-flowing-rivers','grwl-raw']


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cache',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    dirty=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    if dirty: ap.error('Rehearsal requires a clean checkout; no tracked or untracked changes.')
    if a.output.exists(): ap.error('Refusing to overwrite an existing rehearsal.')
    a.output.mkdir(parents=True)
    report={'schema_version':1,'status':'running','clean_checkout_observed':True,
        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'python':sys.version.split()[0],'code_sha256':{p:sha(ROOT/p) for p in [
            'scripts/gee_validation/compare.py','scripts/gee_validation/provenance.py','scripts/gee_validation/uv.lock',
            'research/gee-release-validation-20261106/rehearse.py']},
        'offline':True,'source_data_modified':False,'comparisons':[]}
    try:
        cmd=[sys.executable,'-m','unittest','tests.test_gee_request_contract','tests.test_gee_release_comparison',
            'tests.test_gee_provenance','tests.test_gee_geometry_diagnostic','tests.test_gee_attribute_diagnostics','tests.test_provenance_archive','-v']
        tests=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (a.output/'tests.log').write_text(tests.stdout)
        counts=re.findall(r'Ran (\d+) tests?',tests.stdout)
        report['tests']={'command':cmd,'returncode':tests.returncode,'count':int(counts[-1]) if counts else None,
            'log_sha256':sha(a.output/'tests.log')}
        if tests.returncode or report['tests']['count']!=32: raise RuntimeError('Focused test suite did not pass all 32 checks.')
        summary=subprocess.run([sys.executable,str(REVIEW/'summarize.py'),'--check'],cwd=ROOT,capture_output=True,text=True)
        report['summary_check']={'returncode':summary.returncode,'stdout':summary.stdout,'stderr':summary.stderr}
        if summary.returncode: raise RuntimeError('Retained summary check failed.')
        for layer in LAYERS:
            suffix='r2' if layer in {'free-flowing-rivers','grwl-raw'} else 'r1'
            plan=f'{layer}-plan-r2.json' if suffix=='r2' else f'{layer}-plan.json'
            output=a.output/f'{layer}.json'
            cmd=[sys.executable,str(ROOT/'scripts/gee_validation/compare.py'),
                '--sample',str(a.cache/'samples-r1'/f'{layer}-sample.json'),
                '--capture',str(a.cache/f'{layer}-{suffix}'), '--plan',str(REVIEW/'plans'/plan),
                '--criteria',str(REVIEW/'criteria.json'), '--report',str(output)]
            result=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            (a.output/f'{layer}.log').write_text(result.stdout)
            actual=json.loads(output.read_text()) if output.exists() else {}
            expected=REVIEW/'comparisons-r1'/f'{layer}.json'
            item={'layer_id':layer,'command':cmd,'returncode':result.returncode,'status':actual.get('status'),
                'expected_sha256':sha(expected),'actual_sha256':sha(output) if output.exists() else None,
                'capture_integrity_pass':actual.get('capture_validation',{}).get('pass'),
                'provenance_status':actual.get('provenance',{}).get('independent_verification',{}).get('status')}
            item['byte_identical']=item['actual_sha256']==item['expected_sha256'];report['comparisons'].append(item)
            if not(item['byte_identical'] and result.returncode==1 and item['status']=='sampled_fail' and item['capture_integrity_pass'] and item['provenance_status']=='passed'):
                raise RuntimeError(f'{layer}: strict failure was not reproduced exactly.')
            print(json.dumps({'layer':layer,'byte_identical':True,'strict_status':item['status']}),flush=True)
        report['status']='passed_reproducibility_of_retained_strict_failures'
    except Exception as exc:
        report['status']='failed_rehearsal';report['error']={'type':type(exc).__name__,'message':str(exc)}
    (a.output/'rehearsal.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'report':str(a.output/'rehearsal.json')}))
    return 0 if report['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
