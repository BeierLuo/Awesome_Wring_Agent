import io
import json
import unittest
from unittest.mock import patch
import gemini_stream

class StreamTests(unittest.TestCase):
    def test_visible_deltas_usage_and_function_signature(self):
        chunks=[{'candidates':[{'content':{'parts':[{'text':'private','thought':True},{'text':'Hel'}]}}]},
                {'candidates':[{'content':{'parts':[{'text':'lo'},{'functionCall':{'name':'read_style_memory','args':{'author':'hongxin'}},'thoughtSignature':'signature'}]},'finishReason':'STOP'}],'usageMetadata':{'totalTokenCount':42}}]
        raw=b''.join(('data: '+json.dumps(x)+'\n\n').encode() for x in chunks)
        seen=[]
        with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)) as call:
            result=gemini_stream.generate('https://example.test/model:generateContent',{}, {}, 10, seen.append,lambda:None)
        self.assertEqual(seen,['Hel','lo'])
        self.assertEqual(result['candidates'][0]['content']['parts'][1]['text'],'Hello')
        self.assertEqual(result['candidates'][0]['content']['parts'][2]['thoughtSignature'],'signature')
        self.assertEqual(result['usageMetadata']['totalTokenCount'],42)
        self.assertIn(':streamGenerateContent?alt=sse',call.call_args.args[0].full_url)

    def test_incomplete_stream_is_not_success(self):
        raw=b'data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}\n\n'
        with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)):
            with self.assertRaisesRegex(ValueError,'中途断开'):
                gemini_stream.generate('https://example.test',{}, {},10,lambda _:None,lambda:None)
