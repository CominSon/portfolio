import { useCallback, useEffect, useRef, useState } from "react";
import { api, WarmupQuizQuestion } from "../../services/api";
import { warmupQuestionSignature, warmupTopicSignature } from "./warmupQuizSignature";

const QUIZ_SECONDS = 40;
const FEEDBACK_MS = 5000;
const FEEDBACK_MS_WHEN_MAIN_READY = 1500;

export type QuizWaitMode = "stt" | "blocking" | "off";

export interface QuizWaitState {
  active: boolean;
  mode: QuizWaitMode;
  operationComplete: boolean;
  /** Максимум мини-вопросов за одну сессию ожидания */
  maxQuestions?: number;
  /** Жёсткий лимит длительности сессии (мс) */
  maxSessionMs?: number;
  /** Догрузка новых вопросов с сервера */
  allowRefill?: boolean;
}

interface RevealState {
  selectedIndex: number;
  correctIndex: number;
  isCorrect: boolean;
  timedOut: boolean;
  skipped?: boolean;
}

interface Props {
  interviewId: string;
  questions: WarmupQuizQuestion[];
  answeredSignatures?: string[];
  wait: QuizWaitState | null;
  onSessionComplete: () => void;
  onRefillQuestions?: () => Promise<WarmupQuizQuestion[] | null>;
}

function pickQuestion(
  questions: WarmupQuizQuestion[],
  usedIds: Set<string>,
  usedSignatures?: Set<string>
): WarmupQuizQuestion | null {
  const pool = questions.filter((q) => {
    if (usedIds.has(q.id)) return false;
    if (usedSignatures) {
      const sig = warmupQuestionSignature(q.skill, q.question);
      const topic = warmupTopicSignature(q.skill, q.question);
      if (usedSignatures.has(sig) || usedSignatures.has(topic)) return false;
    }
    return true;
  });
  if (!pool.length) return null;
  return pool[Math.floor(Math.random() * pool.length)];
}

async function submitWarmupWithRetry(
  interviewId: string,
  questionId: string,
  selectedIndex: number,
  timedOut: boolean
) {
  let lastError: unknown;
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      return await api.submitWarmupQuizAnswer(
        interviewId,
        questionId,
        selectedIndex,
        timedOut,
        30_000
      );
    } catch (e) {
      lastError = e;
      await new Promise((r) => window.setTimeout(r, 300 * (attempt + 1)));
    }
  }
  throw lastError;
}

async function skipWarmupAfterFailure(interviewId: string, questionId: string) {
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      return await api.skipWarmupQuizAnswer(interviewId, questionId);
    } catch {
      await new Promise((r) => window.setTimeout(r, 250 * (attempt + 1)));
    }
  }
  return null;
}

