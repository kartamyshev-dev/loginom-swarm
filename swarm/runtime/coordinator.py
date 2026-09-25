"""Native-case infrastructure qualification. Does not authorize Sampling.

Case fields own the operation envelope; worker receipts own process facts. Every
mutation uses the current case/revision version. Unknown API outcomes propagate,
so a subsequent invocation reads authoritative state before doing more work.
"""
import hashlib
import json

ROLE_STAGES = {'developer': 'developer', 'reviewer': 'reviewer', 'acceptance': 'acceptance'}
NEXT = {'developer': 'reviewer', 'reviewer': 'acceptance', 'acceptance': 'done'}


class Coordinator:
    def __init__(self, api, worker, pipeline_id):
        self.api, self.worker, self.pipeline_id = api, worker, pipeline_id

    def tick(self, case_id):
        path = '/api/cases/' + case_id
        detail = self.api.request('GET', path)
        case, stage = detail['case'], detail['stage']['key']
        if case['pipelineId'] != self.pipeline_id or case['fields'].get('purpose') != 'infrastructure-protocol':
            raise ValueError('Coordinator is not qualified for node cases')
        if stage in {'done', 'blocked', 'cancelled'}:
            return {'caseId': case_id, 'stage': stage, 'nodeStarted': False}
        if stage not in ROLE_STAGES:
            raise ValueError('Unknown infrastructure stage')
        lease = self.api.request('POST', path + '/claim', {'leaseSeconds': 60})
        token = lease['leaseToken']
        # Claim can race another actor; always reload after it and compare the stage.
        try:
            detail = self.api.request('GET', path)
            case = detail['case']
            if detail['stage']['key'] != stage:
                raise ValueError('Stage changed during admission')
            fields = case['fields']
            operation = fields.get('activeOperation')
            if not operation or operation.get('role') != ROLE_STAGES[stage]:
                operation = {'caseId': case_id, 'caseVersion': case['version'],
                             'campaign': 'infrastructure', 'role': ROLE_STAGES[stage], 'operation': 'probe'}
                operation['requestKey'] = hashlib.sha256(json.dumps(operation, sort_keys=True).encode()).hexdigest()
                updated = self.api.request('PATCH', path, {
                    'expectedVersion': case['version'], 'leaseToken': token,
                    'fields': {**fields, 'activeOperation': operation}})
                case = updated.get('case', updated)
            # Never send arbitrary case fields as commands/paths/environment.
            required = {'caseId','caseVersion','campaign','role','operation','requestKey'}
            if (set(operation) != required or operation['caseId'] != case_id or
                operation['campaign'] != 'infrastructure' or operation['operation'] != 'probe' or
                operation['role'] != ROLE_STAGES[stage]):
                raise ValueError('Invalid stored operation binding')
            expected = hashlib.sha256(json.dumps({k:v for k,v in operation.items() if k!='requestKey'},sort_keys=True).encode()).hexdigest()
            if operation['requestKey'] != expected:
                raise ValueError('Operation identity changed')
            receipt = self.worker('POST', '/v1/jobs', operation)
            if receipt['request'] != operation:
                raise ValueError('Worker receipt belongs to another operation')
            if receipt['state'] in {'admitted','running','cancelling'}:
                return {'caseId':case_id,'stage':stage,'operation':receipt['requestKey'], 'state':receipt['state'],'nodeStarted':False}
            self.document(case_id, stage+'-receipt', receipt)
            target = NEXT[stage] if receipt['state']=='completed' and receipt['cleanupConfirmed'] else 'blocked'
            # No force transition, no fabricated evidence, no automatic recovery of a failed job.
            result = self.api.request('POST', path+'/transition', {
                'expectedVersion':case['version'],'leaseToken':token,'toStageKey':target,
                'reason':'Infrastructure probe '+receipt['state']})
            return {'caseId':case_id,'stage':target,'state':receipt['state'],'nodeStarted':False}
        finally:
            self.api.request('POST', path+'/release', {'leaseToken':token})

    def document(self, case_id, key, receipt):
        path = '/api/cases/'+case_id+'/documents/'+key
        body = json.dumps(receipt,sort_keys=True,indent=2)
        try:
            existing = self.api.request('GET',path)
        except RuntimeError as error:
            if 'HTTP 404' not in str(error):
                raise
            existing = None
        document = existing.get('document',existing) if existing else None
        if document and document.get('latestBody') == body:
            return
        payload = {'title':'Infrastructure execution receipt','format':'json','body':body}
        if document:
            payload['baseRevisionId'] = document['latestRevisionId']
        self.api.request('PUT',path,payload)
