#!/usr/bin/env python3
"""Configure the closed Sampling graph; no stage entry or automation is invoked."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('api',ROOT/'swarm/scripts/paperclip-api.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
cfg=json.loads((ROOT/'swarm/config/campaign.json').read_text())
sequence=['setup','ready','admission','preparation','development','review','build','acceptance','publication','awaiting-human','done']
edges=list(zip(sequence,sequence[1:]))+[('review','development'),('acceptance','development')]
for stage in sequence[:-1]:
 edges.extend([(stage,'blocked'),(stage,'cancelled')])
# A blocked case requires explicit operator reconciliation; no automatic resume edge.
c=api.Client()
try:
 case=c.request('GET','/api/cases/'+cfg['caseId'])
 if case['stage']['key']!='setup' or case['case']['fields'].get('manualStart') or case.get('activeWork'):
  raise RuntimeError('Refusing to reconfigure an active or qualified case')
 path='/api/pipelines/'+cfg['pipelineId']
 pipeline=c.request('GET',path)
 for stage in pipeline['stages']:
  config=stage.get('config') or {}
  if config.get('onEnter') or config.get('automation'):
   raise RuntimeError('Unexpected automation; inspect before replacing configuration')
  next_config={**config,'disabled':stage['key'] not in {'setup','blocked','cancelled'},
               'disabledReason':'Swarm qualification incomplete; no node processing.'}
  if stage['key']=='review':
   next_config.update(requireApproval=True,approver={'kind':'agent','id':cfg['agentIds']['reviewer']})
  if next_config!=config:
   c.request('PATCH',path+'/stages/'+stage['id'],{'config':next_config})
 c.request('PUT',path+'/transitions',{'enforceTransitions':True,'transitions':[
   {'fromStageKey':a,'toStageKey':b} for a,b in edges]})
 verified=c.request('GET',path)
 assert len(verified['transitions'])==len(edges)
 assert all(s['config'].get('disabled') for s in verified['stages'] if s['key'] not in {'setup','blocked','cancelled'})
 print(json.dumps({'transitions':len(edges),'nodeProcessingEnabled':False,'caseStage':'setup'}))
finally:c.close()
