#!/usr/bin/env python3
"""Validate the DMG's read-only app with the separately installed runtime."""
import json
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='默认验证 tmp 安装包；--release 验证正式包')
parser.add_argument('--release', action='store_true')
args = parser.parse_args()
dmg = root / ('dist/Caret.dmg' if args.release else 'dist/tmp/Caret.dmg')
support = Path.home()/'Library/Application Support/Draft'
python = support/'runtime/bin/python3.12'
with tempfile.TemporaryDirectory(prefix='draft-check-') as tmp:
    tmp = Path(tmp).resolve()
    mount = tmp/'disk'
    subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(dmg)], check=True, stdout=subprocess.DEVNULL)
    try:
        app = mount/'Caret.app'
        resource = app/'Contents/Resources'
        code = resource/'app'
        assert not (resource/'runtime').exists()
        assert not (code/'workspaces').exists()
        assert not (code/'.local').exists()
        info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
        assert 'DraftProjectPath' not in info
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
        env = dict(os.environ, DRAFT_TOOLS_DIR=str(support/'tools'))
        snippet = "import sys,ssl; sys.path.insert(0,sys.argv[1]); import server,writing_agent,pymupdf,langgraph.checkpoint.sqlite,certifi,latex_project; ssl.create_default_context(cafile=certifi.where()); assert latex_project.compiler()==sys.argv[2]; assert not any('paper-local' in p for p in sys.path); print('PASS: relocated runtime, all backend imports, TLS certificates and external compiler')"
        subprocess.run([str(python), '-I', '-B', '-c', snippet, str(code), str(support/'tools/tectonic')], cwd=tmp, env=env, check=True)
        ready = tmp/'ready.json'
        data = tmp/'data'
        child = subprocess.Popen([str(python), '-I', '-B', str(resource/'serve.py'), str(code), str(ready), str(data)], cwd=tmp, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(200):
                if ready.exists(): break
                if child.poll() is not None: raise RuntimeError(child.stderr.read().decode())
                time.sleep(.1)
            url = json.loads(ready.read_text())['url']
            def fetch(endpoint, payload=None, headers=None):
                req = urllib.request.Request(url+endpoint, data=json.dumps(payload).encode() if payload is not None else None, headers=headers or {})
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.read()
            health = json.loads(fetch('api/health'))
            assert health['root'] == str(data/'workspaces')
            assert b'Caret' in fetch('')
            fetch('api/settings', {'openai_model':'migration-smoke-test'}, {'X-Draft-Settings':'1', 'Content-Type':'application/json'})
            assert json.loads((data/'.local/api-config.json').read_text())['openai_model']=='migration-smoke-test'
            assert (data/'.local/api-config.json').stat().st_mode & 0o777 == 0o600
            library = json.loads(fetch('api/style-library', headers={'X-Draft-Library':'1'}))
            assert library['root'] == str(data/'style-library')
            assert (data/'agents/writer/AGENT.md').is_file()
            prefs=json.loads(fetch('api/preferences', headers={'X-Draft-Preferences':'1'}))
            assert prefs['items']==[] and (data/'.local/preferences/.git').is_dir()
            assert prefs['path']==str(data/'.local/preferences')
            second = subprocess.run([str(python), '-I', '-B', str(resource/'serve.py'), str(code), str(tmp/'second.json'), str(data)], cwd=tmp, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            assert second.returncode != 0
            assert not (tmp/'second.json').exists()
            print('PASS: read-only DMG app serves UI, isolates writable data, seeds rules and prevents duplicate servers')
        finally:
            child.terminate(); child.wait(timeout=5)
        with tempfile.TemporaryDirectory(prefix='latex-', dir=tmp) as project:
            project = Path(project)
            (project/'main.tex').write_text(r'\documentclass{article}\begin{document}Draft installation test.\end{document}')
            compile_env = dict(os.environ, TECTONIC_CACHE_DIR=str(support/'tools/tectonic-cache'))
            result = subprocess.run([str(support/'tools/tectonic'), '--untrusted', 'main.tex'], cwd=project, env=compile_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            if result.returncode: raise RuntimeError(result.stdout.decode())
            assert (project/'main.pdf').read_bytes().startswith(b'%PDF-')
            print('PASS: external LaTeX compiler creates PDF')
    finally:
        subprocess.run(['hdiutil', 'detach', str(mount)], check=True, stdout=subprocess.DEVNULL)
print('All installation checks passed; no model calls or personal data changes.')

# Only identical, already-installed builds qualify for cleanup.
if args.release:
    subprocess.run([__import__('sys').executable, str(root/'macos/cleanup_releases.py'), '--apply'], check=True)
