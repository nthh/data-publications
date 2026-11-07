#!/usr/bin/env python3
"""Serve a local prepared release with CORS and single byte-range support."""
from __future__ import annotations
import argparse
import threading
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
MAX_RANGE_BYTES=128*1024*1024
class Handler(SimpleHTTPRequestHandler):
 bytes_served = 0
 bytes_lock = threading.Lock()
 @classmethod
 def reset_bytes_served(cls):
  with cls.bytes_lock: cls.bytes_served = 0
 @classmethod
 def get_bytes_served(cls):
  with cls.bytes_lock: return cls.bytes_served
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
   length=end-start+1
   if length>MAX_RANGE_BYTES:
    self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Accept-Ranges','bytes');self.end_headers();return
   self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Accept-Ranges','bytes');self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Content-Length',str(length));self.end_headers()
   with path.open('rb') as f:
    f.seek(start);remaining=length
    while remaining:
     data=f.read(min(1024*1024,remaining))
     if not data:break
     self.wfile.write(data)
     with self.bytes_lock: type(self).bytes_served += len(data)
     remaining-=len(data)
  except Exception: self.send_error(400)
 def log_message(self,*args): pass
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('release',type=Path);ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8000);a=ap.parse_args();s=ThreadingHTTPServer((a.host,a.port),lambda *x:Handler(*x,directory=str(a.release.resolve())));print(f'Serving {a.release} on http://{a.host}:{a.port}',flush=True);s.serve_forever()
