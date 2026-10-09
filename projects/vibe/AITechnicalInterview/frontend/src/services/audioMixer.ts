export type AudioMixer = {
  /** Поток для записи: микрофон + озвучка агента. */
  mixedStream: MediaStream;
  /** Проиграть URL и одновременно подмешать в запись. */
  playCapturedUrl: (fullUrl: string) => Promise<void>;
  /** Остановить все треки и закрыть AudioContext. */
  stop: () => void;
};

export function createAudioMixer(microphoneRaw: MediaStream): AudioMixer {
  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();
  const dest = ctx.createMediaStreamDestination();

  const micSource = ctx.createMediaStreamSource(microphoneRaw);
  micSource.connect(dest);

  // Слышим микрофон в колонках не надо (будет эхо) — не подключаем к ctx.destination.

  const stop = () => {
    try {
      dest.stream.getTracks().forEach((t) => t.stop());
    } catch {
      /* ignore */
    }
    try {
      ctx.close().catch(() => undefined);
    } catch {
      /* ignore */
    }
  };

  const playCapturedUrl = async (fullUrl: string) => {
    // AudioContext иногда в suspended до первого жеста пользователя.
    if (ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch {
        /* ignore */
      }
    }
    const audio = new Audio(fullUrl);
    audio.preload = "auto";

    // Подмешиваем озвучку в dest.stream (для записи) и в динамики (для прослушивания).
    const node = ctx.createMediaElementSource(audio);
    node.connect(dest);
    node.connect(ctx.destination);

    await new Promise<void>((resolve, reject) => {
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error("Ошибка воспроизведения"));
      void audio.play().catch(reject);
    });
    try {
      node.disconnect();
    } catch {
      /* ignore */
    }
  };

  return { mixedStream: dest.stream, playCapturedUrl, stop };
}

