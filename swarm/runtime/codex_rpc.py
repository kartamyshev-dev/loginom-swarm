"""Pinned Codex app-server transport. Persist only selected lifecycle metadata."""
import json
import queue
import subprocess
import threading
import time


class CodexRPC:
    def __init__(self, argv, env):
        self.process=subprocess.Popen(argv,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL,text=True,bufsize=1,start_new_session=True)
        self.responses=queue.Queue()
        self.events=[]
        self.sequence=0
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
        self.request('initialize',{'clientInfo':{'name':'loginom_swarm_enrollment','version':'20260925.1'},
                                  'capabilities':{'experimentalApi':True}})
        self.notify('initialized',{})

    def _read(self):
        try:
            for line in self.process.stdout:
                message=json.loads(line)
                if 'id' in message:
                    self.responses.put(message)
                else:
                    method=message.get('method','')
                    params=message.get('params',{})
                    if method in {'turn/completed','thread/started','thread/status/changed'} or method.startswith('hook/'):
                        # Hook output and model reasoning never enter the receipt.
                        safe={'method':method,'threadId':params.get('threadId'),'keys':list(params)}
                        if 'turn' in params:safe['turn']={k:params['turn'].get(k) for k in ['id','status']}
                        if 'status' in params:safe['status']=params['status']
                        for key in ['run','hook']:
                            if isinstance(params.get(key),dict):safe[key]={k:params[key].get(k) for k in ['id','eventName','status','sourcePath']}
                        self.events.append(safe)
        except (ValueError,OSError):pass

    def notify(self,method,params):
        self.process.stdin.write(json.dumps({'method':method,'params':params})+'\n');self.process.stdin.flush()

    def request(self,method,params,timeout=45):
        self.sequence+=1;identity=self.sequence
        self.process.stdin.write(json.dumps({'id':identity,'method':method,'params':params})+'\n');self.process.stdin.flush()
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:r=self.responses.get(timeout=min(1,max(.01,deadline-time.monotonic())))
            except queue.Empty:
                if self.process.poll() is not None:raise RuntimeError('Codex app-server exited')
                continue
            # No approval/tool request is silently granted by this observer.
            if r.get('id')!=identity or 'method' in r:raise RuntimeError('Unexpected app-server request; enrollment blocked')
            if 'error' in r:raise RuntimeError('Codex RPC failed: '+method+' code '+str(r['error'].get('code')))
            return r['result']
        raise TimeoutError('Codex RPC timeout: '+method)

    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
