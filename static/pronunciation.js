"use strict";
(() => {
  const speech = window.speechSynthesis;
  const locales = {English: "en-us", Spanish: "es-es"};
  const unavailable = "Pronunciation unavailable.";
  let current = null;

  function report(message) {
    const status = document.querySelector("[data-pronunciation-status]");
    if (status) status.textContent = message;
  }

  function stop() {
    if (!current) return;
    current = null;
    speech.cancel();
  }

  // Give the browser time to discover its voices before the first click.
  speech?.getVoices();
  document.addEventListener("click", event => {
    const button = event.target.closest("[data-pronounce]");
    if (!button) return;

    const locale = locales[button.dataset.pronounceLanguage];
    if (!speech || !window.SpeechSynthesisUtterance || !locale) {
      report(unavailable);
      return;
    }

    try {
      stop();
      const voices = speech.getVoices();
      const language = locale.split("-")[0];
      const voice = voices.find(item => item.lang.toLowerCase() === locale)
        ?? voices.find(item => item.lang.toLowerCase().split("-")[0] === language);
      if (!voice) {
        report(unavailable);
        return;
      }

      const utterance = new SpeechSynthesisUtterance(button.dataset.pronounce);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.onend = utterance.onerror = event => {
        if (current !== utterance) return;
        current = null;
        if (event.type === "error") report(unavailable);
      };
      report("");
      current = utterance;
      speech.speak(utterance);
    } catch (_) {
      current = null;
      report(unavailable);
    }
  });
  window.addEventListener("pagehide", stop);
})();
