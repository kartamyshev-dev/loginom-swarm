import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'memory'))
from gateway_policy import authorize,Denied,ROOT,PEER

class GatewayTests(unittest.TestCase):
    def principal(self):
        return {'role':'developer','peer':PEER,'status':'active','threadId':'12345678-1234-1234-1234-123456789abc'}

    def test_search_scope_is_fixed_and_global_context_mode_is_denied(self):
        _,body=authorize('POST','/api/v1/search/search',{'query':'sampling'},self.principal())
        self.assertEqual(body['target_uri'],ROOT)
        self.assertEqual(body['peer_scope'],'actor')
        for change in [{'target_uri':'viking://user'},{'mode':'context'},{'peer_scope':'all'},{'filter':{}},{'session_id':'cx-foreign'}]:
            with self.assertRaises(Denied):authorize('POST','/api/v1/search/search',{'query':'x',**change},self.principal())

    def test_uri_traversal_and_ambiguous_queries_rejected(self):
        from urllib.parse import urlencode
        for uri in [ROOT+'/../other',ROOT+'//x',ROOT+'/%2e%2e/x',ROOT+'/x?scope=all',ROOT+'evil']:
            with self.assertRaises(Denied):authorize('GET','/api/v1/content/read?'+urlencode({'uri':uri}),None,self.principal())
        with self.assertRaises(Denied):authorize('GET','/api/v1/content/read?uri=x&uri=y',None,self.principal())

    def test_only_enrolled_development_threads_access_memory(self):
        for change in [{'role':'acceptance'},{'status':'pending'},{'threadId':'paperclip-issue-id'},{'peer':'foreign'}]:
            with self.assertRaises(Denied):authorize('POST','/api/v1/search/find',{'query':'x'},{**self.principal(),**change})

    def test_capture_forces_exact_peer_and_session(self):
        url='/api/v1/sessions/cx-'+self.principal()['threadId']+'/messages/batch'
        _,body=authorize('POST',url,{'messages':[{'role':'assistant','content':'verified result'}]},self.principal())
        self.assertEqual(body['messages'][0]['peer_id'],PEER)
        for bad in [{'peer_id':'foreign'},{'parts':[{'type':'reasoning','text':'hidden'}]}]:
            with self.assertRaises(Denied):authorize('POST',url,{'messages':[{'role':'assistant',**bad}]},self.principal())
        with self.assertRaises(Denied):authorize('POST',url.replace('cx-','other-'),{'messages':[]},self.principal())

    def test_direct_writes_and_commit_scope_overrides_are_denied(self):
        for url in ['/api/v1/content/write','/api/v1/fs/mkdir','/api/v1/resources','/api/v1/memories/remember']:
            with self.assertRaises(Denied):authorize('POST',url,{},self.principal())
        with self.assertRaises(Denied):authorize('POST','/api/v1/sessions/cx-'+self.principal()['threadId']+'/commit',{'extraction_metadata':{'peer':'global'}},self.principal())
