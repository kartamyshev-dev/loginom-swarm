# Server memory boundary — preparation

`gateway_policy.py` is a deny-by-default request policy for the server generation.
It fixes the canonical Loginom Peer, requires an operator-enrolled real Codex
thread, rejects foreign sessions, global searches, direct memory writes, and
acceptance-role access. Capture uses only the official session batch/commit API.
Tests cover scope traversal and write bypass attempts.

This module is **not yet a connected memory gateway**. No master credential has
been installed for model use. Pending work: authenticated transport under a
separate service UID, registered scoped credentials, immutable Linux hook runtime,
real SessionStart and completed bootstrap validation, trusted hook receipts,
separate capture cursors, extraction and read-back from the main Mac task.

Keep local generation 20260924.1 unchanged. Do not activate a registration using
an issue/case ID, a fabricated thread UUID, or a caller-supplied ready flag. The
server generation must also disable age-based lock takeover in the upstream
plugin: locks require reconciliation after unknown cleanup.

The API schema was read from the running OpenViking service on 2026-09-25. Search
must use list mode with an exact target URI. The service's default cross-Peer
search scope is overridden with actor scope. No route forwards arbitrary headers,
URLs, resource imports, remember, content writes, or extraction overrides.
