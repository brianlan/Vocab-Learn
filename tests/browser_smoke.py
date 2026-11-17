"""Run against a dedicated preview account; real voice submission uses configured providers."""
import argparse
import base64
import hashlib
import json
import queue
import re
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def run(options):
    access=json.loads(options.access_file.read_text())
    target=options.url or access["url"]
    output=options.output; output.mkdir(parents=True,exist_ok=True)
    errors=[]; checks=[]
    def checked(name):
        checks.append(name); print("PASS:",name,flush=True)
    def write_results():
        result={"status":"passed","checks":checks,"errors":errors,
            "browser":"Headless Chromium, synthetic microphone; physical device and Edge remain manual checks"}
        if options.generic_only:
            result.update(scope="generic-only",assessment="scored" if scored_first else "deadline-failure")
        (output/"browser-results.json").write_text(json.dumps(result,indent=2)+"\n")
    with ExitStack() as cleanup:
        tls=None; loopback_scheme="http"; fixture_pin=None
        if urlsplit(target).scheme=="https":
            folder=Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix="vocab-smoke-")))
            key=folder/"loopback.key"; cert=folder/"loopback.crt"
            subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-keyout",str(key),
                "-out",str(cert),"-days","1","-subj","/CN=127.0.0.1","-addext","subjectAltName=IP:127.0.0.1"],
                check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            public_key=subprocess.check_output(["openssl","pkey","-in",str(key),"-pubout","-outform","DER"])
            fixture_pin=base64.b64encode(hashlib.sha256(public_key).digest()).decode()
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(cert,key)
            loopback_scheme="https"
        playwright=cleanup.enter_context(sync_playwright())
        args=["--no-sandbox","--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream",
              "--use-file-for-fake-audio-capture="+str(options.audio.resolve())]
        # Trust only this run's loopback fixture key; the application's HTTPS certificate remains verified.
        if fixture_pin: args.append("--ignore-certificate-errors-spki-list="+fixture_pin)
        browser=playwright.chromium.launch(headless=True,executable_path=options.chromium,args=args)
        context=browser.new_context(viewport={"width":1440,"height":1050},permissions=["microphone"])
        page=context.new_page(); page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(target+"/login/"); page.screenshot(path=str(output/"login.png"),full_page=True)
        page.locator("#id_username").fill(access["username"]); page.locator("#id_password").fill(access["password"])
        page.get_by_role("button",name="Log in").click(); page.wait_for_url(target+"/")
        assert page.get_by_role("button",name="Practice",exact=True).count()==1
        assert "Start a new run" not in page.locator("main").inner_text()
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
        checked("Manual entry, deck-scoped practice, front has no hidden reference")
        # --- Synthetic recovery probes: controlled transport through a gate queue. Every transition is
        # released by this test, so the controller's automatic watchdog and poller cadence cannot race it.
        # No server attempt is involved; all evidence is labelled synthetic. ---
        status_url=page.locator("#review-card").get_attribute("data-status-url")
        @contextmanager
        def stalled_transport(path,partial=False):
            arrived=queue.Queue(); release=threading.Event()
            class Stall(socketserver.BaseRequestHandler):
                def handle(self):
                    if partial:
                        chunk=b'{"state":"processing"'
                        self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                            b"Access-Control-Allow-Origin: *\r\nTransfer-Encoding: chunked\r\n\r\n"
                            +format(len(chunk),"x").encode()+b"\r\n"+chunk+b"\r\n")
                    arrived.put(time.monotonic()); release.wait()
            server=socketserver.ThreadingTCPServer(("127.0.0.1",0),Stall)
            if tls: server.socket=tls.wrap_socket(server.socket,server_side=True)
            stall_url=f"{loopback_scheme}://127.0.0.1:{server.server_address[1]}/stall"
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            def rewrite(route):
                route.continue_(url=stall_url)
            try:
                page.route("**"+path,rewrite)
                yield stall_url,arrived
            finally:
                try:
                    page.unroute("**"+path,rewrite)
                finally:
                    release.set(); server.shutdown(); server.server_close(); thread.join()
        def synthetic(state,deadline):
            return json.dumps({"state":state,"grade":None,"transcript":None,"next_due":None,
                "deadline":deadline,"metrics":{},"collection":"","back_html":""})
        replies=[]; held=queue.Queue()
        def gate(route):
            if replies: route.fulfill(status=200,content_type="application/json",body=replies.pop(0))
            else: held.put(route)  # the fetch stays pending until the test releases a reply
        def wait_held(timeout=15.0):
            # Synchronous Playwright dispatches route callbacks only while a command is in flight:
            # pump the event loop with wait_for_timeout instead of blocking the dispatcher thread.
            limit=time.monotonic()+timeout
            while time.monotonic()<limit:
                try:
                    return held.get_nowait()
                except queue.Empty:
                    page.wait_for_timeout(100)
            raise AssertionError("no held status request arrived")
        page.route("**"+status_url,gate)
        overdue_past=synthetic("processing",page.evaluate("new Date(Date.now()-5000).toISOString()"))
        fresh=synthetic("processing",page.evaluate("new Date(Date.now()+60000).toISOString()"))
        terminal=synthetic("assessed",None)
        # 1. Overdue recovery appears on the first controlled reply.
        replies.append(overdue_past)
        page.evaluate("document.querySelector('[data-action=check]').click()")
        page.wait_for_selector("#reconnect-controls:not([hidden])",timeout=5000)
        assert "15-second" in page.locator("#technical-message").inner_text()
        # 2. A delayed pending reply arrives 1.2s late; overdue recovery stays visible across it.
        watchdog=wait_held()  # the controller's next automatic status check is held pending
        page.wait_for_timeout(1200)
        assert page.locator("#reconnect-controls").is_visible()
        watchdog.fulfill(status=200,content_type="application/json",body=overdue_past)
        page.wait_for_timeout(300)
        assert page.locator("#reconnect-controls").is_visible()
        # 3. A confirmed new execution (fresh deadline) clears the overdue recovery.
        confirmed=wait_held()
        confirmed.fulfill(status=200,content_type="application/json",body=fresh)
        page.wait_for_selector("#reconnect-controls",state="hidden",timeout=5000)
        # 4. An authoritative terminal result keeps recovery hidden.
        final=wait_held()  # the 1.2s pending poller asks again
        final.fulfill(status=200,content_type="application/json",body=terminal)
        page.wait_for_timeout(400)
        assert page.locator("#reconnect-controls").is_hidden()
        while not held.empty(): held.get_nowait().abort()
        page.unroute("**"+status_url)
        page.reload(); page.wait_for_selector("#review-card")
        assert page.locator("#reconnect-controls").is_hidden()
        checked("Synthetic probe: overdue recovery persists across a delayed pending reply, clears on a confirmed new execution and stays hidden at a terminal result")
        # 5. A status request that stalls until the ten-second abort stays unconfirmed and releases the guard.
        with stalled_transport(status_url) as (_,arrived):
            page.evaluate("document.querySelector('[data-action=check]').click()")
            page.wait_for_selector("#reconnect-controls:not([hidden])",timeout=15000)
            assert not arrived.empty(),"The stalled status request never reached loopback"
            assert "unconfirmed" in page.locator("#technical-message").inner_text()
        page.evaluate("document.querySelector('[data-action=check]').click()")  # trigger a real subsequent check
        for _ in range(40):
            if "No accepted submission" in page.locator("#technical-message").inner_text(): break
            page.wait_for_timeout(100)
        assert "No accepted submission" in page.locator("#technical-message").inner_text()  # the guard released
        page.reload(); page.wait_for_selector("#review-card")
        assert page.locator("#reconnect-controls").is_hidden()  # a clean page starts without recovery
        checked("Synthetic probe: a stalled status request aborts at ten seconds, stays unconfirmed, releases the check guard and a clean reload starts without recovery")
        # 6. A stalled upload aborts at ten seconds, stays unconfirmed and submits nothing.
        page.get_by_role("button",name=re.compile("Speak")).click()
        page.locator("#recording-indicator").filter(has_text=re.compile("^Recording")).wait_for()
        page.wait_for_timeout(800)
        action_url=page.locator("#review-card").get_attribute("data-action-url")
        with stalled_transport(action_url) as (_,arrived):
            page.get_by_role("button",name="Stop & check").click()
            page.wait_for_selector("#reconnect-controls:not([hidden])",timeout=15000)
            assert not arrived.empty(),"The stalled upload never reached loopback"
            assert "unconfirmed" in page.locator("#technical-message").inner_text()
        page.reload(); page.wait_for_selector("#review-card")
        assert page.locator("#reconnect-controls").is_hidden()
        assert page.locator("#review-card").get_attribute("data-state")=="question"  # no attempt was created
        # The ambiguous upload saved a pending marker: the lost-clock guard disables Speak until the
        # explicit Restart question flow starts the next independent scenario with fresh route URLs.
        assert page.locator("#clock-recovery").is_visible()
        assert page.locator("#speak").is_disabled()
        old_presentation=page.locator("#review-card").get_attribute("data-presentation")
        old_status_url,old_action_url=status_url,action_url
        page.get_by_role("button",name="Restart question").click(); page.wait_for_selector("#review-card")
        assert page.locator("#review-card").get_attribute("data-presentation")!=old_presentation
        status_url=page.locator("#review-card").get_attribute("data-status-url")  # presentation-dependent URLs are refreshed
        action_url=page.locator("#review-card").get_attribute("data-action-url")
        assert status_url!=old_status_url and action_url!=old_action_url
        checked("Synthetic probe: a stalled upload aborts at ten seconds, stays unconfirmed, submits nothing and the explicit restart flow reopens the question")
        # 7. A genuinely open response body: JSON headers and the first bytes arrive, completion is
        # withheld past the transport deadline, the ten-second abort fires around the body read, and
        # a real subsequent Check succeeds.
        with stalled_transport(status_url,partial=True) as (stall_url,arrived):
            body_headers=[]
            def observe_body_headers(response):
                if response.url==stall_url:
                    body_headers.append((response.status,response.headers.get("content-type","")))
            page.on("response",observe_body_headers)
            try:
                stall_started=time.monotonic()
                page.evaluate("document.querySelector('[data-action=check]').click()")
                page.wait_for_selector("#reconnect-controls:not([hidden])",timeout=15000)
                stall_elapsed=time.monotonic()-stall_started
                assert not arrived.empty(),"The open-body server did not send the partial response"
                body_sent_at=arrived.get_nowait()
                assert body_headers and body_headers[0][0]==200 and "application/json" in body_headers[0][1],body_headers
                assert 9<=stall_elapsed<15,f"The open body aborted after {stall_elapsed:.2f}s instead of the ten-second deadline"
                message=page.locator("#technical-message").inner_text()
                assert "took too long" in message and "unconfirmed" in message,message
                while time.monotonic()-body_sent_at<10.2: page.wait_for_timeout(100)
                body_open_for=time.monotonic()-body_sent_at
            finally:
                page.remove_listener("response",observe_body_headers)
        page.evaluate("document.querySelector('[data-action=check]').click()")
        for _ in range(40):
            if "No accepted submission" in page.locator("#technical-message").inner_text(): break
            page.wait_for_timeout(100)
        assert "No accepted submission" in page.locator("#technical-message").inner_text()  # the guard released
        page.reload(); page.wait_for_selector("#review-card")
        assert page.locator("#reconnect-controls").is_hidden()
        assert page.locator("#review-card").get_attribute("data-state")=="question"
        checked(f"Loopback probe: response body stayed open {body_open_for:.1f}s after bytes; abort at {stall_elapsed:.1f}s stayed unconfirmed and released the check guard")
        page.wait_for_timeout(13000)
        page.get_by_role("button",name=re.compile("Speak")).click()
        page.locator("#recording-indicator").filter(has_text=re.compile("^Recording")).wait_for()
        page.wait_for_timeout(1800)
        with page.expect_response(lambda response: response.url.endswith(action_url) and response.request.method=="POST") as submission:
            stopped=time.monotonic(); page.get_by_role("button",name="Stop & check").click()
        submission_deadline=submission.value.json().get("deadline")
        page.wait_for_selector("#back:not([hidden])",timeout=15000)
        assert page.locator(".answer").inner_text()=="four"
        display=page.evaluate("""() => ({checking: document.querySelector('.recall-result h3').textContent.includes('Checking'),
            disabledNext: [...document.querySelectorAll('#back button')].some(b => b.textContent.includes('Next card') && b.disabled)})""")
        assert not display["checking"] or display["disabledNext"]
        page.screenshot(path=str(output/"checking.png"),full_page=True)
        checked("MediaRecorder upload revealed the reference while pending" if display["checking"] else "MediaRecorder upload returned a terminal result")
        # A fast success may already be terminal. The no-worker path remains pending long enough
        # to reload a real server response and hold its controller until the original deadline.
        released=None; pending_recovery_checked=False
        verdict_heading=page.locator(".recall-result h3")
        if verdict_heading.count() and "Checking" in verdict_heading.inner_text():
            navigation_url=page.url; pending_html=None
            with stalled_transport(status_url) as (status_stall_url,arrived):
                pending_response=page.reload(); page.wait_for_selector("#back:not([hidden])",timeout=15000)
                assert pending_response.status==200 and pending_response.url==navigation_url
                pending_state=page.locator("#review-card").get_attribute("data-state")
                if pending_state in ("submitted","processing"):
                    deadline_attr=page.locator("#review-card").get_attribute("data-deadline")
                    assert deadline_attr and deadline_attr==submission_deadline,(deadline_attr,submission_deadline)
                    assert "Checking" in page.locator(".recall-result h3").inner_text()
                    pending_html=pending_response.text(); pending_csp=pending_response.headers.get("content-security-policy","")
                    checked("Real pending reload retains the original submission deadline")
                    page.wait_for_selector("#reconnect-controls:not([hidden])",timeout=20000)
                    recovery_elapsed=time.monotonic()-stopped
                    assert recovery_elapsed<20,f"Recovery took {recovery_elapsed:.1f}s after Stop"
                    recovery_message=page.locator("#technical-message").inner_text()
                    assert "unconfirmed" in recovery_message or "15-second" in recovery_message,recovery_message
                    checked(f"Recovery appeared {recovery_elapsed:.1f}s after Stop while status transport was stalled")
                    assert not arrived.empty(),"No status request was stalled before the deadline"
                    script_path=page.locator("script[src$='/review.js']").get_attribute("src")
                    scripts=[]
                    def hold_script(route): scripts.append(route)
                    page.route("**"+script_path,hold_script)
                    try:
                        # The server renders pending before expiry; delay its real controller script
                        # until after expiry rather than substituting a synthetic stale HTML page.
                        pending_response=page.reload(wait_until="commit")
                        page.wait_for_selector("#review-card")
                        for _ in range(50):
                            if scripts: break
                            page.wait_for_timeout(100)
                        assert scripts,"The reloaded controller script was not held"
                        assert pending_response.status==200 and pending_response.url==navigation_url
                        pending_state=page.locator("#review-card").get_attribute("data-state")
                        if pending_state in ("submitted","processing"):
                            assert page.locator("#review-card").get_attribute("data-deadline")==deadline_attr
                            assert page.evaluate("deadline => Date.now() < Date.parse(deadline)",deadline_attr)
                            before_controller=arrived.qsize()
                            page.wait_for_function("deadline => Date.now() >= Date.parse(deadline)",arg=deadline_attr,timeout=30000)
                        else:
                            assert pending_state in ("assessed","failed"),pending_state
                        scripts.pop(0).continue_()
                    finally:
                        for route in scripts: route.abort()
                        page.unroute("**"+script_path,hold_script)
                    if pending_state in ("submitted","processing"):
                        page.wait_for_selector("#reconnect-controls:not([hidden])",timeout=5000)
                        assert "15-second" in page.locator("#technical-message").inner_text()
                        assert page.locator("#review-card").get_attribute("data-deadline")==deadline_attr
                        recovery_delay=page.evaluate("deadline => (Date.now()-Date.parse(deadline))/1000",deadline_attr)
                        assert 0<=recovery_delay<5,recovery_delay
                        for _ in range(50):
                            if arrived.qsize()>before_controller: break
                            page.wait_for_timeout(100)
                        assert arrived.qsize()>before_controller,"No status request was stalled after the real pending reload"
                        assert page.locator("#reconnect-controls").is_visible()
                        pending_recovery_checked=True
                        checked(f"Real pending reload started before the deadline; recovery appeared {recovery_delay:.1f}s after it with status still stalled")
                        # A fresh real server reload after expiry expires pending work instead of
                        # returning the synthetic stale-pending page used by earlier diagnostics.
                        pending_response=page.reload()
                        assert pending_response.status==200 and pending_response.url==navigation_url
                real_state=page.locator("#review-card").get_attribute("data-state")
                assert real_state in ("assessed","failed"),real_state
                assert page.locator("#reconnect-controls").is_hidden()
                if real_state=="failed":
                    assert page.get_by_role("button",name=re.compile("Retry")).is_visible()
                    assert page.get_by_role("button",name="Proceed unassessed").is_visible()
                else:
                    assert page.locator("#next-card").is_visible()
                checked(f"Real server reload returned {real_state} and its recovery/result controls before status was unstalled")
                if pending_html is not None:
                    page.wait_for_function("deadline => Date.now() >= Date.parse(deadline)",arg=deadline_attr,timeout=30000)
                    before_reload=arrived.qsize()
                    origin=urlsplit(navigation_url); origin=f"{origin.scheme}://{origin.netloc}"
                    # The rewritten document's CSP self is the replay server; retain access to the app origin.
                    replay_csp=pending_csp.replace("'self'",f"'self' {origin}")
                    class Replay(BaseHTTPRequestHandler):
                        def log_message(self,*args): pass
                        def do_GET(self):
                            body=pending_html.encode()
                            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
                            if replay_csp: self.send_header("Content-Security-Policy",replay_csp)
                            self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
                    replay=ThreadingHTTPServer(("127.0.0.1",0),Replay)
                    if tls: replay.socket=tls.wrap_socket(replay.socket,server_side=True)
                    replay_url=f"{loopback_scheme}://127.0.0.1:{replay.server_port}/stale"
                    replay_thread=threading.Thread(target=replay.serve_forever,daemon=True); replay_thread.start()
                    status_failures=[]
                    def observe_failure(request):
                        if request.url==status_stall_url: status_failures.append(request.failure)
                    def stale_navigation(route):
                        route.continue_(url=replay_url)
                    page.on("requestfailed",observe_failure)
                    try:
                        page.route(navigation_url,stale_navigation)
                        stale_response=page.reload(); page.wait_for_selector("#reconnect-controls:not([hidden])",timeout=15000)
                        assert stale_response.status==200 and stale_response.url==replay_url and page.url==navigation_url
                        assert page.locator("#review-card").get_attribute("data-deadline")==deadline_attr
                        assert page.evaluate("deadline => Date.now() >= Date.parse(deadline)",deadline_attr)
                        for _ in range(50):
                            if arrived.qsize()>before_reload: break
                            page.wait_for_timeout(100)
                        assert arrived.qsize()>before_reload,"No status request was stalled after the synthetic reload"
                        page.wait_for_timeout(500)
                        assert not status_failures,status_failures
                        assert page.locator("#reconnect-controls").is_visible()
                        stale_message=page.locator("#technical-message").inner_text()
                        assert "15-second" in stale_message or "unconfirmed" in stale_message,stale_message
                        checked("Synthetic stale-navigation reload after the stored deadline keeps recovery visible while status remains stalled")
                    finally:
                        try:
                            page.unroute(navigation_url,stale_navigation)
                        finally:
                            try:
                                page.remove_listener("requestfailed",observe_failure)
                            finally:
                                replay.shutdown(); replay.server_close(); replay_thread.join()
                released=time.monotonic()
            if pending_html is not None:
                page.reload(); page.wait_for_selector("#back:not([hidden])",timeout=15000)
                assert page.locator("#review-card").get_attribute("data-state")==real_state
                assert page.locator("#reconnect-controls").is_hidden()
                checked("Real server reload after releasing the synthetic stall shows the authoritative terminal state")
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            verdict=page.locator(".recall-result h3").inner_text()
            if not verdict.startswith("Checking your response"): break
            page.wait_for_timeout(500)
        assert not verdict.startswith("Checking your response"),"No completed or failed assessment within 30 seconds"
        if released is not None:
            release_elapsed=time.monotonic()-released
            assert release_elapsed<20,f"Verdict took {release_elapsed:.1f}s after the test released its stall"
            checked(f"Real verdict appeared {release_elapsed:.1f}s after the test released its stalled transport")
        scored_first=verdict in ("Correct recall","Quick recall")
        if scored_first:
            assert page.locator(".transcript").inner_text().strip()
            assert re.search(r"~(?:24 hours|[123] days?)",page.locator(".next-review").inner_text())
            assert page.locator('[data-metric="cards_today"]').inner_text()=="1"
            assert page.locator("textarea:not([readonly]),[contenteditable=true]").count()==0
            page.screenshot(path=str(output/"feedback.png"),full_page=True)
            checked("Assessment response shows D/E recall, transcript, readonly response and persisted Next review")
        else:
            assert verdict=="Not assessed",verdict
            if options.generic_only:
                assert pending_recovery_checked,"Generic timeout must exercise recovery after a real pending reload"
            # Only a deadline failure counts as the timeout branch; provider errors must fail loudly here.
            error_text=page.locator(".recall-result .quiet").first.inner_text()
            assert "expired" in error_text,error_text
            if released is None:
                elapsed=time.monotonic()-stopped
                assert elapsed<20,f"Timeout feedback took {elapsed:.1f}s after Stop"
                checked(f"Deadline failure appeared {elapsed:.1f}s after Stop")
            assert page.locator("#back button",has_text="Retry").count()==1
            assert page.locator("#back button",has_text="Proceed unassessed").count()==1
            page.screenshot(path=str(output/"feedback-timeout.png"),full_page=True)
            checked("Deadline failure offers retry and unassessed exit")
            page.get_by_role("button",name="Proceed unassessed").click()
            page.wait_for_selector("#next-card",timeout=15000)
            assert page.locator(".recall-result h3").inner_text()=="Not assessed"
        review_url=page.url
        add_generic(fixtures[1]); page.goto(review_url)
        page.locator("#next-card").click(); page.wait_for_selector("#review-card")
        if not scored_first:
            # The exited card is deferred for 30 minutes; the newly added multi-blank card is next.
            prompt=page.locator(".prompt").inner_text()
            assert "[1]" in prompt and "[2]" in prompt,prompt  # Visible blanks only; the reference stays hidden.
        page.wait_for_selector(".cloze-blank")
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
        assert page.locator("h1").inner_text()=="Nothing to practice right now."
        empty_url=page.url; page.reload(); assert page.url==empty_url
        assert page.locator("h1").inner_text()=="Nothing to practice right now."
        checked("Forgot and persisted one-minute due; temporarily empty practice rechecks availability")
        deck_id=re.search(r"/decks/(\d+)/",deck_url)[1]
        page.goto(target+"/progress/?window=all&deck="+deck_id)
        # Timeout branch: the closed_unassessed card and the Skip are excluded; the only scored
        # answer is Forgot/A, so accuracy is 0%. Success branch: D/E plus A gives 50%.
        expected_metrics=["2","2","50%"] if scored_first else ["1","1","0%"]
        metrics=page.locator(".metric").all_text_contents(); assert metrics==expected_metrics,metrics
        page.screenshot(path=str(output/"progress.png"),full_page=True)
        checked("Distinct-card/scored-review/accuracy metrics exclude Skip")
        page.goto(deck_url);page.get_by_role("button",name="Archive deck",exact=True).click()
        if options.generic_only:
            page.goto(deck_url)
            assert page.get_by_role("button",name="Restore deck",exact=True).count()==1
            assert not errors,errors
            checked("Private Generic deck archived with no browser runtime errors")
            browser.close(); write_results()
            return
        page.goto(target+"/decks/")
        page.locator("#id_name").fill("Vocabulary direction QA "+str(int(time.time())))
        page.get_by_role("button",name="Create deck").click();deck_url=page.url
        page.get_by_role("button",name="Study this deck").click()
        assert page.locator("h1").inner_text()=="Nothing to practice right now."
        empty_url=page.url
        page.goto(deck_url+"new/?kind=vocabulary")
        page.locator("#id_word").fill("compute")
        page.locator("#id_explanation").fill("Calculate a result using numbers, often with a computer.")
        page.locator("#id_target_language").select_option("English"); page.locator("#id_native_language").select_option("Chinese")
        page.get_by_role("button",name="Save",exact=False).click()
        deadline=time.monotonic()+45
        while page.get_by_role("heading",name="Current example pair").count()==0 and time.monotonic()<deadline:
            page.wait_for_timeout(900); page.reload()
        assert page.get_by_role("heading",name="Current example pair").count()==1
        checked("Vocabulary manual creation and actual durable Generator preparation")
        page.goto(empty_url);page.wait_for_selector("#review-card")
        assert page.url!=empty_url
        assert "<focus>" not in page.locator(".prompt").inner_text()
        checked("Newly Ready Vocabulary enters practice from the previously empty URL")
        cue=page.locator(".prompt").inner_text()
        page.get_by_role("button",name=re.compile("Forgot")).click();page.wait_for_selector("#next-card")
        assert page.locator(".recall-result h3").inner_text()=="Needs a refresh"
        assert "min" in page.locator(".next-review").inner_text()
        page.locator("#next-card").click()
        assert page.locator("h1").inner_text()=="Nothing to practice right now."
        deadline=time.monotonic()+75
        while page.locator("#review-card").count()==0 and time.monotonic()<deadline:
            page.wait_for_timeout(900);page.reload()
        page.wait_for_selector("#review-card")
        assert page.locator(".prompt").inner_text()==cue
        checked("Forgot Vocabulary retains its exact cue and language at the actual one-minute review")
        page.get_by_role("button",name=re.compile("Skip")).click()
        page.wait_for_selector("#next-card")
        assert page.locator(".answer").inner_text()=="compute"
        assert page.locator(".explanation").inner_text()=="Calculate a result using numbers, often with a computer."
        assert page.locator(".paired-examples p").count()==2
        assert "<focus>" not in page.locator(".paired-examples").inner_text()
        page.screenshot(path=str(output/"vocabulary-back.png"),full_page=True)
        checked("Vocabulary back retains the authored expression/English explanation and paired examples")
        page.goto(deck_url); page.get_by_role("button",name="Archive deck",exact=True).click()
        page.screenshot(path=str(output/"library.png"),full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        assert not errors,errors
        checked("Private deck archive, no horizontal overflow and no browser runtime errors")
        browser.close()
    write_results()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access-file",type=Path,required=True)
    parser.add_argument("--audio",type=Path,required=True)
    parser.add_argument("--url")
    parser.add_argument("--chromium")
    parser.add_argument("--output",type=Path,default=Path("docs/implementation/previews"))
    parser.add_argument("--generic-only",action="store_true",help="Stop after Generic metrics and deck archive.")
    options=parser.parse_args()
    if not options.audio.is_file(): parser.error("The synthetic audio fixture does not exist.")
    run(options)
