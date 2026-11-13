#!/usr/bin/env python3
"""Archive redundant release bundles, never application data or unpublished builds."""
import argparse
import hashlib
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLED = Path('/Applications/Caret.app')
if not INSTALLED.exists():
    INSTALLED = Path('/Applications/Draft.app')


def info(app):
    return plistlib.loads((app / 'Contents/Info.plist').read_bytes())


def payload(app):
    resources = app / 'Contents'
    paths = sorted(resources.rglob('*'))
    return {str(p.relative_to(resources)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file() and '__pycache__' not in p.parts and '_CodeSignature' not in p.parts and p.name not in ('.DS_Store', 'Info.plist')}


def published_copy(app, installed):
    if app.is_symlink() or not app.is_dir():
        return False
    current, candidate = info(installed), info(app)
    if current.get('DraftBuildChannel') != 'release':
        return False
    if candidate.get('CFBundleIdentifier') != current.get('CFBundleIdentifier'):
        return False
    if candidate.get('DraftBuildChannel') != 'tmp' and candidate.get('CFBundleShortVersionString') != current.get('CFBundleShortVersionString'):
        return False
    return payload(app) == payload(installed)


def archive(app, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        temporary = Path(folder) / 'bundle.zip'
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(temporary)], check=True)
        with zipfile.ZipFile(temporary) as z:
            if z.testzip():
                raise RuntimeError('Archive verification failed')
            for p in app.rglob('*'):
                if p.is_symlink():
                    raise RuntimeError('Unexpected symlink; keeping original app')
                if p.is_file() and z.read(str(Path(app.name) / p.relative_to(app))) != p.read_bytes():
                    raise RuntimeError('Archive differs from original app')
        temporary.replace(destination)
    shutil.rmtree(app)


def cleanup(root=ROOT, installed=INSTALLED, apply=False):
    if not installed.is_dir() or info(installed).get('DraftBuildChannel') != 'release':
        print('Skip: no installed release to compare against'); return
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(installed)], check=True)
    # Do not remove bundles currently used by a native shell or its server.
    processes = subprocess.check_output(['ps', '-axo', 'command='], text=True)
    dist = root / 'dist'
    if dist.is_symlink():
        raise RuntimeError('Refusing a redirected dist directory')
    archive_dir = dist / 'release-archives'
    if archive_dir.is_symlink():
        raise RuntimeError('Refusing a redirected archive directory')
    candidates = [dist / name for name in ('Caret.app', 'tmp/Caret.app', 'Draft.app', 'tmp/Draft.app')]
    candidates += sorted(p for name in ('Caret.app', 'Draft.app') for p in (dist/'backups').glob('*/'+name))
    for app in candidates:
        if not app.exists(): continue
        if app.is_symlink() or not app.resolve().is_relative_to(dist.resolve()): continue
        if str(app) + '/' in processes:
            print('Skip running app:', app); continue
        backup = app.parent.parent == dist / 'backups'
        if backup:
            if info(app).get('CFBundleIdentifier') != 'local.paper.draft': continue
        elif not published_copy(app, installed):
            print('Keep unpublished or different build:', app); continue
        name = ('backup-' + app.parent.name if backup else ('tmp-' if app.parent.name == 'tmp' else 'release-') + info(app)['CFBundleShortVersionString']) + '.zip'
        print(('Archive: ' if apply else 'Would archive: ') + str(app))
        if apply: archive(app, archive_dir / name)
    # Keep three rollback archives; current release and tmp archives are separate.
    backups = sorted(archive_dir.glob('backup-*.zip'), reverse=True)
    for old in backups[3:]:
        print(('Remove old archive: ' if apply else 'Would remove old archive: ') + str(old))
        if apply: old.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='archive verified copies and prune old backups')
    args = parser.parse_args()
    cleanup(apply=args.apply)
