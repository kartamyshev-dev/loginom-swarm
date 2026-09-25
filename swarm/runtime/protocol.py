"""Closed infrastructure protocol. Node operations require a later qualification."""
import re
import uuid
from sandbox import command, registration, PROBE

FIELDS = {'requestKey', 'caseId', 'caseVersion', 'campaign', 'role', 'operation'}


def resolve(request):
    if not isinstance(request, dict) or set(request) != FIELDS:
        raise ValueError('Unknown execution fields')
    if request['campaign'] != 'infrastructure' or request['operation'] not in {'probe', 'cancellation-probe'}:
        raise ValueError('Node execution is not qualified')
    if not isinstance(request['requestKey'], str) or not re.fullmatch('[a-f0-9]{64}', request['requestKey']):
        raise ValueError('Invalid request identity')
    if str(uuid.UUID(request['caseId'])) != request['caseId']:
        raise ValueError('Invalid Paperclip case identity')
    if type(request['caseVersion']) is not int or request['caseVersion'] < 1:
        raise ValueError('Invalid case version')
    row = registration('infrastructure', request['role'])
    payload = PROBE if request['operation'] == 'probe' else 'import time; time.sleep(20); ' + '\n' + PROBE
    return command(row, ['/usr/bin/python3', '-I', '-c', payload])
