#!/usr/bin/python3 -I
"""Operator-only infrastructure build with bounded host resources and scrubbed logs."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sandbox import command,registration
from redaction import redact


def available():
    lines=Path('/proc/meminfo').read_text().splitlines()
    return int(next(x.split()[1] for x in lines if x.startswith('MemAvailable:')))*1024


def main():
    os.umask(0o077)
    state=Path('/opt/loginom-worker/state')
    result=state/'cli-build-result.json'
    if result.exists():raise RuntimeError('Prior build requires reconciliation')
    with open(state/'heavy.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        row=registration('infrastructure','developer')
        argv,env=command(row,['/usr/bin/bash','/opt/loginom-swarm/runtime/build-cli-candidate.sh',
             'f81ebded7333ae7d974fdc5f87e8864cf75dd9c7'],network=True)
        low=available(); disk=shutil.disk_usage('/opt').free
        if low<512*1024**2 or disk<20*1024**3:raise RuntimeError('Resource admission failed')
        p=subprocess.Popen(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        def consume():
            with open(state/'cli-build.log','w') as log:
                for raw in iter(p.stdout.readline,b''):
                    log.write(redact(raw.decode(errors='replace')));log.flush()
        t=threading.Thread(target=consume,daemon=True);t.start()
        started=time.monotonic();reason=None
        while p.poll() is None:
            low=min(low,available());disk=min(disk,shutil.disk_usage('/opt').free)
            if low<512*1024**2:reason='memory_below_512MiB'
            elif disk<20*1024**3:reason='disk_below_20GiB'
            elif time.monotonic()-started>1800:reason='build_timeout'
            if reason:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=30)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
                break
            time.sleep(1)
        t.join(timeout=5)
        outcome={'status':'pass' if p.returncode==0 and not reason else 'blocked',
                 'exitCode':p.returncode,'reason':reason,'minimumAvailableMiB':low//1024**2,
                 'minimumFreeGiB':disk//1024**3,'elapsedSeconds':round(time.monotonic()-started),
                 'nodeStarted':False}
        result.write_text(json.dumps(outcome)+'\n');print(json.dumps(outcome))


if __name__=='__main__':main()
