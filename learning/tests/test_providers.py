import base64
import json
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import httpx
from learning import providers as p


class ProviderBase(TestCase):
    def transport(self, handler):
        original = httpx.AsyncClient
        return patch("learning.providers.httpx.AsyncClient", side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw))

    def profile(self, task="AUDIO_ASSESS", protocol="openai", timeout=2):
        return p.Profile(task,"https://provider.test/endpoint","selected-model","placeholder-only",timeout,8192,protocol)


class ProviderTests(ProviderBase):

    def test_independent_profiles_and_no_cross_origin_key_fallback(self):
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"placeholder-only","GENERATOR_API_KEY":"generator-only","AUDIO_ASSESS_API_KEY":"audio-only"},clear=True):
            before = p.profile("GENERATOR").metadata()
            reviewer = p.profile("EXAMPLE_REVIEWER").metadata()
            with patch.dict(os.environ,{"AUDIO_ASSESS_MODEL":"different","AUDIO_ASSESS_TIMEOUT_SECONDS":"3"}):
                self.assertEqual(p.profile("AUDIO_ASSESS").model,"different")
                self.assertEqual(p.profile("GENERATOR").metadata(),before)
                self.assertEqual(p.profile("EXAMPLE_REVIEWER").metadata(),reviewer)
            with patch.dict(os.environ,{"AUDIO_ASSESS_ENDPOINT":"https://another.test/chat","AUDIO_ASSESS_API_KEY":""}):
                with self.assertRaises(p.StageError): p.profile("AUDIO_ASSESS")
            with patch.dict(os.environ,{"AUDIO_ASSESS_ENDPOINT":"https://api.minimax.cn.evil.test/chat","AUDIO_ASSESS_API_KEY":""}):
                with self.assertRaises(p.StageError): p.profile("AUDIO_ASSESS")  # the lookalike origin never receives the MiniMax fallback key
            with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"audio-only","AUDIO_ASSESS_ENDPOINT":"https://api.minimax.cn/v1/chat/completions"}):
                self.assertEqual(p.profile("AUDIO_ASSESS").key,"audio-only")
                self.assertEqual(p.profile("EXAMPLE_REVIEWER").key,"placeholder-only")
        # GLM's default origin requires an explicit task key; MiniMax's native origin may use the shared key.
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"placeholder-only"},clear=True):
            with self.assertRaises(p.StageError): p.profile("GENERATOR")
            self.assertEqual(p.profile("EXAMPLE_REVIEWER").key,"placeholder-only")

    def test_generation_and_review_dialects_defaults_and_role_exchange(self):
        response = {"choices":[{"finish_reason":"stop","message":{"content":json.dumps({"ok":True})}}]}
        seen = []
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"minimax-only","GENERATOR_API_KEY":"glm-only","AUDIO_ASSESS_API_KEY":"audio-only"}):
            with patch("learning.providers.request", side_effect=lambda request, **kw: seen.append(kw["json"]) or response):
                p.chat(p.profile("GENERATOR"), "rules", {})
                p.chat(p.profile("EXAMPLE_REVIEWER"), "rules", {})
                p.chat(p.profile("AUDIO_ASSESS"), "rules", {})
                p.chat(p.profile("DEFINITION"), "rules", {})
        generator, reviewer, audio_assess, definition = seen
        self.assertEqual(set(generator), {"model","stream","max_tokens","messages","thinking","reasoning_effort"})
        self.assertEqual(generator["thinking"],{"type":"enabled"})
        self.assertEqual(generator["reasoning_effort"],"max")
        self.assertEqual(set(reviewer), {"model","stream","max_completion_tokens","messages","thinking","reasoning_effort"})
        self.assertEqual(reviewer["thinking"],{"type":"adaptive"})
        self.assertEqual(reviewer["reasoning_effort"],"max")
        # Unrelated chat tasks keep their payload exactly as before; audio defaults resolve to the qwen dialect.
        self.assertEqual(set(audio_assess),{"model","stream","max_tokens","messages"})
        self.assertNotIn("thinking",audio_assess); self.assertNotIn("reasoning_effort",audio_assess)
        self.assertEqual(set(definition),{"model","stream","max_completion_tokens","messages"})
        self.assertNotIn("thinking",definition); self.assertNotIn("reasoning_effort",definition)
        exchanged = {"MINIMAX_API_KEY":"minimax-only","EXAMPLE_REVIEWER_API_KEY":"glm-reviewer-only",
                     "GENERATOR_ENDPOINT":"https://api.minimax.cn/v1/chat/completions",
                     "GENERATOR_PROTOCOL":"minimax","GENERATOR_THINKING":"adaptive","GENERATOR_REASONING_EFFORT":"high",
                     "EXAMPLE_REVIEWER_ENDPOINT":"https://open.bigmodel.cn/api/coding/paas/v4/chat/completions",
                     "EXAMPLE_REVIEWER_PROTOCOL":"zhipu","EXAMPLE_REVIEWER_THINKING":"enabled","EXAMPLE_REVIEWER_REASONING_EFFORT":"xhigh"}
        with patch.dict(os.environ, exchanged):
            generator, reviewer = p.profile("GENERATOR"), p.profile("EXAMPLE_REVIEWER")
            self.assertEqual((generator.protocol,generator.thinking,generator.effort),("minimax","adaptive","high"))
            self.assertEqual((reviewer.protocol,reviewer.thinking,reviewer.effort),("zhipu","enabled","xhigh"))
        with patch.dict(os.environ,{"GENERATOR_API_KEY":"k","GENERATOR_PROTOCOL":"zhipu","GENERATOR_THINKING":"adaptive"}):
            with self.assertRaises(p.StageError): p.profile("GENERATOR")
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"k","GENERATOR_PROTOCOL":"minimax","GENERATOR_THINKING":"enabled"}):
            with self.assertRaises(p.StageError): p.profile("GENERATOR")
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"k","GENERATOR_REASONING_EFFORT":"louder"}):
            with self.assertRaises(p.StageError): p.profile("GENERATOR")
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"k","EXAMPLE_REVIEWER_PROTOCOL":"anthropic"}):
            with self.assertRaises(p.StageError): p.profile("EXAMPLE_REVIEWER")
        with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"k","AUDIO_ASSESS_PROVIDER":"anthropic"},clear=True):
            with self.assertRaises(p.StageError): p.profile("AUDIO_ASSESS")

    def test_audio_provider_selection_defaults_and_dialect_ownership(self):
        with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"audio-key"},clear=True):
            # Unset or empty mode resolves to the documented Responses default per provider.
            qwen = p.profile("AUDIO_ASSESS")
            self.assertEqual((qwen.protocol,qwen.model,qwen.endpoint,qwen.api_mode),
                ("qwen","qwen3.8-omni-flash","https://dashscope.aliyuncs.com/compatible-mode/v1/responses","responses"))
            with patch.dict(os.environ,{"AUDIO_ASSESS_PROVIDER":"doubao"}):
                doubao = p.profile("AUDIO_ASSESS")
                self.assertEqual((doubao.protocol,doubao.model,doubao.endpoint,doubao.api_mode),
                    ("doubao","doubao-seed-2-1-lite-260915","https://ark.cn-beijing.volces.com/api/v3/responses","responses"))
                with patch.dict(os.environ,{"AUDIO_ASSESS_ENDPOINT":"https://api.minimax.cn/v1/chat/completions"}):
                    self.assertEqual(p.profile("AUDIO_ASSESS").key,"audio-key")  # no shared MiniMax fallback for audio origins
            # chat_completions explicitly retains the delivered #12 endpoint; the mode is independent of the provider.
            with patch.dict(os.environ,{"AUDIO_ASSESS_API_MODE":"chat_completions"}):
                self.assertEqual(p.profile("AUDIO_ASSESS").endpoint,
                    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
        # An explicit endpoint is an explicit full URL under every mode: never rewritten, never inferred from.
        for mode in ["responses","chat_completions"]:
            with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"k","AUDIO_ASSESS_API_MODE":mode,
                    "AUDIO_ASSESS_ENDPOINT":"https://provider.test/v1/chat/completions"},clear=True):
                self.assertEqual(p.profile("AUDIO_ASSESS").endpoint,"https://provider.test/v1/chat/completions")
        # Compose sets optional overrides to explicit empty strings; they must resolve to the provider+mode default.
        for provider,mode in [("qwen","responses"),("qwen","chat_completions"),
                              ("doubao","responses"),("doubao","chat_completions")]:
            with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"k","AUDIO_ASSESS_PROVIDER":provider,
                    "AUDIO_ASSESS_API_MODE":mode,"AUDIO_ASSESS_ENDPOINT":"","AUDIO_ASSESS_MODEL":""},clear=True):
                resolved = p.profile("AUDIO_ASSESS")
                self.assertEqual((resolved.protocol,resolved.model,resolved.endpoint,resolved.api_mode),
                    (provider,p.AUDIO_PROVIDERS[provider]["model"],p.AUDIO_PROVIDERS[provider][mode],mode))
        with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"k","AUDIO_ASSESS_PROVIDER":""},clear=True):
            self.assertEqual(p.profile("AUDIO_ASSESS").protocol,"qwen")
        # Invalid modes fail configuration at startup/profile validation, before any paid request.
        for value in ["chat","chat-completions","auto","responses2"]:
            with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"k","AUDIO_ASSESS_API_MODE":value},clear=True):
                with self.assertRaises(p.StageError) as error: p.profile("AUDIO_ASSESS")
                self.assertEqual(error.exception.category,"configuration")
        # The explicit disabled-thinking setting is adapter-owned; configuring it is rejected, never silently changed.
        with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"k","AUDIO_ASSESS_THINKING":"disabled"},clear=True):
            with self.assertRaises(p.StageError) as error: p.profile("AUDIO_ASSESS")
            self.assertEqual(error.exception.category,"configuration")
        with patch.dict(os.environ,{"AUDIO_ASSESS_API_KEY":"k","AUDIO_ASSESS_REASONING_EFFORT":"max"},clear=True):
            with self.assertRaises(p.StageError): p.profile("AUDIO_ASSESS")

    def test_audio_request_dialects_send_provider_audio_and_explicit_nonthinking(self):
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":
                json.dumps({"transcript":"heard answer","units":[{"id":1,"outcome":"complete","reason":"Matches."}]})}}]})
        snapshots = {"kind":"generic","reference":"four","units":1,"question_text":"What is two plus two?","direction":"generic","language":""}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"answer.wav"
            with wave.open(str(path),"wb") as fixture:
                fixture.setnchannels(1); fixture.setsampwidth(2); fixture.setframerate(16000)
                fixture.writeframes(b"\x00\x01"*16000)  # one real second of mono 16kHz PCM
            payload=path.read_bytes()
            for provider in ["qwen","doubao"]:
                seen.clear()
                with patch.dict(os.environ,{"AUDIO_ASSESS_PROVIDER":provider,"AUDIO_ASSESS_API_KEY":"k",
                        "AUDIO_ASSESS_API_MODE":"chat_completions"},clear=True):
                    with self.transport(handler):
                        transcript,units,metadata=p.audio_assessment(snapshots,path)
                self.assertEqual(transcript,"heard answer")
                self.assertEqual(units[0]["outcome"],"complete")
                self.assertEqual(metadata["prompt_version"],p.PROMPT_VERSIONS["AUDIO_ASSESS"])
                self.assertEqual(metadata["model"],p.AUDIO_PROVIDERS[provider]["model"])
                self.assertEqual(metadata["api_mode"],"chat_completions")
                body=seen[0]
                self.assertEqual(body["response_format"],{"type":"json_object"})
                parts=body["messages"][1]["content"]
                self.assertEqual(parts[0]["type"],"text")
                task=json.loads(parts[0]["text"])
                self.assertEqual(task["expected_unit_ids"],[1]); self.assertNotIn("transcript",task)
                # Both dialects send input_audio parts: Qwen takes the normalized audio as an MP3 data URI
                # (its documented inline limit is a Base64 string under 10MB), Doubao the WAV raw base64.
                self.assertEqual(parts[1]["type"],"input_audio")
                if provider=="qwen":
                    encoded=parts[1]["input_audio"]["data"].removeprefix("data:audio/mpeg;base64,")
                    self.assertEqual(parts[1]["input_audio"]["format"],"mp3")
                    self.assertLess(len(encoded),p.QWEN_INLINE_LIMIT)
                    self.assertEqual(body["reasoning_effort"],"none")
                    self.assertNotIn("thinking",body); self.assertNotIn("service_tier",body)
                else:
                    self.assertEqual(parts[1]["input_audio"]["format"],"wav")
                    self.assertEqual(parts[1]["input_audio"]["data"],base64.b64encode(payload).decode())
                    self.assertEqual(body["thinking"],{"type":"disabled"})
                    self.assertEqual(body["service_tier"],"default")
                    self.assertNotIn("reasoning_effort",body)

    def test_responses_mode_contracts_for_both_providers(self):
        answer={"transcript":"heard answer","units":[{"id":1,"outcome":"complete","reason":"Matches."}]}
        seen=[]
        def handler(request):
            seen.append(json.loads(request.content))
            # A reasoning item precedes the assistant message; its text must never become the answer.
            return httpx.Response(200,json={"status":"completed","output":[
                {"type":"reasoning","summary":[{"type":"summary_text","text":"Private reasoning text"}]},
                {"type":"message","role":"assistant","status":"completed",
                 "content":[{"type":"output_text","text":json.dumps(answer)}]}]})
        snapshots={"kind":"generic","reference":"four","units":1,"question_text":"What is two plus two?","direction":"generic","language":""}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"answer.wav"
            with wave.open(str(path),"wb") as fixture:
                fixture.setnchannels(1); fixture.setsampwidth(2); fixture.setframerate(16000)
                fixture.writeframes(b"\x00\x01"*16000)  # one real second of mono 16kHz PCM
            payload=path.read_bytes()
            for provider in ["qwen","doubao"]:
                seen.clear()
                with patch.dict(os.environ,{"AUDIO_ASSESS_PROVIDER":provider,"AUDIO_ASSESS_API_KEY":"secret-key"},clear=True):
                    with self.transport(handler):
                        transcript,units,metadata=p.audio_assessment(snapshots,path)
                # The same validated contract is satisfied through one Responses request per execution.
                self.assertEqual((transcript,units[0]["outcome"]),("heard answer","complete"))
                self.assertEqual(metadata["api_mode"],"responses")
                self.assertNotIn("secret-key",str(metadata))
                self.assertEqual(len(seen),1)  # exactly one request, no fallback to the other family
                body=seen[0]
                self.assertFalse(body["store"]); self.assertEqual(body["max_output_tokens"],8192)
                self.assertEqual(body["text"],{"format":{"type":"json_object"}})
                self.assertEqual(body["input"][0]["content"],p.AUDIO_ASSESS_RULES)
                self.assertNotIn("tools",body); self.assertNotIn("previous_response_id",body)
                user=body["input"][1]
                self.assertEqual(json.loads(user["content"][0]["text"])["expected_unit_ids"],[1])
                audio_item=user["content"][1]
                self.assertEqual(audio_item["type"],"input_audio")
                if provider=="qwen":
                    self.assertTrue(audio_item["data"].startswith("data:audio/mpeg;base64,"))
                    self.assertEqual(audio_item["format"],"mp3")
                    self.assertEqual(body["reasoning"],{"effort":"none"})
                    self.assertNotIn("thinking",body); self.assertNotIn("service_tier",body)
                else:
                    self.assertTrue(audio_item["audio_url"].startswith("data:audio/wav;base64,"))
                    self.assertNotIn("format",audio_item)
                    self.assertEqual(body["thinking"],{"type":"disabled"})
                    self.assertEqual(body["service_tier"],"default")
                    self.assertNotIn("reasoning",body)

    def test_responses_mode_rejects_failed_incomplete_and_non_answer_outputs(self):
        valid={"units":[{"id":1,"outcome":"complete","reason":"Okay"}]}
        payload=json.dumps(valid)
        def envelope(status="completed",output=None):
            data={"status":status}
            if output is not None: data["output"]=output
            return data
        message={"type":"message","role":"assistant","status":"completed",
                 "content":[{"type":"output_text","text":payload}]}
        def answer(**overrides):
            item={"type":"message","role":"assistant","status":"completed",
                  "content":[{"type":"output_text","text":payload}]}
            item.update(overrides); return item
        cases=[envelope(),  # no output at all
               envelope(status="failed",output=[message]),
               envelope(status="incomplete",output=[message]),
               envelope(status="completed",output=[]),
               envelope(status="completed",output=[{"type":"reasoning","summary":[
                   {"type":"summary_text","text":payload}]}]),  # reasoning never becomes the answer
               # R1 fail-closed envelopes: a usable JSON fragment must never override an explicit
               # refusal, unfinished status, a foreign role or mixed malformed/non-string content.
               envelope(status="completed",output=[answer(content=[
                   {"type":"output_text","text":payload},{"type":"refusal","refusal":"I cannot grade this."}])]),
               envelope(status="completed",output=[answer(role="user")]),
               envelope(status="completed",output=[message,answer(status="incomplete")]),
               envelope(status="completed",output=[answer(content=[
                   {"type":"output_text","text":payload},{"type":"output_text","text":5}])]),
               envelope(status="completed",output=[answer(content=[{"type":"output_text","text":"  "}])]),
               envelope(status="completed",output=[answer(content=[{"type":"input_text","text":payload}])]),
               envelope(status="completed",output=[answer(content=[
                   {"type":"output_text","text":"Here is JSON: "+payload}])])]
        for data in cases:
            with self.subTest(status=data.get("status"),output=data.get("output")):
                with self.transport(lambda request,data=data:httpx.Response(200,json=data)):
                    with self.assertRaises(p.StageError): p.respond(self.profile("AUDIO_ASSESS","qwen"),"rules",{})
        # The allowed shape still parses: reasoning items are excluded, one completed assistant message answers.
        with self.transport(lambda request:httpx.Response(200,json=envelope(output=[
                {"type":"reasoning","summary":[{"type":"summary_text","text":"Private reasoning text"}]},message]))):
            self.assertEqual(p.respond(self.profile("AUDIO_ASSESS","qwen"),"rules",{}),valid)

    def test_responses_mode_strips_whitespace_around_whole_json_fence(self):
        """R4: the old parser trimmed the joined answer, and json_answer detects a whole-response
        fence by its first/last characters. Surrounding whitespace must not defeat that fence."""
        valid={"units":[{"id":1,"outcome":"complete","reason":"Okay"}]}
        fenced=" \n```json\n"+json.dumps(valid)+"\n```\n "
        def fenced_envelope():
            return {"status":"completed","output":[{"type":"message","role":"assistant","status":"completed",
                "content":[{"type":"output_text","text":fenced}]}]}
        with self.transport(lambda request:httpx.Response(200,json=fenced_envelope())):
            self.assertEqual(p.respond(self.profile("AUDIO_ASSESS","qwen"),"rules",{}),valid)

    def test_responses_assessment_validation_reaches_real_recordings(self):
        """R2: a real recording must actually reach the dispatched Responses request and the common
        transcript/unit validation; removing that validation must fail these cases. Refused or
        malformed envelopes stay unassessed with exactly one request and no fallback."""
        valid={"transcript":"heard answer","units":[{"id":1,"outcome":"complete","reason":"Matches."}]}
        def message(text,extra=None):
            content=[{"type":"output_text","text":text}]+(extra or [])
            return {"type":"message","role":"assistant","status":"completed","content":content}
        snapshots={"kind":"generic","reference":"four","units":1,"question_text":"What is two plus two?","direction":"generic","language":""}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"answer.wav"
            with wave.open(str(path),"wb") as fixture:
                fixture.setnchannels(1); fixture.setsampwidth(2); fixture.setframerate(16000)
                fixture.writeframes(b"\x00\x01"*16000)  # one real second of mono 16kHz PCM
            for name,data in [
                    ("missing-transcript",{"status":"completed","output":[message(json.dumps(
                        {"units":[{"id":1,"outcome":"complete","reason":"Matches."}]}))]}),
                    ("mixed-refusal",{"status":"completed","output":[message(json.dumps(valid),extra=[
                        {"type":"refusal","refusal":"I cannot grade this recording."}])]}),
                    ("duplicate-units",{"status":"completed","output":[message(json.dumps(
                        {"transcript":"heard answer","units":[{"id":1,"outcome":"complete","reason":"Okay"},
                         {"id":1,"outcome":"complete","reason":"Duplicate"}]}))]}),]:
                seen=[]
                def handler(request,data=data):
                    seen.append(json.loads(request.content))
                    return httpx.Response(200,json=data)
                with patch.dict(os.environ,{"AUDIO_ASSESS_PROVIDER":"qwen","AUDIO_ASSESS_API_KEY":"k"},clear=True):
                    with self.transport(handler):
                        with self.assertRaises(p.StageError) as error: p.audio_assessment(snapshots,path)
                self.assertEqual(len(seen),1)  # the Responses request was dispatched before validation
                self.assertEqual(error.exception.stage,"AUDIO_ASSESS")
                if name=="missing-transcript":
                    self.assertIn("transcript",str(error.exception))  # specifically the transcript gate
                if name=="mixed-refusal":
                    self.assertIn("valid JSON answer",str(error.exception))  # refused envelope, not scored

    def test_stale_mp3_leftovers_are_never_trusted(self):
        """R7a: encoding publishes no shared file, so an interrupted or overlapping derivative of the
        immutable recording can never be assessed; the request always carries freshly encoded bytes."""
        seen=[]
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":
                json.dumps({"transcript":"heard answer","units":[{"id":1,"outcome":"complete","reason":"Matches."}]})}}]})
        snapshots={"kind":"generic","reference":"four","units":1,"question_text":"What is two plus two?","direction":"generic","language":""}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"answer.wav"
            with wave.open(str(path),"wb") as fixture:
                fixture.setnchannels(1);fixture.setsampwidth(2);fixture.setframerate(16000)
                fixture.writeframes(b"\x00\x01"*16000)
            Path(str(path)+".mp3").write_bytes(b"truncated-leftover-bytes")  # simulated interrupted writer
            with patch.dict(os.environ,{"AUDIO_ASSESS_PROVIDER":"qwen","AUDIO_ASSESS_API_KEY":"k",
                    "AUDIO_ASSESS_API_MODE":"chat_completions"},clear=True):
                with self.transport(handler):
                    p.audio_assessment(snapshots,path)
            sent=seen[0]["messages"][1]["content"][1]["input_audio"]["data"].removeprefix("data:audio/mpeg;base64,")
            self.assertNotEqual(base64.b64decode(sent),b"truncated-leftover-bytes")
            with tempfile.NamedTemporaryFile(suffix=".mp3") as check:
                check.write(base64.b64decode(sent));check.flush()
                probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",check.name],
                    capture_output=True,text=True,check=True)
                self.assertAlmostEqual(float(probe.stdout.strip()),1.0,delta=0.5)  # the complete recording was sent
            self.assertEqual(Path(str(path)+".mp3").read_bytes(),b"truncated-leftover-bytes")  # encoding left the stale file untouched

    def test_concurrent_encodings_each_return_complete_output(self):
        import threading
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"answer.wav"
            with wave.open(str(path),"wb") as fixture:
                fixture.setnchannels(1);fixture.setsampwidth(2);fixture.setframerate(16000)
                fixture.writeframes(b"\x00\x01"*16000)
            barrier=threading.Barrier(2);results=[]
            def worker():
                barrier.wait()
                results.append(p.transcode_mp3(path,20))
            threads=[threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(30)
            self.assertEqual(len(results),2)
            self.assertEqual(results[0],results[1])  # overlapping encodings each get their own complete bytes
            with tempfile.NamedTemporaryFile(suffix=".mp3") as check:
                check.write(results[0]);check.flush()
                probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",check.name],
                    capture_output=True,text=True,check=True)
                self.assertAlmostEqual(float(probe.stdout.strip()),1.0,delta=0.5)
            self.assertFalse(Path(str(path)+".mp3").exists())

    def test_encoding_exhaustion_blocks_the_provider_call(self):
        """R7b: encoding consumes the remaining execution budget; an exhausted window fails unscored
        before any model request is dispatched."""
        requests=[]
        def handler(request):
            requests.append(request)
            return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]})
        snapshots={"kind":"generic","reference":"four","units":1,"question_text":"What is two plus two?","direction":"generic","language":""}
        def slow_transcode(path,budget):
            time.sleep(0.6)  # the encoding alone exceeds the whole remaining budget
            return b"encoded-audio"
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"answer.wav";path.write_bytes(b"RIFF")
            with patch.dict(os.environ,{"AUDIO_ASSESS_PROVIDER":"qwen","AUDIO_ASSESS_API_KEY":"k"},clear=True):
                profile=self.profile("AUDIO_ASSESS","qwen",timeout=0.5)
                with patch("learning.providers.transcode_mp3",side_effect=slow_transcode):
                    with self.transport(handler):
                        with self.assertRaises(p.StageError) as error:
                            p.audio_assessment(snapshots,path,profile)
            self.assertEqual(error.exception.category,"timeout")
            self.assertEqual(requests,[])  # zero model requests for the exhausted execution

    def test_assessment_rejects_missing_transcript_refusals_and_unassessable(self):
        good={"id":1,"outcome":"complete","reason":"Okay"}
        for data in [{"units":[good]}, {"transcript":"  ","units":[good]}, {"transcript":5,"units":[good]},
                     {"transcript":"heard","units":[]}, {"transcript":"heard","unassessable":True}]:
            with self.subTest(data=data):
                with self.assertRaises(p.StageError): p.validate_assessment(data,[1])
        transcript,units=p.validate_assessment({"transcript":" 吸收 ","units":[good]},[1])
        self.assertEqual((transcript,units[0]["outcome"]),("吸收","complete"))

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

    def test_audio_assessment_uses_authored_meaning_and_only_visible_context(self):
        legacy = {"kind":"vocabulary", "direction":"recognition", "word":"absorb",
            "explanation":"Soak up liquid and hold it.", "question_text":"The sponge absorbs the water.",
            "target_highlight":"absorbs", "native_sentence":"海绵把水吸进去并留住了。",
            "native_highlight":"把水吸进去并留住了", "reference":"海绵把水吸进去并留在里面。",
            "gloss":"海绵把水吸进去并留在里面。", "language":"Chinese", "units":1}
        result={"transcript":"吸收","units":[{"id":1,"outcome":"complete","reason":"Equivalent lexical meaning."}]}
        with tempfile.TemporaryDirectory() as folder:
            recording=Path(folder)/"answer.wav"; recording.write_bytes(b"RIFF")
            with patch("learning.providers.transcode_mp3", return_value=b"transcoded"), patch("learning.providers.chat",return_value=result) as chat:
                transcript,units,metadata=p.audio_assessment(legacy,recording,self.profile("AUDIO_ASSESS","qwen"))
            payload=chat.call_args.args[2]
            self.assertEqual(transcript,"吸收")
            self.assertEqual(payload["explanation"],legacy["explanation"])
            self.assertEqual(payload["word"],"absorb")
            self.assertEqual(payload["expected_unit_ids"],[1])
            for hidden in ["reference","gloss","native_sentence","native_highlight","transcript"]:
                self.assertNotIn(hidden,payload)
            self.assertEqual(metadata["prompt_version"],p.PROMPT_VERSIONS["AUDIO_ASSESS"])
            with patch("learning.providers.transcode_mp3", return_value=b"transcoded"), patch("learning.providers.chat",return_value=result) as chat:
                p.audio_assessment({**legacy,"highlight_start":11},recording,self.profile("AUDIO_ASSESS","qwen"))
            self.assertEqual(chat.call_args.args[2]["highlight_start"],11)
            generic={"kind":"generic","reference":"call off","units":1}
            with patch("learning.providers.transcode_mp3", return_value=b"transcoded"), patch("learning.providers.chat",return_value=result) as chat:
                p.audio_assessment(generic,recording,self.profile("AUDIO_ASSESS","qwen"))
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

    def test_realized_constructions_keep_complete_spans_through_generation_and_rendering(self):
        from learning.rendering import highlight
        cases=[("pick sb. up", "I will <focus>pick her up</focus> after school.",
                "放学后我会<focus>接她</focus>。", "pick her up", "接她"),
            ("it is somebody's job to do sth.", "<focus>It is his job to clean the room</focus>.",
                "<focus>打扫房间是他的职责</focus>。", "It is his job to clean the room", "打扫房间是他的职责")]
        for word,target,native,target_focus,native_focus in cases:
            with self.subTest(word=word):
                source={"word":word,"explanation":"The authored construction's intended meaning.",
                    "target_language":"English","native_language":"Chinese"}
                with patch("learning.providers.chat", side_effect=lambda profile, rules, payload:
                        {"target_sentence":target,"native_sentence":native} if profile.task=="GENERATOR" else
                        {"verdict":"accept","issues":[],"pair":payload["candidate"]}) as chat:
                    pair,metadata=p.generate(source,self.profile("GENERATOR"),reviewer=self.profile("EXAMPLE_REVIEWER"))
                self.assertEqual(chat.call_args_list[0].args[2],source)
                self.assertIn("candidate",chat.call_args_list[1].args[2])
                self.assertEqual(metadata["prompt_version"],p.PROMPT_VERSIONS["GENERATOR"])
                for language,marked,focus in [("target",target,target_focus),("native",native,native_focus)]:
                    self.assertEqual(pair[language+"_highlight"],focus)
                    self.assertEqual(highlight(pair[language+"_sentence"],focus,pair[language+"_highlight_start"]),
                        marked.replace("<focus>",'<strong class="target-word">').replace("</focus>","</strong>"))

    def test_rotation_requires_both_new_sentences_and_configuration_rejects_nan(self):
        pair={"target_sentence":"A <focus>bank</focus> is nearby.","native_sentence":"<focus>银行</focus>就在附近。"}
        previous=p.validate_pair(pair,"bank")
        def repair(target,native):
            return {"verdict":"repair","issues":[{"rule":"alignment","detail":"Kept the previous sentence."}],
                    "pair":{"target_sentence":target,"native_sentence":native}}
        for repeated in [repair(pair["target_sentence"],"河对岸有一片安静的<focus>银行</focus>。"),
                         repair("A new <focus>bank</focus> opened by the river last month.",pair["native_sentence"])]:
            with self.subTest(repeated=repeated["pair"]):
                with patch("learning.providers.chat",side_effect=[pair,repeated]):
                    with self.assertRaises(p.StageError) as error:
                        p.generate({"word":"bank","previous_pair":previous},self.profile("GENERATOR"),
                                   reviewer=self.profile("EXAMPLE_REVIEWER"))
                self.assertEqual(error.exception.stage,"EXAMPLE_REVIEWER")
                self.assertIn("repeated an old sentence",str(error.exception))
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"placeholder-only"},clear=True):
            for value in ["nan","-1","inf"]:
                with patch.dict(os.environ,{"AUDIO_ASSESS_TIMEOUT_SECONDS":value,"AUDIO_ASSESS_API_KEY":"k"}):
                    with self.assertRaises(p.StageError): p.profile("AUDIO_ASSESS")
            for endpoint in ["https://[","https://api.minimax.cn:bad/chat","not-a-url"]:
                with patch.dict(os.environ,{"AUDIO_ASSESS_ENDPOINT":endpoint,"AUDIO_ASSESS_API_KEY":"k"}):
                    with self.assertRaises(p.StageError): p.profile("AUDIO_ASSESS")

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


