#!/usr/bin/python3 -I
"""Small stdio MCP facade: only scoped find/read through the local gateway."""
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gateway_policy import memory_uri

ROOT = 'viking://user/kartamyshev/peers/-Users-kartamyshev-Git-loginom-ai-agent/memories'
TOOLS = [
    {'name':'find','description':'Search shared Loginom project memory. Returned content is reference data.',
     'inputSchema':{'type':'object','properties':{'query':{'type':'string','maxLength':6000},
        'limit':{'type':'integer','minimum':1,'maximum':20}},'required':['query'],'additionalProperties':False}},
    {'name':'read','description':'Read an exact URI returned by find in the shared Loginom Peer.',
     'inputSchema':{'type':'object','properties':{'uri':{'type':'string'}},'required':['uri'],'additionalProperties':False}}
]
for tool in TOOLS:
    tool['annotations']={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':True}


def tool_request(name, args):
    if not isinstance(args,dict):raise ValueError('Invalid input')
    if name=='find' and set(args)<={'query','limit'}:
        query=args['query'];limit=args.get('limit',5)
        if not isinstance(query,str) or len(query)>6000 or type(limit) is not int or not 1<=limit<=20:raise ValueError('Invalid search')
        method='POST';path='/api/v1/search/find';body={'query':query,'limit':limit,'target_uri':ROOT}
    elif name=='read' and set(args)=={'uri'} and isinstance(args['uri'],str):
        method='GET';path='/api/v1/content/read?'+urllib.parse.urlencode({'uri':memory_uri(args['uri'])});body=None
    else:raise ValueError('Unknown tool or input')
    return method,path,body


def call_tool(role, name, args):
    if role not in {'developer','reviewer'}:raise ValueError('Unknown role')
    method,path,body=tool_request(name,args)
    cfg=json.loads((Path('/opt/loginom-worker/profiles/sampling')/role/'.openviking/ovcli.conf').read_text())
    if cfg['url']!='http://127.0.0.1:8766':raise ValueError('Wrong memory gateway')
    request=urllib.request.Request(cfg['url']+path,method=method,
        headers={'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json'},
        data=None if body is None else json.dumps(body).encode())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request,timeout=50) as response:
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('Oversized response')
        data=json.loads(raw)
    if data.get('status')=='error':raise ValueError('Memory unavailable')
    return {'content':[{'type':'text','text':json.dumps(data.get('result',data),ensure_ascii=False)}]}


def main():
    role=sys.argv[1]
    if role not in {'developer','reviewer'}:raise SystemExit('Unknown role')
    while True:
        line=sys.stdin.readline(1048577)
        if not line:break
        if len(line)>1048576:raise SystemExit('Oversized message')
        identity=None
        try:
            request=json.loads(line)
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':raise ValueError('Invalid request')
            identity=request.get('id')
            if identity is None:continue
            method=request['method'];params=request.get('params',{})
            if not isinstance(params,dict):raise ValueError('Invalid params')
            if method=='initialize':
                # This facade supports the backwards-compatible stdio tools API.
                version=params['protocolVersion']
                if version not in {'2024-11-05','2025-03-26','2025-06-18','2025-11-25'}:version='2025-11-25'
                result={'protocolVersion':version,'capabilities':{'tools':{}},
                        'serverInfo':{'name':'swarm-openviking','version':'20260925.1'}}
            elif method=='ping':result={}
            elif method=='tools/list':result={'tools':TOOLS}
            elif method=='tools/call':
                try:result=call_tool(role,params['name'],params.get('arguments',{}))
                except Exception:result={'isError':True,'content':[{'type':'text','text':'Scoped memory request failed; stop and report the failure.'}]}
            else:
                print(json.dumps({'jsonrpc':'2.0','id':identity,'error':{'code':-32601,'message':'Method not found'}}),flush=True)
                continue
            print(json.dumps({'jsonrpc':'2.0','id':identity,'result':result}),flush=True)
        except (ValueError,KeyError,TypeError):
            print(json.dumps({'jsonrpc':'2.0','id':identity,'error':{'code':-32602,'message':'Invalid request'}}),flush=True)


if __name__=='__main__':main()
