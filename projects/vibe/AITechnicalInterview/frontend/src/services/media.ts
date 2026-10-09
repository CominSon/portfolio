/** Работа с камерой, микрофоном, экраном и MediaRecorder. */
export type MediaStreams = {
  camera: MediaStream | null;
  microphone: MediaStream | null;
  screen: MediaStream | null;
};

export type RecorderSet = {
  camera?: MediaRecorder;
  audio?: MediaRecorder;
  screen?: MediaRecorder;
};

/** Поток для записи — клон треков, чтобы не гасить превью камеры. */
export function isStreamLive(stream: MediaStream | null | undefined): boolean {
  return Boolean(stream?.getTracks().some((t) => t.readyState === "live"));
}

export function isAudioStreamLive(stream: MediaStream | null | undefined): boolean {
  return Boolean(stream?.getAudioTracks().some((t) => t.readyState === "live" && t.enabled));
}

export function streamForRecording(stream: MediaStream): MediaStream {
  const tracks = stream.getTracks().map((t) => t.clone());
  return new MediaStream(tracks);
}

export function cameraMicErrorMessage(err?: unknown): string {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return "Камера и микрофон доступны только по HTTPS. Откройте сайт через https:// (не http://) и примите предупреждение браузера о сертификате, если оно появится.";
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return "Браузер не поддерживает доступ к камере/микрофону. Используйте Chrome или Edge.";
  }
  const name =
    err && typeof err === "object" && "name" in err ? String((err as DOMException).name) : "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "Разрешите доступ к камере и микрофону в диалоге браузера (иконка замка в адресной строке).";
  }
  if (name === "NotFoundError") {
    return "Камера или микрофон не найдены. Проверьте подключение устройств.";
  }
  if (name === "NotReadableError") {
    return "Камера или микрофон заняты другим приложением. Закройте Zoom/Teams/другие программы и попробуйте снова.";
  }
  const msg = err instanceof Error ? err.message : "";
  return msg ? `Не удалось включить камеру/микрофон: ${msg}` : "Разрешите доступ к камере и микрофону";
}

export async function acquireCameraAndMic(): Promise<{ camera: MediaStream; microphone: MediaStream }> {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    throw new DOMException("Insecure context", "SecurityError");
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new DOMException("getUserMedia is not supported", "NotSupportedError");
  }
  const camera = await navigator.mediaDevices.getUserMedia({
    video: {
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { ideal: 30, max: 30 },
    },
    audio: false,
  });
  const microphone = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  return { camera, microphone };
}

export function displayMediaErrorMessage(err: unknown): string {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return "Демонстрация экрана доступна только по HTTPS. Откройте ссылку интервью через https:// (quick tunnel), не по http://.";
  }
  if (!navigator.mediaDevices?.getDisplayMedia) {
    return "Браузер не поддерживает захват экрана. Используйте Chrome или Edge последней версии.";
  }
  const name =
    err && typeof err === "object" && "name" in err ? String((err as DOMException).name) : "";
  switch (name) {
    case "NotAllowedError":
      return (
        "Доступ к экрану запрещён. В диалоге браузера выберите «Весь экран» или окно и нажмите «Поделиться». " +
        "Windows 11: Параметры → Конфиденциальность и безопасность → Запись экрана — включите Chrome или Edge, " +
        "затем обновите страницу."
      );
    case "AbortError":
      return "Выбор экрана отменён. Нажмите «Включить демонстрацию экрана» снова и выберите экран в диалоге.";
    case "NotFoundError":
      return "Нет доступного источника для захвата экрана.";
    case "NotReadableError":
      return "Экран занят другим приложением или захват заблокирован системой.";
    default:
      break;
  }
  const msg = err instanceof Error ? err.message : "";
  return msg ? `Не удалось включить экран: ${msg}` : "Не удалось включить демонстрацию экрана";
}

export async function acquireScreenShare(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    throw new DOMException("getDisplayMedia is not supported", "NotSupportedError");
  }
  const videoDetailed = {
    width: { ideal: 1920 },
    height: { ideal: 1080 },
    frameRate: { ideal: 30, min: 15, max: 30 },
  };
  /* audio: true часто ломает getDisplayMedia на Windows 11 (Chrome/Edge). */
  try {
    return await navigator.mediaDevices.getDisplayMedia({
      video: videoDetailed,
      audio: false,
    });
  } catch (first) {
    if (first instanceof DOMException && first.name === "AbortError") {
      throw first;
    }
    return navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
  }
}

