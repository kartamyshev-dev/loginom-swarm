"""Deny-by-default HTTP policy between model hooks and OpenViking.

Bindings are operator records, not request input. No remember, resource import,
content write, arbitrary session, global directory, or cross-Peer search exists.
"""
import copy
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

PEER = '-Users-kartamyshev-Git-loginom-ai-agent'
ROOT = 'viking://user/kartamyshev/peers/' + PEER + '/memories'


class Denied(ValueError):
    pass


def memory_uri(value):
    if not isinstance(value,str) or '%' in value or '\\' in value or any(ord(c)<32 for c in value):
        raise Denied('Invalid memory URI')
    if value != ROOT and not value.startswith(ROOT + '/'):
        raise Denied('Foreign memory scope')
    suffix=value[len(ROOT):]
    if any(x in ('.','..','') for x in suffix[1:].split('/')) and suffix:
        raise Denied('Noncanonical memory URI')
    if '?' in value or '#' in value:
        raise Denied('Memory URI query or fragment')
    return value


def authorize(method,target,body,principal):
    if principal.get('role') not in {'developer','reviewer'} or principal.get('peer') != PEER:
        raise Denied('No development memory permission')
    if principal.get('status') != 'active':
        raise Denied('Enrollment has not passed')
    thread=principal.get('threadId','')
    if not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',thread):
        raise Denied('A real registered Codex thread is required')
    parts=urlsplit(target)
    if parts.scheme or parts.netloc or parts.fragment or '%' in parts.path or '//' in parts.path:
        raise Denied('Invalid gateway target')
    pairs=parse_qsl(parts.query,keep_blank_values=True)
    query=dict(pairs)
    if len(query)!=len(pairs):raise Denied('Duplicate query keys')
    path=parts.path
    data=copy.deepcopy(body)
    reads={'/api/v1/content/read','/api/v1/content/abstract','/api/v1/content/overview',
           '/api/v1/fs/ls','/api/v1/fs/stat','/api/v1/fs/tree'}
    if method=='GET' and path in reads:
        if body is not None or set(query)-{'uri','level','recursive','output','limit','depth'}:
            raise Denied('Unsupported read parameter')
        query['uri']=memory_uri(query.get('uri'))
        # Do not let unbounded traversal bypass result limits.
        for key in ('limit','depth','level'):
            if key in query and (not query[key].isdigit() or int(query[key])>100):
                raise Denied('Read limit exceeded')
        return path+'?'+urlencode(query),None
    if method!='POST' or query or not isinstance(data,dict):raise Denied('Unsupported operation')
    if path in {'/api/v1/search/find','/api/v1/search/search'}:
        allowed={'query','target_uri','limit','score_threshold','read_content','level','peer_scope',
                 'mode','session_id','context_type'}
        if set(data)-allowed or data.get('peer_scope','actor')!='actor' or data.get('mode','list')!='list':
            raise Denied('Unsupported search scope')
        data['target_uri']=memory_uri(data.get('target_uri',ROOT))
        if type(data.get('limit',5)) is not int or not 1<=data.get('limit',5)<=20:
            raise Denied('Search limit exceeded')
        if data.get('session_id') not in (None,'cx-'+thread):raise Denied('Foreign session')
        if path.endswith('/search'):data['peer_scope']='actor'
        else:data.pop('peer_scope',None)
        data['telemetry']=False
        return path,data
    base='/api/v1/sessions/cx-'+thread
    if path==base+'/messages/batch':
        if set(data)-{'messages','telemetry'} or not isinstance(data.get('messages'),list) or not 1<=len(data['messages'])<=100:
            raise Denied('Invalid capture batch')
        for message in data['messages']:
            if not isinstance(message,dict) or set(message)-{'role','content','parts','peer_id','created_at','turn_id','message_kind','source_message_ids'}:
                raise Denied('Unsupported capture fields')
            if message.get('role') not in {'user','assistant','tool'} or message.get('peer_id',PEER)!=PEER:
                raise Denied('Capture identity mismatch')
            if any(p.get('type') in {'reasoning','analysis'} for p in message.get('parts',[]) if isinstance(p,dict)):
                raise Denied('Reasoning capture is forbidden')
            message['peer_id']=PEER
        data['telemetry']=False
        return path,data
    if path==base+'/commit':
        allowed={'keep_recent_count','retention_mode','keep_recent_turn_count','retained_message_token_budget','min_raw_tail_steps','telemetry'}
        if set(data)-allowed:raise Denied('Unsupported commit override')
        data['telemetry']=False
        return path,data
    raise Denied('Operation is not in the memory allowlist')
