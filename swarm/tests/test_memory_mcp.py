import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'memory'))
from mcp import tool_request,ROOT


class MCPTests(unittest.TestCase):
    def test_tool_scope_cannot_be_overridden(self):
        _,_,body=tool_request('find',{'query':'Sampling','limit':2})
        self.assertEqual(body['target_uri'],ROOT)
        for name,args in [('find',{'query':'x','target_uri':'viking://user/other'}),
                          ('find',{'query':'x','limit':True}),('remember',{'text':'x'}),
                          ('read',{'uri':ROOT+'/../other'}),('read',{'uri':'viking://user/other/memories'})]:
            with self.assertRaises(ValueError):tool_request(name,args)

    def test_stdio_handshake_notifications_and_tool_errors(self):
        script=Path(__file__).resolve().parents[1]/'memory/mcp.py'
        requests=[{'id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
                  {'method':'notifications/initialized'}, {'id':2,'method':'tools/list'},
                  {'id':3,'method':'tools/call','params':{'name':'remember','arguments':{}}},
                  {'id':4,'method':'unknown'}, {'id':5,'method':'ping','params':[]}]
        data='\n'.join(json.dumps({'jsonrpc':'2.0',**r}) for r in requests)+'\n'
        result=subprocess.run([sys.executable,'-I',str(script),'developer'],input=data,text=True,capture_output=True,check=True)
        responses=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r['id'] for r in responses],[1,2,3,4,5])
        self.assertEqual(responses[0]['result']['protocolVersion'],'2025-11-25')
        self.assertEqual({t['name'] for t in responses[1]['result']['tools']},{'find','read'})
        self.assertTrue(responses[2]['result']['isError'])
        self.assertEqual(responses[3]['error']['code'],-32601)
        self.assertEqual(responses[4]['error']['code'],-32602)
        self.assertEqual(result.stderr,'')
