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

    def test_transport_errors_are_distinct_and_do_not_expose_details(self):
        import socket,ssl,urllib.error
        cases=[(TimeoutError('SECRET'),False,'connection_timeout'),
               (TimeoutError('SECRET'),True,'read_timeout'),
               (urllib.error.URLError(socket.gaierror('SECRET')),False,'dns_error'),
               (urllib.error.URLError(ssl.SSLError('SECRET')),False,'tls_error'),
               (ConnectionRefusedError('SECRET'),False,'connection_refused'),
               (ConnectionResetError('SECRET'),True,'connection_interrupted'),
               (urllib.error.URLError('SECRET'),False,'connection_failed')]
        for error,connected,code in cases:
            with self.subTest(code=code):
                result=gemini_stream.transport_error(error,connected)
                self.assertEqual(result.code,code)
                self.assertNotIn('SECRET',str(result))
                self.assertIn('当前稿未改写',str(result))
        for code in [400,401,403,404,429,500,503]:
            result=gemini_stream.transport_error(urllib.error.HTTPError('SECRET',code,'SECRET',{},None))
            self.assertEqual(result.code,'http_'+str(code))
            self.assertIn('HTTP '+str(code),str(result))
            self.assertNotIn('SECRET',str(result))

    def test_local_deadline_is_not_network_timeout(self):
        raw=b'data: {}\n\n'
        with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)),patch('gemini_stream.time.monotonic',side_effect=[0,121]):
            with self.assertRaises(gemini_stream.StreamError) as raised:
                gemini_stream.generate('https://example.test',{}, {},120,lambda _:None,lambda:None)
        self.assertEqual(raised.exception.code,'generation_deadline')
        self.assertIn('120 秒',str(raised.exception))

    def test_connected_read_timeout(self):
        class Interrupted(io.BytesIO):
            def __next__(self):raise TimeoutError('private details')
        with patch('urllib.request.urlopen',return_value=Interrupted()):
            with self.assertRaises(gemini_stream.StreamError) as raised:
                gemini_stream.generate('https://example.test',{}, {},120,lambda _:None,lambda:None)
        self.assertEqual(raised.exception.code,'read_timeout')

    def test_connection_timeout_and_upstream_error_payload(self):
        with patch('urllib.request.urlopen',side_effect=TimeoutError()):
            with self.assertRaises(gemini_stream.StreamError) as raised:
                gemini_stream.generate('https://example.test',{}, {},120,lambda _:None,lambda:None)
        self.assertEqual(raised.exception.code,'connection_timeout')
        raw=b'data: {"error":{"code":429,"message":"SECRET"}}\n\n'
        with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)):
            with self.assertRaises(gemini_stream.StreamError) as raised:
                gemini_stream.generate('https://example.test',{}, {},120,lambda _:None,lambda:None)
        self.assertEqual(raised.exception.code,'http_429')
        self.assertNotIn('SECRET',str(raised.exception))

    def test_status_and_text_arrive_before_stream_finishes(self):
        states=[];texts=[]
        first={'candidates':[{'content':{'parts':[{'text':'hidden reasoning','thought':True}]}}]}
        second={'candidates':[{'content':{'parts':[{'text':'Hello'}]}}]}
        final={'candidates':[{'content':{'parts':[{'text':' world'}]},'finishReason':'STOP'}]}
        class LiveResponse:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def __iter__(self):
                for item in [first,second,final]:
                    if item is second:
                        self_test.assertEqual(states[-1]['stage'],'receiving')
                        self_test.assertEqual(texts,[])
                    if item is final:self_test.assertEqual(texts,['Hello'])
                    yield ('data: '+json.dumps(item)+'\n').encode()
                    yield b'\n'
        self_test=self
        with patch('urllib.request.urlopen',return_value=LiveResponse()):
            result=gemini_stream.generate('https://example.test',{}, {},120,texts.append,lambda:None,states.append)
        self.assertEqual([s['stage'] for s in states],['requesting','connected','receiving','text','completed'])
        self.assertEqual(states[-1]['characters'],11)
        self.assertEqual(states[-1]['chunks'],3)
        self.assertNotIn('hidden reasoning',json.dumps(states)+json.dumps(texts))
        self.assertEqual(result['candidates'][0]['finishReason'],'STOP')

    def test_timeout_before_headers_still_reports_waiting(self):
        states=[]
        with patch('urllib.request.urlopen',side_effect=TimeoutError()):
            with self.assertRaises(gemini_stream.StreamError):
                gemini_stream.generate('https://example.test',{}, {},120,lambda _:None,lambda:None,states.append)
        self.assertEqual([s['stage'] for s in states],['requesting'])
