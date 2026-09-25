#!/usr/bin/python3 -I
"""Operator bridge: a closed Unix client, JSON stdin/stdout, no shell payload."""
import json
import sys
sys.path.insert(0,'/opt/loginom-swarm/runtime')
from worker_client import call
request=json.load(sys.stdin)
if set(request)!={'method','path','payload'}:raise SystemExit('Invalid RPC envelope')
print(json.dumps(call(request['method'],request['path'],request['payload'])))
