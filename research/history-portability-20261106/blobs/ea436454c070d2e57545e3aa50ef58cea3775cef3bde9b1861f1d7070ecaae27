#!/usr/bin/env python3
"""Acquire the pinned original HydroLAKES ZIP, streaming and verifying bytes."""
from pathlib import Path
import argparse, hashlib, json, shutil, urllib.request
URL="https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip"
SIZE=820295132
SHA="9ef63498569dd7ccd0b8d8852da026e009a75f42d293f00e483f3b9fcfe8e1f9"
def identity(path):
 h=hashlib.sha256();size=0
 with path.open("rb") as f:
  while b:=f.read(8*1024*1024):h.update(b);size+=len(b)
 return size,h.hexdigest()
def acquire(path):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  if identity(path)!=(SIZE,SHA):raise ValueError("Existing source fails pinned identity")
  return
 if shutil.disk_usage(path.parent).free < SIZE+5*1024**3:raise RuntimeError("Insufficient disk reserve")
 partial=path.with_suffix(path.suffix+".partial")
 if partial.exists():raise FileExistsError("Retained partial download; inspect before retry")
 with urllib.request.urlopen(urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.hydrosheds.org/products/hydrolakes","Accept-Encoding":"identity"}),timeout=60) as r, partial.open("xb") as f:
  count=0
  while b:=r.read(8*1024*1024):
   count+=len(b)
   if count>SIZE:raise ValueError("Source exceeds pinned byte count")
   f.write(b)
 if identity(partial)!=(SIZE,SHA):raise ValueError("Downloaded source fails pinned identity; partial retained")
 partial.rename(path)
if __name__=="__main__":
 a=argparse.ArgumentParser(description=__doc__);a.add_argument("--output",type=Path,required=True);args=a.parse_args();acquire(args.output)
 print(json.dumps({"name":args.output.name,"bytes":SIZE,"sha256":SHA,"url":URL}))