export function startRecorders(
  _interviewId: string,
  streams: MediaStreams,
  onChunk: (streamType: string, index: number, blob: Blob) => void
): RecorderSet {
  const recorders: RecorderSet = {};
  const mk = (stream: MediaStream, type: string, mimeType?: string, videoBitsPerSecond?: number) => {
    let index = 0;
    const options: MediaRecorderOptions = {};
    if (mimeType) options.mimeType = mimeType;
    if (videoBitsPerSecond) options.videoBitsPerSecond = videoBitsPerSecond;
    let rec: MediaRecorder;
    try {
      rec = Object.keys(options).length
        ? new MediaRecorder(stream, options)
        : new MediaRecorder(stream);
    } catch {
      rec = new MediaRecorder(stream);
    }
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) onChunk(type, index++, e.data);
    };
    /* Чаще чанки — стабильнее таймкоды при склейке на сервере. */
    rec.start(2000);
    return rec;
  };
  if (streams.camera) {
    const recStream = streamForRecording(streams.camera);
    try {
      recorders.camera = mk(recStream, "camera", "video/webm;codecs=vp8", 2_500_000);
    } catch {
      recorders.camera = mk(recStream, "camera", undefined, 2_500_000);
    }
  }
  /* Полная запись микрофона для итогового видео (STT по-прежнему через answer capture). */
  if (streams.microphone) {
    const micStream = streamForRecording(streams.microphone);
    try {
      recorders.audio = mk(micStream, "audio", "audio/webm;codecs=opus");
    } catch {
      try {
        recorders.audio = mk(micStream, "audio", "audio/webm");
      } catch {
        recorders.audio = mk(micStream, "audio");
      }
    }
  }
  if (streams.screen) {
    const recStream = streamForRecording(streams.screen);
    try {
      recorders.screen = mk(recStream, "screen", "video/webm;codecs=vp8", 4_000_000);
    } catch {
      recorders.screen = mk(recStream, "screen", undefined, 4_000_000);
    }
  }
  return recorders;
}

export function stopRecorders(recorders: RecorderSet) {
  Object.values(recorders).forEach((r) => {
    if (r && r.state !== "inactive") r.stop();
  });
}

const ANSWER_SLICE_MS = 400;
/** Не обрезать аудио ответа: до ~10 мин непрерывной речи между нажатиями «Ответить». */
export const MAX_ANSWER_DURATION_MS = 600_000;

export function pushAnswerChunk(chunks: Blob[], data: Blob): void {
  if (data.size === 0) return;
  chunks.push(data);
  const maxChunks = Math.ceil(MAX_ANSWER_DURATION_MS / ANSWER_SLICE_MS);
  while (chunks.length > maxChunks) {
    chunks.shift();
  }
}

function pickAudioMimeType(): string | undefined {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t));
}

/** Непрерывная запись речи кандидата; сегменты нарезаются через takeAudioSegment. */
export function startContinuousAnswerCapture(microphone: MediaStream): MediaRecorder {
  const mimeType = pickAudioMimeType();
  const options = mimeType ? { mimeType } : undefined;
  let rec: MediaRecorder;
  try {
    rec = options ? new MediaRecorder(microphone, options) : new MediaRecorder(microphone);
  } catch {
    rec = new MediaRecorder(microphone);
  }
  try {
    rec.start(ANSWER_SLICE_MS);
  } catch {
    rec.start();
  }
  return rec;
}

export function takeAudioSegment(chunks: Blob[]): Blob {
  const taken = chunks.splice(0, chunks.length);
  return new Blob(taken, { type: taken[0]?.type || "audio/webm" });
}

/** Сбросить буфер MediaRecorder перед нарезкой сегмента ответа. */
export function flushAnswerRecorder(recorder: MediaRecorder | null): Promise<void> {
  if (!recorder || recorder.state !== "recording") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    const onData = () => {
      recorder.removeEventListener("dataavailable", onData);
      done();
    };
    recorder.addEventListener("dataavailable", onData);
    try {
      recorder.requestData();
    } catch {
      done();
      return;
    }
    window.setTimeout(done, 600);
  });
}

/** Остановить запись ответа и собрать все чанки в один Blob (без очистки до сборки). */
export async function finalizeAnswerAudio(
  recorder: MediaRecorder | null,
  chunks: Blob[]
): Promise<Blob> {
  if (recorder) {
    await flushAnswerRecorder(recorder);
    if (recorder.state === "recording") {
      await new Promise<void>((resolve) => {
        const onStop = () => {
          recorder.removeEventListener("stop", onStop);
          resolve();
        };
        recorder.addEventListener("stop", onStop);
        try {
          recorder.stop();
        } catch {
          resolve();
        }
      });
      await new Promise((r) => setTimeout(r, 800));
    }
  }
  const blob = takeAudioSegment(chunks);
  if (blob.size > 0 && blob.size < 800) {
    await new Promise((r) => setTimeout(r, 300));
  }
  return blob;
}

export function sttFilenameForBlob(blob: Blob): string {
  const t = blob.type || "";
  if (t.includes("ogg")) return "answer.ogg";
  if (t.includes("mp4") || t.includes("m4a")) return "answer.m4a";
  return "answer.webm";
}

export function isAnswerCaptureActive(recorder: MediaRecorder | null): boolean {
  return recorder?.state === "recording";
}

export function attachPreview(videoEl: HTMLVideoElement, stream: MediaStream) {
  videoEl.srcObject = stream;
  videoEl.muted = true;
  void videoEl.play().catch(() => {
    /* autoplay может быть заблокирован до жеста пользователя */
  });
}

export function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((t) => t.stop());
}

export function stopAllStreams(streams: MediaStreams | null) {
  if (!streams) return;
  stopStream(streams.camera);
  stopStream(streams.microphone);
  stopStream(streams.screen);
}
