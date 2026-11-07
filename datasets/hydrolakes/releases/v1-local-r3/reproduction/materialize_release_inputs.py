#!/usr/bin/env python3
"""Resolve path-free HydroLAKES r3 fidelity and package templates."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path
from typing import Any
REPO_ROOT=Path(__file__).resolve().parents[5]
TOKENS={"__ARTIFACT_ROOT__","__REPO_ROOT__","__FIDELITY_ROOT__","__PACKAGE_OUTPUT__"}
def load(path:Path)->dict[str,Any]:
 value=json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
 if not isinstance(value,dict): raise ValueError(f"template must be an object: {path}")
 return value
def replace(value:Any,roots:dict[str,Path])->Any:
 if isinstance(value,dict): return {k:replace(v,roots) for k,v in value.items()}
 if isinstance(value,list): return [replace(v,roots) for v in value]
 if isinstance(value,str):
  for token,root in roots.items():
   if value.startswith(token+"/"): return str((root/value[len(token)+1:]).resolve())
 return value
def write_new(path:Path,value:dict[str,Any])->None:
 path=path.expanduser().resolve()
 if path.exists(): raise FileExistsError(f"refuse to overwrite materialized input: {path.name}")
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); print(path)
def observed_clean_checkout(path:Path,expected:str)->dict[str,Any]:
 path=path.expanduser().resolve()
 commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=path,text=True).strip()
 status=subprocess.check_output(["git","status","--porcelain"],cwd=path,text=True)
 branch=subprocess.check_output(["git","branch","--show-current"],cwd=path,text=True).strip()
 if commit!=expected: raise ValueError(f"clean checkout HEAD {commit} differs from required {expected}")
 if status: raise ValueError("clean checkout has uncommitted or untracked files")
 if branch: raise ValueError("clean checkout is expected to be detached")
 return {"commit":commit,"detached_checkout":True,"git_status_porcelain_empty":True,"checked_by":"datasets/hydrolakes/releases/v1-local-r3/reproduction/materialize_release_inputs.py"}
def main()->None:
 parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest="command",required=True)
 f=sub.add_parser("fidelity"); f.add_argument("--artifact-root",type=Path,required=True); f.add_argument("--clean-checkout",type=Path,required=True); f.add_argument("--output",type=Path,required=True)
 p=sub.add_parser("package"); p.add_argument("--artifact-root",type=Path,required=True); p.add_argument("--repo-root",type=Path,default=REPO_ROOT); p.add_argument("--fidelity-root",type=Path,required=True); p.add_argument("--package-output",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
 args=parser.parse_args()
 if args.command=="fidelity":
  value=load(Path(__file__).with_name("fidelity-normalizer-template.json")); expected=value["rebuild_context"]["clean_checkout"]["commit"]
  value["rebuild_context"]["clean_checkout"]=observed_clean_checkout(args.clean_checkout,expected)
  value=replace(value,{"__ARTIFACT_ROOT__":args.artifact_root.expanduser().resolve()})
 else:
  value=load(Path(__file__).with_name("package-spec-template.json")); value=replace(value,{"__ARTIFACT_ROOT__":args.artifact_root.expanduser().resolve(),"__REPO_ROOT__":args.repo_root.expanduser().resolve(),"__FIDELITY_ROOT__":args.fidelity_root.expanduser().resolve()}); value["output_dir"]=str(args.package_output.expanduser().resolve())
 write_new(args.output,value)
if __name__=="__main__": main()
