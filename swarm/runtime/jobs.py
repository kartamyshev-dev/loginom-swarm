"""Durable execution receipts, not a campaign queue. Paperclip owns stage/order.

Only the trusted worker constructs commands. Receipt admission precedes any side
 effect; after an interrupted process the operator must reconcile cleanup. No TTL
 can release that barrier. Every record is fsynced and outside model mounts.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

ACTIVE = {'admitted', 'running', 'cancelling'}
KEY = re.compile(r'^[a-f0-9]{64}$')


class Conflict(ValueError):
    pass


class Jobs:
    def __init__(self, directory, heavy_lock, execute, timeout=30):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.heavy_lock = Path(heavy_lock)
        self.execute = execute
        self.timeout = timeout
        self.mutex = threading.RLock()
        self.processes = {}
        self.threads = []
        # A receipt left active by a previous worker is NOT permission to rerun.
        for path in self.directory.glob('*.json'):
            record = json.loads(path.read_text())
            if record['state'] in ACTIVE:
                record.update(state='blocked', reason='worker_interrupted', cleanupConfirmed=False)
                self._save(record)

    def _path(self, key):
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ValueError('Invalid request key')
        return self.directory / (key + '.json')

    def _save(self, record):
        record['version'] = record.get('version', 0) + 1
        path = self._path(record['requestKey'])
        tmp = path.with_suffix('.pending')
        with open(tmp, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
            json.dump(record, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
        fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def get(self, key):
        with self.mutex:
            return json.loads(self._path(key).read_text())

    def submit(self, request):
        key = request['requestKey']
        path = self._path(key)
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with self.mutex:
            if path.exists():
                record = self.get(key)
                if record['requestSha256'] != digest:
                    raise Conflict('Request key already binds another operation')
                return record
            for receipt in self.directory.glob('*.json'):
                record = json.loads(receipt.read_text())
                if record['state'] in ACTIVE or record.get('cleanupConfirmed') is not True:
                    raise Conflict('Previous execution or unknown cleanup blocks admission')
            # No shell or caller-chosen executable: operator resolver validates first.
            argv, env = self.execute(request)
            lock = open(self.heavy_lock, 'a')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                raise Conflict('Heavy stage is already active') from None
            record = {'schema': 1, 'requestKey': key, 'requestSha256': digest,
                      'request': request, 'state': 'admitted', 'cleanupConfirmed': False,
                      'version': 0, 'createdAt': time.time()}
            try:
                self._save(record)
                thread = threading.Thread(target=self._run, args=(key, argv, env, lock), daemon=True)
                self.threads.append(thread)
                thread.start()
            except BaseException:
                lock.close()
                raise
            return record

    def cancel(self, key, version):
        if type(version) is not int:
            raise ValueError('Expected receipt version required')
        with self.mutex:
            record = self.get(key)
            if record['state'] not in ACTIVE or record['state'] == 'cancelling':
                return record
            if record['version'] != version:
                raise Conflict('Receipt version changed')
            record.update(state='cancelling', reason='cancel_requested')
            self._save(record)
            process = self.processes.get(key)
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            return record

    def _run(self, key, argv, env, lock):
        started = time.monotonic()
        process = None
        output = None
        reason = None
        try:
            with self.mutex:
                record = self.get(key)
                if record['state'] == 'cancelling':
                    record.update(state='cancelled', cleanupConfirmed=True)
                    self._save(record)
                    return
                # Child output uses a private file to avoid unbounded memory and pipes.
                # This protocol only runs fixed probes emitting a bounded boolean map.
                import tempfile
                output = tempfile.TemporaryFile()
                process = subprocess.Popen(argv, env=env, stdout=output, stderr=subprocess.DEVNULL,
                                           start_new_session=True, close_fds=True)
                self.processes[key] = process
                record.update(state='running', pid=process.pid)
                self._save(record)
            cancelled_at = None
            while process.poll() is None:
                record = self.get(key)
                if record['state'] == 'cancelling':
                    reason = 'cancel_requested'
                    cancelled_at = cancelled_at or time.monotonic()
                elif time.monotonic() - started >= self.timeout:
                    reason = 'timeout'
                    cancelled_at = cancelled_at or time.monotonic()
                if cancelled_at is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL if time.monotonic() - cancelled_at > 2 else signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                time.sleep(0.02)
            process.wait()
            # Do not call cleanup successful while any descendant remains in its group.
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                clean = True
            else:
                clean = False
                os.killpg(process.pid, signal.SIGKILL)
            output.seek(0)
            raw = output.read(65537)
            output.close()
            checks = None
            if not reason and process.returncode == 0 and len(raw) <= 65536:
                try:
                    checks = json.loads(raw)
                except ValueError:
                    pass
            valid = isinstance(checks, dict) and bool(checks) and all(type(v) is bool for v in checks.values())
            with self.mutex:
                record = self.get(key)
                if record['state'] == 'cancelling':
                    reason = 'cancel_requested'
                state = ('blocked' if not clean else 'cancelled' if reason == 'cancel_requested'
                         else 'completed' if not reason and valid and all(checks.values()) else 'failed')
                record.update(state=state, reason=reason or (None if state == 'completed' else 'probe_failed'),
                              cleanupConfirmed=clean, elapsedSeconds=round(time.monotonic() - started, 3),
                              exitCode=process.returncode, checks=checks if valid else None)
                self._save(record)
        except Exception:
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
            with self.mutex:
                record = self.get(key)
                record.update(state='blocked', reason='executor_error', cleanupConfirmed=False)
                self._save(record)
        finally:
            if output is not None:
                output.close()
            with self.mutex:
                self.processes.pop(key, None)
            lock.close()

    def join(self, timeout=10):
        for thread in self.threads:
            thread.join(timeout)
