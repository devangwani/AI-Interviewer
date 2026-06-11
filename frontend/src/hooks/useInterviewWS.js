/**
 * useInterviewWS.js
 * ──────────────────
 * Manages the single WebSocket connection to
 *   /api/v1/interviews/ws/{sessionId}
 *
 * Sends:
 *   · Raw PCM Int16 audio bytes         mic → Deepgram on the server
 *   · { type: "video_frame", data }     base64 JPEG every 3 s → CNN
 *   · { type: "end_answer" }            candidate finished speaking
 *   · { type: "ping" }                  keepalive
 *
 * Receives:
 *   · ai_question, transcript, generating_report, interview_complete, error
 */

import { useRef, useCallback, useEffect } from "react";
import useInterviewStore from "../store/interviewStore";

const WS_BASE           = import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000";
const FRAME_INTERVAL_MS = 3000;   // send one frame every 3 seconds

export default function useInterviewWS({
  sessionId,
  onQuestion,           // (text, questionIndex, totalQuestions) => void
  onGeneratingReport,   // () => void
  onComplete,           // (sessionId, overallScore) => void
  onError,              // (message) => void
}) {
  const wsRef         = useRef(null);
  const processorRef  = useRef(null);
  const audioCtxRef   = useRef(null);
  const frameTimerRef = useRef(null);
  const canvasRef     = useRef(null);

  // Use refs for callbacks so the WebSocket message handler never goes stale
  // even when the parent component re-renders with new closures.
  const onQuestionRef         = useRef(onQuestion);
  const onGeneratingReportRef = useRef(onGeneratingReport);
  const onCompleteRef         = useRef(onComplete);
  const onErrorRef            = useRef(onError);

  useEffect(() => { onQuestionRef.current         = onQuestion;         }, [onQuestion]);
  useEffect(() => { onGeneratingReportRef.current = onGeneratingReport; }, [onGeneratingReport]);
  useEffect(() => { onCompleteRef.current         = onComplete;         }, [onComplete]);
  useEffect(() => { onErrorRef.current            = onError;            }, [onError]);

  const appendTranscript      = useInterviewStore((s) => s.appendTranscript);
  const setPartialTranscript  = useInterviewStore((s) => s.setPartialTranscript);
  const setListening          = useInterviewStore((s) => s.setListening);

  // Create the canvas once — reused for every frame
  if (!canvasRef.current) {
    const c    = document.createElement("canvas");
    c.width    = 224;
    c.height   = 224;
    canvasRef.current = c;
  }

  // ── Connect ───────────────────────────────────────────────
  const connect = useCallback(() => {
    if (!sessionId || wsRef.current) return;

    const ws = new WebSocket(`${WS_BASE}/api/v1/interviews/ws/${sessionId}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case "ai_question":
            onQuestionRef.current?.(msg.text, msg.question_index, msg.total_questions);
            break;
          case "transcript":
            if (msg.is_final && msg.text) {
              // Confirmed utterance — append to permanent transcript
              // (appendTranscript also clears partialTranscript)
              appendTranscript(msg.text);
            } else if (!msg.is_final && msg.text) {
              // Live partial — show immediately so the user sees words appear as they speak
              setPartialTranscript(msg.text);
            }
            break;
          case "generating_report":
            onGeneratingReportRef.current?.();
            break;
          case "interview_complete":
            onCompleteRef.current?.(msg.session_id, msg.overall_score);
            break;
          case "error":
            onErrorRef.current?.(msg.message);
            break;
          // "pong" is a no-op
        }
      } catch { /* ignore malformed frames */ }
    };

    ws.onerror = () => onErrorRef.current?.("WebSocket connection error.");
  }, [sessionId, appendTranscript]);

  // ── Disconnect (call on unmount) ──────────────────────────
  const disconnect = useCallback(() => {
    _stopAudio();
    clearInterval(frameTimerRef.current);
    wsRef.current?.close();
    wsRef.current = null;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Audio streaming: mic → PCM Int16 → WebSocket ─────────
  const startAudio = useCallback(async (mediaStream) => {
    if (!mediaStream || !wsRef.current) return;
    if (audioCtxRef.current) return;   // already running

    const audioCtx = new AudioContext({ sampleRate: 16000 });
    // Chrome suspends AudioContexts created outside a direct user-gesture chain.
    // resume() is a no-op if already running, safe to call unconditionally.
    try { await audioCtx.resume(); } catch { /* ignore — non-fatal */ }
    const source    = audioCtx.createMediaStreamSource(mediaStream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      const f32 = e.inputBuffer.getChannelData(0);
      const i16 = new Int16Array(f32.length);
      for (let i = 0; i < f32.length; i++) {
        const s = Math.max(-1, Math.min(1, f32[i]));
        i16[i]  = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      wsRef.current.send(i16.buffer);
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);

    audioCtxRef.current  = audioCtx;
    processorRef.current = processor;
    setListening(true);
  }, [setListening]);

  // Plain function so disconnect() can call it without a stale useCallback closure
  function _stopAudio() {
    processorRef.current?.disconnect();
    try { audioCtxRef.current?.close(); } catch { /* ignore */ }
    processorRef.current = null;
    audioCtxRef.current  = null;
  }

  const stopAudio = useCallback(() => {
    _stopAudio();
    setListening(false);
  }, [setListening]);

  // ── Video frames: canvas → base64 JPEG → WebSocket ───────
  const startFrames = useCallback((videoEl) => {
    if (!videoEl) return;
    clearInterval(frameTimerRef.current);

    frameTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      const canvas = canvasRef.current;
      canvas.getContext("2d").drawImage(videoEl, 0, 0, 224, 224);
      const b64 = canvas.toDataURL("image/jpeg", 0.7);
      wsRef.current.send(JSON.stringify({ type: "video_frame", data: b64 }));
    }, FRAME_INTERVAL_MS);
  }, []);

  const stopFrames = useCallback(() => {
    clearInterval(frameTimerRef.current);
  }, []);

  // ── Control ───────────────────────────────────────────────
  const sendEndAnswer = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end_answer" }));
    }
  }, []);

  return {
    connect,
    disconnect,
    startAudio,
    stopAudio,
    startFrames,
    stopFrames,
    sendEndAnswer,
  };
}
