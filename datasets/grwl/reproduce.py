#!/usr/bin/env python3
"""Rehearse, validate and package a local GRWL release from a clean checkout."""
from __future__ import annotations
import argparse,hashlib,json,re,shutil,subprocess,sys,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEFAULT_SOURCE=ROOT/'.local/grwl/GRWL_summaryStats_V01.02.zip'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def call(stage,command,cwd,logs,allow_failure=False):
 result=subprocess.run([str(x) for x in command],cwd=cwd,capture_output=True,text=True)
 output=result.stdout+result.stderr;(logs/(stage+'.log')).write_text(output)
 if result.returncode and not allow_failure:
  failure={'status':'failed','stage':stage,'returncode':result.returncode,'log_path':str(logs/(stage+'.log')),'output':output}
  persist_failure(stage+'-failure.json',failure)
  raise RuntimeError(f'{stage} exited {result.returncode}; retained output at {logs/(stage+".log")} and datasets/grwl/evidence/failures/{stage}-failure.json')
 return result

def persist_failure(name,report):
 dest=HERE/'evidence/failures';dest.mkdir(parents=True,exist_ok=True)
 payload=json.dumps(report,indent=2)+'\n';target=dest/(Path(name).stem+'-'+hashlib.sha256(payload.encode()).hexdigest()[:12]+'.json')
 if not target.exists():target.write_text(payload)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);ap.add_argument('--source',type=Path,default=DEFAULT_SOURCE);a=ap.parse_args()
 work=a.work.resolve();source=a.source.resolve()
 if work.exists(): raise SystemExit('Refuse overwrite; choose new work directory')
 if sha(source)!='78aa43a7104d24b1696e9b1547347eec13ba5d660aa990c1e7cea98e7ae70e4a': raise SystemExit('Source checksum mismatch')
 if subprocess.check_output(['git','status','--porcelain','--','datasets/grwl'],cwd=ROOT,text=True).strip(): raise SystemExit('Commit GRWL code, contract and locks before release rehearsal')
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 work.mkdir(parents=True);checkout=work/'clean-checkout';reports=work/'reports';reports.mkdir();logs=work/'logs';logs.mkdir()
 call('clone',['git','clone','--quiet','--shared','--no-checkout',ROOT,checkout],ROOT,logs);call('checkout',['git','checkout','--quiet','--detach',revision],checkout,logs)
 if subprocess.check_output(['git','status','--porcelain'],cwd=checkout,text=True).strip(): raise SystemExit('Fresh checkout is not clean')
 clean_here=checkout/'datasets/grwl'
 call('python-environment',['uv','sync','--locked','--project',clean_here],checkout,logs)
 call('node-environment',['npm','ci','--prefix',clean_here,'--ignore-scripts','--no-audit','--no-fund'],checkout,logs)
 python=clean_here/'.venv/bin/python';release=work/'release';rebuild=work/'rebuild'
 call('build-first',[python,clean_here/'build.py','--source',source,'--output',release],checkout,logs)
 val=call('validate',[python,clean_here/'validate.py',release,'--source',source,'--http','--report',reports/'validation.json'],checkout,logs);print(val.stdout)
 validation=json.loads((reports/'validation.json').read_text());manifest_path=release/'manifest.json';m1=manifest_path.read_bytes();manifest_sha=hashlib.sha256(m1).hexdigest()
 if validation.get('status')!='passed' or validation.get('release_manifest_sha256')!=manifest_sha: raise SystemExit('Validation report does not pass or bind to this release manifest')
 node=clean_here/'node_modules/.bin/stac-node-validator'
 node_result=call('stac-node',[node,release/'catalog.json',release/'grwl/collection.json'],checkout,logs,allow_failure=True);node_output=node_result.stdout+node_result.stderr
 matches={k:re.search(rf'{k}:\s*(\d+)\b',node_output,re.I) for k in ('Passed','Invalid','Skipped')}
 counts={k:int(v.group(1)) if v else None for k,v in matches.items()}
 stac_report={'status':'passed' if node_result.returncode==0 and counts=={'Passed':2,'Invalid':0,'Skipped':0} else 'failed','validator':'stac-node-validator 2.0.0','exit_code':node_result.returncode,'release_manifest_sha256':manifest_sha,'validated_documents':['catalog.json','grwl/collection.json'],'counts':counts,'output':node_output}
 (reports/'stac-validation.json').write_text(json.dumps(stac_report,indent=2)+'\n')
 if stac_report['status']!='passed':persist_failure('stac-node-validation.json',stac_report);raise SystemExit('STAC Node validation failed; retained its report and raw log')
 rashid=clean_here/'.venv/bin/rashid';port=call('portolan',[rashid,'check',release,'--schema','--data-scope','local','--json'],checkout,logs,allow_failure=True);port_output=port.stdout+port.stderr
 try: port_json=json.loads(port_output)
 except json.JSONDecodeError: port_json={'raw_output':port_output}
 port_report={'status':'passed' if port.returncode==0 and isinstance(port_json,dict) and port_json.get('passed') is True and port_json.get('error_count')==0 else 'failed','validator':'rashid 0.1.8','exit_code':port.returncode,'release_manifest_sha256':manifest_sha,'checks':['Portolan v0.2 bundled JSON schema','STAC structural schema','local asset checksums and sizes'],'result':port_json}
 (reports/'portolan-validation.json').write_text(json.dumps(port_report,indent=2)+'\n')
 if port_report['status']!='passed':persist_failure('portolan-validation.json',port_report);raise SystemExit('Rashid Portolan validation failed; retained its report and raw log')
 call('build-second',[python,clean_here/'build.py','--source',source,'--output',rebuild],checkout,logs)
 m2=(rebuild/'manifest.json').read_bytes()
 if m1!=m2: raise SystemExit('Independent clean-checkout rebuild manifest differs')
 manifest=json.loads(m1);hashes={n:sha(release/n) for n in manifest['assets']}
 if hashes!={n:sha(rebuild/n) for n in manifest['assets']}: raise SystemExit('Independent clean-checkout asset hashes differ')
 for name,expected in manifest['build_input_sha256'].items():
  if sha(clean_here/name)!=expected: raise SystemExit(f'Build input changed before packaging: {name}')
 repro={'status':'passed','manifest_sha256':manifest_sha,'clean_checkout_commit':revision,'clean_checkout_status':'clean','asset_count':len(hashes),'asset_sha256':hashes,'scope':'Two output directories built from one fresh detached checkout with locked Python/Node dependencies and pinned Tippecanoe; not cross-platform proof.'}
 (reports/'reproducibility.json').write_text(json.dumps(repro,indent=2)+'\n')
 if repro['manifest_sha256']!=manifest_sha or repro['asset_sha256']!=hashes: raise SystemExit('Reproducibility report binding mismatch')
 serve_test=call('serve-tests',[python,clean_here/'test_serve.py','--report',reports/'serve-tests.json'],checkout,logs);print(serve_test.stdout)
 fault=call('fault-tests',[python,clean_here/'fault_tests.py',release,'--source',source,'--report',reports/'fault-tests.json'],checkout,logs);print(fault.stdout)
 faults=json.loads((reports/'fault-tests.json').read_text())
 if faults.get('status')!='passed' or faults.get('release_manifest_sha256')!=manifest_sha: raise SystemExit('Fault tests do not pass or bind to this release manifest')
 report_names=('validation.json','serve-tests.json','stac-validation.json','portolan-validation.json','reproducibility.json','fault-tests.json')
 verification={n:sha(reports/n) for n in report_names};history_file=HERE/'evidence/development/failures.json';history_sha=sha(history_file);code={n:sha(clean_here/n) for n in manifest['build_input_sha256']}
 binding={'manifest_sha256':manifest_sha,'source_sha256':sha(source),'dataset_record_sha256':manifest['dataset_record_sha256'],'development_failure_evidence_sha256':history_sha,'verification_sha256':verification,'build_input_sha256':code}
 (reports/'package-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
 instructions=b'''# Reproducing this release\n\nThis release was built from the detached repository commit recorded in `manifest.json`. The conversion code and locks are under `verification/workflow/datasets/grwl/`; the adjacent `dataset.yaml` is the exact snapshot bound by the manifest. For a full rebuild, clone that commit, install the pinned Python environment with `uv sync --locked --project datasets/grwl`, install Node dependencies with `npm ci --prefix datasets/grwl`, install the Tippecanoe version and binary hash recorded in `tippecanoe.lock.json`, obtain the source ZIP matching the pinned SHA-256, then run `uv run --locked --project datasets/grwl python datasets/grwl/reproduce.py --source /path/to/GRWL_summaryStats_V01.02.zip --work /path/to/new-output`. The Apache software license and notice are under `software/`; dataset terms are CC BY 4.0.\n'''
 target=work/'grwl-summary-v0102-local-r1.zip'
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  items=[(release/n,n) for n in sorted(manifest['assets'])]
  items += [(clean_here/n,'verification/workflow/datasets/grwl/'+n) for n in manifest['build_input_sha256']]
  items += [(clean_here/'dataset.yaml','verification/workflow/datasets/grwl/dataset.yaml'),(history_file,'verification/history/development-failures.json'),(None,'verification/workflow/README.md'),(ROOT/'LICENSE','software/LICENSE'),(ROOT/'NOTICE','software/NOTICE'),(release/'manifest.json','manifest.json'),(reports/'package-binding.json','verification/receipt.json'),(source,'source/GRWL_summaryStats_V01.02.zip')]
  items += [(reports/n,'verification/'+n) for n in report_names]
  for src,name in items:
   payload=instructions if src is None else src.read_bytes();zi=zipfile.ZipInfo(name,(2026,10,30,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o100644<<16;z.writestr(zi,payload)
 with zipfile.ZipFile(target) as z:
  names=z.namelist()
  if len(names)!=len(set(names)): raise SystemExit('Package contains duplicate paths')
  if z.testzip(): raise SystemExit('Package CRC validation failed')
  bind=json.loads(z.read('verification/receipt.json'));zmanifest=z.read('manifest.json')
  if hashlib.sha256(zmanifest).hexdigest()!=bind['manifest_sha256']: raise SystemExit('Packaged manifest binding mismatch')
  zm=json.loads(zmanifest)
  for name,item in zm['assets'].items():
   raw=z.read(name)
   if len(raw)!=item['size_bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']: raise SystemExit(f'Packaged asset mismatch: {name}')
  for name,expected in bind['build_input_sha256'].items():
   if hashlib.sha256(z.read('verification/workflow/datasets/grwl/'+name)).hexdigest()!=expected: raise SystemExit(f'Packaged build input mismatch: {name}')
  if hashlib.sha256(z.read('verification/workflow/datasets/grwl/dataset.yaml')).hexdigest()!=bind['dataset_record_sha256']: raise SystemExit('Packaged dataset snapshot mismatch')
  for name,expected in bind['verification_sha256'].items():
   if hashlib.sha256(z.read('verification/'+name)).hexdigest()!=expected: raise SystemExit(f'Packaged verification report mismatch: {name}')
  if hashlib.sha256(z.read('verification/history/development-failures.json')).hexdigest()!=bind['development_failure_evidence_sha256']: raise SystemExit('Historical development failure evidence mismatch')
  if hashlib.sha256(z.read('source/GRWL_summaryStats_V01.02.zip')).hexdigest()!=bind['source_sha256']: raise SystemExit('Packaged source mismatch')
 target.chmod(0o444)
 result={'status':'packaged_locally_not_published','archive':target.name,'size_bytes':target.stat().st_size,'sha256':sha(target),'members':len(zipfile.ZipFile(target).namelist()),'source_sha256':sha(source),'manifest_sha256':manifest_sha,'verification_sha256':verification}
 (work/'package-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
 # Status changes occur only after validation, reproduction, fault, catalog and package gates pass.
 import yaml
 record=yaml.safe_load((HERE/'dataset.yaml').read_text());record['build']['status']='local_release_prepared';record['build']['release_id']='summary-v01.02-local-r1';record['publication']['status']='prepared';record['publication']['release']={'version':'summary-v01.02-local-r1','archive_name':target.name,'archive_sha256':result['sha256'],'manifest_sha256':manifest_sha}
 (HERE/'dataset.yaml').write_text(yaml.safe_dump(record,sort_keys=False,allow_unicode=True))
 evidence=HERE/'evidence';evidence.mkdir(exist_ok=True)
 for n in report_names:shutil.copyfile(reports/n,evidence/n)
 package_record={k:result[k] for k in ('status','archive','size_bytes','sha256','members','source_sha256','manifest_sha256','verification_sha256')};(evidence/'package-receipt.json').write_text(json.dumps(package_record,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__': main()
