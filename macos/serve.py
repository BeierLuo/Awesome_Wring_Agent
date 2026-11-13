"""App-owned server: ephemeral port, readiness file, and parent lifetime guard."""
import json
import os
import shutil
import fcntl
from pathlib import Path
import sys
import threading
import time

project = Path(sys.argv[1]).resolve()
ready = Path(sys.argv[2])
data_root = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else project
port = int(sys.argv[4]) if len(sys.argv) > 4 else 0
parent = os.getppid()
sys.path.insert(0, str(project))
import server

try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
except ImportError:
    pass


def watch_parent():
    while True:
        time.sleep(1)
        if os.getppid() != parent:
            os._exit(0)


threading.Thread(target=watch_parent, daemon=True).start()
data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
# Prevent two app-owned servers from editing the same data directory.
lock = (data_root / '.app-server.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
for directory in ('agents', 'skills'):
    if data_root != project and (project / directory).exists():
        for source in (project / directory).rglob('*.md'):
            target = data_root / source.relative_to(project)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists(): shutil.copy2(source, target)
try:
    httpd = server.ThreadingHTTPServer(('127.0.0.1', port), server.Handler)
except OSError:
    if not port: raise
    httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
httpd.config_dir = data_root / '.local'
httpd.instruction_base = data_root
httpd.library_root = data_root / 'style-library'
httpd.root = data_root / 'workspaces'
httpd.root.mkdir(parents=True, exist_ok=True)
ready.write_text(json.dumps({'url': f'http://127.0.0.1:{httpd.server_port}/'}))
try:
    httpd.serve_forever()
finally:
    httpd.server_close()
