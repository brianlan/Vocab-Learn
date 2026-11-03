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

    def test_vocabulary_judge_uses_authored_meaning_and_only_visible_context(self):
        legacy = {"kind":"vocabulary", "direction":"recognition", "word":"absorb",
            "explanation":"Soak up liquid and hold it.", "question_text":"The sponge absorbs the water.",
            "target_highlight":"absorbs", "native_sentence":"海绵把水吸进去并留住了。",
            "native_highlight":"把水吸进去并留住了", "reference":"海绵把水吸进去并留在里面。",
            "gloss":"海绵把水吸进去并留在里面。", "language":"Chinese", "units":1}
        result={"units":[{"id":1,"outcome":"complete","reason":"Equivalent lexical meaning."}]}
        with patch("learning.providers.chat",return_value=result) as chat:
            units,metadata=p.assess(legacy,"吸收",self.profile())
        payload=chat.call_args.args[2]
        self.assertEqual(payload["explanation"],legacy["explanation"])
        self.assertEqual(payload["word"],"absorb")
        self.assertEqual(payload["transcript"],"吸收")
        for hidden in ["reference","gloss","native_sentence","native_highlight"]:
            self.assertNotIn(hidden,payload)
        self.assertEqual(metadata["prompt_version"],p.PROMPT_VERSIONS["JUDGE"])
        with patch("learning.providers.chat",return_value=result) as chat:
            p.assess({**legacy,"highlight_start":11},"吸收",self.profile())
        self.assertEqual(chat.call_args.args[2]["highlight_start"],11)
        generic={"kind":"generic","reference":"call off","units":1}
        with patch("learning.providers.chat",return_value=result) as chat:
            p.assess(generic,"cancel",self.profile())
        self.assertEqual(chat.call_args.args[2]["reference"],"call off")

    def test_invalid_pair_shape_highlights_and_answer_leak(self):
        valid={"target_sentence":"A <focus>bank</focus> is nearby.","native_sentence":"<focus>银行</focus>就在附近。"}
        plain={"target_sentence":"A bank is nearby.","target_highlight":"bank","target_highlight_start":2,
            "native_sentence":"银行就在附近。","native_highlight":"银行","native_highlight_start":0}
        self.assertEqual(p.validate_pair(valid,"bank"),plain)
        with self.assertRaises(p.StageError): p.validate_pair({**valid,"gloss":"银行"},"bank","Chinese")
        with self.assertRaises(p.StageError): p.validate_pair({**valid,"native_sentence":"A financial <focus>institution</focus>."},"bank","Chinese")
        for changed in [{"native_sentence":"<focus>bank</focus>"},
                        {"native_sentence":"<focus></focus>就在附近。"},
                        {"native_sentence":"银行就在附近。"},
                        {"native_sentence":"<focus><focus>银行</focus></focus>就在附近。"},
                        {"native_sentence":"</focus>银行<focus>就在附近。"},
                        {"native_sentence":"bank这个词表示<focus>银行</focus>。"}]:
            with self.assertRaises(p.StageError): p.validate_pair({**valid,**changed},"bank")
        marked={"target_sentence":"The <focus>abrupt</focus> change surprised us.",
                "native_sentence":"这个<focus>突然的</focus>变化让我们吃惊。"}
        result=p.validate_pair(marked,"abrupt","Chinese")
        self.assertEqual(result["native_highlight"],"突然的")
        self.assertNotIn("<focus>",result["native_sentence"])

    def test_highlighting_uses_the_marked_occurrence_not_a_shared_substring(self):
        from learning.rendering import highlight
        cases=[("compute", "We <focus>compute</focus> the total with a computer.",
                'We <strong class="target-word">compute</strong> the total with a computer.'),
            ("compute", "I use a computer to <focus>compute</focus> the total.",
                'I use a computer to <strong class="target-word">compute</strong> the total.'),
            ("compute", "We compute a sum, then <focus>compute</focus> the total.",
                'We compute a sum, then <strong class="target-word">compute</strong> the total.'),
            ("pan", "El panadero compra <focus>pan</focus>.",
                'El panadero compra <strong class="target-word">pan</strong>.')]
        for word,sentence,expected in cases:
            with self.subTest(word=word,sentence=sentence):
                native="面包师买<focus>面包</focus>。" if word=="pan" else "我用计算机<focus>计算</focus>总数。"
                data={"target_sentence":sentence,"native_sentence":native}
                result=p.validate_pair(data,word,"Chinese")
                self.assertEqual(highlight(result["target_sentence"],result["target_highlight"],
                    result["target_highlight_start"]),expected)
                expected_native=('面包师买<strong class="target-word">面包</strong>。' if word=="pan" else
                    '我用计算机<strong class="target-word">计算</strong>总数。')
                self.assertEqual(highlight(result["native_sentence"],result["native_highlight"],
                    result["native_highlight_start"]),expected_native)

    def test_focus_offsets_preserve_unicode_padding_and_safe_html(self):
        from learning.rendering import highlight
        data={"target_sentence":"🧮 A computer can <focus> compute </focus> a total < 10.",
            "native_sentence":"用计算机<focus> 计算 </focus>总数。"}
        result=p.validate_pair(data,"compute","Chinese")
        self.assertEqual(highlight(result["target_sentence"],result["target_highlight"],result["target_highlight_start"]),
            '🧮 A computer can  <strong class="target-word">compute</strong>  a total &lt; 10.')
        self.assertEqual(highlight(result["native_sentence"],result["native_highlight"],result["native_highlight_start"]),
            '用计算机 <strong class="target-word">计算</strong> 总数。')
        with self.assertRaises(ValueError):highlight(result["native_sentence"],"计算",0)

    def test_rotation_requires_both_new_sentences_and_configuration_rejects_nan(self):
        pair={"target_sentence":"A <focus>bank</focus> is nearby.","native_sentence":"<focus>银行</focus>就在附近。"}
        with patch("learning.providers.chat",return_value=pair):
            with self.assertRaises(p.StageError): p.generate({"word":"bank","previous_pair":p.validate_pair(pair,"bank")},self.profile("GENERATOR"))
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
