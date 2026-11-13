import io
import json
import unittest
from unittest.mock import patch
import openai_writer as writer
from gemini_stream import StreamError


class OpenAIWriterTests(unittest.TestCase):
    def body(self):
        return {'contents': [{'role': 'user', 'parts': [{'text': 'Polish'}]}],
                'tools': [{'functionDeclarations': [{'name': 'lookup', 'parameters': {
                    'type': 'OBJECT', 'properties': {'question': {'type': 'STRING'}}}}]}]}

    def stream(self, events, check=lambda: None):
        data = ''.join('data: ' + json.dumps(c) + '\n\n' for c in events)
        visible = []
        with patch('urllib.request.urlopen', return_value=io.BytesIO(data.encode())) as transport:
            result = writer.generate('dummy-secret', 'writer-model', self.body(), 30, visible.append, check)
            request = transport.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
            self.assertFalse(json.loads(request.data)['store'])
        return result, visible

    def completed(self, output, **kw):
        return {'type':'response.completed','response':{'status':'completed','output':output,**kw}}

    def test_reasoning_effort_request_and_default(self):
        self.assertNotIn('reasoning',writer.request_body(self.body(),'gpt-6-astra'))
        for effort in ['low','medium','high']:
            body=self.body();body['reasoningEffort']=effort
            self.assertEqual(writer.request_body(body,'gpt-6-astra')['reasoning'],{'effort':effort})

    def test_stream_text_and_usage(self):
        result, visible = self.stream([
            {'type':'response.output_text.delta','delta':'Hello '},
            {'type':'response.output_text.delta','delta':'world'},
            self.completed([{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Hello world'}]}],
                           usage={'input_tokens':7,'output_tokens':2,'total_tokens':9})])
        self.assertEqual(visible, ['Hello ', 'world'])
        self.assertEqual(result['candidates'][0]['content']['parts'], [{'text': 'Hello world'}])
        self.assertEqual(result['usageMetadata']['totalTokenCount'], 9)

    def test_tools_reasoning_and_image_roundtrip(self):
        output=[{'type':'reasoning','id':'rs1','summary':[],'encrypted_content':'opaque'},
                {'type':'function_call','call_id':'call1','name':'lookup','arguments':'{"question":"why?"}'}]
        result, _ = self.stream([self.completed(output)])
        body = self.body()
        body['contents'].extend([result['candidates'][0]['content'], {'role': 'user', 'parts': [
            {'functionResponse': {'id': 'call1', 'name': 'lookup', 'response': {'output': 'Evidence'},
                                  'parts': [{'inlineData': {'mimeType': 'image/png', 'data': 'AAA',
                                                           'displayName': 'original-page-2.png'}}]}}]}])
        request = writer.request_body(body, 'writer-model')
        self.assertEqual(request['input'][1:3],output)
        self.assertEqual(request['input'][3]['call_id'],'call1')
        self.assertEqual(request['input'][4]['content'][1]['image_url'],'data:image/png;base64,AAA')
        self.assertEqual(request['tools'][0]['parameters']['properties']['question']['type'],'string')
        self.assertFalse(request['tools'][0]['strict'])

    def test_incomplete_stream_and_bad_tools_rejected(self):
        for events in [[{'type':'response.output_text.delta','delta':'partial'}],
                       [{'type':'response.incomplete'}],
                       [self.completed([{'type':'function_call','call_id':'x','name':'lookup','arguments':'{'}])]]:
            with self.subTest(events=events), self.assertRaises(StreamError):self.stream(events)

    def test_cancellation_propagates(self):
        class Stopped(ValueError):pass
        checks=0
        def check():
            nonlocal checks
            checks+=1
            if checks>1:raise Stopped('stopped')
        with self.assertRaises(Stopped):self.stream([{'type':'response.created'}],check)
