import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from jobs import Jobs, Conflict


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.request = {'requestKey': 'a'*64, 'caseId': 'test-case', 'operation': 'fixture'}
        self.effect = self.root/'effects'
        self.manager = None

    def tearDown(self):
        if self.manager:
            self.manager.join()
        self.tmp.cleanup()

    def start(self, script, timeout=3):
        self.manager = Jobs(self.root/'jobs', self.root/'heavy.lock',
                            lambda _: ([sys.executable, '-c', script], {}), timeout=timeout)
        return self.manager

    def wait(self, key='a'*64):
        until = time.monotonic()+8
        while time.monotonic()<until:
            record = self.manager.get(key)
            if record['state'] not in {'admitted','running','cancelling'}:
                return record
            time.sleep(.02)
        self.fail('Operation never completed')

    def test_retry_executes_once_and_survives_worker_recreation(self):
        script = f"from pathlib import Path; Path({str(self.effect)!r}).open('a').write('effect\\n'); print('{{\"checked\":true}}')"
        m = self.start(script)
        first = m.submit(self.request)
        m.submit(self.request)
        done = self.wait()
        self.assertEqual(done['state'], 'completed')
        self.assertTrue(done['cleanupConfirmed'])
        m.join()
        m = self.start(script)
        self.assertEqual(m.submit(self.request), done)
        self.assertEqual(self.effect.read_text(), 'effect\n')
        self.assertLess(first['version'], done['version'])

    def test_conflicting_retry_does_not_execute(self):
        m = self.start("print('{\"ok\":true}')")
        m.submit(self.request)
        with self.assertRaises(Conflict):
            m.submit({**self.request,'operation':'different'})
        self.wait()

    def test_concurrent_stage_refused_and_cancel_kills_ignoring_process(self):
        m = self.start("import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)")
        m.submit(self.request)
        until=time.monotonic()+2
        while m.get('a'*64)['state'] != 'running' and time.monotonic()<until:
            time.sleep(.01)
        time.sleep(.1)
        with self.assertRaises(Conflict):
            m.submit({**self.request,'requestKey':'b'*64})
        record = m.get('a'*64)
        with self.assertRaises(Conflict):
            m.cancel('a'*64, record['version']-1)
        m.cancel('a'*64, record['version'])
        done=self.wait()
        self.assertEqual(done['state'],'cancelled')
        self.assertTrue(done['cleanupConfirmed'])
        self.assertEqual(m.cancel('a'*64,record['version']),done)
        with self.assertRaises(ProcessLookupError):
            import os
            os.kill(done['pid'],0)

    def test_interrupted_receipt_blocks_retry_and_other_stages(self):
        m=self.start("print('{\"ok\":true}')")
        # Durable admitted receipt models a crash before any completion is committed.
        digest=hashlib.sha256(json.dumps(self.request,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        m._save({'requestKey':'a'*64,'requestSha256':digest,'request':self.request,'state':'running','cleanupConfirmed':False})
        m=self.start("print('{\"ok\":true}')")
        self.assertEqual(m.submit(self.request)['state'],'blocked')
        with self.assertRaises(Conflict):
            m.submit({**self.request,'requestKey':'b'*64})

    def test_timeout_and_invalid_output_never_pass(self):
        m=self.start('import time;time.sleep(10)',timeout=.1)
        m.submit(self.request)
        self.assertEqual(self.wait()['reason'],'timeout')
        m.join()
        m=self.start("print('{\"ok\":\"true\"}')")
        m.submit({**self.request,'requestKey':'b'*64})
        self.assertEqual(self.wait('b'*64)['state'],'failed')

    def test_host_lock_blocks_new_admission_without_receipt(self):
        import fcntl
        m=self.start("print('{\"ok\":true}')")
        with open(self.root/'heavy.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(Conflict):
                m.submit(self.request)
        self.assertFalse((self.root/'jobs'/('a'*64+'.json')).exists())


if __name__ == '__main__':
    unittest.main()
