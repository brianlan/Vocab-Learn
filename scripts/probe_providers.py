"""Opt-in, paid real-provider checks using public hand-authored learning fixtures."""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from learning.providers import assess, generate, transcribe, StageError


def snapshot(kind, direction, question, reference, explanation="", word="", units=1, language=""):
    return {"kind":kind,"direction":direction,"question_text":question,"reference":reference,"explanation":explanation,
            "word":word,"units":units,"language":language}


def run(audio_dir, task="all"):
    generic=snapshot("generic","generic","I had to [1] the meeting because I was [2].","call off; feeling unwell",units=2)
    recognition=snapshot("vocabulary","recognition","A misunderstanding stopped their conversation.","误会",
        "A problem caused by people understanding each other incorrectly.","misunderstanding",language="Chinese")
    postpone=snapshot("vocabulary","recognition","We postponed the meeting from Monday to Friday.","推迟",
        "Reschedule specifically to a later time, without cancelling.","postpone",language="Chinese")
    bank=snapshot("vocabulary","production","我们坐在河岸上。","bank","Land beside a river, not a financial institution.","bank",language="English")
    cases=[("GENERIC-MULTI",generic,"call off, feeling unwell",["complete","complete"]),
           ("GENERIC-TARGET-LIVE",generic,"cancel, feeling unwell",["partial","complete"]),
           ("GENERIC-SENTENCE",generic,"I had to call off the meeting because I was feeling unwell.",["complete","complete"]),
           ("RECOGNITION-CHINESE",recognition,"彼此理解错了",["complete"]),
           ("RECOGNITION-SPANISH",{**recognition,"reference":"malentendido","language":"Spanish"},"entenderse mal",["complete"]),
           ("RECOGNITION-SPANISH-CHINESE",{**recognition,"word":"malentendido","question_text":"Un malentendido interrumpió la conversación."},"误会",["complete"]),
           ("PARTIAL-MEANING",postpone,"改时间",["partial"]),
           ("WRONG-MEANING",postpone,"取消",["incorrect"]),
           ("PRODUCTION-TARGET",{**bank,"reference":"misunderstanding","word":"misunderstanding","question_text":"一个小小的误会打断了谈话。","explanation":"People understood each other incorrectly."},"misunderstanding",["complete"]),
           ("PRODUCTION-SUBSTITUTE",bank,"shore",["partial"]),
           ("PRODUCTION-WRONG-SENSE",bank,"financial institution",["incorrect"]),
           ("PRODUCTION-SPANISH",{**recognition,"direction":"production","question_text":"一个误会打断了谈话。","reference":"malentendido","word":"malentendido","language":"Spanish"},"malentendido",["complete"])]
    results=[]
    def check(name, action, expected=None):
        started=time.monotonic()
        try:
            data,profile=action()
            observed=[u["outcome"] for u in data] if isinstance(data,list) else None
            passed=expected is None or observed==expected
            record={"name":name,"status":"passed" if passed else "needs-review","seconds":round(time.monotonic()-started,2),
                    "expected":expected,"result":data,"profile":profile}
        except StageError as error:
            record={"name":name,"status":"blocked","seconds":round(time.monotonic()-started,2),"stage":error.stage,"message":str(error)}
        results.append(record); print(name,record["status"],record["seconds"],flush=True)
    for name,context,response,expected in cases if task in ["all", "judge"] else []:
        check(name,lambda c=context,t=response:assess(c,t),expected)
    for target,native,word in ([("English","Chinese","misunderstanding"),("English","Spanish","misunderstanding"),("Spanish","Chinese","malentendido")] if task in ["all", "generator"] else []):
        check("GENERATOR-"+target+"-"+native,lambda t=target,n=native,w=word:generate({"word":w,"target_language":t,"native_language":n,
            "explanation":"A disagreement or problem caused when people do not understand each other correctly."}))
    initial = next((r.get("result") for r in results if r["name"] == "GENERATOR-English-Chinese" and r["status"] == "passed"), None)
    if initial:
        check("GENERATOR-ROTATION", lambda:generate({"word":"misunderstanding", "target_language":"English", "native_language":"Chinese",
            "explanation":"A disagreement or problem caused when people do not understand each other correctly.", "previous_pair":initial}))
    if audio_dir and task in ["all", "asr"]:
        for language in ["English","Spanish","Chinese"]:
            check("ASR-"+language,lambda l=language:transcribe(audio_dir/(l+".wav"),l))
    return {"status":"passed" if all(r["status"]=="passed" for r in results) else "needs-review", "results":results,
            "limits":"Representative fixtures only. Structural generation checks require sense/alignment review; synthetic audio is not physical-microphone or broad language-accuracy evidence."}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true",help="Acknowledge that these calls use configured provider credentials and incur charges.")
    parser.add_argument("--audio-dir",type=Path,help="Optional English.wav, Spanish.wav and Chinese.wav speech fixtures.")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--task",choices=["all", "judge", "generator", "asr"],default="all")
    options=parser.parse_args()
    if not options.live: parser.error("Pass --live to run paid model calls.")
    report=run(options.audio_dir, options.task)
    options.output.parent.mkdir(parents=True,exist_ok=True)
    options.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    raise SystemExit(0 if report["status"]=="passed" else 1)
