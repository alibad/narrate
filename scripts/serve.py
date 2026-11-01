"""Loopback-only local review server, including byte ranges for video seeking."""
import os,re
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]/'dist';PORT=int(os.environ.get('NARRATE_SITE_PORT','8770'))
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kw):super().__init__(*args,directory=str(ROOT),**kw)
 def log_message(self,*args):pass
 def end_headers(self):self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');super().end_headers()
 def do_GET(self):
  target=Path(self.translate_path(self.path))
  if 'Range'in self.headers and target.is_file():
   m=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
   if not m:return self.send_error(416)
   total=target.stat().st_size;start=int(m[1]);end=min(int(m[2])if m[2]else total-1,total-1)
   if start>=total or end<start:return self.send_error(416)
   self.send_response(206);self.send_header('Content-Type',self.guess_type(str(target)));self.send_header('Content-Range',f'bytes {start}-{end}/{total}');self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.end_headers()
   with target.open('rb')as f:
    f.seek(start);remaining=end-start+1
    while remaining:
     block=f.read(min(256*1024,remaining))
     if not block:break
     self.wfile.write(block);remaining-=len(block)
   return
  super().do_GET()
if __name__=='__main__':
 print(f'Narrate local review: http://127.0.0.1:{PORT}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
