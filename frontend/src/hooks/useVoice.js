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
  return preferred || named[0] || null;
}

export function useVoice({ language, onFinal, onInterim, enabled = true } = {}) {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voices, setVoices] = useState([]);
  const [error, setError] = useState(null);
  const [support, setSupport] = useState({
    recognition: false,
    speech: false,
    permission: "unknown",
  });

  const recognitionRef = useRef(null);
  const listeningAttemptRef = useRef(0);
  const mountedRef = useRef(true);
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
    (text, { lang, key, fallbackText } = {}) => {
      if (!text || typeof window === "undefined" || !window.speechSynthesis) return false;
      if (key && lastSpokenRef.current === key) return false;
      let utteranceText = text;
      let resolved = resolvedLang(lang || language);
      let voice = pickVoice(voices, resolved);

      if (resolved === "hi" && voices.length > 0 && !voice) {
        if (!fallbackText) return false;
        utteranceText = fallbackText;
        resolved = "en";
        voice = pickVoice(voices, resolved);
        if (!voice) return false;
      } else if (!voice && resolved === "en") {
        voice = voices[0] || null;
      }

      const utterance = new SpeechSynthesisUtterance(utteranceText);
      utterance.lang = recognitionLocale(resolved);
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
    listeningAttemptRef.current += 1;
    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        recognition.stop();
      } catch {
        recognitionRef.current = null;
      }
    }
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
    setError(null);
    const attempt = ++listeningAttemptRef.current;

    if (navigator.permissions?.query) {
      try {
        const status = await navigator.permissions.query({ name: "microphone" });
        setSupport((current) => ({ ...current, permission: status.state }));
        if (attempt !== listeningAttemptRef.current) return;
        if (status.state === "denied") {
          setError("micDenied");
          return;
        }
      } catch {
        /* Safari and some Chromium builds omit microphone from permissions */
      }
    }
    if (attempt !== listeningAttemptRef.current || !enabled) return;

    const recognition = new Ctor();
    recognition.lang = recognitionLocale(language);
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      if (mountedRef.current && recognitionRef.current === recognition) setListening(true);
    };
    recognition.onend = () => {
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
        if (mountedRef.current) setListening(false);
      }
    };
    recognition.onerror = (event) => {
      if (!mountedRef.current || recognitionRef.current !== recognition) return;
      const err = event?.error;
      if (err === "not-allowed") {
        setSupport((current) => ({ ...current, permission: "denied" }));
        setError("micDenied");
      } else if (err === "audio-capture") {
        setError("micUnavailable");
      } else if (err === "network") {
        setError("speechNetwork");
      } else if (err === "no-speech") {
        setError("speechNoSpeech");
      } else if (err !== "aborted") {
        setError("speechRecognitionFailed");
      }
      if (recognitionRef.current === recognition) {
        setListening(false);
        recognitionRef.current = null;
      }
    };
    recognition.onresult = (event) => {
      if (!mountedRef.current || recognitionRef.current !== recognition) return;
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
      recognitionRef.current = null;
      setError("speechRecognitionFailed");
    }
  }, [enabled, language, stopListening, stopSpeech]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopListening();
      stopSpeech();
    };
  }, [stopListening, stopSpeech]);

  return {
    listening,
    speaking,
    error,
    support,
    voices,
    startListening,
    stopListening,
    speak,
    stopSpeech,
  };
}
