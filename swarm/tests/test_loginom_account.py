import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from loginom_account import AccountBlocked, AccountLease


class AccountTests(unittest.TestCase):
    def test_successful_process_exit_does_not_release_remote_barrier(self):
        with tempfile.TemporaryDirectory() as directory:
            first = AccountLease(directory, 'first')
            first.close()
            with self.assertRaises(AccountBlocked):
                AccountLease(directory, 'second')
            record = json.loads((Path(directory) / 'loginom-account.json').read_text())
            self.assertEqual(record['attempt'], 'first')
            self.assertFalse(record['cleanupConfirmed'])

    def test_crashed_owner_stays_blocked_after_flock_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            first = AccountLease(directory, 'first')
            first.lock.close()  # Simulate abrupt termination before any final receipt.
            with self.assertRaises(AccountBlocked):
                AccountLease(directory, 'second')

    def test_live_owner_excludes_another_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            first = AccountLease(directory, 'first')
            try:
                with self.assertRaises(BlockingIOError):
                    AccountLease(directory, 'second')
            finally:
                first.close()

    def test_corrupted_journal_never_grants_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'loginom-account.json').write_text('{')
            with self.assertRaises(ValueError):
                AccountLease(directory, 'second')

    def test_status_label_without_reconciliation_proof_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'loginom-account.json').write_text(json.dumps({
                'schema': 1, 'state': 'reconciled', 'cleanupConfirmed': True}))
            with self.assertRaises(AccountBlocked):
                AccountLease(directory, 'second')
