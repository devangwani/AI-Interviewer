/**
 * useWebRTC.js
 * ─────────────
 * Camera and microphone access only.
 *
 * Audio streaming and video frame capture are handled by useInterviewWS,
 * which sends both over the main WebSocket connection.
 */

import { useRef, useState, useCallback, useEffect } from "react";

export default function useWebRTC() {
  const videoRef  = useRef(null);
  const streamRef = useRef(null);   // exposed so InterviewPage can pass to useInterviewWS

  const [mediaReady, setMediaReady] = useState(false);
  const [mediaError, setMediaError] = useState(null);
  // Tracked in state so useEffect below can react when it changes
  const [activeStream, setActiveStream] = useState(null);

  // Assign srcObject after React commits the video element to the DOM.
  // Doing this inside an async callback is unreliable — the play() Promise
  // can be interrupted, leaving a permanently black video.
  useEffect(() => {
    if (!activeStream || !videoRef.current) return;
    videoRef.current.srcObject = activeStream;
    // play() is a no-op on muted+autoPlay videos in most browsers, but
    // calling it explicitly handles the edge case where autoPlay was blocked.
    const p = videoRef.current.play();
    if (p) p.catch(() => {});   // suppress "interrupted" DOMException
  }, [activeStream]);

  // ── Request camera + mic access ───────────────────────────
  const startMedia = useCallback(async () => {
    // Wrap getUserMedia with a hard 20 s timeout so the "Requesting camera…"
    // spinner never hangs forever. Returns the stream on success, throws on failure.
    const getMediaWithTimeout = (constraints) => {
      let timedOut = false;
      return Promise.race([
        navigator.mediaDevices.getUserMedia(constraints).then((stream) => {
          if (timedOut) {
            stream.getTracks().forEach((t) => t.stop()); // clean up orphaned stream
            throw new Error("Camera access timed out");
          }
          return stream;
        }),
        new Promise((_, reject) =>
          setTimeout(() => {
            timedOut = true;
            reject(new Error("Camera access timed out — make sure no other app (Teams, Zoom, Discord) is using the camera"));
          }, 20_000)
        ),
      ]);
    };

    // Try specific constraints first, then bare fallback.
    // A failed specific constraint (e.g. exact resolution) throws a
    // DOMException that kills both video AND audio in a single call.
    const attempts = [
      { video: { width: 640, height: 480, facingMode: "user" }, audio: { channelCount: 1, echoCancellation: true } },
      { video: true, audio: true },
    ];

    for (const constraints of attempts) {
      try {
        const stream = await getMediaWithTimeout(constraints);
        streamRef.current = stream;
        setActiveStream(stream);
        setMediaReady(true);
        setMediaError(null);
        return true;   // ← caller can check success
      } catch (err) {
        if (constraints === attempts[attempts.length - 1]) {
          setMediaError(err.message);
        }
      }
    }
    return false;      // ← all attempts failed
  }, []);

  // ── Stop all tracks ───────────────────────────────────────
  const stopMedia = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActiveStream(null);
    setMediaReady(false);
  }, []);

  return {
    videoRef,
    streamRef,    // pass streamRef.current to ws.startAudio()
    mediaReady,
    mediaError,
    startMedia,
    stopMedia,
  };
}
