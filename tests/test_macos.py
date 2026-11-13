"""Native-shell lifecycle checks; uses loopback sockets and no model calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class MacAppServerTests(unittest.TestCase):
    def wait_ready(self, ready, child):
        for _ in range(100):
            if ready.exists():
                return json.loads(ready.read_text())['url']
            if child.poll() is not None:
                self.fail('App server exited before becoming ready')
            time.sleep(.1)
        self.fail('App server did not become ready')

    def test_health_and_ui_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / 'ready.json'
            child = subprocess.Popen([sys.executable, str(ROOT/'macos/serve.py'), str(ROOT), str(ready)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                url = self.wait_ready(ready, child)
                with urllib.request.urlopen(url+'api/health', timeout=3) as response:
                    health = json.load(response)
                self.assertEqual(health['app'], 'paper-local')
                self.assertEqual(health['root'], str(ROOT/'workspaces'))
                with urllib.request.urlopen(url, timeout=3) as response:
                    self.assertIn(b'Draft', response.read())
            finally:
                child.terminate()
                child.wait(timeout=5)
            with self.assertRaises(OSError):
                urllib.request.urlopen(url+'api/health', timeout=1)

    def test_server_stops_when_app_parent_disappears(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / 'ready.json'
            code = 'import subprocess,sys,time; subprocess.Popen(sys.argv[1:]); time.sleep(60)'
            parent = subprocess.Popen([sys.executable, '-c', code, sys.executable, str(ROOT/'macos/serve.py'), str(ROOT), str(ready)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                url = self.wait_ready(ready, parent)
            finally:
                parent.terminate()
                parent.wait(timeout=5)
            for _ in range(40):
                try:
                    urllib.request.urlopen(url+'api/health', timeout=.2).close()
                except OSError:
                    return
                time.sleep(.1)
            self.fail('Server remained running after its parent exited')


if __name__ == '__main__':
    unittest.main()
