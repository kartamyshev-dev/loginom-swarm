#!/usr/bin/env python3
"""Run on the host as operator; no node/model work or mutable shell endpoint."""
import http.client
import json
import socket


class Connection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost', timeout=45)
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/run/loginom-swarm/control.sock')


def request(method, path, body=None):
    conn=Connection()
    try:
        conn.request(method,path,json.dumps(body) if body is not None else None,
                     {'Content-Type':'application/json'})
        r=conn.getresponse()
        return r.status,json.loads(r.read())
    finally:
        conn.close()


def main():
    status, health=request('GET','/health')
    assert status == 200 and health['processingEnabled'] is False
    results={}
    for role in ['developer','reviewer','acceptance']:
        status, result=request('POST','/v1/probe',{'campaign':'infrastructure','role':role})
        assert status == 200 and len(result['checks']) == 11 and all(result['checks'].values()), result
        results[role]=result['checks']
    # The model/client must never supply a command, inherited env, mounts, or path.
    for body in [
        {'campaign':'infrastructure','role':'developer','command':['/bin/sh']},
        {'campaign':'../sampling','role':'developer'},
        {'campaign':'sampling','role':'developer'},
        {'campaign':'infrastructure','role':'root'},
        {'campaign':'infrastructure','role':'reviewer','environment':{'BASH_ENV':'/tmp/evil'}},
    ]:
        status,_=request('POST','/v1/probe',body)
        assert status == 422
    status,_=request('POST','/v1/run',{'campaign':'sampling'})
    assert status == 409
    print(json.dumps({'status':'pass','checks':results,'negativeRequests':6,'nodeStarted':False}))


if __name__ == '__main__': main()
