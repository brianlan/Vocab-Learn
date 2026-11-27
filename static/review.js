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
  let stoppedAt = null, deadlineAt = card.dataset.deadline ? Date.parse(card.dataset.deadline) : null,
      announced = false, checking = false;
  const started = performance.now();
  let lastPayload = "", busy = false;
  const player = $("#clip-player");
  let clipRequested = false;
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
    document.querySelectorAll("#front [data-play]").forEach(b => b.disabled = phase !== "question");
  }
  function playClip(button) {
    if (!player) return;
    clipRequested = true;
    if (player.dataset.src !== button.dataset.src) { player.dataset.src = button.dataset.src; player.src = button.dataset.src; }
    try { player.currentTime = 0; } catch (_) { /* A loading source starts from its beginning anyway. */ }
    const request = player.play();
    // Cancelled starts stay silent, but an older promise must not pause a newer permitted Play.
    if (request) request.then(() => { if (!clipRequested) player.pause(); }).catch(() => { /* Blocked or interrupted: Play stays available. */ });
  }
  function stopClip() {
    clipRequested = false;
    if (player && !player.paused) player.pause();
  }
  function toggleIllustration(region) {
    const figure = region.querySelector("[data-illustration-figure]");
    const image = figure.querySelector("img");
    // The image loads on first reveal, so a collapsed scene sends no request.
    if (figure.hidden && !image.getAttribute("src")) image.src = region.dataset.illustrationSrc;
    figure.hidden = !figure.hidden;
    const toggle = region.querySelector("[data-illustration-toggle]");
    toggle.setAttribute("aria-expanded", String(!figure.hidden));
    toggle.textContent = figure.hidden ? "Show illustration" : "Hide illustration";
  }
  // Polling replaces the answer fragment; an open, loaded or focused disclosure survives it.
  // The enclosing paired-examples panel and the revealed img element are carried over too, so
  // the scene stays visible and is never refetched.
  function illustrationState() {
    const region = $("#back [data-illustration]");
    if (!region) return null;
    const figure = region.querySelector("[data-illustration-figure]");
    const panel = region.closest("details");
    return {open: !figure.hidden, panelOpen: panel ? panel.open : false, image: figure.querySelector("img"),
        focused: document.activeElement === region.querySelector("[data-illustration-toggle]")};
  }
  function restoreIllustration(state) {
    const region = $("#back [data-illustration]");
    if (!region || !state) return false;
    const figure = region.querySelector("[data-illustration-figure]");
    // The parent panel restores to exactly its captured state: a panel the learner
    // deliberately closed stays closed, with the loaded image retained inside it.
    const panel = region.closest("details");
    if (panel) panel.open = state.panelOpen;
    if (state.image.getAttribute("src")) figure.querySelector("img").replaceWith(state.image);
    figure.hidden = !state.open;
    const toggle = region.querySelector("[data-illustration-toggle]");
    toggle.setAttribute("aria-expanded", String(state.open));
    toggle.textContent = state.open ? "Hide illustration" : "Show illustration";
    if (state.focused) { toggle.focus(); return true; }  // a held disclosure keeps focus over Next card
    return false;
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
    // The upload phase keeps a client-side window only for recovery display; the server owns the real deadline.
    stoppedAt = performance.now(); announced = false;
    $("#recording-indicator").textContent = "Saving your fixed response…";
    recorder.stop();
  }
  async function api(url, data) {
    // Bound transport and response parsing so a stalled request cannot wedge recovery.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(url, {method: data ? "POST" : "GET", body: data, signal: controller.signal,
        headers: data ? {"X-CSRFToken": csrf()} : {}, credentials: "same-origin"});
      if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("Your session may have expired. Reload or log in, then resume this question.");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "The server could not confirm this request.");
      return result;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The server took too long to respond. Its outcome stays unconfirmed; check again shortly.");
      throw error;
    } finally { clearTimeout(timer); }
  }
  const terminal = () => ["assessed", "skipped", "closed_unassessed"].includes(phase);
  const overdue = () => deadlineAt !== null && Date.now() >= deadlineAt && !terminal();
  const uploadOverdue = () => phase === "uploading" && stoppedAt !== null && performance.now()-stoppedAt >= 15000;
  function announceOverdue() {
    // Overdue recovery stays visible across late pending responses and reloads until a terminal
    // result or a confirmed new execution (whose fresh deadline clears the overdue state) arrives.
    $("#reconnect-controls").hidden = false;
    if (!announced) { announced = true; tell("This is taking longer than the 15-second assessment budget. You can keep waiting or use the recovery options."); }
  }
  function show(data) {
    if (data.state === "not_submitted") { tell("No accepted submission is visible yet. Retry the same submission; do not replace its recording."); return; }
    phase = data.state; $("#front").hidden = true; $("#back").hidden = false;
    $("#clock-recovery").hidden = true;
    stoppedAt = null;
    deadlineAt = data.deadline ? Date.parse(data.deadline) : null;
    if (deadlineAt !== null && Date.now() < deadlineAt) announced = false;  // A confirmed new execution restarts announcements.
    let disclosureFocused = false;
    if (data.back_html !== lastPayload) {
      const disclosure = illustrationState();
      $("#back").innerHTML = data.back_html;
      disclosureFocused = restoreIllustration(disclosure);
      lastPayload = data.back_html;
    }
    for (const [name,value] of Object.entries(data.metrics || {})) {
      document.querySelectorAll('[data-metric="'+name+'"]').forEach(node => { node.textContent = value ?? "—"; });
    }
    const collection = document.querySelector("[data-collection-label]");
    if (collection && data.collection) { collection.textContent = data.collection === "Forgot" ? "Forgot collection" : "Normal review"; collection.classList.toggle("warm", data.collection === "Forgot"); }
    try { localStorage.removeItem(key); } catch (_) { /* Submitted timing is durable on the server. */ }
    if (["submitted", "processing"].includes(phase)) startPolling();
    else { clearInterval(polling); polling = null; deadlineAt = null; }
    if (!terminal()) {
      if (overdue()) announceOverdue();
      else { $("#reconnect-controls").hidden = true; tell(""); }
    } else { $("#reconnect-controls").hidden = true; announced = false; if (["assessed", "skipped", "closed_unassessed"].includes(phase) && !disclosureFocused) $("#next-card")?.focus(); }
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
  async function check() {
    if (checking) return;
    checking = true;
    try { show(await api(card.dataset.statusUrl)); } catch (error) { reconnect(error.message); }
    finally { checking = false; }
  }
  function startPolling() { if (!polling) polling = setInterval(check, 1200); }
  $("#clock-recovery form").addEventListener("submit", stopClip);
  card.addEventListener("click", async event => {
    if (event.target.closest("#next-card, [data-pronounce]")) { stopClip(); return; }
    // Show and Hide stay separate from playback and review actions: neither pauses the clip.
    const illustrationToggle = event.target.closest("[data-illustration-toggle]");
    if (illustrationToggle) { toggleIllustration(illustrationToggle.closest("[data-illustration]")); return; }
    const playButton = event.target.closest("[data-play]");
    if (playButton) {
      if (!playButton.disabled && !busy) playClip(playButton);
      return;
    }
    const button = event.target.closest("[data-action]");
    if (!button || button.disabled || busy) return;
    stopClip();  // Every Practice control pauses the clip and cancels a pending start.
    const action = button.dataset.action;
    if (action === "speak") { speak(); return; }
    if (action === "cancel") { cancel(); return; }
    if (action === "stop") { stop(); return; }
    if (["skip", "forgot"].includes(action) && phase === "question") { saveClock(); submit(action); return; }
    if (action === "check") { check(); return; }
    if (action === "resend") {
      // An ambiguous replay never resets the deadline; the server returns the original attempt unchanged.
      if (frozenAction) submit(frozenAction); else check();
      return;
    }
    busy = true; button.disabled = true;
    try {
      if (action === "retry") show(await api(card.dataset.retryUrl, new URLSearchParams()));
      if (action === "exit") show(await api(card.dataset.exitUrl, new URLSearchParams()));
    } catch (error) { reconnect(error.message); }
    finally { busy = false; button.disabled = false; }
  });
  if (phase === "question") readClock();
  else if (["submitted", "processing"].includes(phase)) startPolling();
  // One autoplay attempt per new question: first display only, when the learner allows it
  // and the visible side's clip is ready. A blocked attempt leaves manual Play available.
  if (phase === "question" && card.dataset.firstDisplay === "1" && card.dataset.autoplay === "1") {
    const auto = $("#front [data-play]");
    if (auto) playClip(auto);
  }
  setInterval(() => {
    saveClock();
    if (!terminal() && (overdue() || uploadOverdue())) { announceOverdue(); check(); }
    if (phase === "recording" && recorder) {
      const seconds = Math.floor((performance.now()-recorder.started)/1000);
      $("#recording-indicator").textContent = "Recording · " + Math.floor(seconds/60) + ":" + String(seconds%60).padStart(2,"0");
      if (seconds >= 500) { cancel(); tell("The 500-second recording limit was reached. Please record a shorter answer. Nothing was submitted."); }
    }
  }, 300);
  window.addEventListener("pagehide", () => { saveClock(); stopClip(); ++acquisition; if (recorder) recorder.discarded = true; stopTracks(stream); });
})();
