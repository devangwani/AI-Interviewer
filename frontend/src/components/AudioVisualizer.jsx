import { useEffect, useRef } from "react";

const BAR_COUNT = 48;
const BASE_HEIGHT = 4;

export default function AudioVisualizer({ active = false, color = "#6366f1" }) {
  const canvasRef    = useRef(null);
  const analyserRef  = useRef(null);
  const rafRef       = useRef(null);
  const streamRef    = useRef(null);
  const audioCtxRef  = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    let bars = Array.from({ length: BAR_COUNT }, () => BASE_HEIGHT);

    const draw = (dataArray) => {
      const W = canvas.width;
      const H = canvas.height;
      ctx.clearRect(0, 0, W, H);

      const barWidth = (W / BAR_COUNT) * 0.6;
      const gap      = (W / BAR_COUNT) * 0.4;

      bars.forEach((barH, i) => {
        const x = i * (barWidth + gap) + gap / 2;
        const y = (H - barH) / 2;

        const gradient = ctx.createLinearGradient(x, y + barH, x, y);
        gradient.addColorStop(0, color + "99");
        gradient.addColorStop(1, color);

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barH, barWidth / 2);
        ctx.fill();
      });
    };

    if (!active) {
      // idle gentle wave
      let t = 0;
      const idle = () => {
        t += 0.04;
        bars = bars.map((_, i) => BASE_HEIGHT + Math.sin(t + i * 0.35) * 3);
        draw(bars);
        rafRef.current = requestAnimationFrame(idle);
      };
      rafRef.current = requestAnimationFrame(idle);
      return () => cancelAnimationFrame(rafRef.current);
    }

    // active: connect to mic
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        streamRef.current = stream;
        const audioCtx  = new AudioContext();
        audioCtxRef.current = audioCtx;
        const source    = audioCtx.createMediaStreamSource(stream);
        const analyser  = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        analyserRef.current = analyser;

        const bufferLen = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLen);

        const animate = () => {
          analyser.getByteFrequencyData(dataArray);
          const step = Math.floor(bufferLen / BAR_COUNT);
          bars = Array.from({ length: BAR_COUNT }, (_, i) => {
            const val = dataArray[i * step] / 255;
            return BASE_HEIGHT + val * (canvas.height * 0.75);
          });
          draw(bars);
          rafRef.current = requestAnimationFrame(animate);
        };
        rafRef.current = requestAnimationFrame(animate);
      } catch {
        // fallback to idle if mic denied
      }
    })();

    return () => {
      cancelAnimationFrame(rafRef.current);
      audioCtxRef.current?.close();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [active, color]);

  return (
    <canvas
      ref={canvasRef}
      width={480}
      height={120}
      className="w-full h-full"
    />
  );
}
