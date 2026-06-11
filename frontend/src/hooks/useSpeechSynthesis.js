import { useCallback, useEffect, useRef } from "react";
import useInterviewStore from "../store/interviewStore";

export default function useSpeechSynthesis() {
  const setSpeaking = useInterviewStore((s) => s.setSpeaking);
  const utteranceRef = useRef(null);
  const voiceRef     = useRef(null);

  // Pre-load a natural English voice once voices are available
  useEffect(() => {
    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      voiceRef.current =
        voices.find((v) => v.name.includes("Google US English")) ||
        voices.find((v) => v.lang === "en-US" && !v.localService) ||
        voices.find((v) => v.lang.startsWith("en")) ||
        voices[0] ||
        null;
    };

    pickVoice();
    window.speechSynthesis.addEventListener("voiceschanged", pickVoice);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", pickVoice);
  }, []);

  const speak = useCallback(
    (text, { rate = 1.0, pitch = 1.0, onEnd } = {}) => {
      if (!window.speechSynthesis) return;
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.voice  = voiceRef.current;
      utterance.rate   = rate;
      utterance.pitch  = pitch;
      utterance.volume = 1;

      utterance.onstart = () => setSpeaking(true);
      utterance.onend   = () => {
        setSpeaking(false);
        onEnd?.();
      };
      // "interrupted"/"canceled" fires when we explicitly cancel() — don't advance phase.
      // Any other error (synthesis-failed, network, etc.) must still advance phase so
      // the interview doesn't get permanently stuck with the button disabled.
      utterance.onerror = (e) => {
        setSpeaking(false);
        if (e.error !== "interrupted" && e.error !== "canceled") {
          onEnd?.();
        }
      };

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [setSpeaking]
  );

  const cancel = useCallback(() => {
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [setSpeaking]);

  return { speak, cancel };
}
