#!/usr/bin/env python3
"""Exercise byte ranges and CORS on the shipped local HTTP handler."""
from __future__ import annotations
import argparse,json,tempfile,threading,urllib.error,urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from serve import Handler
def run():
 with tempfile.TemporaryDirectory(prefix='grwl-http-fixture-') as td:
  root=Path(td);data=bytes(range(64));(root/'sample.bin').write_bytes(data)
  server=ThreadingHTTPServer(('127.0.0.1',0),lambda *args:Handler(*args,directory=str(root)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/sample.bin';cases=[]
  try:
   for name,rng,expected,status,expected_range in [('first','bytes=0-7',data[:8],206,'bytes 0-7/64'),('middle','bytes=20-27',data[20:28],206,'bytes 20-27/64'),('suffix','bytes=-8',data[-8:],206,'bytes 56-63/64'),('invalid','bytes=64-72',b'',416,'bytes */64')]:
    req=urllib.request.Request(url,headers={'Range':rng})
    try:resp=urllib.request.urlopen(req);code=resp.status;headers=resp.headers;payload=resp.read()
    except urllib.error.HTTPError as error:code=error.code;headers=error.headers;payload=error.read()
    if code!=status or payload!=expected or headers.get('Content-Range')!=expected_range or headers.get('Access-Control-Allow-Origin')!='*':raise ValueError(f'HTTP fixture failed: {name}')
    cases.append({'case':name,'range':rng,'status':code,'bytes':len(payload),'content_range':headers['Content-Range'],'cors':headers['Access-Control-Allow-Origin']})
  finally:server.shutdown();server.server_close()
 return {'status':'passed','handler':'datasets/grwl/serve.py','fixture_bytes':64,'cases':cases}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();r=run();a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
