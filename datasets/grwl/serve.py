#!/usr/bin/env python3
"""Serve a local prepared release with CORS and single byte-range support."""
from __future__ import annotations
import argparse
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
class Handler(SimpleHTTPRequestHandler):
 def end_headers(self): self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Methods','GET, HEAD, OPTIONS'); self.send_header('Access-Control-Allow-Headers','Range'); super().end_headers()
 def do_OPTIONS(self): self.send_response(204); self.end_headers()
 def do_GET(self):
  value=self.headers.get('Range')
  if not value or not value.startswith('bytes='): return super().do_GET()
  path=Path(self.translate_path(self.path))
  if not path.is_file(): self.send_error(404); return
  try:
   a,b=value[6:].split('-',1); size=path.stat().st_size
   if not a and not b: self.send_error(400); return
   if not a:
    suffix=int(b)
    if suffix<=0: self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
    start=max(0,size-suffix);end=size-1
   else:
    start=int(a);end=min(int(b),size-1) if b else size-1
   if start<0 or end<start or start>=size: self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
   with path.open('rb') as f: f.seek(start); data=f.read(end-start+1)
   self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Accept-Ranges','bytes');self.send_header('Content-Range',f'bytes {start}-{start+len(data)-1}/{size}');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  except Exception: self.send_error(400)
 def log_message(self,*args): pass
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('release',type=Path);ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8000);a=ap.parse_args();s=ThreadingHTTPServer((a.host,a.port),lambda *x:Handler(*x,directory=str(a.release.resolve())));print(f'Serving {a.release} on http://{a.host}:{a.port}',flush=True);s.serve_forever()
