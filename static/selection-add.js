"use strict";
(() => {
  const bootstrap = document.querySelector("#selection-add-config");
  const ui = document.querySelector("#selection-add");
  if (!bootstrap || !ui) return;
  let config;
  try { config = JSON.parse(bootstrap.textContent); } catch (_) { return; }
  if (!config.enabled) return;
  const $ = id => document.getElementById("selection-add-" + id);
  const picker = $("picker"), deckSelect = $("deck"), languageSelect = $("language");
  const feedback = $("feedback"), status = $("status"), retry = $("retry");
  const decks = new Map(config.decks.map(deck => [deck.id, deck.name]));
  const pairs = config.language_pairs;
  const unavailable = new Set();
  const storageKey = "vocab-selection-deck:" + config.user_id;
  const blocked = 'a,button,input,textarea,select,option,summary,label,nav,[role="navigation"],[role="button"],[role="link"],[role="textbox"],[contenteditable]:not([contenteditable="false"]),[hidden],[inert],[aria-hidden="true"],script,style';
  let enabled = true, remembered = null, current = null, dismissedRange = null;
  let pending = false, failed = null, pointerInside = false;
  const validDeck = id => decks.has(Number(id)) && !unavailable.has(Number(id));
  try {
    const stored = Number(localStorage.getItem(storageKey));
    if (Number.isSafeInteger(stored) && stored > 0 && validDeck(stored)) remembered = stored;
  } catch (_) { /* Accepted destinations still live in page memory. */ }
  for (const [id, name] of decks) deckSelect.add(new Option(name, String(id)));
  pairs.forEach((pair, index) => languageSelect.add(new Option(pair.join(" → "), String(index))));
  $("create-deck").href = config.create_deck_url;
  $("settings").href = $("disabled-settings").href = config.settings_url;

  function sameRange(a, b) {
    return a && b && a.startContainer === b.startContainer && a.startOffset === b.startOffset &&
      a.endContainer === b.endContainer && a.endOffset === b.endOffset;
  }
  function hidden(element) {
    const style = getComputedStyle(element);
    return style.display === "none" || style.visibility !== "visible" || style.opacity === "0" || style.contentVisibility === "hidden";
  }
  function capture() {
    if (!enabled) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount !== 1) {
      if (pointerInside || ui.contains(document.activeElement) || feedback.contains(document.activeElement)) return;
      dismiss(); dismissedRange = null; return;
    }
    if (ui.contains(selection.anchorNode) || feedback.contains(selection.anchorNode)) return;
    const range = selection.getRangeAt(0);
    const element = node => node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    const region = element(range.startContainer)?.closest("[data-selection-region]");
    if (!region || region !== element(range.endContainer)?.closest("[data-selection-region]") || region.closest(blocked)) {
      dismiss(); return;
    }
    for (let ancestor = region; ancestor; ancestor = ancestor.parentElement) {
      if (hidden(ancestor)) { dismiss(); return; }
    }
    for (const node of region.querySelectorAll("*")) {
      if (range.intersectsNode(node) && (node.matches(blocked + ",[data-selection-region]") || hidden(node))) {
        dismiss(); return;
      }
    }
    const text = selection.toString().replace(/\s+/gu, " ").trim();
    const language = region.dataset.selectionLanguage || "";
    if (!text || (language && !pairs.some(pair => pair[0] === language))) { dismiss(); return; }
    if (sameRange(range, dismissedRange)) return;
    if (current && sameRange(range, current.range) && current.text === text && current.region === region) {
      position(); return;
    }
    const pair = pairs.findIndex(pair => pair[0] === (language || config.target_language) && pair[1] === config.native_language);
    current = {text, region, range: range.cloneRange(), deck: remembered, pair: pair < 0 ? "" : String(pair), focusOrigin: document.activeElement};
    dismissedRange = null;
    picker.hidden = true;
    render();
  }
  function dismiss() {
    if (current) dismissedRange = current.range.cloneRange();
    current = null;
    ui.hidden = true;
    picker.hidden = true;
    $("toggle").setAttribute("aria-expanded", "false");
  }
  function position() {
    if (!current) return;
    let rect = current.range.getBoundingClientRect();
    if (rect.width && rect.height) current.anchor = rect;
    // Polling may replace the answer node while the picker still owns its captured text.
    else if (!picker.hidden && current.anchor) rect = current.anchor;
    const margin = 8, gap = 8, width = window.innerWidth, height = window.innerHeight;
    if (!rect.width || !rect.height || rect.bottom < 0 || rect.top > height || rect.right < 0 || rect.left > width) {
      ui.hidden = true; return;
    }
    ui.hidden = false;
    ui.style.maxHeight = (height - margin * 2) + "px";
    const w = ui.offsetWidth;
    let h = ui.offsetHeight;
    const clamp = (value, max) => Math.max(margin, Math.min(value, max - margin));
    const below = height - margin - rect.bottom - gap, above = rect.top - gap - margin;
    let x = clamp(rect.left, width - w), y;
    if (below >= h) y = rect.bottom + gap;
    else if (above >= h) y = rect.top - gap - h;
    else if (width - margin - rect.right - gap >= w) { x = rect.right + gap; y = clamp(rect.top, height - h); }
    else if (rect.left - gap - margin >= w) { x = rect.left - gap - w; y = clamp(rect.top, height - h); }
    else {
      const room = Math.max(below, above);
      if (room < 44) { ui.hidden = true; return; }
      ui.style.maxHeight = room + "px";
      h = ui.offsetHeight;
      y = below >= above ? rect.bottom + gap : rect.top - gap - h;
    }
    ui.style.left = x + "px";
    ui.style.top = y + "px";
  }
  function render() {
    retry.disabled = pending;
    if (!current || !enabled) return;
    const hasDeck = validDeck(current.deck);
    $("submit").textContent = hasDeck ? "Add to " + decks.get(Number(current.deck)) : "Choose a deck";
    $("submit").title = $("submit").textContent;
    $("submit").disabled = pending;
    $("expression").textContent = current.text;
    deckSelect.value = hasDeck ? String(current.deck) : "";
    for (const option of deckSelect.options) option.disabled = unavailable.has(Number(option.value));
    const noDecks = ![...decks.keys()].some(validDeck);
    deckSelect.disabled = noDecks;
    $("no-decks").hidden = !noDecks;
    languageSelect.value = current.pair;
    $("hint").textContent = [...current.text].length > 500 ? "Select at most 500 characters; reselect a shorter expression." :
      !pairs[current.pair] ? "Choose a supported language pair for this text." : "Temporary language choices apply only to this add.";
    $("toggle").setAttribute("aria-expanded", String(!picker.hidden));
    ui.classList.toggle("is-open", !picker.hidden);
    position();
  }
  function openPicker() {
    if (!current) return;
    picker.hidden = false;
    render();
    (validDeck(current.deck) && !pairs[current.pair] ? languageSelect : deckSelect.disabled ? languageSelect : deckSelect).focus({preventScroll: true});
  }
  async function submit(snapshot) {
    if (pending || !enabled) return;
    pending = true; failed = null;
    feedback.hidden = false;
    $("feedback-expression").textContent = snapshot.payload.text;
    $("feedback-destination").textContent = "To " + snapshot.deckName + " · " + snapshot.payload.target_language + " → " + snapshot.payload.native_language;
    status.textContent = "Adding to " + snapshot.deckName + "…";
    for (const id of ["retry", "card-link", "disabled-settings", "reload"]) $(id).hidden = true;
    render();
    try {
      const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
      if (!csrf) throw new Error("Reload this page to refresh your session before retrying.");
      const response = await fetch(config.create_url, {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf}, body: JSON.stringify(snapshot.payload)});
      if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("Your session may have expired. Reload or sign in before retrying.");
      const result = await response.json();
      if (!response.ok) {
        const error = new Error(result.error || "The server could not confirm this add.");
        error.code = result.code;
        throw error;
      }
      if (![200, 201].includes(response.status) || typeof result.created !== "boolean" || typeof result.archived !== "boolean" || typeof result.card_url !== "string") {
        throw new Error("The server could not confirm this add.");
      }
      remembered = snapshot.payload.deck_id;
      try { localStorage.setItem(storageKey, String(remembered)); } catch (_) { /* Keep the accepted page-local destination. */ }
      status.textContent = (result.created ? "Added to " + snapshot.deckName + " · Preparing" : "Already in " + snapshot.deckName) + (result.archived ? " · Archived (not restored)" : "");
      const cardURL = new URL(result.card_url, window.location.href);
      if (cardURL.origin === window.location.origin && ["http:", "https:"].includes(cardURL.protocol)) {
        $("card-link").href = cardURL.href;
        $("card-link").textContent = result.created ? "View card" : "View existing card";
        $("card-link").hidden = false;
      }
    } catch (error) {
      if (error.code === "disabled") {
        enabled = false; dismiss();
        feedback.hidden = false;
        status.textContent = "Selection add is disabled. Enable it in Settings, then reload this page.";
        $("disabled-settings").hidden = false;
      } else if (error.code === "invalid_deck") {
        unavailable.add(snapshot.payload.deck_id);
        if (remembered === snapshot.payload.deck_id) remembered = null;
        status.textContent = "This deck is no longer available. Choose another deck or reload the choices.";
        $("reload").hidden = false;
      } else {
        failed = snapshot;
        status.textContent = (error.message || "The add could not be confirmed.") + " Retry sends the same expression, deck and languages.";
        retry.hidden = false;
      }
    } finally {
      pending = false;
      render();
    }
  }
  $("submit").addEventListener("click", () => {
    if (!current || pending) return;
    if (!validDeck(current.deck) || !pairs[current.pair] || [...current.text].length > 500) { openPicker(); return; }
    const pair = pairs[current.pair];
    submit(Object.freeze({deckName: decks.get(Number(current.deck)), payload: Object.freeze({
      deck_id: Number(current.deck), text: current.text, target_language: pair[0], native_language: pair[1],
    })}));
  });
  $("toggle").addEventListener("click", () => {
    if (picker.hidden) openPicker();
    else { picker.hidden = true; render(); }
  });
  deckSelect.addEventListener("change", () => { if (current) { current.deck = deckSelect.value ? Number(deckSelect.value) : null; render(); } });
  languageSelect.addEventListener("change", () => { if (current) { current.pair = languageSelect.value; render(); } });
  retry.addEventListener("click", () => { if (failed) submit(failed); });
  $("dismiss-feedback").addEventListener("click", () => { feedback.hidden = true; });
  document.addEventListener("pointerdown", event => {
    pointerInside = ui.contains(event.target) || feedback.contains(event.target);
    if (!pointerInside) {
      dismiss();
      if (event.target.closest("[data-selection-region]")) dismissedRange = null;
    }
  }, true);
  document.addEventListener("pointerup", () => { pointerInside = false; });
  document.addEventListener("selectionchange", capture);
  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    const origin = ui.contains(document.activeElement) ? current?.focusOrigin : null;
    dismiss();
    feedback.hidden = true;
    if (origin?.isConnected) origin.focus({preventScroll: true});
  });
  window.addEventListener("resize", position);
  document.addEventListener("scroll", position, true);
})();
