import json
import unittest
import urllib.request
from unittest.mock import patch
import test_http
import server
import style_memory
from writing_agent import WritingAgent


class SectionTypeHTTPTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    post = test_http.HTTPTests.post

    def test_confirm_without_model_then_reopen_and_use_in_chat(self):
        folder = self.server.root/'paper'
        self.server.library_root = self.server.root.parent/'library'
        before = (folder/'workspace.json').read_bytes()
        style_memory.set_settings(folder, 'auto', 'Keep my goal')
        style_memory.set_section_type(folder, self.state, 'abstract', 'method')
        headers = {'X-Draft-Library': '1'}
        payload = {'workspaceId': 'paper', 'sectionId': 'abstract', 'section': 'motivation'}
        with patch.object(server, 'read_config', side_effect=AssertionError('No API settings needed')), patch.object(server, 'cloud_json', side_effect=AssertionError('No model needed')):
            code, raw = self.post('/api/style-library/section-type', payload, headers)
            self.assertEqual(code, 200, raw)
            result = json.loads(raw)
            self.assertEqual(result['section_types']['abstract'], 'motivation')
            self.assertEqual(result['goal'], 'Keep my goal')
        req = urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/api/style-library/strategy?workspaceId=paper&sectionId=abstract', headers=headers)
        with urllib.request.urlopen(req) as r:
            self.assertEqual(json.load(r)['dashboard']['current_section'], 'motivation')
        agent = WritingAgent(folder, self.state, self.state['sections'][0], 'Compare styles', None, 'section-type-check', library_root=self.server.library_root)
        self.assertEqual(agent.reference_section, 'motivation')
        self.assertEqual({m['section'] for m in agent.strategy_dashboard['available_memories']}, {'motivation'})
        self.assertEqual((folder/'workspace.json').read_bytes(), before)
        self.assertIsNone(agent.strategy_dashboard['selected_plan'])
        self.assertFalse((folder/'memory/writing').exists())
        # Invalid types/sections and unauthorized requests cannot overwrite confirmation.
        for change in ({'section': '../method'}, {'section': []}, {'sectionId': 'missing'}, {'sectionId': ''}):
            self.assertEqual(self.post('/api/style-library/section-type', {**payload, **change}, headers)[0], 400)
        self.assertEqual(self.post('/api/style-library/section-type', payload)[0], 403)
        self.assertEqual(self.post('/api/style-library/section-type', payload, {**headers, 'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(style_memory.settings(folder)['section_types'], {'abstract': 'motivation'})
        # Saving project preferences later preserves the type; confirming while off stays off.
        style_memory.set_settings(folder, 'off', 'New goal')
        self.assertEqual(self.post('/api/style-library/section-type', {**payload, 'section': 'method'}, headers)[0], 200)
        self.assertEqual(style_memory.settings(folder), {'mode': 'off', 'goal': 'New goal', 'section_types': {'abstract': 'method'}})


if __name__ == '__main__':
    unittest.main()
