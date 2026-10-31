"use strict";
(() => {
  const card = document.querySelector("#review-card");
  if (!card) return;
  const $ = s => document.querySelector(s);
  const key = "vocab-clock:" + card.dataset.presentation;
  const csrf = () => document.querySelector("input[name=csrfmiddlewaretoken]").value;
  let phase = card.dataset.state, recorder = null, stream = null, acquisition = 0;
  let frozenBlob = null, frozenDuration = null, frozenAction = null, polling = null;
  let baseElapsed = 0, excluded = 0, waitStart = null, clockLost = false;
  const started = performance.now();
  let lastPayload = "", busy = false;
  const tell = message => { $("#technical-message").textContent = message; $("#technical-message").hidden = !message; };
  const elapsed = () => baseElapsed + (performance.now()-started)/1000-excluded-(waitStart === null ? 0 : (performance.now()-waitStart)/1000);
  function saveClock() {
    if (phase !== "question" && phase !== "permission" && phase !== "recording") return;
    try { localStorage.setItem(key, JSON.stringify({elapsed: elapsed(), savedAt: Date.now(), waiting: waitStart !== null})); } catch (_) { /* A reload will explicitly restart an unavailable clock. */ }
  }
  function readClock() {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) { if (card.dataset.firstDisplay !== "1") throw new Error(); saveClock(); return; }
      const old = JSON.parse(raw), gap = (Date.now()-old.savedAt)/1000;
      if (old.waiting || old.pending || !Number.isFinite(old.elapsed) || !Number.isFinite(gap) || gap < 0 || old.elapsed < 0) throw new Error();
      baseElapsed = old.elapsed+gap;
    } catch (_) { clockLost = true; $("#clock-recovery").hidden = false; $("#speak").disabled = true; }
  }
  function frontControls() {
    $(".front-actions").hidden = phase !== "question";
    $("#record-controls").hidden = !["recording", "permission"].includes(phase);
    $("#stop").hidden = phase !== "recording";
    $("#recording-indicator").classList.toggle("recording", phase === "recording");
  }
  function endPermission() {
    if (waitStart !== null) { excluded += (performance.now()-waitStart)/1000; waitStart = null; }
  }
  function stopTracks(owned) { if (owned) owned.getTracks().forEach(t => t.stop()); }
  function rememberPending() {
    try { localStorage.setItem(key, JSON.stringify({elapsed: frozenDuration ?? elapsed(), savedAt: Date.now(), waiting: false, pending: true})); } catch (_) { /* Reload will require explicit clock recovery. */ }
  }
  async function speak() {
    if (phase !== "question" || clockLost) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      tell("Recording is unavailable. Use desktop Chrome or Edge on localhost or your trusted private HTTPS address."); return;
    }
    const id = ++acquisition;
    phase = "permission"; waitStart = performance.now(); saveClock(); frontControls(); tell("");
    $("#recording-indicator").textContent = "Waiting for microphone permission. You can Cancel.";
    try {
      const owned = await navigator.mediaDevices.getUserMedia({audio: true});
      if (id !== acquisition || phase !== "permission") { stopTracks(owned); return; }
      stream = owned; endPermission();
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find(t => MediaRecorder.isTypeSupported(t));
      const active = new MediaRecorder(owned, mime ? {mimeType: mime} : undefined);
      recorder = active;
      const chunks = [];
      active.discarded = false;
      active.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      active.onerror = () => { active.discarded = true; stopTracks(owned); phase = "question"; tell("The recording device stopped unexpectedly. Try again; no answer has been submitted."); frontControls(); };
      active.onstop = async () => {
        stopTracks(owned);
        if (active.discarded) return;
        frozenBlob = new Blob(chunks, {type: active.mimeType});
        await submit("speak");
      };
      phase = "recording"; active.started = performance.now(); active.start(1000); frontControls(); saveClock();
    } catch (_) {
      if (id !== acquisition) return;
      endPermission(); stopTracks(stream); phase = "question"; frontControls(); saveClock();
      $("#recording-indicator").textContent = "";
      tell("Microphone access was denied or no device is available. Check browser permissions, then try Speak again, Skip or Forgot.");
    }
  }
  function cancel() {
    ++acquisition; endPermission();
    if (recorder && recorder.state !== "inactive") { recorder.discarded = true; recorder.stop(); }
    stopTracks(stream); recorder = null; stream = null; phase = "question";
    $("#recording-indicator").textContent = ""; frontControls(); saveClock(); $("#speak").focus();
  }
  function stop() {
    if (phase !== "recording") return;
    frozenDuration = elapsed(); rememberPending(); phase = "uploading"; frontControls();
    $("#recording-indicator").textContent = "Saving your fixed response…";
    recorder.stop();
  }
  async function api(url, data) {
    const response = await fetch(url, {method: data ? "POST" : "GET", body: data,
      headers: data ? {"X-CSRFToken": csrf()} : {}, credentials: "same-origin"});
    if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("Your session may have expired. Reload or log in, then resume this question.");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The server could not confirm this request.");
    return result;
  }
  function show(data) {
    if (data.state === "not_submitted") { tell("No accepted submission is visible yet. Retry the same submission; do not replace its recording."); return; }
    phase = data.state; $("#front").hidden = true; $("#back").hidden = false;
    $("#clock-recovery").hidden = true; $("#reconnect-controls").hidden = true; tell("");
    if (data.back_html !== lastPayload) { $("#back").innerHTML = data.back_html; lastPayload = data.back_html; }
    for (const [name,value] of Object.entries(data.metrics || {})) {
      document.querySelectorAll('[data-metric="'+name+'"]').forEach(node => { node.textContent = value ?? "—"; });
    }
    const collection = document.querySelector("[data-collection-label]");
    if (collection && data.collection) { collection.textContent = data.collection === "Forgot" ? "Forgot collection" : "Normal review"; collection.classList.toggle("warm", data.collection === "Forgot"); }
    try { localStorage.removeItem(key); } catch (_) { /* Submitted timing is durable on the server. */ }
    if (["submitted", "processing"].includes(phase)) startPolling();
    else { clearInterval(polling); polling = null; if (["assessed", "skipped", "closed_unassessed"].includes(phase)) $("#next-card")?.focus(); }
  }
  function reconnect(message) {
    tell(message + " The server outcome is unconfirmed. Check status or retry the same request.");
    $("#reconnect-controls").hidden = false;
  }
  async function submit(action) {
    frozenAction = action;
    rememberPending();
    const body = new FormData(); body.append("action", action);
    if (action === "speak") {
      body.append("audio", frozenBlob, "response.webm"); body.append("duration", String(frozenDuration));
    }
    phase = "uploading"; frontControls();
    try { show(await api(card.dataset.actionUrl, body)); } catch (error) { reconnect(error.message); }
  }
  async function check() { try { show(await api(card.dataset.statusUrl)); } catch (error) { reconnect(error.message); } }
  function startPolling() { if (!polling) polling = setInterval(check, 1200); }
  card.addEventListener("click", async event => {
    const button = event.target.closest("[data-action]");
    if (!button || button.disabled || busy) return;
    const action = button.dataset.action;
    if (action === "speak") { speak(); return; }
    if (action === "cancel") { cancel(); return; }
    if (action === "stop") { stop(); return; }
    if (["skip", "forgot"].includes(action) && phase === "question") { saveClock(); submit(action); return; }
    if (action === "check") { check(); return; }
    if (action === "resend") { if (frozenAction) submit(frozenAction); else check(); return; }
    busy = true; button.disabled = true;
    try {
      if (action === "retry") show(await api(card.dataset.retryUrl, new URLSearchParams()));
      if (action === "exit") show(await api(card.dataset.exitUrl, new URLSearchParams()));
    } catch (error) { reconnect(error.message); }
    finally { busy = false; button.disabled = false; }
  });
  if (phase === "question") readClock();
  else if (["submitted", "processing"].includes(phase)) startPolling();
  setInterval(() => {
    saveClock();
    if (phase === "recording" && recorder) {
      const seconds = Math.floor((performance.now()-recorder.started)/1000);
      $("#recording-indicator").textContent = "Recording · " + Math.floor(seconds/60) + ":" + String(seconds%60).padStart(2,"0");
      if (seconds >= 500) { cancel(); tell("The 500-second recording limit was reached. Please record a shorter answer. Nothing was submitted."); }
    }
  }, 300);
  window.addEventListener("pagehide", () => { saveClock(); ++acquisition; if (recorder) recorder.discarded = true; stopTracks(stream); });
})();
