import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import MonacoWorkspace, { EditorDecoration } from "../../editor/MonacoWorkspace";
import { api, Interview, TranscriptItem, WarmupQuizQuestion } from "../../services/api";
import { AudioMixer, createAudioMixer } from "../../services/audioMixer";
import {
  acquireCameraAndMic,
  cameraMicErrorMessage,
  acquireScreenShare,
  displayMediaErrorMessage,
  attachPreview,
  MediaStreams,
  finalizeAnswerAudio,
  isAnswerCaptureActive,
  isAudioStreamLive,
  pushAnswerChunk,
  sttFilenameForBlob,
  startContinuousAnswerCapture,
  startRecorders,
  stopAllStreams,
  stopRecorders,
  RecorderSet,
} from "../../services/media";
import { InterviewWebSocket, WSMessage } from "../../services/websocket";
import MicLevelMeter from "./MicLevelMeter";
import { MessageBody } from "./formatMessage";
import WarmupQuizPanel, { QuizWaitMode, QuizWaitState } from "./WarmupQuizPanel";
import {
  appendUniqueEntry,
  buildAgentPayloadPreview,
  QUIZ_BLOCKING_SESSION_MS,
  QUIZ_MAX_QUESTIONS,
  QUIZ_STT_SESSION_MS,
  sanitizeSttDisplay,
  wantsEndInterview,
} from "./interviewUi";
import "./interview-room.css";

const ACTIVE_STATUSES = new Set(["active", "paused"]);
const CLOSED_STATUSES = new Set(["completing", "completed", "report_ready"]);

const MSG_LINK_EXPIRED = "Интервью завершено. Ссылка недействительна.";
const MSG_SESSION_ENDED = "Спасибо за участие! Отчёт будет отправлен на почту, указанную при создании интервью.";

function hasOpeningQuestion(messages: { role: string; text: string }[]): boolean {
  if (messages.some((m) => m.role === "candidate" && m.text.includes("[Interview started]"))) {
    return true;
  }
  const aiTurns = messages.filter((m) => m.role === "ai");
  return aiTurns.length >= 2;
}

function audioFullUrl(url: string) {
  return `${import.meta.env.VITE_API_URL || ""}${url}`;
}

async function playAudioWithRetry(
  url: string,
  onProgress?: (message: string) => void,
  attempts = 45,
  mixer?: AudioMixer | null
): Promise<void> {
  const full = audioFullUrl(url);
  for (let i = 0; i < attempts; i++) {
    if (i > 0) {
      onProgress?.(`Ожидание озвучки… (${i + 1}/${attempts})`);
    }
    try {
      const head = await fetch(full, { method: "HEAD", cache: "no-store" });
      if (head.ok) {
        if (mixer) {
          await mixer.playCapturedUrl(full);
        } else {
          const audio = new Audio(full);
          audio.preload = "auto";
          await new Promise<void>((resolve, reject) => {
            audio.onended = () => resolve();
            audio.onerror = () => reject(new Error("Ошибка воспроизведения"));
            void audio.play().catch(reject);
          });
        }
        return;
      }
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, i < 3 ? 400 : 1000));
  }
  throw new Error("Озвучка ещё не готова");
}

function transcriptsToMessages(transcripts: TranscriptItem[]) {
  return transcripts.map((t) => ({
    role: t.speaker === "ai" ? "ai" : "candidate",
    text: t.text,
  }));
}

function elapsedFromStartedAt(startedAt: string | null | undefined): number {
  if (!startedAt) return 0;
  return Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
}

type AgentTurnResponse = {
  ai_message: string;
  audio_url: string | null;
  audio_ready?: boolean;
  editor_content?: string;
  editor_language?: string;
  should_end_interview?: boolean;
  code_actions_applied?: number;
};

function isAgentTurnReady(res: AgentTurnResponse): boolean {
  if (!res.ai_message?.trim()) return false;
  if (!res.audio_url) return true;
  return res.audio_ready === true;
}

