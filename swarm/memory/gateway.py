"""Scoped OpenViking transport. The upstream credential never enters model homes.

Only root-enrolled principals can use the reviewed policy. Mutation receipts
stop ambiguous retries; a crash or network failure needs operator reconciliation.
"""
import hashlib
import http.server
import json
import os
from pathlib import Path
import threading
import urllib.error
import urllib.request

from gateway_policy import authorize, Denied, PEER

LIMIT = 2 * 1024 * 1024


class Uncertain(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Gateway:
    def __init__(self, config, state_dir, upstream=None):
        self.config = config
        self.state = Path(state_dir)
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.upstream = upstream or self._forward

    def _forward(self, method, target, body):
        cfg = self.config
        # Never forward caller headers, credentials, identity overrides or URLs.
        headers = {'Content-Type':'application/json','Authorization':'Bearer '+cfg['apiKey'],
                   'X-API-Key':cfg['apiKey'],'X-OpenViking-Actor-Peer':PEER}
        if cfg.get('account'):headers['X-OpenViking-Account']=cfg['account']
        if cfg.get('user'):headers['X-OpenViking-User']=cfg['user']
        request=urllib.request.Request(cfg['upstream']+target,method=method,headers=headers,
                    data=None if body is None else json.dumps(body).encode())
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=45) as response:
            raw=response.read(LIMIT+1)
            if len(raw)>LIMIT:raise ValueError('Oversized upstream response')
            return json.loads(raw)

    def _save(self, path, record):
        temp=path.with_suffix('.pending')
        with open(temp,'w',opener=lambda p,flags:os.open(p,flags,0o600)) as output:
            json.dump(record,output)
            output.flush();os.fsync(output.fileno())
        os.replace(temp,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def request(self, token, method, target, body):
        if not isinstance(token,str) or not 32<=len(token)<=256:raise Denied('Invalid principal')
        identity=hashlib.sha256(token.encode()).hexdigest()
        principal=self.config['principals'].get(identity)
        if not principal:raise Denied('Unknown principal')
        route,data=authorize(method,target,body,principal)
        if method=='GET' or not route.startswith('/api/v1/sessions/'):
            return self.upstream(method,route,data)
        # A single ordered mutation stream for each real registered thread.
        path=self.state/(principal['threadId']+'.json')
        offset=data.pop('swarm_capture_offset')
        operation=('batch:' if route.endswith('/messages/batch') else 'commit:')+str(offset)
        digest=hashlib.sha256(json.dumps([method,route,data],sort_keys=True).encode()).hexdigest()
        with self.lock:
            journal=json.loads(path.read_text()) if path.exists() else {'schema':2,'nextOffset':0,'entries':{}}
            if journal.get('schema')!=2:raise Uncertain('Legacy capture needs verified migration')
            if any(e['state']=='uncertain' for e in journal['entries'].values()):raise Uncertain('Capture needs reconciliation')
            previous=journal['entries'].get(operation)
            if previous:
                if previous['digest']!=digest:raise Uncertain('Capture offset already binds different content')
                return previous['result']
            if offset!=journal['nextOffset']:raise Uncertain('Capture offset differs from acknowledged cursor')
            journal['entries'][operation]={'state':'uncertain','digest':digest}
            self._save(path,journal)
            result=self.upstream(method,route,data)
            # Even an HTTP 200 may contain an application error: do not advance.
            if isinstance(result,dict) and result.get('status')=='error':raise Uncertain('Upstream mutation failed')
            journal['entries'][operation]={'state':'completed','digest':digest,'result':result}
            if operation.startswith('batch:'):journal['nextOffset']+=len(data['messages'])
            self._save(path,journal)
            return result


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*_):pass

    def send(self,status,body):
        data=json.dumps(body).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

    def handle_request(self):
        if self.command=='GET' and self.path=='/health':
            return self.send(200,{'status':'ok','scope':'loginom-ai-agent','schema':1,
                                  'activePrincipals':sum(p.get('status')=='active' for p in self.server.gateway.config['principals'].values())})
        try:
            self.connection.settimeout(10)
            auth=self.headers.get_all('Authorization',[])
            if len(auth)!=1 or not auth[0].startswith('Bearer '):raise Denied('Authentication required')
            token=auth[0][7:]
            alternative=self.headers.get_all('X-API-Key',[])
            if alternative and alternative!=[token]:raise Denied('Conflicting authentication')
            if self.headers.get('Transfer-Encoding'):raise Denied('Unsupported transfer')
            sizes=self.headers.get_all('Content-Length',[])
            if len(sizes)>1:raise Denied('Ambiguous size')
            size=int(sizes[0]) if sizes else 0
            if not 0<=size<=LIMIT:raise Denied('Invalid size')
            body=json.loads(self.rfile.read(size)) if size else None
            result=self.server.gateway.request(token,self.command,self.path,body)
            self.send(200,result)
        except Denied:self.send(403,{'status':'error','error':{'code':'scope_denied'}})
        except Uncertain:self.send(409,{'status':'error','error':{'code':'capture_reconciliation_required'}})
        except (ValueError,TypeError,KeyError):self.send(422,{'status':'error','error':{'code':'invalid_request'}})
        except (OSError,urllib.error.URLError):self.send(502,{'status':'error','error':{'code':'upstream_unavailable'}})

    do_GET=handle_request
    do_POST=handle_request


def main():
    path=Path('/etc/loginom-swarm/memory-gateway.json')
    info=path.lstat()
    if path.is_symlink() or info.st_uid!=0 or info.st_mode & 0o027:raise ValueError('Unprotected gateway configuration')
    cfg=json.loads(path.read_text())
    if cfg['upstream']!='https://ov.kartamyshev.dev':raise ValueError('Unexpected memory endpoint')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',8766),Handler)
    server.gateway=Gateway(cfg,'/var/lib/loginom-swarm-memory')
    server.serve_forever()


if __name__=='__main__':main()
