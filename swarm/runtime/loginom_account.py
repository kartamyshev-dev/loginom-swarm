"""Durable barrier for the shared Loginom account, separate from OS process locks.

A dead process releases flock, but says nothing about a remote upload or package.
Only an operator reconciliation can release this journal; time never releases it.
The journal and receipts live outside all model mounts.
"""
import fcntl
import json
import os
from pathlib import Path
import re


class AccountBlocked(RuntimeError):
    pass


class AccountLease:
    def __init__(self, directory, attempt):
        self.directory = Path(directory)
        self.path = self.directory / 'loginom-account.json'
        self.lock = (self.directory / 'loginom-agent.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists():
                previous = json.loads(self.path.read_text())
                if (previous.get('schema') != 1 or previous.get('state') != 'reconciled'
                        or previous.get('remoteEffectsKnown') is not True
                        or previous.get('cleanupConfirmed') is not True
                        or not re.fullmatch('[a-f0-9]{64}', previous.get('reconciliationSha256', ''))):
                    raise AccountBlocked('Previous Loginom effects require operator reconciliation')
            self.record = {'schema': 1, 'attempt': attempt, 'state': 'admitted',
                           'remoteEffectsKnown': False, 'cleanupConfirmed': False}
            self.save()
        except BaseException:
            self.lock.close()
            raise

    def save(self):
        temporary = self.path.with_suffix('.pending')
        with open(temporary, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
            json.dump(self.record, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)
        directory = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def close(self):
        # A successful CLI exit still needs independent output and cleanup proof.
        self.record['state'] = 'awaiting-reconciliation'
        try:
            self.save()
        finally:
            self.lock.close()
