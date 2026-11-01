"""Run against a dedicated preview account; real voice submission uses configured providers."""
import argparse
import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(options):
    access=json.loads(options.access_file.read_text())
    target=options.url or access["url"]
    output=options.output; output.mkdir(parents=True,exist_ok=True)
    errors=[]; checks=[]
    def checked(name):
        checks.append(name); print("PASS:",name,flush=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,executable_path=options.chromium,
            args=["--no-sandbox","--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream",
                  "--use-file-for-fake-audio-capture="+str(options.audio.resolve())])
        context=browser.new_context(viewport={"width":1440,"height":1050},permissions=["microphone"])
        page=context.new_page(); page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(target+"/login/"); page.screenshot(path=str(output/"login.png"),full_page=True)
        page.locator("#id_username").fill(access["username"]); page.locator("#id_password").fill(access["password"])
        page.get_by_role("button",name="Log in").click(); page.wait_for_url(target+"/")
        page.screenshot(path=str(output/"dashboard.png"),full_page=True)
        checked("Fieldnotes login and dashboard")
        page.goto(target+"/decks/")
        page.locator("#id_name").fill("Browser QA "+str(int(time.time())))
        page.locator("#id_description").fill("Isolated acceptance fixtures; archived after the browser check.")
        page.get_by_role("button",name="Create deck").click()
        deck_url=page.url
        fixtures=[("What is two plus two?","four","Two pairs make **four**. <u>A little arithmetic.</u>"),
                  ("I had to **{{blank}}** the meeting because I was <u>{{blank}}</u>.","call off; feeling unwell","Recall both target expressions."),
                  ("Why did you postpone the meeting?","To give everyone more time to prepare.","Move an event to a later time.")]
        def add_generic(fixture):
            question,answer,explanation=fixture
            page.goto(deck_url+"new/"); page.locator("#id_question").fill(question)
            page.locator("#id_answer").fill(answer); page.locator("#id_explanation").fill(explanation)
            page.get_by_role("button",name="Save",exact=False).click(); page.wait_for_url(re.compile(r"/cards/\d+/$"))
        add_generic(fixtures[0])
        page.goto(deck_url); page.get_by_role("button",name="Study this deck").click()
        page.wait_for_selector("#review-card"); assert page.locator(".prompt").inner_text()=="What is two plus two?"
        assert "four" not in page.content().lower()
        page.screenshot(path=str(output/"review-front.png"),full_page=True)
        checked("Manual entry, deck-scoped run, front has no hidden reference")
        page.get_by_role("button",name=re.compile("Speak")).click()
        page.locator("#recording-indicator").filter(has_text=re.compile("^Recording")).wait_for()
        page.wait_for_timeout(1800); page.get_by_role("button",name="Stop & check").click()
        page.wait_for_selector("#back:not([hidden])",timeout=15000)
        assert page.locator(".answer").inner_text()=="four"
        assert page.locator("#back button",has_text="Next card").is_disabled()
        page.screenshot(path=str(output/"checking.png"),full_page=True)
        checked("Actual MediaRecorder upload reveals reference before model completion")
        page.wait_for_selector("#next-card",timeout=60000)
        assert page.locator(".transcript").inner_text().strip()
        assert page.locator(".recall-result h3").inner_text() in ["Quick recall","Correct recall"]
        assert page.locator('[data-metric="cards_today"]').inner_text()=="1"
        assert page.locator("textarea:not([readonly]),[contenteditable=true]").count()==0
        page.screenshot(path=str(output/"feedback.png"),full_page=True)
        checked("Real ASR/Judge result, readonly response, persisted Next review")
        review_url=page.url
        add_generic(fixtures[1]); page.goto(review_url)
        page.locator("#next-card").click(); page.wait_for_selector(".cloze-blank")
        assert page.locator(".cloze-blank").count()==2
        assert page.locator(".prompt strong .cloze-blank").count()==1
        assert page.locator(".prompt u .cloze-blank").count()==1
        page.get_by_role("button",name=re.compile("Skip")).click()
        page.wait_for_selector("#next-card"); assert page.locator(".recall-result h3").inner_text()=="Skipped"
        review_url=page.url
        add_generic(fixtures[2]); page.goto(review_url)
        page.locator("#next-card").click(); page.wait_for_selector("#front:not([hidden])")
        page.get_by_role("button",name=re.compile("Speak")).click()
        page.locator("#recording-indicator").filter(has_text=re.compile("^Recording")).wait_for()
        page.wait_for_timeout(400); page.get_by_role("button",name="Cancel",exact=True).click()
        before=page.evaluate("JSON.parse(localStorage.getItem('vocab-clock:'+document.querySelector('#review-card').dataset.presentation)).elapsed")
        page.reload(); page.wait_for_timeout(400)
        after=page.evaluate("JSON.parse(localStorage.getItem('vocab-clock:'+document.querySelector('#review-card').dataset.presentation)).elapsed")
        assert after>=before; assert not page.locator("#speak").is_disabled()
        old_id=page.locator("#review-card").get_attribute("data-presentation")
        page.add_init_script("localStorage.removeItem("+json.dumps("vocab-clock:"+old_id)+")")
        page.reload(); assert page.locator("#speak").is_disabled(); assert page.locator("#clock-recovery").is_visible()
        page.get_by_role("button",name="Restart question").click(); page.wait_for_selector("#review-card")
        assert page.locator("#review-card").get_attribute("data-presentation")!=old_id
        pending_id=page.locator("#review-card").get_attribute("data-presentation")
        page.add_init_script("localStorage.setItem("+json.dumps("vocab-clock:"+pending_id)+", JSON.stringify({elapsed:2,savedAt:Date.now(),waiting:false,pending:true}))")
        page.reload(); assert page.locator("#speak").is_disabled()
        page.get_by_role("button",name="Restart question").click(); page.wait_for_selector("#review-card")
        assert page.locator("#review-card").get_attribute("data-presentation")!=pending_id
        checked("Formatted multi-blanks, neutral Skip, Cancel/refresh clock retention, explicit lost-clock restart")
        page.evaluate("""() => {window.pending=[]; window.stopped=0; navigator.mediaDevices.getUserMedia=()=>new Promise((resolve,reject)=>window.pending.push({resolve,reject}));} """)
        page.get_by_role("button",name=re.compile("Speak")).click()
        assert page.get_by_role("button",name="Cancel",exact=True).is_visible()
        page.get_by_role("button",name="Cancel",exact=True).click()
        page.get_by_role("button",name=re.compile("Speak")).click()
        page.evaluate("window.pending[0].resolve({getTracks:()=>[{stop:()=>window.stopped++},{stop:()=>window.stopped++}]})")
        page.wait_for_timeout(50); assert page.evaluate("window.stopped")==2
        assert "Waiting for microphone permission" in page.locator("#recording-indicator").inner_text()
        page.get_by_role("button",name="Cancel",exact=True).click()
        page.get_by_role("button",name=re.compile("Speak")).click()
        page.evaluate("window.pending[1].reject(new Error('obsolete rejection'))")
        page.wait_for_timeout(50); assert "Waiting for microphone permission" in page.locator("#recording-indicator").inner_text()
        page.get_by_role("button",name="Cancel",exact=True).click()
        checked("Ignored permissions remain cancellable; obsolete streams stop all tracks and late rejections cannot replace newer UI")
        page.get_by_role("button",name=re.compile("Forgot")).click(); page.wait_for_selector("#next-card")
        assert page.locator(".recall-result h3").inner_text()=="Needs a refresh"
        assert "min" in page.locator(".next-review").inner_text()
        page.locator("#next-card").click(); page.wait_for_selector("h1",state="visible")
        assert page.locator("h1").inner_text()=="Finished this run."
        finished=page.url; page.reload(); assert page.url==finished; assert page.locator("h1").inner_text()=="Finished this run."
        checked("Forgot and persisted one-minute due; exhausted run does not automatically restart")
        deck_id=re.search(r"/decks/(\d+)/",deck_url)[1]
        page.goto(target+"/progress/?window=all&deck="+deck_id)
        metrics=page.locator(".metric").all_text_contents(); assert metrics==["2","2","50%"],metrics
        page.screenshot(path=str(output/"progress.png"),full_page=True)
        checked("Distinct-card/scored-review/accuracy metrics exclude Skip")
        page.goto(deck_url+"new/?kind=vocabulary")
        page.locator("#id_word").fill("misunderstanding")
        page.locator("#id_explanation").fill("A problem caused when people understand one another incorrectly.")
        page.locator("#id_target_language").select_option("English"); page.locator("#id_native_language").select_option("Chinese")
        page.get_by_role("button",name="Save",exact=False).click()
        deadline=time.monotonic()+45
        while page.get_by_role("heading",name="Current example pair").count()==0 and time.monotonic()<deadline:
            page.wait_for_timeout(900); page.reload()
        assert page.get_by_role("heading",name="Current example pair").count()==1
        checked("Vocabulary manual creation and actual durable Generator preparation")
        page.goto(deck_url); page.get_by_role("button",name="Archive deck",exact=True).click()
        page.screenshot(path=str(output/"library.png"),full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        assert not errors,errors
        checked("Private deck archive, no horizontal overflow and no browser runtime errors")
        browser.close()
    (output/"browser-results.json").write_text(json.dumps({"status":"passed","checks":checks,"errors":errors,
        "browser":"Headless Chromium, synthetic microphone; physical device and Edge remain manual checks"},indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access-file",type=Path,required=True)
    parser.add_argument("--audio",type=Path,required=True)
    parser.add_argument("--url")
    parser.add_argument("--chromium")
    parser.add_argument("--output",type=Path,default=Path("docs/implementation/previews"))
    options=parser.parse_args()
    if not options.audio.is_file(): parser.error("The synthetic audio fixture does not exist.")
    run(options)
