"""Control-plane-only client. No model/environment data crosses the Unix socket."""
import http.client
import json
import socket


class WorkerConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost',timeout=45)
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/run/loginom-swarm/control.sock')


def call(method,path,payload=None):
    if (method,path) not in {('GET','/health'),('POST','/v1/probe')}:
        raise ValueError('Node execution is not qualified')
    c=WorkerConnection()
    try:
        c.request(method,path,json.dumps(payload) if payload is not None else None,
                  {'Content-Type':'application/json'})
        response=c.getresponse()
        result=json.loads(response.read(65536))
        if response.status!=200:raise RuntimeError('Worker rejected request')
        return result
    finally:c.close()
