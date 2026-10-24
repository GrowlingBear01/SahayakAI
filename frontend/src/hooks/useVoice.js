import { useCallback, useEffect, useRef, useState } from "react";
import { recognitionLocale, resolvedLang } from "../utils/messages.js";

function getRecognitionCtor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function pickVoice(voices, lang) {
  const locale = recognitionLocale(lang).toLowerCase();
  const prefix = locale.slice(0, 2);
  const named = voices.filter((voice) => voice.lang?.toLowerCase().startsWith(prefix));
  const preferred = named.find((voice) => voice.lang?.toLowerCase() === locale);
  return preferred || named[0] || voices[0] || null;
}

export function useVoice({ language, onFinal, onInterim, enabled = true } = {}) {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voices, setVoices] = useState([]);
  const [support, setSupport] = useState({
    recognition: false,
    speech: false,
    permission: "unknown",
  });

  const recognitionRef = useRef(null);
  const lastSpokenRef = useRef("");
  const onFinalRef = useRef(onFinal);
  const onInterimRef = useRef(onInterim);
  onFinalRef.current = onFinal;
  onInterimRef.current = onInterim;

  useEffect(() => {
    const Ctor = getRecognitionCtor();
    const speech = typeof window !== "undefined" && "speechSynthesis" in window;
    setSupport((current) => ({ ...current, recognition: Boolean(Ctor), speech }));

    if (!speech) return undefined;
    const load = () => setVoices(window.speechSynthesis.getVoices() || []);
    load();
    window.speechSynthesis.addEventListener?.("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener?.("voiceschanged", load);
  }, []);

  const stopSpeech = useCallback(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text, { lang, key } = {}) => {
      if (!text || typeof window === "undefined" || !window.speechSynthesis) return false;
      if (key && lastSpokenRef.current === key) return false;
      const utterance = new SpeechSynthesisUtterance(text);
      const resolved = resolvedLang(lang || language);
      utterance.lang = recognitionLocale(resolved);
      const voice = pickVoice(voices, resolved);
      if (voice) utterance.voice = voice;
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
      setSpeaking(true);
      if (key) lastSpokenRef.current = key;
      return true;
    },
    [language, voices],
  );

  const stopListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        recognition.stop();
      } catch {
        /* already stopped */
      }
    }
    recognitionRef.current = null;
    setListening(false);
  }, []);

  const startListening = useCallback(async () => {
    if (!enabled) return;
    const Ctor = getRecognitionCtor();
    if (!Ctor) {
      setSupport((current) => ({ ...current, recognition: false }));
      return;
    }

    stopSpeech();
    stopListening();

    if (navigator.permissions?.query) {
      try {
        const status = await navigator.permissions.query({ name: "microphone" });
        setSupport((current) => ({ ...current, permission: status.state }));
        if (status.state === "denied") return;
      } catch {
        /* Safari and some Chromium builds omit microphone from permissions */
      }
    }

    const recognition = new Ctor();
    recognition.lang = recognitionLocale(language);
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setListening(true);
    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
    };
    recognition.onerror = (event) => {
      const err = event?.error;
      if (err === "not-allowed") {
        setSupport((current) => ({ ...current, permission: "denied" }));
      }
      setListening(false);
      recognitionRef.current = null;
    };
    recognition.onresult = (event) => {
      let interim = "";
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript || "";
        if (result.isFinal) finalText += text;
        else interim += text;
      }
      if (interim) onInterimRef.current?.(interim);
      if (finalText) onFinalRef.current?.(finalText.trim());
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setListening(false);
    }
  }, [enabled, language, stopListening, stopSpeech]);

  useEffect(
    () => () => {
      stopListening();
      stopSpeech();
    },
    [stopListening, stopSpeech],
  );

  return {
    listening,
    speaking,
    support,
    voices,
    startListening,
    stopListening,
    speak,
    stopSpeech,
  };
}