export default function InterviewRoom() {
  const { token } = useParams<{ token: string }>();
  const [interview, setInterview] = useState<Interview | null>(null);
  const [code, setCode] = useState("");
  const [editorRevision, setEditorRevision] = useState(0);
  const [language, setLanguage] = useState("python");
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [transcript, setTranscript] = useState<{ speaker: string; text: string }[]>([]);
  const [decorations, setDecorations] = useState<EditorDecoration[]>([]);
  const [timeline, setTimeline] = useState<string[]>([]);
  const [aiTyping, setAiTyping] = useState(false);
  const [media, setMedia] = useState({ camera: false, mic: false, screen: false });
  const [streams, setStreams] = useState<MediaStreams | null>(null);
  const [rawMicStream, setRawMicStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [answerBusy, setAnswerBusy] = useState(false);
  const [briefingAudioUrl, setBriefingAudioUrl] = useState<string | null>(null);
  const [audioHint, setAudioHint] = useState<string | null>(null);
  const [showBriefingGate, setShowBriefingGate] = useState(false);
  const [audioWait, setAudioWait] = useState<{
    title: string;
    phase: string;
    transcript?: string;
  } | null>(null);
  const [answerHint, setAnswerHint] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [endMessage, setEndMessage] = useState<string | null>(null);
  const [sttReview, setSttReview] = useState<{
    voiceText: string;
    blobKb: number;
  } | null>(null);
  const [warmupQuiz, setWarmupQuiz] = useState<WarmupQuizQuestion[]>([]);
  const [warmupAnsweredSigs, setWarmupAnsweredSigs] = useState<string[]>([]);
  const [quizWait, setQuizWait] = useState<QuizWaitState | null>(null);
  const [micCheckPending, setMicCheckPending] = useState(false);
  const [micCheckOk, setMicCheckOk] = useState(false);
  const [micCheckSuccessHold, setMicCheckSuccessHold] = useState(false);
  const [pendingOpening, setPendingOpening] = useState(false);

  const releaseQuizWaitRef = useRef<(() => void) | null>(null);
  const micVoiceAccumRef = useRef(0);
  const lastMicLevelTickRef = useRef(0);
  const micCheckClosingRef = useRef(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamsRef = useRef<MediaStreams | null>(null);
  const wsRef = useRef<InterviewWebSocket | null>(null);
  const recordersRef = useRef<RecorderSet>({});
  const rawMicRef = useRef<MediaStream | null>(null);
  const mixerRef = useRef<AudioMixer | null>(null);

  const answerCaptureRef = useRef<MediaRecorder | null>(null);
  const answerSegmentChunksRef = useRef<Blob[]>([]);
  const pendingSttBlobRef = useRef<Blob | null>(null);
  const startedRef = useRef(false);
  const [micMeterKey, setMicMeterKey] = useState(0);

  const streamsReady = Boolean(streams?.camera && streams?.microphone && streams?.screen);
  const isSessionActive = interview ? ACTIVE_STATUSES.has(interview.status) : false;
  const canStart = streamsReady && interview && !started;
  const canResume = streamsReady && interview && isSessionActive && !started;

  const refreshCameraPreview = useCallback(() => {
    const camera = streamsRef.current?.camera;
    if (camera && videoRef.current) {
      attachPreview(videoRef.current, camera);
    }
  }, []);

  const ensureWarmupQuestions = useCallback(async (): Promise<WarmupQuizQuestion[]> => {
    if (warmupQuiz.length) return warmupQuiz;
    if (!interview) return [];
    for (let attempt = 0; attempt < 40; attempt++) {
      try {
        const res = await api.getWarmupQuiz(interview.id);
        if (res.questions.length) {
          setWarmupQuiz(res.questions);
          if (res.answered_signatures?.length) {
            setWarmupAnsweredSigs(res.answered_signatures);
          }
          return res.questions;
        }
      } catch {
        /* мини-вопросы опциональны */
      }
      if (attempt < 39) {
        await new Promise((r) => window.setTimeout(r, 2000));
      }
    }
    return [];
  }, [interview, warmupQuiz]);

  const refillWarmupQuestions = useCallback(async (): Promise<WarmupQuizQuestion[] | null> => {
    if (!interview) return null;
    try {
      const res = await api.refillWarmupQuiz(interview.id);
      if (res.questions?.length) {
        setWarmupQuiz(res.questions);
        return res.questions;
      }
    } catch {
      /* догрузка опциональна */
    }
    return null;
  }, [interview]);

  const armQuizWait = useCallback(
    async (
      mode: QuizWaitMode,
      opts?: { force?: boolean; maxQuestions?: number; maxSessionMs?: number; allowRefill?: boolean }
    ): Promise<void | null> => {
      if (mode === "off") return null;
      if (!opts?.force && !startedRef.current) return null;
      const qs = await ensureWarmupQuestions();
      if (!qs.length) return null;
      const maxQuestions =
        opts?.maxQuestions ??
        (mode === "blocking" || mode === "stt" ? QUIZ_MAX_QUESTIONS : undefined);
      const maxSessionMs =
        opts?.maxSessionMs ??
        (mode === "blocking"
          ? QUIZ_BLOCKING_SESSION_MS
          : mode === "stt"
            ? QUIZ_STT_SESSION_MS
            : 90_000);
      setQuizWait({
        active: true,
        mode,
        operationComplete: false,
        maxQuestions,
        maxSessionMs,
        allowRefill: opts?.allowRefill ?? true,
      });
      return new Promise((resolve) => {
        releaseQuizWaitRef.current = resolve;
      });
    },
    [ensureWarmupQuestions]
  );

  const applyAgentTurnToUi = useCallback((res: AgentTurnResponse) => {
    setMessages((m) =>
      appendUniqueEntry(
        m.map((x) => ({ speaker: x.role, text: x.text })),
        "ai",
        res.ai_message
      ).map((x) => ({ role: x.speaker, text: x.text }))
    );
    setTranscript((t) => appendUniqueEntry(t, "ai", res.ai_message));
    if (res.editor_content !== undefined) {
      setCode(res.editor_content);
      if ((res.code_actions_applied ?? 0) > 0 || res.editor_content === "") {
        setEditorRevision((n) => n + 1);
      }
    }
    if (res.editor_language) {
      setLanguage(res.editor_language);
    }
  }, []);

  const finishQuizOperation = useCallback(() => {
    setQuizWait((w) => (w ? { ...w, operationComplete: true } : w));
  }, []);

  const handleQuizSessionComplete = useCallback(() => {
    setQuizWait(null);
    releaseQuizWaitRef.current?.();
    releaseQuizWaitRef.current = null;
  }, []);

  const waitForQuizEnd = useCallback(
    async (quizPromise: Promise<void | null> | null, capMs: number) => {
      if (!quizPromise) return;
      await Promise.race([
        quizPromise,
        new Promise<void>((resolve) => window.setTimeout(resolve, capMs)),
      ]);
      handleQuizSessionComplete();
    },
    [handleQuizSessionComplete]
  );

  const clearQuizWait = useCallback(() => {
    finishQuizOperation();
    handleQuizSessionComplete();
    setAudioWait(null);
  }, [finishQuizOperation, handleQuizSessionComplete]);

  useEffect(() => {
    streamsRef.current = streams;
    refreshCameraPreview();
  }, [streams, refreshCameraPreview]);

  useEffect(() => {
    if (!token) return;
    api
      .joinInterview(token)
      .then((data) => {
        setInterview(data);
        setCode(data.editor_content || "");
        setLanguage(data.editor_language || "python");
        setMedia({ camera: false, mic: false, screen: false });

        if (CLOSED_STATUSES.has(data.status)) {
          setSessionEnded(true);
          setEndMessage(MSG_LINK_EXPIRED);
          return;
        }
        const active = ACTIVE_STATUSES.has(data.status);
        setStarted(active);
        setElapsed(active ? elapsedFromStartedAt(data.started_at) : 0);

        const restored = transcriptsToMessages(data.transcripts || []);
        if (restored.length > 0) {
          setMessages(restored);
          setTranscript(
            (data.transcripts || []).map((t) => ({ speaker: t.speaker, text: t.text }))
          );
        } else if (data.briefing_text) {
          setMessages([{ role: "ai", text: data.briefing_text }]);
          setTranscript([{ speaker: "ai", text: data.briefing_text }]);
        }

        if (data.briefing_audio_url) {
          setBriefingAudioUrl(data.briefing_audio_url);
          if (!active) setShowBriefingGate(true);
        } else if (data.briefing_text && !active) {
          setAudioHint("Озвучка готовится на сервере — подождите несколько секунд и обновите страницу.");
        }
        setWarmupQuiz(data.warmup_quiz || []);
      })
      .catch((e) => {
        const msg = String(e);
        if (
          msg.includes("410") ||
          msg.includes("завершено") ||
          msg.includes("не действует") ||
          msg.includes("недействительна")
        ) {
          setSessionEnded(true);
          setEndMessage(MSG_LINK_EXPIRED);
        } else {
          setError(msg);
        }
      });
  }, [token]);

  useEffect(() => {
    startedRef.current = started;
  }, [started]);

  useEffect(() => {
    if (!started) return;
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [started]);

  const stopAnswerCapture = useCallback(() => {
    const rec = answerCaptureRef.current;
    if (rec && rec.state !== "inactive") {
      try {
        rec.stop();
      } catch {
        /* ignore */
      }
    }
    answerCaptureRef.current = null;
    answerSegmentChunksRef.current = [];
  }, []);

  const startAnswerCapture = useCallback((microphone: MediaStream) => {
    if (!isAudioStreamLive(microphone)) {
      return;
    }
    const prev = answerCaptureRef.current;
    if (prev) {
      const sameStream = prev.stream === microphone;
      const prevLive = isAudioStreamLive(prev.stream);
      if (prev.state === "recording" && sameStream && prevLive) {
        return;
      }
      try {
        if (prev.state !== "inactive") prev.stop();
      } catch {
        /* ignore */
      }
      answerCaptureRef.current = null;
    }
    answerSegmentChunksRef.current = [];
    const rec = startContinuousAnswerCapture(microphone);
    rec.ondataavailable = (e) => {
      pushAnswerChunk(answerSegmentChunksRef.current, e.data);
    };
    answerCaptureRef.current = rec;
  }, []);

  useEffect(() => {
    return () => {
      stopAnswerCapture();
      stopRecorders(recordersRef.current);
      stopAllStreams(streamsRef.current);
    };
  }, [stopAnswerCapture]);

  useEffect(() => {
    const mic = rawMicRef.current;
    if (mic && started) {
      startAnswerCapture(mic);
    } else if (!started) {
      stopAnswerCapture();
    }
  }, [started, startAnswerCapture, stopAnswerCapture]);

  const syncMediaStatus = useCallback(
    async (state: typeof media) => {
      if (!interview) return;
      await api.mediaStatus(interview.id, {
        camera_enabled: state.camera,
        microphone_enabled: state.mic,
        screenshare_enabled: state.screen,
      });
    },
    [interview]
  );

  const enableCameraMic = async () => {
    try {
      const { camera, microphone } = await acquireCameraAndMic();
      rawMicRef.current = microphone;
      setRawMicStream(microphone);
      bindMicLifecycle(microphone);
      try {
        mixerRef.current?.stop();
      } catch {
        /* ignore */
      }
      mixerRef.current = createAudioMixer(microphone);
      const mixedMic = mixerRef.current.mixedStream;
      const nextStreams: MediaStreams = {
        camera,
        microphone: mixedMic,
        screen: streamsRef.current?.screen ?? null,
      };
      streamsRef.current = nextStreams;
      setStreams(nextStreams);
      const state = { camera: true, mic: true, screen: media.screen };
      setMedia(state);
      wsRef.current?.send({ type: "camera_enabled" });
      wsRef.current?.send({ type: "microphone_enabled" });
      await syncMediaStatus(state);
      setMicMeterKey((k) => k + 1);
      if (startedRef.current) {
        stopAnswerCapture();
        startAnswerCapture(microphone);
        if (nextStreams.screen) {
          restartSessionRecorders();
        }
      }
      setAnswerHint("Речь записывается постоянно. Когда закончите ответ — нажмите «Ответить».");
      setError(null);
      requestAnimationFrame(refreshCameraPreview);
    } catch (err) {
      setError(cameraMicErrorMessage(err));
    }
  };

  const enableScreen = async () => {
    try {
      const screen = await acquireScreenShare();
      screen.getVideoTracks()[0]?.addEventListener("ended", () => {
        setMedia((m) => ({ ...m, screen: false }));
        setStreams((prev) => (prev ? { ...prev, screen: null } : prev));
        setError("Демонстрация экрана остановлена — включите снова");
      });
      setStreams((prev) => {
        const next = {
          camera: prev?.camera ?? null,
          microphone: prev?.microphone ?? null,
          screen,
        };
        streamsRef.current = next;
        return next;
      });
      const state = { camera: media.camera, mic: media.mic, screen: true };
      setMedia(state);
      wsRef.current?.send({ type: "screenshare_started" });
      await syncMediaStatus(state);
      if (startedRef.current && streamsRef.current?.camera && streamsRef.current?.microphone) {
        restartSessionRecorders();
        resumeAnswerCaptureIfNeeded();
      }
      setError(null);
      requestAnimationFrame(refreshCameraPreview);
    } catch (e) {
      setError(displayMediaErrorMessage(e));
    }
  };

  useEffect(() => {
    if (!interview || !token) return;
    const ws = new InterviewWebSocket();
    let cancelled = false;

    ws.onMessage((msg: WSMessage) => {
      if (msg.type === "connected" && msg.editor_state) {
        const es = msg.editor_state as { content?: string; language?: string };
        if (es.content != null) setCode(es.content);
        if (es.language) setLanguage(es.language);
      }
      if (msg.type === "ai_message") {
        setMessages((m) => [...m, { role: "ai", text: String(msg.text) }]);
        setTranscript((t) => [...t, { speaker: "ai", text: String(msg.text) }]);
      }
      if (msg.type === "ai_typing") setAiTyping(Boolean(msg.active));
      if (msg.type === "ai_voice_finished" && msg.audio_url) {
        void playAudioWithRetry(String(msg.audio_url)).catch(() => undefined);
      }
      if (msg.type === "code_applied" || msg.type === "ai_code_action") {
        const op = msg.operation as { after?: string; actor?: string; action?: string };
        if (op?.after != null) {
          setCode(op.after);
          setEditorRevision((n) => n + 1);
        }
        setTimeline((tl) => [
          ...tl,
          `${new Date().toLocaleTimeString()} [${op?.actor}] ${op?.action}`,
        ]);
      }
      if (msg.type === "line_highlight") {
        const lines = (msg.lines as number[]) || [];
        setDecorations(lines.map((line) => ({ line, className: "ai-line-highlight" })));
      }
      if (msg.type === "inline_comment") {
        setDecorations((d) => [
          ...d,
          { line: Number(msg.line), comment: String(msg.text), className: "ai-line-highlight" },
        ]);
      }
      if (msg.type === "interview_event" && msg.event === "media_warning") {
        setError(
          String(msg.message || "Включите камеру, микрофон и демонстрацию экрана. Таймер продолжает идти.")
        );
      }
      if (msg.type === "transcript_update") {
        setTranscript((t) => [
          ...t,
          { speaker: String(msg.speaker), text: String(msg.text) },
        ]);
      }
    });

    void ws.connect(interview.id, token).then(() => {
      if (!cancelled) wsRef.current = ws;
      else ws.disconnect();
    });

    return () => {
      cancelled = true;
      ws.disconnect();
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [interview?.id, token]);

  const uploadChunk = async (streamType: string, index: number, blob: Blob) => {
    if (!interview) return;
    const fd = new FormData();
    fd.append("file", blob);
    await fetch(
      `${import.meta.env.VITE_API_URL || ""}/api/v1/interviews/${interview.id}/recordings/chunk?stream_type=${streamType}&chunk_index=${index}`,
      { method: "POST", body: fd }
    );
  };

  const restartSessionRecorders = useCallback(() => {
    if (!interview || !startedRef.current) return;
    const currentStreams = streamsRef.current;
    if (!currentStreams?.camera || !currentStreams.microphone || !currentStreams.screen) {
      return;
    }
    stopRecorders(recordersRef.current);
    recordersRef.current = startRecorders(interview.id, currentStreams, uploadChunk);
  }, [interview]);

  const resumeAnswerCaptureIfNeeded = useCallback(() => {
    const mic = rawMicRef.current;
    if (mic && startedRef.current && isAudioStreamLive(mic)) {
      startAnswerCapture(mic);
    }
  }, [startAnswerCapture]);

  const bindMicLifecycle = useCallback(
    (microphone: MediaStream) => {
      microphone.getAudioTracks().forEach((track) => {
        track.addEventListener("ended", () => {
          stopAnswerCapture();
          setMedia((m) => ({ ...m, mic: false, camera: false }));
          setStreams((prev) =>
            prev ? { ...prev, microphone: null, camera: null } : prev
          );
          rawMicRef.current = null;
          setRawMicStream(null);
          setError("Микрофон отключился — снова нажмите «Включить камеру и микрофон».");
        });
      });
    },
    [stopAnswerCapture]
  );

  const syncTranscriptsFromServer = useCallback(async () => {
    if (!token) return;
    const data = await api.joinInterview(token);
    const restored = transcriptsToMessages(data.transcripts || []);
    if (restored.length) {
      setMessages(restored);
      setTranscript((data.transcripts || []).map((t) => ({ speaker: t.speaker, text: t.text })));
    }
    return data;
  }, [token]);

  const presentAgentTurn = useCallback(
    async (res: AgentTurnResponse, title: string) => {
      if (!isAgentTurnReady(res)) {
        throw new Error(
          "Озвучка не подготовлена. Обновите страницу (Ctrl+Shift+R) или проверьте TTS на сервере."
        );
      }
      stopAnswerCapture();
      applyAgentTurnToUi(res);
      try {
        await syncTranscriptsFromServer();
      } catch {
        /* optional */
      }
      const readyPhase =
        title === "Первый вопрос" ? "Первый вопрос готов." : "Вопрос готов.";
      setAudioWait({
        title,
        phase: readyPhase,
        transcript: res.ai_message,
      });
      try {
        if (res.audio_url) {
          await playAudioWithRetry(
            res.audio_url,
            (phase) => setAudioWait((w) => (w ? { ...w, phase } : w)),
            5,
            mixerRef.current
          );
        }
      } catch {
        setAnswerHint("Не удалось воспроизвести озвучку. Текст — в чате и в Transcript.");
        throw new Error("Не удалось воспроизвести озвучку.");
      } finally {
        setAudioWait(null);
        resumeAnswerCaptureIfNeeded();
      }
    },
    [applyAgentTurnToUi, resumeAnswerCaptureIfNeeded, stopAnswerCapture, syncTranscriptsFromServer]
  );

  const playVoiceWithOverlay = async (
    audioUrl: string | null | undefined,
    title: string,
    transcript?: string,
    enableQuiz = true
  ) => {
    stopAnswerCapture();
    const quizMode: QuizWaitMode =
      enableQuiz &&
      startedRef.current &&
      title !== "Приветствие" &&
      title !== "Завершение"
        ? "blocking"
        : "off";
    const quizPromise = armQuizWait(quizMode, {
      maxQuestions: QUIZ_MAX_QUESTIONS,
      maxSessionMs: QUIZ_BLOCKING_SESSION_MS,
      allowRefill: true,
    });
    try {
      if (!audioUrl) {
        setAudioWait({
          title,
          phase: "Озвучка недоступна — читайте текст ниже",
          transcript,
        });
        finishQuizOperation();
        if (quizPromise) {
          await quizPromise;
        } else {
          await new Promise((r) => setTimeout(r, 4000));
        }
        setAudioWait(null);
        setAudioHint("Озвучка недоступна — текст вопроса показан на экране и в чате.");
        return;
      }
      setAudioWait({
        title,
        phase: "Готовим озвучку…",
        transcript,
      });
      try {
        await playAudioWithRetry(
          audioUrl,
          (phase) => setAudioWait((w) => (w ? { ...w, phase } : w)),
          45,
          mixerRef.current
        );
      } catch {
        setAudioHint("Не удалось воспроизвести озвучку. Текст вопроса — в чате и в Transcript.");
      } finally {
        finishQuizOperation();
        await waitForQuizEnd(quizPromise, QUIZ_BLOCKING_SESSION_MS + 10_000);
        setAudioWait(null);
      }
    } finally {
      resumeAnswerCaptureIfNeeded();
    }
  };

  const enterRoom = async () => {
    const briefingText =
      messages.find((m) => m.role === "ai")?.text || interview?.briefing_text || "";
    if (!briefingAudioUrl) {
      setShowBriefingGate(false);
      return;
    }
    await playVoiceWithOverlay(briefingAudioUrl, "Приветствие", briefingText);
    setShowBriefingGate(false);
    setAudioHint(null);
  };

  const handleMicLevel = useCallback(
    (level: number) => {
      if (!micCheckPending || micCheckClosingRef.current) return;
      const now = Date.now();
      const delta = lastMicLevelTickRef.current ? now - lastMicLevelTickRef.current : 0;
      lastMicLevelTickRef.current = now;
      if (level > 16) {
        micVoiceAccumRef.current += Math.min(delta, 120);
        if (level > 22) setMicCheckOk(true);
      } else {
        micVoiceAccumRef.current = Math.max(0, micVoiceAccumRef.current - 50);
      }
      // ~1.6 с устойчивого звука — кашель реже проходит
      if (micVoiceAccumRef.current >= 1600) {
        micCheckClosingRef.current = true;
        setMicCheckOk(true);
        setMicCheckSuccessHold(true);
        window.setTimeout(() => {
          setMicCheckPending(false);
          setMicCheckSuccessHold(false);
          micCheckClosingRef.current = false;
        }, 2200);
      }
    },
    [micCheckPending]
  );

  const runOpeningTurn = useCallback(async () => {
    if (!interview) return;
    setAudioWait({ title: "Первый вопрос", phase: "Готовим первый вопрос…" });

    const quizPromise = armQuizWait("blocking", {
      force: true,
      maxQuestions: QUIZ_MAX_QUESTIONS,
      maxSessionMs: QUIZ_BLOCKING_SESSION_MS,
      allowRefill: true,
    });

    const openingPromise = api.createOpeningTurn(interview.id);
    void openingPromise.then((g) => {
      if (isAgentTurnReady(g)) finishQuizOperation();
    });

    await waitForQuizEnd(quizPromise, QUIZ_BLOCKING_SESSION_MS + 10_000);

    let greeting: AgentTurnResponse;
    try {
      greeting = await openingPromise;
    } catch (e) {
      clearQuizWait();
      throw e;
    }

    if (!isAgentTurnReady(greeting)) {
      clearQuizWait();
      throw new Error(
        "Озвучка первого вопроса не подготовлена. Обновите страницу или проверьте TTS на сервере."
      );
    }

    await presentAgentTurn(greeting, "Первый вопрос");
    setAnswerHint(
      "Говорите свободно — микрофон пишет всё время. Когда закончите ответ — нажмите «Ответить»."
    );
  }, [interview]);

  useEffect(() => {
    if (!pendingOpening || micCheckPending) return;
    setPendingOpening(false);
    setSubmitting(true);
    void (async () => {
      try {
        await runOpeningTurn();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setSubmitting(false);
      }
    })();
  }, [pendingOpening, micCheckPending, runOpeningTurn]);

  const handleStart = async () => {
    if (!interview || (!canStart && !canResume)) return;
    setError(null);
    setSubmitting(true);
    try {
      if (!isSessionActive) {
        await api.startInterview(interview.id);
        setInterview({ ...interview, status: "active" });
      }
      setStarted(true);
      startedRef.current = true;
      const currentStreams = streamsRef.current;
      const mic = rawMicRef.current;
      if (mic) {
        startAnswerCapture(mic);
      }
      if (currentStreams) {
        recordersRef.current = startRecorders(interview.id, currentStreams, uploadChunk);
        requestAnimationFrame(refreshCameraPreview);
      }
      if (!hasOpeningQuestion(messages)) {
        micVoiceAccumRef.current = 0;
        lastMicLevelTickRef.current = Date.now();
        micCheckClosingRef.current = false;
        setMicCheckOk(false);
        setMicCheckSuccessHold(false);
        setMicCheckPending(true);
        setPendingOpening(true);
        return;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleEndInterview = async () => {
    if (!interview || sessionEnded) return;
    setAnswerBusy(true);
    setSttReview(null);
    stopAnswerCapture();
    stopRecorders(recordersRef.current);
    stopAllStreams(streamsRef.current);
    setStreams(null);
    streamsRef.current = null;
    rawMicRef.current = null;
    setRawMicStream(null);
    try {
      mixerRef.current?.stop();
    } catch {
      /* ignore */
    }
    mixerRef.current = null;
    setAudioWait({ title: "Завершение", phase: "Закрываем интервью…" });
    try {
      const res = await api.completeInterview(interview.id);
      setEndMessage(res.farewell_message);
      setSessionEnded(true);
      if (res.audio_url) {
        try {
          await playAudioWithRetry(
            res.audio_url,
            (phase) => setAudioWait((w) => (w ? { ...w, phase } : w)),
            45,
            mixerRef.current
          );
        } catch {
          /* озвучка прощания опциональна */
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAudioWait(null);
      setAnswerBusy(false);
    }
  };

  const sendAnswerToAgent = async (voiceText: string) => {
    if (!interview) return;
    setAudioWait({ title: "Обработка ответа", phase: "Формируем ответ и синтез речи…" });
    const quizPromise = armQuizWait("blocking", {
      maxQuestions: QUIZ_MAX_QUESTIONS,
      maxSessionMs: QUIZ_BLOCKING_SESSION_MS,
      allowRefill: true,
    });

    if (wantsEndInterview(voiceText)) {
      await handleEndInterview();
      return;
    }

    const answerPromise = api.submitAnswer(
      interview.id,
      "combined",
      voiceText || undefined,
      code
    );
    void answerPromise.then((res) => {
      if (isAgentTurnReady(res)) {
        finishQuizOperation();
        setAudioWait((w) =>
          w?.title === "Обработка ответа" ? { ...w, phase: "Ответ готов…" } : w
        );
      }
    });

    let res: AgentTurnResponse;
    try {
      res = await answerPromise;
    } catch (e) {
      clearQuizWait();
      setAudioWait({
        title: "Связь с сервером",
        phase: "Не удалось получить следующий вопрос. Повторите отправку ответа.",
      });
      await new Promise((r) => setTimeout(r, 5000));
      throw e;
    }

    if (res.should_end_interview) {
      finishQuizOperation();
      await waitForQuizEnd(quizPromise, QUIZ_BLOCKING_SESSION_MS + 10_000);
      if (isAgentTurnReady(res)) {
        await presentAgentTurn(res, "Завершение");
      } else {
        applyAgentTurnToUi(res);
      }
      await handleEndInterview();
      return;
    }

    await waitForQuizEnd(quizPromise, QUIZ_BLOCKING_SESSION_MS + 10_000);

    if (!isAgentTurnReady(res)) {
      throw new Error(
        "Озвучка ответа интервьюера не подготовлена. Обновите страницу или проверьте TTS на сервере."
      );
    }

    await presentAgentTurn(res, "Ответ интервьюера");
    setAnswerHint("Говорите свободно. Когда закончите ответ — снова «Ответить».");
  };

  const handleAnswerClick = async () => {
    if (!interview || sessionEnded) return;
    if (!started) {
      setError("Сначала нажмите «Начать интервью».");
      return;
    }
    if (answerBusy) return;

    const mic = rawMicRef.current;
    if (!mic || !isAudioStreamLive(mic)) {
      setError("Сначала включите камеру и микрофон.");
      return;
    }

    if (!isAnswerCaptureActive(answerCaptureRef.current)) {
      stopAnswerCapture();
      startAnswerCapture(mic);
      await new Promise((r) => setTimeout(r, 800));
    }
    if (!isAnswerCaptureActive(answerCaptureRef.current)) {
      setError("Не удалось запустить запись речи. Переподключите микрофон.");
      return;
    }

    setAnswerBusy(true);
    setError(null);
    const kb = (n: number) => `${(n / 1024).toFixed(0)} КБ`;
    setAudioWait({ title: "Обработка ответа", phase: "Распознаём речь…" });
    const quizPromise = armQuizWait("stt", {
      maxQuestions: QUIZ_MAX_QUESTIONS,
      maxSessionMs: QUIZ_STT_SESSION_MS,
      allowRefill: true,
    });

    try {
      const captureRecorder = answerCaptureRef.current;
      answerCaptureRef.current = null;
      const blob = await finalizeAnswerAudio(captureRecorder, answerSegmentChunksRef.current);
      pendingSttBlobRef.current = blob;

      let voiceText = "";
      const minAudio = 200;
      if (blob.size >= minAudio) {
        const fname = sttFilenameForBlob(blob);
        for (let attempt = 1; attempt <= 3; attempt++) {
          setAudioWait({
            title: "Обработка ответа",
            phase: `Распознаём речь (${kb(blob.size)})… попытка ${attempt}/3`,
          });
          try {
            const stt = await api.stt(interview.id, blob, fname);
            voiceText = sanitizeSttDisplay(stt.text.trim());
            if (voiceText) break;
            if (stt.warning && attempt < 3) {
              setAnswerHint(stt.warning + " Повторяем распознавание автоматически…");
            }
          } catch (sttErr) {
            const msg = sttErr instanceof Error ? sttErr.message : String(sttErr);
            if (attempt >= 3) {
              if (!code.trim()) {
                setError(`Распознавание речи: ${msg}`);
                clearQuizWait();
                setAudioWait(null);
                resumeAnswerCaptureIfNeeded();
                return;
              }
              setAnswerHint(`${msg} Можно отправить только код из редактора.`);
            }
          }
          if (!voiceText && attempt < 3) {
            await new Promise((r) => setTimeout(r, 1200));
          }
        }
      } else if (!code.trim()) {
        setError(
          `Мало аудио (${blob.size} байт). Говорите 3–5 секунд, затем снова «Ответить».`
        );
        clearQuizWait();
        setAudioWait(null);
        resumeAnswerCaptureIfNeeded();
        return;
      }

      finishQuizOperation();
      await waitForQuizEnd(quizPromise, 95_000);
      setAudioWait(null);
      setSttReview({
        voiceText,
        blobKb: Math.round(blob.size / 1024),
      });
      resumeAnswerCaptureIfNeeded();
    } catch (e) {
      clearQuizWait();
      setAudioWait(null);
      setError(e instanceof Error ? e.message : String(e));
      setAnswerHint("Связь с сервером прервалась. Повторите ответ кнопкой «Ответить».");
      resumeAnswerCaptureIfNeeded();
    } finally {
      setAnswerBusy(false);
    }
  };

  const confirmSttReview = async () => {
    if (!interview || !sttReview) return;
    const voiceText = sttReview.voiceText.trim();
    const hasCode = Boolean(code.trim());
    if (!voiceText && !hasCode) {
      setError("Пустой ответ: допишите текст вручную или введите код в редакторе.");
      return;
    }
    setSttReview(null);
    setAnswerBusy(true);
    setError(null);

    if (voiceText) {
      setTranscript((t) => appendUniqueEntry(t, "candidate", voiceText));
      setMessages((m) =>
        appendUniqueEntry(
          m.map((x) => ({ speaker: x.role, text: x.text })),
          "candidate",
          voiceText
        ).map((x) => ({ role: x.speaker, text: x.text }))
      );
    } else if (code.trim()) {
      setAnswerHint(
        (h) =>
          h ||
          "Устная речь не распознана — агенту уйдёт код из редактора. При необходимости допишите текст выше."
      );
    }

    try {
      await sendAnswerToAgent(voiceText);
      pendingSttBlobRef.current = null;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setAnswerHint("Не удалось отправить ответ. Нажмите «Ответить» ещё раз или допишите текст вручную.");
    } finally {
      setAudioWait(null);
      setAnswerBusy(false);
      resumeAnswerCaptureIfNeeded();
    }
  };

  const formatTime = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  if (sessionEnded) {
    return (
      <div className="interview-room interview-ended">
        <div className="card end-screen-card">
          <h2>Интервью завершено</h2>
          <p>{endMessage || MSG_SESSION_ENDED}</p>
        </div>
      </div>
    );
  }

  if (!interview) {
    return <div className="room-loading">{error || "Загрузка комнаты интервью…"}</div>;
  }

  return (
    <div className="interview-room">
      <MicLevelMeter
        key={micMeterKey}
        stream={rawMicStream ?? streams?.microphone ?? null}
        active={media.mic}
        unlockSignal={micMeterKey}
        onLevelChange={handleMicLevel}
      />
      {micCheckPending && (
        <div className="mic-check-overlay" role="dialog" aria-modal="true">
          <div className="mic-check-card card">
            <h2>{micCheckSuccessHold ? "Микрофон работает" : "Проверка микрофона"}</h2>
            {micCheckSuccessHold ? (
              <p className="mic-check-ok">
                Проверка прошла успешно — голос слышен. Через пару секунд начнём интервью.
              </p>
            ) : (
              <>
                <p>
                  Скажите вслух «раз-два-три» и посмотрите на индикатор <strong>Мик</strong> в правом
                  нижнем углу — полоска должна загораться зелёным, когда вы говорите.
                </p>
                <p className={micCheckOk ? "mic-check-ok" : "hint"}>
                  {micCheckOk
                    ? "Слышим вас — продолжайте говорить ещё секунду…"
                    : "Пока голос не распознан. Проверьте, что выбран нужный микрофон в системе."}
                </p>
              </>
            )}
          </div>
        </div>
      )}
      {sttReview && (
        <div className="stt-review-overlay" role="dialog" aria-modal="true">
          <div className="stt-review-card card">
            <h2>Проверьте текст перед отправкой</h2>
            <p className="hint">
              Распознано с микрофона ({sttReview.blobKb} КБ). Если текст обрезан или с ошибками —
              исправьте вручную в поле ниже. Код из редактора добавится автоматически.
            </p>
            <label className="stt-review-label" htmlFor="stt-review-text">
              Устный ответ (редактируемый)
            </label>
            <textarea
              id="stt-review-text"
              className="stt-review-textarea"
              rows={5}
              value={sttReview.voiceText}
              onChange={(e) =>
                setSttReview((r) => (r ? { ...r, voiceText: e.target.value } : r))
              }
            />
            <p className="stt-review-label">Что уйдёт агенту (устный текст + код):</p>
            <pre className="stt-review-preview">
              {buildAgentPayloadPreview(sttReview.voiceText, code)}
            </pre>
            <div className="stt-review-actions">
              <button type="button" className="btn-primary" onClick={() => void confirmSttReview()}>
                Отправить агенту
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setSttReview(null);
                  resumeAnswerCaptureIfNeeded();
                }}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
      {audioWait && (
        <div className="audio-wait-overlay" role="status" aria-live="polite">
          <div className="audio-wait-card">
            <div className="hourglass" aria-hidden="true">
              ⏳
            </div>
            <h2>{audioWait.title}</h2>
            <p className="audio-wait-phase">{audioWait.phase}</p>
            {interview && (
              <WarmupQuizPanel
                interviewId={interview.id}
                questions={warmupQuiz}
                answeredSignatures={warmupAnsweredSigs}
                wait={quizWait}
                onSessionComplete={handleQuizSessionComplete}
                onRefillQuestions={refillWarmupQuestions}
              />
            )}
            {audioWait.transcript && (
              <div className="audio-wait-transcript">
                <p className="audio-wait-transcript-label">Текст интервьюера:</p>
                <MessageBody text={audioWait.transcript} large />
              </div>
            )}
          </div>
        </div>
      )}
      {showBriefingGate && (
        <div className="briefing-gate" role="dialog" aria-modal="true">
          <div className="briefing-gate-card">
            <h2>Комната интервью</h2>
            <p>Нажмите кнопку ниже — включится приветствие AI-интервьюера.</p>
            <button
              type="button"
              className="btn-primary"
              disabled={Boolean(audioWait)}
              onClick={() => void enterRoom()}
            >
              {audioWait ? "Подождите…" : "Войти и прослушать приветствие"}
            </button>
          </div>
        </div>
      )}
      <header className="room-header">
        <div>
          <h1>AI Interview Room</h1>
          <span className="format-tag">{interview.selected_format || "Формат не выбран"}</span>
          {interview.live_coding_ai_assistant &&
            (interview.selected_format || "").includes("Live Coding") && (
              <span className="badge badge-ok">AI-помощник</span>
            )}
          {interview.sql_dialect && (
            <span className="badge badge-ok" title="Диалект SQL из вакансии или резюме">
              SQL: {interview.sql_dialect}
            </span>
          )}
        </div>
        <div className="header-meta">
          <span className="timer">{formatTime(elapsed)}</span>
          <span className={`badge ${streamsReady ? "badge-ok" : "badge-warn"}`}>
            {streamsReady ? "Media OK" : "Media required"}
          </span>
          {isSessionActive && !streamsReady && (
            <span className="badge badge-warn">Сессия активна — подключите медиа</span>
          )}
          {aiTyping && <span className="ai-typing">AI печатает...</span>}
          {started && media.mic && (
            <span className="badge badge-ok" title="Микрофон пишет речь для ответов">
              Запись речи
            </span>
          )}
          {started && (
            <button
              type="button"
              className="btn-primary header-answer-btn"
              disabled={answerBusy}
              onClick={() => void handleAnswerClick()}
            >
              {answerBusy ? "Обработка…" : "Ответить"}
            </button>
          )}
          {started && (
            <button
              type="button"
              className="btn-secondary"
              disabled={answerBusy}
              onClick={() => void handleEndInterview()}
            >
              Завершить
            </button>
          )}
        </div>
      </header>

      {error && <div className="blocking-warning">{error}</div>}
      {audioHint && <div className="hint-banner">{audioHint}</div>}
      {answerHint && <div className="hint-banner answer-hint">{answerHint}</div>}

      <section className="media-panel card">
        <h3>Медиа</h3>
        {isSessionActive && !streamsReady && (
          <p className="hint">
            Интервью уже идёт. Подключите камеру, микрофон и экран снова — таймер и история сохранены.
          </p>
        )}
        <div className="media-grid">
          <div className="media-item">
            <span>Камера</span>
            <span className={`badge ${media.camera ? "badge-ok" : "badge-err"}`}>
              {media.camera ? "ON" : "OFF"}
            </span>
          </div>
          <div className="media-item">
            <span>Микрофон</span>
            <span className={`badge ${media.mic ? "badge-ok" : "badge-err"}`}>{media.mic ? "ON" : "OFF"}</span>
          </div>
          <div className="media-item">
            <span>Экран</span>
            <span className={`badge ${media.screen ? "badge-ok" : "badge-err"}`}>
              {media.screen ? "ON" : "OFF"}
            </span>
          </div>
        </div>
        <div className="media-actions">
          {(!media.camera || !media.mic) && (
            <button type="button" className="btn-primary" onClick={() => void enableCameraMic()}>
              Включить камеру и микрофон
            </button>
          )}
          {media.camera && media.mic && !media.screen && (
            <button type="button" className="btn-primary" onClick={() => void enableScreen()}>
              Включить демонстрацию экрана
            </button>
          )}
          {(!started || canResume) && (
            <button
              type="button"
              className="btn-primary"
              disabled={(!canStart && !canResume) || submitting}
              onClick={() => void handleStart()}
            >
              {isSessionActive && !started ? "Продолжить интервью" : "Начать интервью"}
            </button>
          )}
        </div>
      </section>

      {(() => {
        const lastAi = [...messages].reverse().find((m) => m.role === "ai")?.text?.trim();
        if (!started || !lastAi) return null;
        return (
          <section className="current-question-panel card" aria-live="polite">
            <h3>Текущий вопрос</h3>
            <div className="current-question-text">{lastAi}</div>
          </section>
        );
      })()}

      <div className="room-main">
        <aside className="sidebar">
          <video ref={videoRef} className="camera-preview" playsInline autoPlay muted />
          <div className="card transcript-panel">
            <h3>Transcript</h3>
            <div className="transcript-list scroll-panel">
              {transcript.map((t, i) => (
                <p key={i}>
                  <strong>{t.speaker}:</strong> {t.text}
                </p>
              ))}
            </div>
          </div>
          <div className="card timeline-panel">
            <h3>Code timeline</h3>
            <ul>
              {timeline.slice(-20).map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </div>
        </aside>

        <main className="editor-panel">
          <p className="hint editor-lang-hint">
            Язык редактора: <strong>{language}</strong>
            {interview.sql_dialect && (
              <>
                {" "}
                · Диалект SQL: <strong>{interview.sql_dialect}</strong>
              </>
            )}
            {interview.competencies?.length
              ? ` (основной язык из вакансии: ${
                  [...interview.competencies].sort((a, b) => b.weight - a.weight)[0]?.skill
                })`
              : ""}
          </p>
          <MonacoWorkspace
            key={editorRevision}
            language={language}
            value={code}
            onChange={setCode}
            decorations={decorations}
            onCursorMove={(line, column) =>
              wsRef.current?.send({ type: "cursor_move", position: { line, column } })
            }
          />
          {!started && (
            <p className="hint action-hint">Сначала нажмите «Начать интервью». Кнопка «Ответить» — в шапке.</p>
          )}
        </main>

        <aside className="chat-panel card">
          <h3>AI Interviewer</h3>
          <div className="chat-messages scroll-panel">
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role}`}>
                {m.role === "ai" ? <MessageBody text={m.text} /> : <p>{m.text}</p>}
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
