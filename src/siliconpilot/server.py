"""Loopback-only observatory and compiler adapter; public demo stays static."""
from __future__ import annotations
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading
from typing import Any
from urllib.parse import urlparse
import uuid


def serve(root: str | Path,port: int=8791) -> None:
    root=Path(root).resolve()
    if not (root/'observatory/index.html').is_file():
        raise ValueError('Run serve --root from the SILICONPILOT source checkout')
    gate=threading.Lock()
    jobs: dict[str,Path]={}
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args: Any,**kwargs: Any) -> None:
            super().__init__(*args,directory=str(root/'observatory'),**kwargs)

        def json_response(self,value: Any,status: int=200) -> None:
            content=json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            path=urlparse(self.path).path
            if path=='/api/health':
                self.json_response({'mode':'local','tools':{n:bool(shutil.which(n)) for n in ('iverilog','yosys','nextpnr-ecp5')}})
            elif path=='/api/models':
                self.json_response({'models':[{'id':f'banknote-4x{w}x2','name':f'4 → {w} → 2'} for w in (4,8,12)]})
            elif path.startswith('/api/artifacts/'):
                parts=path.split('/')
                allowed={'design.v','manifest.json','weights.json','verification.json','build.json','core.log','streaming.log','waveform.vcd'}
                if len(parts)!=5 or parts[3] not in jobs or parts[4] not in allowed:
                    self.send_error(404)
                    return
                file=jobs[parts[3]]/parts[4]
                if not file.is_file():
                    self.send_error(404)
                    return
                data=file.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                super().do_GET()

        def do_POST(self) -> None:
            if urlparse(self.path).path!='/api/compile':
                self.send_error(404)
                return
            # Prevent a remote website from making the local machine compile.
            origin=self.headers.get('Origin')
            expected={f'http://127.0.0.1:{port}',f'http://localhost:{port}'}
            if origin and origin not in expected:
                self.json_response({'error':'Cross-origin compilation refused'},403)
                return
            if self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:
                self.json_response({'error':'Unexpected local host'},403)
                return
            if not gate.acquire(blocking=False):
                self.json_response({'error':'A compiler job is already running; wait for it to finish'},409)
                return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:
                    raise ValueError('JSON request must be 1–65536 bytes')
                data=json.loads(self.rfile.read(size))
                model_id=data.get('model_id','banknote-4x8x2')
                paths={f'banknote-4x{w}x2':root/f'models/banknote_4x{w}x2.json' for w in (4,8,12)}
                if model_id not in paths:
                    raise ValueError('Unknown packaged model')
                from .model import HardwareConfig,load_model
                from .compiler import compile_model
                cfg=HardwareConfig.from_dict(data.get('config',{}))
                model=load_model(paths[model_id])
                ident=uuid.uuid4().hex
                directory=root/'work/jobs'/ident
                jobs[ident]=directory
                manifest=compile_model(model,cfg,directory)
                result={'job_id':ident,'manifest':manifest,'artifact_base':f'/api/artifacts/{ident}/'}
                if data.get('verify',True) is not True:
                    raise ValueError('Local UI jobs require independent verification')
                from .verification import verify_model
                from .dataset import load_dataset
                from .reference import quantize_input
                values,_=load_dataset(root,'validation')
                result['verification']=verify_model(model,cfg,directory,[quantize_input(row,cfg) for row in values])
                if data.get('route',False):
                    from .toolchain import run_build
                    result['build']=run_build(model,cfg,directory,route=True)
                self.json_response(result)
            except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
                self.json_response({'error':str(exc)},400)
            finally:
                gate.release()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'SILICONPILOT local observatory: http://127.0.0.1:{port}/',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
