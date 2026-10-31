import json
import os
import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import httpx
from learning import providers as p


class ProviderTests(TestCase):
    def transport(self, handler):
        original = httpx.AsyncClient
        return patch("learning.providers.httpx.AsyncClient", side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw))

    def profile(self, task="JUDGE", protocol="openai", timeout=2):
        return p.Profile(task,"https://provider.test/endpoint","selected-model","placeholder-only",timeout,8192,protocol)

    def test_independent_profiles_and_no_cross_origin_key_fallback(self):
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"placeholder-only"},clear=True):
            before = p.profile("GENERATOR").metadata()
            with patch.dict(os.environ,{"JUDGE_MODEL":"different","JUDGE_TIMEOUT_SECONDS":"3"}):
                self.assertEqual(p.profile("JUDGE").model,"different")
                self.assertEqual(p.profile("GENERATOR").metadata(),before)
            with patch.dict(os.environ,{"JUDGE_ENDPOINT":"https://another.test/chat"}):
                with self.assertRaises(p.StageError): p.profile("JUDGE")
            with patch.dict(os.environ,{"JUDGE_ENDPOINT":"https://api.minimax.cn.evil.test/chat"}):
                with self.assertRaises(p.StageError): p.profile("JUDGE")
            with patch.dict(os.environ,{"ASR_API_KEY":"asr-only"}):
                self.assertEqual(p.profile("ASR").key,"asr-only")
                self.assertEqual(p.profile("JUDGE").key,"placeholder-only")

    def test_native_header_vs_transcription_form(self):
        with tempfile.TemporaryDirectory() as folder:
            audio=Path(folder)/"test.wav"; audio.write_bytes(b"sample")
            for protocol,language,code in [("minimax","Chinese","zh"),("openai","Spanish","es")]:
                seen=[]
                def handler(request):
                    seen.append(request)
                    return httpx.Response(200,json={"text":"recognized text","base_resp":{"status_code":0}})
                with self.transport(handler):
                    text,metadata=p.transcribe(audio,language,self.profile("ASR",protocol))
                request=seen[0]; body=request.content.decode()
                self.assertEqual(text,"recognized text")
                self.assertIn('name="file"',body); self.assertIn('name="model"',body)
                if protocol=="minimax":
                    self.assertEqual(request.headers.get("language"),code)
                    self.assertNotIn('name="language"',body)
                else:
                    self.assertNotIn("language",request.headers)
                    self.assertIn('name="language"',body); self.assertIn(code,body)

    def test_chat_contract_fence_reasoning_and_failure_variants(self):
        valid={"units":[{"id":1,"outcome":"complete","reason":"Complete content."}]}
        body={"choices":[{"finish_reason":"stop","message":{"content":"```json\n"+json.dumps(valid)+"\n```","reasoning_content":"Never learner feedback"}}]}
        seen=[]
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json=body)
        with self.transport(handler):
            self.assertEqual(p.chat(self.profile(),"rules",{})["units"],valid["units"])
        self.assertEqual(seen[0]["max_completion_tokens"],8192)
        self.assertNotIn("temperature",seen[0]); self.assertNotIn("thinking",seen[0])
        for fault in [{"base_resp":{"status_code":1004}}, {"error":{"message":"private raw body"}},
                      {"choices":[{"finish_reason":"length","message":{"content":json.dumps(valid)}}]},
                      {"choices":[{"finish_reason":"stop","message":{"content":"","reasoning_content":json.dumps(valid)}}]},
                      {"choices":[{"finish_reason":"stop","message":{"content":"Here is JSON: "+json.dumps(valid)}}]},
                      {"choices":[{"finish_reason":"stop","message":{"content":"{}","refusal":"refused"}}]}]:
            with self.transport(lambda request:httpx.Response(200,json=fault)):
                with self.assertRaises(p.StageError) as error: p.chat(self.profile(),"rules",{})
                self.assertNotIn("private raw body",str(error.exception))

    def test_invalid_unit_sets_are_not_wrong_answers(self):
        good={"id":1,"outcome":"complete","reason":"Okay"}
        for data in [{"units":[good]}, {"units":[good,good]}, {"units":[good,{"id":2,"outcome":"E","reason":"bad"}]},
                     {"units":[good,{"id":True,"outcome":"complete","reason":"bad"}]}]:
            with self.assertRaises(p.StageError): p.validate_units(data,[1,2])
        result=p.validate_units({"units":[good,{"id":2,"outcome":"incorrect","reason":"Learner left blank unanswered"}]},[1,2])
        self.assertEqual(result[1]["outcome"],"incorrect")

    def test_invalid_pair_shape_highlights_and_answer_leak(self):
        valid={"target_sentence":"A bank is nearby.","target_highlight":"bank","native_sentence":"银行就在附近。","native_highlight":"银行","gloss":"银行"}
        self.assertEqual(p.validate_pair(valid,"bank"),valid)
        with self.assertRaises(p.StageError): p.validate_pair({**valid,"gloss":"A financial institution"},"bank","Chinese")
        for changed in [{"native_highlight":"bank","native_sentence":"bank"},{"target_sentence":"bank bank"},{"gloss":""},
                        {"native_sentence":"bank这个词表示银行。","native_highlight":"银行"}]:
            with self.assertRaises(p.StageError): p.validate_pair({**valid,**changed},"bank")

    def test_rotation_requires_both_new_sentences_and_configuration_rejects_nan(self):
        pair={"target_sentence":"A bank is nearby.","target_highlight":"bank","native_sentence":"银行就在附近。","native_highlight":"银行","gloss":"银行"}
        with patch("learning.providers.chat",return_value=pair):
            with self.assertRaises(p.StageError): p.generate({"word":"bank","previous_pair":pair},self.profile("GENERATOR"))
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"placeholder-only"},clear=True):
            for value in ["nan","-1","inf"]:
                with patch.dict(os.environ,{"JUDGE_TIMEOUT_SECONDS":value}):
                    with self.assertRaises(p.StageError): p.profile("JUDGE")
            for endpoint in ["https://[","https://api.minimax.cn:bad/chat","not-a-url"]:
                with patch.dict(os.environ,{"JUDGE_ENDPOINT":endpoint}):
                    with self.assertRaises(p.StageError): p.profile("JUDGE")

    def test_redirect_and_inactivity_trickle_are_bounded(self):
        with self.transport(lambda request:httpx.Response(302,headers={"Location":"https://evil.test"})):
            with self.assertRaises(p.StageError): p.request(self.profile(),json={})
        class Trickle(httpx.AsyncByteStream):
            async def __aiter__(self):
                import asyncio
                while True:
                    await asyncio.sleep(.02)
                    yield b" "
        start=time.monotonic()
        with self.transport(lambda request:httpx.Response(200,stream=Trickle())):
            with self.assertRaises(p.StageError) as e: p.request(self.profile(timeout=.15),json={})
        self.assertEqual(e.exception.category,"timeout")
        self.assertLess(time.monotonic()-start,1)
