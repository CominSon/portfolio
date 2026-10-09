import { useEffect, useRef, useState } from "react";

type Props = {
  stream: MediaStream | null;
  active?: boolean;
  /** Меняется при жесте пользователя (включение микрофона) — разблокирует AudioContext */
  unlockSignal?: number;
  onLevelChange?: (level: number) => void;
};

export default function MicLevelMeter({ stream, active = true, unlockSignal = 0, onLevelChange }: Props) {
  const [level, setLevel] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const rafRef = useRef<number>(0);
  useEffect(() => {
    if (!stream || !active) {
      setLevel(0);
      setBlocked(false);
      return;
    }

    const track = stream.getAudioTracks()[0];
    if (!track) {
      setLevel(0);
      setBlocked(true);
      return;
    }

    let cancelled = false;
    const ctx = new AudioContext();

    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.55;
    source.connect(analyser);

    const timeData = new Uint8Array(analyser.fftSize);
    const freqData = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      if (cancelled) return;

      if (ctx.state === "suspended") {
        void ctx.resume().then(() => setBlocked(ctx.state === "suspended"));
      } else {
        setBlocked(false);
      }

      if (track.muted || !track.enabled) {
        setLevel(0);
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      analyser.getByteTimeDomainData(timeData);
      analyser.getByteFrequencyData(freqData);

      let sum = 0;
      for (let i = 0; i < timeData.length; i++) {
        const v = (timeData[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / timeData.length);

      let freqSum = 0;
      for (let i = 0; i < freqData.length; i++) {
        freqSum += freqData[i];
      }
      const freqAvg = freqSum / freqData.length;

      const combined = Math.max(rms * 420, freqAvg * 1.8);
      const nextLevel = Math.min(100, Math.round(combined));
      setLevel(nextLevel);
      onLevelChange?.(nextLevel);
      rafRef.current = requestAnimationFrame(tick);
    };

    void ctx.resume().then(() => {
      if (!cancelled) tick();
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
      void ctx.close();
    };
  }, [stream, active, unlockSignal, onLevelChange]);

  if (!active) return null;

  return (
    <div
      className="mic-level-meter"
      title={blocked ? "Нажмите «Включить камеру и микрофон» для активации" : "Уровень микрофона"}
    >
      <span className="mic-level-label">{blocked ? "Мик ?" : "Мик"}</span>
      <div className="mic-level-track" aria-hidden="true">
        <div
          className={`mic-level-fill ${level > 8 ? "mic-level-fill--live" : ""}`}
          style={{ height: `${Math.max(6, level)}%` }}
        />
      </div>
    </div>
  );
}
