import { useCallback, useRef } from "react";
import useInterviewStore from "../store/interviewStore";

const WS_BASE = import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000";

export default function useDeepgramSTT({ interviewId }) {
  const ws          = useRef(null);
  const processorRef = useRef(null);
  const audioCtxRef  = useRef(null);
  const setListening = useInterviewStore((s) => s.setListening);
  const appendTranscript = useInterviewStore((s) => s.appendTranscript);

  const start = useCallback(
    async (stream) => {
      if (!interviewId || !stream) return;

      ws.current = new WebSocket(`${WS_BASE}/api/v1/interviews/${interviewId}/stream`);

      ws.current.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "transcript" && data.is_final && data.text) {
          appendTranscript(data.text);
        }
      };

      await new Promise((resolve, reject) => {
        ws.current.onopen  = resolve;
        ws.current.onerror = reject;
      });

      // Pipe mic audio to the WebSocket as raw PCM (16-bit LE, 16 kHz)
      const audioCtx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;
      const source    = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);

      processor.onaudioprocess = (e) => {
        if (ws.current?.readyState !== WebSocket.OPEN) return;
        const float32 = e.inputBuffer.getChannelData(0);
        const int16   = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          const s = Math.max(-1, Math.min(1, float32[i]));
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        ws.current.send(int16.buffer);
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);
      processorRef.current = processor;

      setListening(true);
    },
    [interviewId, appendTranscript, setListening]
  );

  const stop = useCallback(() => {
    processorRef.current?.disconnect();
    audioCtxRef.current?.close();
    ws.current?.close();
    setListening(false);
  }, [setListening]);

  return { start, stop };
}