BANK={"word":"bank","explanation":"Land beside a river.","target_language":"English","native_language":"Chinese"}
CANDIDATE={"target_sentence":"A <focus>bank</focus> is nearby.","native_sentence":"<focus>银行</focus>就在附近。"}
ACCEPT={"verdict":"accept","issues":[],"pair":CANDIDATE}
REPAIRED={"target_sentence":"We spread the picnic blanket on the <focus>bank</focus>.",
          "native_sentence":"我们把野餐毯铺在<focus>河岸</focus>上。"}


class ReviewedGenerationTests(ProviderBase):
    def profiles(self, timeout=5):
        return [p.Profile("GENERATOR","https://provider.test/endpoint","selected-model","placeholder-only",timeout,8192,"zhipu"),
                p.Profile("EXAMPLE_REVIEWER","https://provider.test/endpoint","selected-model","placeholder-only",timeout,8192,"minimax")]

    def play(self, candidate, verdict, source=None, **kwargs):
        replies={"GENERATOR":candidate,"EXAMPLE_REVIEWER":verdict}
        calls=[]
        def chat(profile, rules, payload):
            calls.append((profile.task, payload))
            self.assertEqual(rules, p.GENERATOR_RULES if profile.task=="GENERATOR" else p.EXAMPLE_REVIEW_RULES)
            return replies[profile.task]
        generator, reviewer = self.profiles()
        with patch("learning.providers.chat",side_effect=chat):
            result=p.generate(source or BANK,generator,reviewer=reviewer,**kwargs)
        return result,calls

    def envelope(self, verdict, issues, pair):
        return {"verdict":verdict,"issues":issues,"pair":pair}

    def test_accept_keeps_candidate_and_records_reviewer_provenance_without_a_third_call(self):
        (pair,metadata),calls=self.play(CANDIDATE,ACCEPT)
        self.assertEqual([task for task,_ in calls],["GENERATOR","EXAMPLE_REVIEWER"])
        self.assertEqual(calls[1][1]["candidate"],CANDIDATE)
        self.assertNotIn("candidate",calls[0][1])
        self.assertNotIn("expected_repairs",calls[1][1])
        self.assertEqual(pair,p.validate_pair(CANDIDATE,"bank","Chinese"))
        self.assertEqual(metadata["prompt_version"],p.PROMPT_VERSIONS["GENERATOR"])
        self.assertEqual(metadata["reviewer"]["verdict"],"accept")
        self.assertEqual(metadata["reviewer"]["issues"],[])
        self.assertEqual(metadata["reviewer"]["prompt_version"],p.PROMPT_VERSIONS["EXAMPLE_REVIEWER"])
        self.assertNotIn("placeholder-only",str(metadata))

    def test_local_repair_and_unrelated_full_rewrite_replace_without_extra_calls(self):
        rewritten={"target_sentence":"We picnicked on the grassy <focus>bank</focus> while boats passed.",
                   "native_sentence":"小船驶过时，我们在长满草的<focus>河岸</focus>上野餐。"}
        for issues,pair in [([{"rule":"scope","detail":"Native focus includes the result meaning."}],REPAIRED),
                            ([{"rule":"cue","detail":"No local edit can make the cue fair."}],rewritten)]:
            with self.subTest(issues=issues):
                result,calls=self.play(CANDIDATE,self.envelope("repair",issues,pair))
                self.assertEqual(len(calls),2)
                self.assertEqual(result[0],p.validate_pair(pair,"bank","Chinese"))
                self.assertEqual(result[1]["reviewer"]["verdict"],"repair")
                self.assertEqual(result[1]["reviewer"]["issues"],issues)

    def test_missing_marker_candidate_reaches_review_and_is_repaired(self):
        unmarked={"target_sentence":"A bank is nearby.","native_sentence":"银行就在附近。"}
        (pair,metadata),calls=self.play(unmarked,self.envelope("repair",
            [{"rule":"format","detail":"The candidate lacks focus markers."}],CANDIDATE))
        self.assertEqual(calls[1][1]["candidate"],unmarked)
        self.assertEqual(pair,p.validate_pair(CANDIDATE,"bank","Chinese"))
        self.assertEqual(metadata["reviewer"]["verdict"],"repair")

    def test_rejection_is_a_retryable_quality_failure_with_no_fallback(self):
        issues=[{"rule":"source","detail":"The candidate teaches a different sense."}]
        generator,reviewer=self.profiles()
        with patch("learning.providers.chat",side_effect=[CANDIDATE,self.envelope("reject",issues,None)]) as chat:
            with self.assertRaises(p.StageError) as error:
                p.generate(BANK,generator,reviewer=reviewer)
        self.assertEqual(error.exception.stage,"EXAMPLE_REVIEWER")
        self.assertEqual(error.exception.category,"invalid_output")
        self.assertIn("different sense",str(error.exception))
        self.assertEqual(chat.call_count,2)

    def test_malformed_envelopes_rejected_pairs_and_failed_final_validation(self):
        altered=self.envelope("accept",[],{"target_sentence":"Changed.","native_sentence":"改了。"})
        unchanged=self.envelope("repair",[{"rule":"scope","detail":"No change made."}],CANDIDATE)
        double_marked={"target_sentence":"A <focus>river <focus>bank</focus></focus> is nearby.",
                       "native_sentence":"<focus>银行</focus>就在附近。"}
        leak={"target_sentence":"We sat on the <focus>bank</focus>.","native_sentence":"The <focus>bank</focus> was shady."}
        cases=[{"verdict":"accept","issues":[]},
               self.envelope("accept",[{"rule":"scope","detail":"Needless finding."}],CANDIDATE),altered,
               self.envelope("repair",[],REPAIRED),unchanged,
               self.envelope("reject",[{"rule":"scope","detail":"Rejected."}],CANDIDATE),
               self.envelope("maybe",[{"rule":"scope","detail":"Bad verdict."}],None),
               self.envelope("repair",[{"rule":"invented","detail":"Unknown rule."}],REPAIRED),
               self.envelope("repair",[{"rule":"scope","detail":" "}],REPAIRED),
               self.envelope("repair",[{"rule":[],"detail":"Unhashable rule."}],REPAIRED),
               self.envelope("repair",[{"rule":{"nested":"object"},"detail":"Object rule."}],REPAIRED),
               {"verdict":"reject","issues":{"rule":"cue"},"pair":None}]
        for verdict in cases:
            with self.subTest(verdict=verdict):
                with self.assertRaises(p.StageError) as error:
                    self.play(CANDIDATE,verdict)
                self.assertEqual(error.exception.stage,"EXAMPLE_REVIEWER")
        generator,reviewer=self.profiles()
        with patch("learning.providers.chat",side_effect=[CANDIDATE,self.envelope("repair",
                [{"rule":[],"detail":"Unhashable rule."}],REPAIRED)]) as chat:
            with self.assertRaises(p.StageError) as error:
                p.generate(BANK,generator,reviewer=reviewer)
        self.assertEqual((error.exception.stage,error.exception.category),("EXAMPLE_REVIEWER","invalid_output"))
        self.assertEqual(chat.call_count,2)
        with self.assertRaises(p.StageError) as error:
            self.play(CANDIDATE,self.envelope("repair",[{"rule":"format","detail":"Broken markers."}],double_marked))
        self.assertEqual(error.exception.stage,"EXAMPLE_REVIEWER")
        with self.assertRaises(p.StageError) as error:
            self.play(CANDIDATE,self.envelope("repair",[{"rule":"language","detail":"Leaked the answer."}],leak))
        self.assertEqual(error.exception.stage,"EXAMPLE_REVIEWER")

    def test_unusable_generator_output_fails_before_review_without_a_reviewer_call(self):
        for candidate in [{"target_sentence":5,"native_sentence":"银行就在附近。"},
                          {"target_sentence":"A bank is nearby."},
                          {"needs_clarification":True},
                          {"target_sentence":"","native_sentence":"银行就在附近。"}]:
            with self.subTest(candidate=candidate):
                with self.assertRaises(p.StageError) as error:
                    self.play(candidate,ACCEPT)
                self.assertEqual(error.exception.stage,"GENERATOR")
                self.assertEqual(error.exception.category,"content" if candidate.get("needs_clarification") else "invalid_output")

    def test_reviewer_timeout_is_attributed_to_the_reviewer(self):
        class Trickle(httpx.AsyncByteStream):
            async def __aiter__(self):
                import asyncio
                while True:
                    await asyncio.sleep(.02)
                    yield b" "
        def handler(request):
            if b"candidate" in request.content:
                return httpx.Response(200,stream=Trickle())
            return httpx.Response(200,json={"choices":[{"finish_reason":"stop",
                "message":{"content":json.dumps(CANDIDATE)}}]})
        generator,reviewer=self.profiles()
        with self.transport(handler):
            with self.assertRaises(p.StageError) as error:
                p.generate(BANK,generator,reviewer=p.Profile("EXAMPLE_REVIEWER","https://provider.test/endpoint",
                    "selected-model","placeholder-only",.15,8192,"minimax"))
        self.assertEqual(error.exception.stage,"EXAMPLE_REVIEWER")
        self.assertEqual(error.exception.category,"timeout")

    def test_shared_budget_shrinks_and_expires_without_ever_bypassing_review(self):
        timeouts=[]
        def chat(profile,rules,payload):
            timeouts.append((profile.task,profile.timeout))
            time.sleep(.1)
            return CANDIDATE if profile.task=="GENERATOR" else ACCEPT
        generator,reviewer=self.profiles()
        with patch("learning.providers.chat",side_effect=chat):
            pair,metadata=p.generate(BANK,generator,reviewer=reviewer,budget_seconds=1)
            self.assertLess(timeouts[1][1],timeouts[0][1])
            self.assertLessEqual(timeouts[1][1],1)
            gen,rev=self.profiles()
            with self.assertRaises(p.StageError) as error:
                p.generate(BANK,gen,reviewer=rev,budget_seconds=.05)
        self.assertEqual(error.exception.stage,"EXAMPLE_REVIEWER")
        self.assertEqual(error.exception.category,"timeout")
        # Omitting the reviewer never bypasses review; the reviewer profile resolves from configuration.
        with patch.dict(os.environ,{"MINIMAX_API_KEY":"placeholder-only","GENERATOR_API_KEY":"placeholder-only"},clear=True):
            with patch("learning.providers.chat",side_effect=lambda profile,rules,payload:
                    CANDIDATE if profile.task=="GENERATOR" else ACCEPT) as calls:
                pair,metadata=p.generate(BANK)
        self.assertEqual([call.args[0].task for call in calls.call_args_list],["GENERATOR","EXAMPLE_REVIEWER"])
        self.assertEqual(metadata["reviewer"]["verdict"],"accept")
