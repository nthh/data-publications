#!/usr/bin/env python3
"""Reproduce a validated regional width overview and UI from a clean checkout."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
SOURCE_SHA='1c7177cc55b732dc7e609ed22ae50c46d677548da98c4b39e4f1ab76996ca509'
ROWS=919832
CODE_PATHS=(
    'datasets/grwl-raw/build_width_overview.py','datasets/grwl-raw/validate_width_overview.py',
    'datasets/grwl-raw/combine_width_display.py','datasets/grwl-raw/prepare_width_preview.py',
    'datasets/grwl-raw/finalize_width_display.py','datasets/grwl-raw/finalize_display.py',
    'scripts/source_products.py','scripts/display_tools/uv.lock','scripts/display_tools/pyproject.toml',
    'scripts/cloud_viewer/src/app.js','scripts/cloud_viewer/src/core.js','scripts/cloud_viewer/src/style.css',
    'scripts/cloud_viewer/src/index.html','scripts/cloud_viewer/src/parquet.worker.js','scripts/cloud_viewer/src/land.geojson',
    'scripts/cloud_viewer/build.mjs','scripts/cloud_viewer/fetch-assets.mjs','scripts/cloud_viewer/serve.py',
    'scripts/cloud_viewer/package.json','scripts/cloud_viewer/package-lock.json','scripts/cloud_viewer/runtime-assets.json',
    'scripts/cloud_viewer/width-overview-browser-check.mjs','scripts/cloud_viewer/export-raw-width-style.mjs',
    'research/grwl-width-overview-20261106/criteria.json','research/grwl-width-overview-20261106/run_width_replay.py',
)


def identity(path):
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return {'sha256':sha,'size_bytes':path.stat().st_size}


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def require(condition,message):
    if not condition:raise ValueError(message)


def guard(task_root,start=False):
    free=shutil.disk_usage(task_root).free
    used=sum(p.stat().st_size for p in task_root.rglob('*') if p.is_file() and not p.is_symlink())
    require(free >= (40 if start else 15)*2**30 and used<=12*2**30,'Frozen resource floor or task ceiling exceeded')
    return {'free_bytes':free,'task_bytes':used}


def replay(source,source_manifest,baseline,baseline_sha,reference_overview,overview_report,
        reference_combined,reference_viewer_build,output,task_root,native_lock):
    paths=[source,source_manifest,baseline,reference_overview,overview_report,reference_combined,
        reference_viewer_build,output,task_root,native_lock]
    source,source_manifest,baseline,reference_overview,overview_report,reference_combined,reference_viewer_build,output,task_root,native_lock=[Path(p).expanduser().resolve() for p in paths]
    require(not os.path.lexists(output),'Refusing existing clean-replay output')
    output.relative_to(task_root)
    task_root.mkdir(parents=True,exist_ok=True)
    start_resources=guard(task_root,True)
    before,commit=git('status','--porcelain=v1'),git('rev-parse','HEAD')
    require(not before,'Replay requires a clean committed checkout')
    require(identity(source)['sha256']==SOURCE_SHA,'Replay requires the frozen nine-tile source')
    meta=json.loads(source_manifest.read_text());criteria=json.loads((ROOT/CODE_PATHS[-2]).read_text())
    require(meta['parquet_sha256']==SOURCE_SHA and meta['rows']==ROWS
        and sorted(t.get('tile',t.get('source_tile')) for t in meta['tiles'])==sorted(criteria['development_tiles']),
        'Replay source manifest or development tile split differs')
    code_pins={p:identity(ROOT/p) for p in CODE_PATHS}
    ui=json.loads(reference_viewer_build.read_text())
    require(ui['package_lock_sha256']==identity(ROOT/'scripts/cloud_viewer/package-lock.json')['sha256'],'Reference UI lock differs')
    for rel,pin in ui['files'].items():require(identity(reference_viewer_build.parent/rel)==pin,'Reference UI file differs: '+rel)
    output.mkdir();(output/'logs').mkdir()
    result={'schema_version':1,'status':'running','source_sha256':SOURCE_SHA,'source_rows':ROWS,
        'source_manifest':identity(source_manifest),'reference_viewer_build_sha256':identity(reference_viewer_build)['sha256'],
        'clean_checkout':{'commit':commit,'before':before},'code_pins':code_pins,'stages':[],
        'resources_start':start_resources,'scope':'Clean regional reproduction; this is not a second global build.'}
    start=time.monotonic()
    def save():
        (output/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    def run(name,command):
        guard(task_root);log=output/'logs'/f'{name}.log'
        print(json.dumps({'stage':name,'status':'running'}),flush=True)
        with log.open('xb') as stream:r=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        result['stages'].append({'name':name,'command':command,'exit_code':r.returncode,'log':{'path':str(log),**identity(log)}})
        save();require(r.returncode==0,'Replay stage failed: '+name)
    try:
        new_overview=output/'overview'
        run('width-overview',[sys.executable,str(ROOT/'datasets/grwl-raw/build_width_overview.py'),
            '--source',str(source),'--source-manifest',str(source_manifest),'--output',str(new_overview),
            '--task-root',str(task_root),'--native-lock',str(native_lock)])
        require(identity(new_overview/'overview.pmtiles')==identity(reference_overview/'overview.pmtiles'),'Overview archive bytes differ')
        for z in range(8):require(identity(new_overview/f'samples/z{z}.parquet')==identity(reference_overview/f'samples/z{z}.parquet'),f'Sample bytes differ at z{z}')
        new_combined=output/'combined'
        run('combine',[sys.executable,str(ROOT/'datasets/grwl-raw/combine_width_display.py'),
            '--baseline',str(baseline),'--baseline-sha256',baseline_sha,'--overview',str(new_overview/'overview.pmtiles'),
            '--overview-report',str(overview_report),'--output',str(new_combined),'--task-root',str(task_root),'--native-lock',str(native_lock)])
        require(identity(new_combined/'assets/grwl-raw.pmtiles')==identity(reference_combined),'Combined archive bytes differ')
        new_ui=output/'ui'
        run('viewer',['node',str(ROOT/'scripts/cloud_viewer/build.mjs'),'--out',str(new_ui)])
        require(identity(new_ui/'build.json')==identity(reference_viewer_build),'Viewer build manifest differs')
        for rel,pin in ui['files'].items():require(identity(new_ui/rel)==pin,'Viewer file differs: '+rel)
        after,after_commit=git('status','--porcelain=v1'),git('rev-parse','HEAD')
        result['clean_checkout'].update(after=after,after_commit=after_commit)
        require(after==before=='' and after_commit==commit,'Replay checkout changed')
        require({p:identity(ROOT/p) for p in CODE_PATHS}==code_pins,'Replay code changed during execution')
        result.update(status='passed',byte_equal={'samples':True,'overview_archive':True,'combined_archive':True,
            'viewer_build':True,'viewer_files':True},resources_end=guard(task_root),seconds=time.monotonic()-start)
        save();return result
    except BaseException as error:
        result.update(status='failed',error=f'{type(error).__name__}: {error}',seconds=time.monotonic()-start)
        result['clean_checkout'].update(after=git('status','--porcelain=v1'),after_commit=git('rev-parse','HEAD'))
        save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','source-manifest','baseline','reference-overview','overview-report','reference-combined','reference-viewer-build','output','task-root','native-lock'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--baseline-sha256',required=True)
    a=p.parse_args();print(json.dumps(replay(a.source,a.source_manifest,a.baseline,a.baseline_sha256,a.reference_overview,
        a.overview_report,a.reference_combined,a.reference_viewer_build,a.output,a.task_root,a.native_lock),sort_keys=True))