export default function WarmupQuizPanel({
  interviewId,
  questions,
  answeredSignatures = [],
  wait,
  onSessionComplete,
  onRefillQuestions,
}: Props) {
  const [current, setCurrent] = useState<WarmupQuizQuestion | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(QUIZ_SECONDS);
  const [locked, setLocked] = useState(false);
  const [reveal, setReveal] = useState<RevealState | null>(null);
  const [refilling, setRefilling] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const questionsRef = useRef(questions);
  const usedIdsRef = useRef<Set<string>>(new Set());
  const usedSignaturesRef = useRef<Set<string>>(new Set(answeredSignatures));
  const sessionCompleteRef = useRef(false);
  const submittingRef = useRef(false);
  const feedbackTimerRef = useRef<number | null>(null);
  const waitWasActiveRef = useRef(false);
  const operationCompleteRef = useRef(false);
  const refillInFlightRef = useRef(false);

  useEffect(() => {
    for (const sig of answeredSignatures) {
      usedSignaturesRef.current.add(sig);
    }
  }, [answeredSignatures]);

  useEffect(() => {
    questionsRef.current = questions;
    // Не перезаписывать options во время показа верного/неверного ответа —
    // иначе correctIndex с API перестаёт совпадать с кнопками.
    if (!current || reveal || locked) return;
    const fresh = questions.find((q) => q.id === current.id);
    if (fresh && fresh.options.join("|") !== current.options.join("|")) {
      setCurrent(fresh);
    }
  }, [questions, current, reveal, locked]);

  useEffect(() => {
    operationCompleteRef.current = Boolean(wait?.operationComplete);
  }, [wait?.operationComplete]);

  const clearFeedbackTimer = () => {
    if (feedbackTimerRef.current != null) {
      window.clearTimeout(feedbackTimerRef.current);
      feedbackTimerRef.current = null;
    }
  };

  const finishSession = useCallback(() => {
    if (sessionCompleteRef.current) return;
    sessionCompleteRef.current = true;
    clearFeedbackTimer();
    setCurrent(null);
    setReveal(null);
    setLocked(false);
    onSessionComplete();
  }, [onSessionComplete]);

  const tryRefill = useCallback(async (): Promise<WarmupQuizQuestion[] | null> => {
    if (wait?.allowRefill === false) return null;
    if (operationCompleteRef.current || refillInFlightRef.current) return null;
    refillInFlightRef.current = true;
    setRefilling(true);
    try {
      if (onRefillQuestions) {
        const updated = await onRefillQuestions();
        if (updated?.length) {
          questionsRef.current = updated;
          return updated;
        }
      }
      const res = await api.refillWarmupQuiz(interviewId);
      if (res.questions?.length) {
        questionsRef.current = res.questions;
        return res.questions;
      }
    } catch {
      /* не блокируем UX */
    } finally {
      refillInFlightRef.current = false;
      setRefilling(false);
    }
    return null;
  }, [interviewId, onRefillQuestions, wait?.allowRefill]);

  const questionLimitReached = useCallback(() => {
    const maxQ = wait?.maxQuestions;
    return maxQ != null && maxQ > 0 && usedIdsRef.current.size >= maxQ;
  }, [wait?.maxQuestions]);

  const startQuestion = useCallback(async () => {
    if (sessionCompleteRef.current) return;
    if (operationCompleteRef.current) {
      finishSession();
      return;
    }

    let next = pickQuestion(questionsRef.current, usedIdsRef.current, usedSignaturesRef.current);
    if (!next) {
      const updated = await tryRefill();
      if (operationCompleteRef.current) {
        finishSession();
        return;
      }
      if (updated) {
        next = pickQuestion(updated, usedIdsRef.current, usedSignaturesRef.current);
      }
    }

    if (operationCompleteRef.current || questionLimitReached()) {
      finishSession();
      return;
    }

    if (!next) {
      finishSession();
      return;
    }

    usedIdsRef.current.add(next.id);
    usedSignaturesRef.current.add(warmupQuestionSignature(next.skill, next.question));
    usedSignaturesRef.current.add(warmupTopicSignature(next.skill, next.question));
    setCurrent(next);
    setSecondsLeft(QUIZ_SECONDS);
    setLocked(false);
    setReveal(null);
  }, [finishSession, questionLimitReached, tryRefill]);

  useEffect(() => {
    if (!wait?.active) return;
    const maxMs = wait.maxSessionMs ?? 90_000;
    const hardStop = window.setTimeout(() => finishSession(), maxMs);
    return () => window.clearTimeout(hardStop);
  }, [wait?.active, wait?.maxSessionMs, finishSession]);

  useEffect(() => {
    const active = Boolean(wait?.active && wait.mode !== "off" && questions.length);
    if (active && !waitWasActiveRef.current) {
      sessionCompleteRef.current = false;
      void startQuestion();
    }
    if (!active) {
      clearFeedbackTimer();
    }
    waitWasActiveRef.current = active;
  }, [wait?.active, wait?.mode, questions.length, startQuestion]);

  useEffect(() => {
    if (!wait?.active || !wait.operationComplete) return;
    operationCompleteRef.current = true;
    if (sessionCompleteRef.current) return;
    if (!current && !locked && !refilling) {
      finishSession();
    }
  }, [wait?.active, wait?.operationComplete, current, locked, refilling, finishSession]);

  useEffect(() => () => clearFeedbackTimer(), []);

  const proceedAfterFeedback = useCallback(() => {
    clearFeedbackTimer();
    if (
      operationCompleteRef.current ||
      sessionCompleteRef.current ||
      questionLimitReached()
    ) {
      finishSession();
      return;
    }
    void startQuestion();
  }, [finishSession, questionLimitReached, startQuestion]);

  const showFeedbackThenProceed = useCallback(
    (nextReveal: RevealState) => {
      setReveal(nextReveal);
      setLocked(true);
      clearFeedbackTimer();
      const delay = operationCompleteRef.current ? FEEDBACK_MS_WHEN_MAIN_READY : FEEDBACK_MS;
      feedbackTimerRef.current = window.setTimeout(() => {
        proceedAfterFeedback();
      }, delay);
    },
    [proceedAfterFeedback]
  );

  const proceedAfterSubmitFailure = useCallback(
    async (questionId: string) => {
      const skipRes = await skipWarmupAfterFailure(interviewId, questionId);
      const correctIndex = skipRes?.correct_index ?? 0;
      setSubmitError("Ответ не сохранён — вопрос пропущен и не влияет на итоговую оценку.");
      showFeedbackThenProceed({
        selectedIndex: -1,
        correctIndex,
        isCorrect: false,
        timedOut: false,
        skipped: true,
      });
    },
    [interviewId, showFeedbackThenProceed]
  );

  useEffect(() => {
    if (!wait?.active || !current || locked) return;
    if (secondsLeft <= 0) {
      void (async () => {
        if (submittingRef.current) return;
        submittingRef.current = true;
        setSubmitError(null);
        let correctIndex = 0;
        try {
          const res = await submitWarmupWithRetry(interviewId, current.id, -1, true);
          correctIndex = res.correct_index ?? 0;
        } catch {
          submittingRef.current = false;
          await proceedAfterSubmitFailure(current.id);
          return;
        } finally {
          submittingRef.current = false;
        }
        showFeedbackThenProceed({
          selectedIndex: -1,
          correctIndex,
          isCorrect: false,
          timedOut: true,
        });
      })();
      return;
    }
    const t = window.setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [current, interviewId, locked, proceedAfterSubmitFailure, secondsLeft, showFeedbackThenProceed, wait?.active]);

  const handleSelect = async (index: number) => {
    if (!current || locked || submittingRef.current) return;
    submittingRef.current = true;
    setLocked(true);
    setSubmitError(null);
    let correctIndex = index;
    let isCorrect = false;
    try {
      const res = await submitWarmupWithRetry(interviewId, current.id, index, false);
      correctIndex = res.correct_index ?? index;
      isCorrect = Boolean(res.is_correct);
    } catch {
      submittingRef.current = false;
      await proceedAfterSubmitFailure(current.id);
      return;
    } finally {
      submittingRef.current = false;
    }
    showFeedbackThenProceed({
      selectedIndex: index,
      correctIndex,
      isCorrect,
      timedOut: false,
    });
  };

  if (!wait?.active || wait.mode === "off" || !questions.length) {
    return null;
  }

  if (!current && !refilling) {
    return (
      <div className="warmup-quiz-panel">
        <p className="warmup-quiz-label">Мини-тест</p>
        <p className="warmup-quiz-wait-main">
          {wait.operationComplete
            ? "Основной вопрос готов — можно продолжить интервью."
            : "Загружаем вопрос…"}
        </p>
        {submitError && <p className="warmup-quiz-error">{submitError}</p>}
        <button type="button" className="warmup-quiz-option" onClick={() => finishSession()}>
          Продолжить интервью
        </button>
      </div>
    );
  }

  const mainReadyHint = wait.operationComplete && !locked;

  return (
    <div className="warmup-quiz-panel">
      <p className="warmup-quiz-label">Пока идёт обработка — короткий вопрос по навыку</p>
      {refilling && (
        <p className="warmup-quiz-wait-main">Подгружаем дополнительные вопросы…</p>
      )}
      {mainReadyHint && (
        <p className="warmup-quiz-wait-main">Основной вопрос готов — завершите мини-вопрос</p>
      )}
      {submitError && <p className="warmup-quiz-error">{submitError}</p>}
      {current && (
        <>
          <p className="warmup-quiz-skill">{current.skill}</p>
          <p className="warmup-quiz-question">{current.question}</p>
          {!reveal && <p className="warmup-quiz-timer">Осталось: {secondsLeft} с</p>}
          {reveal && (
            <p className="warmup-quiz-feedback">
              {reveal.skipped
                ? "Вопрос пропущен из‑за сбоя сохранения — в итоговую оценку не входит."
                : reveal.timedOut
                ? "Время вышло — верный ответ подсвечен зелёным."
                : reveal.isCorrect
                  ? "Верно!"
                  : "Неверно — ваш ответ красным, верный зелёным."}
            </p>
          )}
          <div className="warmup-quiz-options">
            {current.options.map((option, index) => {
              const isCorrectOption = reveal && index === reveal.correctIndex;
              const isWrongPick =
                reveal && !reveal.timedOut && index === reveal.selectedIndex && !reveal.isCorrect;
              const className = [
                "warmup-quiz-option",
                isCorrectOption ? "warmup-quiz-option--correct" : "",
                isWrongPick ? "warmup-quiz-option--wrong" : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <button
                  key={`${current.id}-${index}`}
                  type="button"
                  className={className}
                  disabled={locked}
                  onClick={() => void handleSelect(index)}
                >
                  {option}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
