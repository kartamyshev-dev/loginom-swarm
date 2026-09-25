#!/usr/bin/env python3
"""Check extracted backup files against immutable tar snapshots, never live files."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile

ARCHIVES = ('files', 'worker', 'secrets')


def digest(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(chunk)
    return value.hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe archive member path')
    return str(path)


def normalize_acl(value):
    entries = []
    for line in value.replace(',', '\n').splitlines():
        entry = line.split('#', 1)[0].strip()
        if not entry:
            continue
        parts = entry.split(':')
        if len(parts) == 4 and parts[0] in ('user', 'group'):
            parts = [parts[0], parts[3], parts[2]]
        entries.append(':'.join(parts))
    return sorted(entries)


def create(directory):
    records = []
    for archive in ARCHIVES:
        with tarfile.open(directory / (archive + '.tar'), 'r:') as source:
            seen = set()
            for member in source:
                name = safe_name(member.name)
                if name in seen:
                    raise ValueError('Duplicate archive member')
                seen.add(name)
                if member.isreg():
                    kind = 'file'
                elif member.isdir():
                    kind = 'directory'
                elif member.issym():
                    kind = 'symlink'
                elif member.islnk():
                    kind = 'hardlink'
                else:
                    raise ValueError('Unsupported archive member type')
                row = dict(archive=archive, path=name, kind=kind, mode=member.mode,
                           uid=member.uid, gid=member.gid)
                if kind in ('file', 'hardlink'):
                    with source.extractfile(member) as content:
                        row['sha256'] = digest(content)
                if kind == 'symlink':
                    row['target'] = member.linkname
                # ACLs have a separate getfacl/system encoding. GNU tar also
                # records Linux binary ACL xattrs when --xattrs-include=* is used.
                row['xattrs'] = {
                    key.removeprefix('SCHILY.xattr.'): hashlib.sha256(
                        value.encode('utf-8', 'surrogateescape')).hexdigest()
                    for key, value in member.pax_headers.items()
                    if key.startswith('SCHILY.xattr.')}
                row['acls'] = {kind: normalize_acl(member.pax_headers[key])
                               for kind, key in (('access', 'SCHILY.acl.access'),
                                                 ('default', 'SCHILY.acl.default'))
                               if key in member.pax_headers}
                records.append(row)
    (directory / 'snapshot-manifest.json').write_text(
        json.dumps({'version': 1, 'files': records}, ensure_ascii=True) + '\n')
    (directory / 'snapshot-manifest.json').chmod(0o600)


def verify(directory, extracted):
    manifest = json.loads((directory / 'snapshot-manifest.json').read_text())
    if manifest.get('version') != 1:
        raise ValueError('Unsupported snapshot manifest version')
    count = 0
    for row in manifest['files']:
        archive = row['archive']
        if archive not in ARCHIVES:
            raise ValueError('Unknown archive')
        relative = Path(safe_name(row['path']))
        base = extracted / archive
        for parent in relative.parents:
            if parent != Path('.') and (base / parent).is_symlink():
                raise ValueError('Archive member traverses a symlink')
        path = base / relative
        info = path.lstat()
        expected = row['kind']
        valid_type = ((expected == 'directory' and stat.S_ISDIR(info.st_mode))
                      or (expected == 'symlink' and stat.S_ISLNK(info.st_mode))
                      or (expected in ('file', 'hardlink') and stat.S_ISREG(info.st_mode)))
        if not valid_type or stat.S_IMODE(info.st_mode) != row['mode']:
            raise ValueError('Restored file type or mode differs from snapshot')
        if (info.st_uid, info.st_gid) != (row['uid'], row['gid']):
            raise ValueError('Restored ownership differs from snapshot')
        if expected in ('file', 'hardlink'):
            with path.open('rb') as content:
                if digest(content) != row['sha256']:
                    raise ValueError('Restored content differs from snapshot')
        elif expected == 'symlink' and os.readlink(path) != row['target']:
            raise ValueError('Restored symlink differs from snapshot')
        for name, expected_hash in row['xattrs'].items():
            value = os.getxattr(path, name, follow_symlinks=False)
            if hashlib.sha256(value).hexdigest() != expected_hash:
                raise ValueError('Restored extended attribute differs from snapshot')
        if row.get('acls'):
            result = subprocess.run(['getfacl', '--numeric', '--omit-header', '--', str(path)],
                                    capture_output=True, text=True, check=True)
            access, default = [], []
            for line in result.stdout.splitlines():
                if line.startswith('default:'):
                    default.append(line[len('default:'):])
                else:
                    access.append(line)
            actual = {'access': normalize_acl('\n'.join(access)),
                      'default': normalize_acl('\n'.join(default))}
            if any(actual[kind] != value for kind, value in row['acls'].items()):
                raise ValueError('Restored ACL differs from snapshot')
        count += 1
    print(f'Snapshot manifest verified: {count} entries; content, modes, owners, ACLs and recorded xattrs.')


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == 'create':
            create(Path(sys.argv[2]))
        elif len(sys.argv) == 4 and sys.argv[1] == 'verify':
            verify(Path(sys.argv[2]), Path(sys.argv[3]))
        else:
            raise ValueError('Usage: backup-manifest.py create BACKUP | verify BACKUP EXTRACTED')
    except Exception as error:
        # Paths or underlying errors can disclose profile/credential metadata.
        print('Snapshot manifest check failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
