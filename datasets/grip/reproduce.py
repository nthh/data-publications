#!/usr/bin/env python3
"""Build, validate and reproduce GRIP4 in a clean local checkout, then package."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from build import sha256,write_json
from dataset_config import load_config
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);p.add_argument('--source-cache',type=Path,required=True)
    a=p.parse_args();work=a.work.resolve();cache=a.source_cache.resolve();config=load_config()
    if work.exists():raise SystemExit('Choose a new work path; earlier runs are retained.')
    if subprocess.check_output(['git','status','--porcelain','--',str(HERE)],cwd=ROOT,text=True).strip():raise SystemExit('Commit the dataset workflow first.')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    work.mkdir(parents=True);reports=work/'verification';reports.mkdir();logs=work/'logs';logs.mkdir()
    release=work/config['release'];rebuild=work/'rebuild';checkout=work/'checkout';python=sys.executable
    def run(name,cmd):
        print(name+': running',flush=True)
        with (logs/(name+'.log')).open('w') as output:
            result=subprocess.run([str(x) for x in cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'{name} failed ({result.returncode}); preserve {logs/(name+".log")}')
        print(name+': passed',flush=True)
        return (logs/(name+'.log')).read_text()
    run('build',[python,HERE/'build.py','--source-cache',cache,'--output',release])
    manifest=json.loads((release/'manifest.json').read_text());binding=sha256(release/'manifest.json')
    run('validation',[python,HERE/'validate.py',release,'--source-cache',cache,'--http','--report',reports/'validation.json'])
    text=run('stac',[HERE/'node_modules/.bin/stac-node-validator',release/'catalog.json',release/'grip/collection.json'])
    if not all(re.search(regex,text) for regex in (r'Passed:\s*2\b',r'Invalid:\s*0\b',r'Skipped:\s*0\b')):raise ValueError('STAC did not validate both documents')
    write_json(reports/'stac-validation.json',{'status':'passed','release_manifest_sha256':binding,'validated_documents':2,'invalid':0,'skipped':0,'validator':'stac-node-validator 2.0.0','output':text})
    text=run('portolan',[Path(python).parent/'rashid','check',release,'--schema','--data-scope','local','--json'])
    write_json(reports/'portolan-validation.json',{'status':'passed','release_manifest_sha256':binding,'exit_code':0,'rawresult':json.loads(text)})
    run('faults',[python,HERE/'test_validation.py','--report',reports/'fault-detail.json'])
    detail=json.loads((reports/'fault-detail.json').read_text());detail['release_manifest_sha256']=binding
    write_json(reports/'fault-tests.json',detail)
    run('workflow-tests',[python,'-m','unittest',str(HERE/'test_package.py'),str(HERE/'test_catalog_release.py')])
    run('checkout',['git','clone','--shared','--no-checkout',ROOT,checkout])
    run('checkout-revision',['git','-C',checkout,'checkout','--detach',revision])
    clean=subprocess.check_output(['git','-C',checkout,'status','--porcelain'],text=True)
    if clean.strip():raise ValueError('Reproduction checkout is dirty')
    run('environment',['uv','sync','--locked','--project',checkout/'datasets/grip'])
    run('rebuild',[checkout/'datasets/grip/.venv/bin/python',checkout/'datasets/grip/build.py','--source-cache',cache,'--output',rebuild])
    if (release/'manifest.json').read_bytes()!=(rebuild/'manifest.json').read_bytes():raise ValueError('Independent rebuild manifest differs')
    hashes={name:sha256(rebuild/name) for name in manifest['assets']}
    if hashes!={name:entry['sha256'] for name,entry in manifest['assets'].items()}:raise ValueError('Independent rebuild assets differ')
    write_json(reports/'reproducibility.json',{'status':'passed','release_manifest_sha256':binding,'manifest_equal':True,
       'conversion_git_commit':revision,'assets_compared':len(hashes),'hashes':hashes,
       'scope':'Separate clean Git checkout and locked Python environment; same source archive, native tools and machine. Not cross-platform proof.'})
    archive=work/('grip-'+config['release']+'.zip')
    run('package',[python,HERE/'package.py',release,'--reports',reports,'--output',archive])
    summary={'status':'passed_local_release','release':config['release'],'conversion_git_commit':revision,
       'release_manifest_sha256':binding,'rows':config['expected_rows'],'archive':{'name':archive.name,'sha256':sha256(archive),'size_bytes':archive.stat().st_size},
       'limits':['No live GEE or scientific observational validation.','No public hosting or registry submission.']}
    write_json(reports/'rehearsal.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
