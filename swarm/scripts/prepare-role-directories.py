#!/usr/bin/python3
"""Operator migration of existing server OAuth profiles; never copies Mac tokens."""
import json
import os
from pathlib import Path
import pwd
import subprocess

BASE=Path('/opt/loginom-worker')
SHA='f81ebded7333ae7d974fdc5f87e8864cf75dd9c7'


def main():
    assert os.getuid()==0
    user=pwd.getpwnam('loginom-worker')
    config=Path('/etc/loginom-swarm/roles.json')
    rows=json.loads(config.read_text())
    for role in ['developer','reviewer','acceptance']:
        profile=BASE/'profiles/sampling'/role
        workspace=BASE/'workspaces/sampling'/role
        for parent in [profile.parent,workspace.parent]:
            parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            os.chown(parent,user.pw_uid,user.pw_gid)
        old=BASE/'profiles'/role
        if not profile.exists():
            assert old.is_dir()
            old.rename(profile)
        elif old.exists():
            raise RuntimeError('Both old and new profile exist; reconcile before retry')
        if not workspace.exists():
            if role=='acceptance':
                workspace.mkdir(mode=0o700);os.chown(workspace,user.pw_uid,user.pw_gid)
            else:
                subprocess.run(['runuser','-u','loginom-worker','--','git','clone','--no-hardlinks','--no-checkout',str(BASE/'repo'),str(workspace)],check=True)
                subprocess.run(['runuser','-u','loginom-worker','--','git','-C',str(workspace),'checkout','--detach',SHA],check=True)
        if role!='acceptance':
            for key,value in [('user.name','kartamyshev-dev'),('user.email','97161574+kartamyshev-dev@users.noreply.github.com')]:
                subprocess.run(['runuser','-u','loginom-worker','--','git','-C',str(workspace),'config','--local',key,value],check=True)
            subprocess.run(['runuser','-u','loginom-worker','--','git','-C',str(workspace),'remote','set-url','origin','https://github.com/gooddaytoday/loginom-ai-agent.git'],check=True)
            gitdir=subprocess.check_output(['runuser','-u','loginom-worker','--','git','-C',str(workspace),'rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip()
            assert gitdir==str(workspace/'.git') and (workspace/'.git').is_dir()
        row={'campaign':'sampling','role':role,'workspace':str(workspace),'profile':str(profile)}
        matches=[r for r in rows if r['campaign']=='sampling' and r['role']==role]
        if matches:
            assert matches==[row]
        else:rows.append(row)
    tmp=config.with_suffix('.prepare')
    with tmp.open('x') as f:json.dump(rows,f,indent=2);f.write('\n')
    tmp.chmod(0o644);tmp.replace(config)
    print(json.dumps({'roleDirectories':'registered','profiles':'moved-on-server','nodeStarted':False}))


if __name__=='__main__':main()
