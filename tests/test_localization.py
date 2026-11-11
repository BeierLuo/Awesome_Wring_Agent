import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import localization as lang

ROOT = Path(__file__).resolve().parents[1]

class LocalizationTests(unittest.TestCase):
    def test_english_html_and_scripts(self):
        html = lang.english_resource('index.html', (ROOT/'ui/index.html').read_text())
        self.assertIn('lang="en"', html)
        self.assertIn('What would you like to revise today?', html)
        self.assertFalse(lang.CJK.search(html))
        with tempfile.TemporaryDirectory() as temp:
            for source in (ROOT/'ui').glob('*.js'):
                translated = lang.english_resource(source.name, source.read_text())
                target = Path(temp)/source.name
                target.write_text(translated)
                subprocess.run(['node', '--check', str(target)], check=True, capture_output=True)
                if source.name not in ('language.js','writing-strategy.js'):
                    self.assertFalse(lang.CJK.search(translated), source.name)

    def test_user_content_is_not_translated(self):
        data = {'state': {'name':'论文', 'sections':[{'title':'摘要','text':'正文','chat':[{'text':'你好'}]}]}, 'text':'写作偏好', 'items':[{'name':'论文','title':'摘要'}]}
        self.assertEqual(lang.response_metadata(data), data)
        self.assertEqual(lang.response_metadata({'error':'Project 不存在'})['error'], 'Project does not exist')
        self.assertEqual(lang.response_metadata({'roles':{'gap':'研究缺口'}})['roles']['gap'], 'Research gap')
        event={'type':'writer_delta','text':'原稿保持中文'}
        self.assertEqual(lang.response_metadata(event),event)
        self.assertEqual(lang.response_metadata({'type':'activity','message':'Gemini 第 2 轮生成 · 已调用 3 个工具'})['message'], 'Gemini generation round 2 · 3 tools used')

    def test_english_http_resources_and_api(self):
        import server
        import threading
        import urllib.request
        with tempfile.TemporaryDirectory() as temp:
            http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            http.root=Path(temp);http.config_dir=Path(temp)/'.local'
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                base='http://127.0.0.1:'+str(http.server_port)
                for route, expected in [('/', 'lang="zh-CN"'),('/en/','lang="en"'),('/en','lang="en"'),('/en/projects.js',"'en-US'"),('/en/vendor/katex.min.css','katex')]:
                    with urllib.request.urlopen(base+route) as response:
                        self.assertIn(expected,response.read().decode())
                request=urllib.request.Request(base+'/api/style-library',headers={'X-Draft-Language':'en'})
                try:urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    self.assertFalse(lang.CJK.search(json.loads(error.read())['error']))
            finally:
                http.shutdown();http.server_close()

if __name__=='__main__':unittest.main()
