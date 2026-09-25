import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'memory'))
from gateway import Gateway,Uncertain
from gateway_policy import Denied,PEER,ROOT


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.token='scoped-fixture-token-'+'x'*32
        self.principal={'role':'developer','peer':PEER,'status':'active','threadId':'11111111-1111-4111-8111-111111111111'}
        self.cfg={'principals':{hashlib.sha256(self.token.encode()).hexdigest():self.principal}}
        self.calls=[]
        def send(method,path,body):
            self.calls.append([method,path,body]);return {'status':'ok','result':{'accepted':True}}
        self.gateway=Gateway(self.cfg,self.tmp.name,send)
        self.capture='/api/v1/sessions/cx-'+self.principal['threadId']+'/messages/batch'
        self.body={'swarm_capture_offset':0,'messages':[{'role':'assistant','content':'Verified infrastructure result'}]}

    def tearDown(self):self.tmp.cleanup()

    def test_foreign_scope_and_unenrolled_principal_never_reach_upstream(self):
        with self.assertRaises(Denied):self.gateway.request(self.token,'GET','/api/v1/content/read?uri=viking://user/other/memories',None)
        self.principal['status']='pending'
        with self.assertRaises(Denied):self.gateway.request(self.token,'GET','/api/v1/content/read?uri='+ROOT,None)
        self.assertEqual(self.calls,[])

    def test_capture_retry_is_cached_across_service_restart(self):
        first=self.gateway.request(self.token,'POST',self.capture,self.body)
        second=Gateway(self.cfg,self.tmp.name,self.gateway.upstream).request(self.token,'POST',self.capture,self.body)
        self.assertEqual(first,second);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][2]['messages'][0]['peer_id'],PEER)

    def test_lost_mutation_response_blocks_all_further_capture(self):
        def lost(*_):raise OSError('connection lost')
        self.gateway.upstream=lost
        with self.assertRaises(OSError):self.gateway.request(self.token,'POST',self.capture,self.body)
        restarted=Gateway(self.cfg,self.tmp.name,lambda *_:self.fail('Unknown mutation was retried'))
        with self.assertRaises(Uncertain):restarted.request(self.token,'POST',self.capture,self.body)
        with self.assertRaises(Uncertain):restarted.request(self.token,'POST',self.capture,{'swarm_capture_offset':0,'messages':[{'role':'user','content':'new'}]})

    def test_acceptance_and_unknown_tokens_rejected(self):
        for token in [self.token,'not-enrolled-token-'+'z'*32]:
            self.principal['role']='acceptance'
            with self.assertRaises(Denied):self.gateway.request(token,'GET','/api/v1/content/read?uri='+ROOT,None)
        self.assertEqual(self.calls,[])

    def test_own_session_inspection_is_uncached_and_foreign_session_is_denied(self):
        route='/api/v1/sessions/cx-'+self.principal['threadId']
        self.gateway.request(self.token,'GET',route,None)
        self.gateway.request(self.token,'GET',route,None)
        self.assertEqual(len(self.calls),2)
        self.assertEqual(list(Path(self.tmp.name).iterdir()),[])
        with self.assertRaises(Denied):
            self.gateway.request(self.token,'GET',route.replace('11111111','22222222'),None)

    def test_equal_text_in_later_turn_is_new_and_old_retry_stays_deduplicated(self):
        self.gateway.request(self.token,'POST',self.capture,self.body)
        self.gateway.request(self.token,'POST',self.capture,{**self.body,'swarm_capture_offset':1})
        self.gateway.request(self.token,'POST',self.capture,self.body)
        self.assertEqual(len(self.calls),2)
        self.assertNotIn('swarm_capture_offset',self.calls[0][2])
        with self.assertRaises(Uncertain):
            self.gateway.request(self.token,'POST',self.capture,{**self.body,'messages':[{'role':'assistant','content':'different'}]})
        with self.assertRaises(Uncertain):
            self.gateway.request(self.token,'POST',self.capture,{**self.body,'swarm_capture_offset':99})

    def test_commit_retry_after_new_capture_does_not_repeat_extraction(self):
        self.gateway.request(self.token,'POST',self.capture,self.body)
        commit=self.capture.replace('/messages/batch','/commit')
        self.gateway.request(self.token,'POST',commit,{'swarm_capture_offset':1})
        self.gateway.request(self.token,'POST',self.capture,{**self.body,'swarm_capture_offset':1})
        self.gateway.request(self.token,'POST',commit,{'swarm_capture_offset':1})
        self.assertEqual(len(self.calls),3)


if __name__=='__main__':unittest.main()
