#!/usr/bin/env python3
"""Publish the reviewed infrastructure report into the existing native case.

This operator command does not transition a case, enable an agent or start work.
Document revisions are compared, so an uncertain write is reconciled by reading.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('api', ROOT / 'swarm/scripts/paperclip-api.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
config = json.loads((ROOT / 'swarm/config/campaign.json').read_text())
body = (ROOT / 'doc/loginom-swarm/CLI-INFRASTRUCTURE-2026-09-25.md').read_text()
client = api.Client()
try:
    case_path = '/api/cases/' + config['caseId']
    before = client.request('GET', case_path)
    if before['stage']['key'] != 'setup' or before['case']['fields'].get('manualStart'):
        raise RuntimeError('Case changed; inspect before publishing setup report')
    path = case_path + '/documents/infrastructure-qualification'
    try:
        found = client.request('GET', path)
    except RuntimeError as error:
        if 'HTTP 404' not in str(error):
            raise
        found = None
    document = found.get('document', found) if found else None
    if not document or document.get('latestBody') != body:
        payload = {'title': 'Проверка инфраструктуры Loginom — требуется разбор',
                   'format': 'markdown', 'body': body}
        if document:
            payload['baseRevisionId'] = document['latestRevisionId']
        client.request('PUT', path, payload)
    verified = client.request('GET', path)
    assert verified.get('document', verified)['latestBody'] == body
    after = client.request('GET', case_path)
    assert after['stage']['key'] == 'setup' and not after['case']['fields'].get('manualStart')
    print(json.dumps({'caseId': config['caseId'], 'reportReadback': True,
                      'stage': 'setup', 'nodeStarted': False}))
finally:
    client.close()
