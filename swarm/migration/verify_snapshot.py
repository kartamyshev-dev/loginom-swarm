#!/usr/bin/env python3
"""Verify private snapshot; optionally restore into a NEW empty staging directory.
Never extracts to / or starts services. Preserve original IDs until verification;
optional remap applies only outside opt/paperclip (container ownership preserved).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile
from snapshot import digest, metadata

ARTIFACTS = {'database.dump', 'database.roles.sql', 'database.rows.sha256', 'filesystem.tar.gz'}

def safe_name(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\x00' in name or str(p) != name:
        raise ValueError('Unsafe archive path')
    return name

def validate_bundle(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('complete') is not True or manifest.get('noRestart') is not True:
        raise ValueError('Incomplete/unsupported snapshot')
    if set(manifest.get('artifacts', {})) != ARTIFACTS:
        raise ValueError('Incomplete artifact set')
    for name, expected in manifest['artifacts'].items():
        if not (bundle / name).is_file() or (bundle / name).is_symlink() or digest(bundle / name) != expected:
            raise ValueError('Artifact hash mismatch: ' + name)
    rows = {}
    for row in manifest['files']:
        name = safe_name(row['path'])
        if name in rows or row['kind'] not in ('file', 'directory', 'symlink'):
            raise ValueError('Invalid/duplicate manifest member')
        rows[name] = row
    seen = set()
    with tarfile.open(bundle / 'filesystem.tar.gz', 'r:gz') as archive:
        for item in archive:
            name = safe_name(item.name.rstrip('/') if item.isdir() else item.name)
            if name in seen or name not in rows: raise ValueError('Duplicate/unlisted tar member')
            seen.add(name)
            row = rows[name]
            kind = 'directory' if item.isdir() else 'file' if item.isfile() else 'symlink' if item.issym() else None
            if kind != row['kind']: raise ValueError('Tar member type mismatch')
            if item.uid != row['uid'] or item.gid != row['gid'] or item.mode != row['mode']:
                raise ValueError('Tar member metadata mismatch')
            if kind == 'symlink' and item.linkname != row['target']: raise ValueError('Symlink target mismatch')
            for parent in PurePosixPath(name).parents:
                if str(parent) in rows and rows[str(parent)]['kind'] != 'directory':
                    raise ValueError('Extraction through non-directory ancestor')
            if kind == 'file':
                if item.size != row['size']: raise ValueError('File size mismatch')
                h = hashlib.sha256()
                with archive.extractfile(item) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
                if h.hexdigest() != row.get('sha256'): raise ValueError('Archived file hash mismatch')
    if seen != set(rows): raise ValueError('Missing tar members')
    return manifest

def verify_tree(root, manifest, remapped=False):
    for row in manifest['files']:
        name = safe_name(row['path'])
        path = root / name
        # Do not follow archived symlink ancestors, including pre-existing paths.
        for parent in path.parents:
            if parent == root: break
            if parent.is_symlink(): raise ValueError('Symlink extraction ancestor')
        actual = metadata(path, name)
        expected = dict(row)
        if remapped and not name.startswith('opt/paperclip/'):
            expected['uid'] = {1000: 21001, 999: 21002, 997: 21003}.get(row['uid'], row['uid'])
            expected['gid'] = {1000: 21001, 987: 21002, 986: 21003}.get(row['gid'], row['gid'])
        for field in ('kind', 'mode', 'uid', 'gid', 'sha256', 'size', 'target', 'xattrs'):
            if actual.get(field) != expected.get(field): raise ValueError('Restored metadata/hash mismatch: ' + name + ' (' + field + ')')

def remap_plan(manifest):
    """Validate the entire remap before filesystem mutations, including mkdir."""
    changes = []
    for row in manifest['files']:
        if row['path'].startswith('opt/paperclip/'): continue
        attrs = row.get('xattrs', {})
        # Named ACL identities need translation independently of file ownership.
        if any(k.startswith('system.posix_acl') for k in attrs):
            raise ValueError('Named POSIX ACL requires explicit reviewed identity translation before remap')
        uid = {1000: 21001, 999: 21002, 997: 21003}.get(row['uid'], row['uid'])
        gid = {1000: 21001, 987: 21002, 986: 21003}.get(row['gid'], row['gid'])
        if (uid, gid) == (row['uid'], row['gid']): continue
        # Linux chown strips file capabilities, including some no-op chowns.
        if 'security.capability' in attrs:
            raise ValueError('Capability-bearing file requires explicit reviewed translation before remap')
        changes.append((row, uid, gid))
    return changes


def apply_remap(destination, changes):
    for row, uid, gid in changes:
        path = destination / row['path']
        os.chown(path, uid, gid, follow_symlinks=False)
        if row['kind'] != 'symlink': os.chmod(path, row['mode'])


def extract(bundle, destination, manifest, remap=False):
    if os.geteuid() != 0: raise ValueError('Extraction with ownership requires root')
    destination = destination.absolute()
    if destination == Path('/') or destination.exists() or destination.is_symlink():
        raise ValueError('Destination must be a NEW staging directory')
    for parent in destination.parents:
        if parent.is_symlink(): raise ValueError('Destination ancestor is symlink')
    changes = remap_plan(manifest) if remap else []
    destination.mkdir(mode=0o700)
    subprocess.run(['tar', '--extract', '--gzip', '--file', str(bundle / 'filesystem.tar.gz'),
                    '--directory', str(destination), '--numeric-owner', '--same-owner', '--same-permissions',
                    '--acls', '--xattrs', '--xattrs-include=*', '--delay-directory-restore'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    verify_tree(destination, manifest)
    if remap:
        apply_remap(destination, changes)
        verify_tree(destination, manifest, remapped=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle', type=Path)
    p.add_argument('--extract-to', type=Path)
    p.add_argument('--remap-service-owners', action='store_true')
    a = p.parse_args()
    if a.remap_service_owners and not a.extract_to: p.error('Remap requires --extract-to')
    manifest = validate_bundle(a.bundle)
    if a.extract_to: extract(a.bundle, a.extract_to, manifest, a.remap_service_owners)
    print(json.dumps({'verified': True, 'files': len(manifest['files']), 'extracted': bool(a.extract_to)}))

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as e:
        raise SystemExit('Snapshot verification failed: ' + (str(e) if not isinstance(e, subprocess.CalledProcessError) else 'private extraction failed'))
