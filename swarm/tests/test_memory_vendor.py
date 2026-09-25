import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]/'memory/vendor-plugin'


class VendorTests(unittest.TestCase):
    def test_manifest_matches_exact_deployed_sources(self):
        manifest=json.loads((ROOT/'provenance.json').read_text())
        self.assertEqual(set(manifest['deployedSha256']),set(manifest['originalSha256']))
        for name,digest in manifest['deployedSha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
            if digest!=manifest['originalSha256'][name]:self.assertIn(name,manifest['patches'])

    def test_capture_state_refuses_corruption_and_aged_lock_takeover(self):
        script='''
import {mkdtemp,writeFile,mkdir,utimes,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const dir=await mkdtemp(join(tmpdir(),'swarm-memory-test-'));
process.env.OPENVIKING_CODEX_STATE_DIR=dir;
const state=await import(process.argv[1]);
try{
 assert.equal((await state.loadState('new')).capturedTurnCount,0);
 await writeFile(join(dir,'broken.json'),'{broken');
 await assert.rejects(()=>state.loadState('broken'),/CAPTURE_STATE_REQUIRES_RECONCILIATION/);
 await mkdir(join(dir,'locked.lock'));
 await writeFile(join(dir,'locked.lock/owner'),'original-owner');
 await utimes(join(dir,'locked.lock/owner'),new Date(0),new Date(0));
 await assert.rejects(()=>state.withSessionLock('locked',()=>assert.fail('lock taken'),{staleMs:1}),/CAPTURE_LOCK_REQUIRES_RECONCILIATION/);
 assert.equal(await readFile(join(dir,'locked.lock/owner'),'utf8'),'original-owner');
}finally{await rm(dir,{recursive:true,force:true});}
'''
        subprocess.run(['node','--input-type=module','-e',script,(ROOT/'scripts/session-state.mjs').as_uri()],check=True)

    def test_empty_transcript_cannot_reset_or_hide_an_existing_cursor(self):
        script='''
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const dir=await mkdtemp(join(tmpdir(),'swarm-cursor-test-'));
const {catchUpTurns}=await import(process.argv[1]);
try{
 const transcript=join(dir,'rollout.jsonl');await writeFile(transcript,'');
 const state={capturedTurnCount:2};
 await assert.rejects(()=>catchUpTurns({state,transcriptPath:transcript,cfg:{},fetchJSONRes:()=>assert.fail('sent data')}),/CAPTURE_CURSOR_SHRINK_REQUIRES_RECONCILIATION/);
 assert.equal(state.capturedTurnCount,2);
}finally{await rm(dir,{recursive:true,force:true});}
'''
        subprocess.run(['node','--input-type=module','-e',script,(ROOT/'scripts/ov-session.mjs').as_uri()],check=True)
