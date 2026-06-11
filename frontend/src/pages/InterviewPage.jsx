/**
 * InterviewPage.jsx
 * ──────────────────
 * Wires the Phase 2 UI to the Phase 3B/3C WebSocket engine.
 *
 * Data flow
 * ---------
 *   useWebRTC        → camera + mic access → videoRef, streamRef
 *   useInterviewWS   → ONE WebSocket to /ws/{sessionId}
 *                       sends: PCM audio, base64 video frames, end_answer
 *                       receives: ai_question, transcript, interview_complete
 *
 * Phase state machine
 * -------------------
 *   loading    → fetching interview metadata + requesting camera
 *   ready      → camera ready, WebSocket connecting
 *   speaking   → AI TTS is reading the question aloud
 *   listening  → audio + frames streaming; candidate answering
 *   submitting → end_answer sent; server generating report
 *   done       → interview_complete received; navigating to report
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";

import Navbar          from "../components/Navbar";
import AudioVisualizer from "../components/AudioVisualizer";
import TabSwitchWarning from "../components/TabSwitchWarning";

import useInterviewStore from "../store/interviewStore";
import useWebRTC         from "../hooks/useWebRTC";
import useInterviewWS    from "../hooks/useInterviewWS";
import useVisibility     from "../hooks/useVisibility";
import useSpeechSynthesis from "../hooks/useSpeechSynthesis";

import { getInterview, getAnalysisReport } from "../services/api";

const ANSWER_TIMEOUT_S = 120;

export default function InterviewPage() {
  const { id: interviewId } = useParams();
  const navigate = useNavigate();

  // ── Global store ──────────────────────────────────────────
  const {
    interview,
    transcript,
    partialTranscript,
    isListening,
    isSpeaking,
    tabSwitchCount,
    setInterview,
    setTranscript,
    setReport,
  } = useInterviewStore();

  // ── Camera + mic (no frame capture — that's in useInterviewWS) ───
  const { videoRef, streamRef, mediaReady, mediaError, startMedia, stopMedia } =
    useWebRTC();

  const { speak, cancel: cancelSpeech } = useSpeechSynthesis();

  // ── Local UI state ────────────────────────────────────────
  const [phase,       setPhase]       = useState("loading");
  const [timeLeft,    setTimeLeft]    = useState(ANSWER_TIMEOUT_S);
  const [submitError, setSubmitError] = useState("");

  // Current question driven by the server's ai_question messages
  const [qText,  setQText]  = useState("");
  const [qIndex, setQIndex] = useState(0);
  const [totalQ, setTotalQ] = useState(0);

  const timerRef        = useRef(null);
  // Ref so TTS onEnd can call ws methods without stale closures
  const wsActionsRef    = useRef(null);
  // Ref so the countdown timer always calls the latest handleSubmit
  const handleSubmitRef = useRef(null);

  // Proctoring
  useVisibility({ enabled: phase !== "done" && phase !== "loading" });

  // ── WebSocket callbacks ───────────────────────────────────

  // Called when the server sends the next question.
  // Speaks it via TTS, then starts audio + frame capture on completion.
  const onQuestion = useCallback((text, questionIndex, total) => {
    setQText(text);
    setQIndex(questionIndex);
    setTotalQ(total);
    setTranscript("");
    setTimeLeft(ANSWER_TIMEOUT_S);
    setPhase("speaking");

    speak(text, {
      rate: 0.95,
      onEnd: () => {
        setPhase("listening");
        // wsActionsRef.current is always up-to-date (synced in useEffect below)
        wsActionsRef.current?.startAudio(streamRef.current);
        wsActionsRef.current?.startFrames(videoRef.current);
      },
    });
  }, [speak, setTranscript, streamRef, videoRef]);

  const onGeneratingReport = useCallback(() => {
    setPhase("submitting");
  }, []);

  const onComplete = useCallback(async (sessionId) => {
    try {
      const report = await getAnalysisReport(sessionId);
      setReport(report);
    } catch { /* non-fatal — navigate anyway */ }
    stopMedia();
    setPhase("done");
    navigate(`/report/${interviewId}`);
  }, [navigate, interviewId, stopMedia, setReport]);

  const onError = useCallback((message) => {
    setSubmitError(message);
  }, []);

  // ── WebSocket hook ────────────────────────────────────────
  const ws = useInterviewWS({
    sessionId: interviewId,
    onQuestion,
    onGeneratingReport,
    onComplete,
    onError,
  });

  // Keep wsActionsRef in sync so TTS onEnd always calls fresh ws methods
  useEffect(() => { wsActionsRef.current = ws; });

  // ── Fetch interview metadata ──────────────────────────────
  useEffect(() => {
    if (!interview) {
      getInterview(interviewId)
        .then(setInterview)
        .catch(() => navigate("/dashboard"));
    }
  }, [interviewId, interview, setInterview, navigate]);

  // ── Once media is ready, connect WebSocket ────────────────
  // phase === "loading" is the one-shot guard:
  //   - starts as "loading"
  //   - setPhase("ready") fires after startMedia succeeds → guard fails on next run
  //   - if camera fails we stay in "loading" → retry button can call startMedia again
  // ws is intentionally excluded from deps — useInterviewWS returns a new plain object
  // every render but ws.connect is a stable memoized ref. Including ws would re-fire
  // this effect on every single render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!interview || phase !== "loading") return;
    startMedia().then((ok) => {
      if (!ok) return;   // camera failed — stay in "loading", show error + retry
      setPhase("ready");
      ws.connect();
    });
  }, [interview, phase, startMedia]); // ws excluded — see comment above

  // ── Clean up on unmount AND on browser back/refresh ─────────────────────
  // Uses wsActionsRef (always current) instead of closing over the initial ws
  // object so refs are always fresh at call time.
  // Both the React unmount path and the window unload path stop the mic tracks,
  // preventing the browser's "recording" indicator from persisting after navigation.
  useEffect(() => {
    const cleanup = () => {
      // Cancel TTS first so the AI voice doesn't keep speaking after navigation
      try { window.speechSynthesis?.cancel(); }   catch { /* ignore */ }
      try { wsActionsRef.current?.disconnect(); } catch { /* ignore */ }
      try { stopMedia(); }                        catch { /* ignore */ }
    };
    window.addEventListener("beforeunload", cleanup);
    return () => {
      window.removeEventListener("beforeunload", cleanup);
      cleanup();
    };
  }, [stopMedia]); // wsActionsRef is a ref — doesn't need to be in deps

  // ── Countdown timer while listening ──────────────────────
  useEffect(() => {
    if (phase !== "listening") {
      clearInterval(timerRef.current);
      return;
    }
    timerRef.current = setInterval(() => {
      setTimeLeft((t) => {
        if (t <= 1) {
          clearInterval(timerRef.current);
          handleSubmitRef.current?.(); // always fresh via ref — avoids stale closure
          return 0;
        }
        return t - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [phase]);

  // ── Submit answer ─────────────────────────────────────────
  const handleSubmit = useCallback(() => {
    if (phase !== "listening") return;
    clearInterval(timerRef.current);
    cancelSpeech();
    ws.stopAudio();
    ws.stopFrames();
    ws.sendEndAnswer();    // server will send next ai_question or generating_report
    setPhase("processing"); // show "Processing…" while waiting for server response
    setSubmitError("");
  }, [phase, cancelSpeech, ws]);

  // Keep handleSubmitRef in sync so the countdown timer always calls the latest version
  useEffect(() => { handleSubmitRef.current = handleSubmit; });

  // ── UI helpers ────────────────────────────────────────────
  const totalQuestions = totalQ || interview?.questions_answers?.length || 0;
  const progress       = totalQuestions ? (qIndex / totalQuestions) * 100 : 0;
  const formatTime     = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const phaseLabel = {
    loading:    "Initialising…",
    ready:      "Connecting…",
    speaking:   "AI is speaking…",
    listening:  "Your turn — answer now",
    processing: "Processing answer…",
    submitting: "Generating report…",
    done:       "Complete",
  }[phase] ?? phase;

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-surface-900 flex flex-col">
      <Navbar />
      <TabSwitchWarning />

      {/* Progress bar */}
      <div className="h-1 bg-surface-700">
        <div
          className="h-full bg-brand-500 transition-all duration-700"
          style={{ width: `${progress}%` }}
        />
      </div>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6">

        {/* Header row */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <span className="badge bg-brand-600/20 border border-brand-500/30 text-brand-300">
                Q {qIndex + 1} / {totalQuestions || "?"}
              </span>
              {tabSwitchCount > 0 && (
                <span className="badge bg-red-500/20 border border-red-500/30 text-red-300">
                  ⚠ {tabSwitchCount} violation{tabSwitchCount > 1 ? "s" : ""}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {interview?.job_role} · {interview?.difficulty}
            </p>
          </div>

          {/* Status pill */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium transition-all ${
            phase === "listening"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : phase === "speaking"
              ? "border-brand-500/40 bg-brand-500/10 text-brand-300"
              : phase === "processing" || phase === "submitting"
              ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
              : "border-white/10 bg-white/5 text-slate-400"
          }`}>
            {phase === "listening" && (
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            )}
            {phase === "speaking" && (
              <span className="w-2 h-2 rounded-full bg-brand-400 animate-pulse" />
            )}
            {(phase === "processing" || phase === "submitting") && (
              <span className="w-2 h-2 rounded-full border-2 border-amber-400 border-t-transparent animate-spin" />
            )}
            {phaseLabel}
          </div>
        </div>

        {/* Split-screen layout */}
        <div className="grid lg:grid-cols-2 gap-5 mb-5">

          {/* ── Left: Webcam ────────────────────────────── */}
          <div className="glass p-4 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-300">Candidate</h3>
              {mediaReady && (
                <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  Live
                </span>
              )}
            </div>

            <div className="relative bg-surface-800 rounded-xl overflow-hidden aspect-video flex items-center justify-center">
              <video
                ref={videoRef}
                autoPlay
                muted
                playsInline
                className="w-full h-full object-cover"
              />

              {!mediaReady && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-surface-800 p-4">
                  {mediaError ? (
                    <div className="text-center flex flex-col items-center gap-3 max-w-xs">
                      <svg className="w-10 h-10 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                          d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                      </svg>
                      <p className="text-sm text-red-400 font-semibold">Camera / Mic Error</p>
                      {/* Show exact browser error so the user knows what to fix */}
                      <p className="text-xs text-slate-300 bg-surface-700 rounded-lg px-3 py-2 font-mono leading-relaxed text-left w-full">
                        {mediaError}
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Close any other app using the camera (Teams, Zoom, Discord), then retry.
                        Or check <strong className="text-slate-400">Chrome → Settings → Privacy → Camera</strong>.
                      </p>
                      <button
                        onClick={() =>
                          startMedia().then((ok) => {
                            if (!ok) return;
                            setPhase("ready");
                            ws.connect();
                          })
                        }
                        className="btn-primary py-1.5 px-5 text-xs"
                      >
                        Retry Camera
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-2">
                      <div className="w-8 h-8 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
                      <p className="text-sm text-slate-400">Requesting camera…</p>
                    </div>
                  )}
                </div>
              )}

              {/* Countdown overlay */}
              {phase === "listening" && (
                <div className={`absolute bottom-3 right-3 px-2.5 py-1 rounded-lg text-sm font-mono font-bold backdrop-blur-sm ${
                  timeLeft <= 15 ? "bg-red-500/30 text-red-300" : "bg-black/40 text-white"
                }`}>
                  {formatTime(timeLeft)}
                </div>
              )}
            </div>
          </div>

          {/* ── Right: AI panel ─────────────────────────── */}
          <div className="glass p-4 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-300">AI Interviewer</h3>
              <span className="flex items-center gap-1.5 text-xs text-brand-400">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                Groq · llama3-70b
              </span>
            </div>

            {/* AI avatar + waveform */}
            <div className="flex-1 bg-surface-800 rounded-xl flex flex-col items-center justify-center gap-4 p-6 min-h-[220px]">
              <div className={`relative w-20 h-20 rounded-full flex items-center justify-center transition-all duration-500 ${
                isSpeaking ? "shadow-glow" : ""
              }`}>
                <div className={`absolute inset-0 rounded-full border-2 transition-all duration-300 ${
                  isSpeaking
                    ? "border-brand-500 scale-110 opacity-60 animate-ping"
                    : "border-white/10"
                }`} />
                <div className="w-full h-full rounded-full bg-gradient-to-br from-brand-600/80 to-indigo-700/80 flex items-center justify-center">
                  <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                  </svg>
                </div>
              </div>

              <div className="w-full h-20 rounded-xl overflow-hidden bg-surface-700/50">
                <AudioVisualizer active={isSpeaking} color={isSpeaking ? "#6366f1" : "#334155"} />
              </div>
            </div>

            {/* Current question text */}
            {qText && (
              <div className="bg-surface-700/60 rounded-xl p-4 border border-white/5">
                <p className="text-xs font-semibold text-brand-400 uppercase tracking-widest mb-2">
                  Question {qIndex + 1}
                </p>
                <p className="text-sm text-slate-200 leading-relaxed">{qText}</p>
              </div>
            )}
          </div>
        </div>

        {/* Transcript + submit */}
        <div className="glass p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-300">Live Transcript</h3>
              {isListening && (
                <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Transcribing
                </span>
              )}
            </div>

            {submitError && (
              <p className="text-xs text-red-400">{submitError}</p>
            )}

            <button
              onClick={handleSubmit}
              disabled={phase !== "listening"}
              className="btn-primary py-2 px-5 text-sm"
            >
              {phase === "submitting" ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  Generating Report…
                </span>
              ) : phase === "processing" ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  Processing…
                </span>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  Submit Answer
                </>
              )}
            </button>
          </div>

          <div className="min-h-[80px] bg-surface-700/40 rounded-xl p-4 text-sm text-slate-300 leading-relaxed font-mono border border-white/5">
            {(transcript || partialTranscript) ? (
              <>
                {transcript}
                {partialTranscript && (
                  <span className="text-slate-500 italic">
                    {transcript ? " " : ""}{partialTranscript}
                  </span>
                )}
              </>
            ) : (
              <span className="text-slate-600 italic">
                {phase === "listening"
                  ? "Speak now — your transcript will appear here…"
                  : "Transcript will appear when you are asked to answer."}
              </span>
            )}
          </div>
        </div>

      </main>
    </div>
  );
}
