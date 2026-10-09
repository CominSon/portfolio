/** REST-клиент: по умолчанию через прокси Vite (/api → :8000), без CORS-проблем. */
import { getAdminAuthHeader } from "../features/admin/adminAuth";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, options?: RequestInit, timeoutMs = 0): Promise<T> {
  const url = API_BASE ? `${API_BASE}${path}` : path;
  let res: Response;
  const controller = timeoutMs > 0 ? new AbortController() : null;
  const timer =
    timeoutMs > 0
      ? window.setTimeout(() => controller?.abort("timeout"), timeoutMs)
      : null;
  const auth = getAdminAuthHeader();
  try {
    res = await fetch(url, {
      ...options,
      signal: options?.signal ?? controller?.signal,
      headers: {
        ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(auth ? { Authorization: auth } : {}),
        ...options?.headers,
      },
    });
  } catch (e) {
    if (timer) window.clearTimeout(timer);
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("Распознавание речи заняло слишком долго. Нажмите «Ответить» снова или отправьте код/текст вручную.");
    }
    const hint =
      "Не удалось связаться с API. Проверьте: backend на :8000, откройте UI как http://localhost:5173";
    throw new Error(e instanceof Error ? `${hint} (${e.message})` : hint);
  }
  if (timer) window.clearTimeout(timer);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export interface Competency {
  skill: string;
  level: string;
  weight: number;
  source: string;
}

export interface TranscriptItem {
  speaker: string;
  text: string;
}

export interface WarmupQuizQuestion {
  id: string;
  skill: string;
  question: string;
  options: string[];
}

export interface Interview {
  id: string;
  status: string;
  access_token: string;
  candidate_link?: string;
  selected_format?: string;
  allowed_formats: string[];
  format_selection_mode: string;
  duration_minutes: number;
  editor_language: string;
  editor_content: string;
  media_camera: boolean;
  media_microphone: boolean;
  media_screenshare: boolean;
  competencies: Competency[];
  feedback_emails?: string[];
  started_at?: string | null;
  transcripts?: TranscriptItem[];
  briefing_text?: string | null;
  briefing_audio_url?: string | null;
  warmup_quiz?: WarmupQuizQuestion[];
  live_coding_ai_assistant?: boolean;
  sql_dialect?: string | null;
  session_mode?: "test" | "full";
  test_max_turns?: number | null;
  candidate_name?: string | null;
}

export interface Employer {
  id: string;
  name: string;
  email: string;
  contact_emails: string[];
}

export const api = {
  adminMe: () => request<{ ok: boolean; username: string }>("/api/v1/admin/me"),

  createEmployer: (name: string, email: string, contactEmails: string[] = []) =>
    request<Employer>("/api/v1/employers", {
      method: "POST",
      body: JSON.stringify({ name, email, contact_emails: contactEmails }),
    }),

  getEmployer: (id: string) => request<Employer>(`/api/v1/employers/${id}`),

  rememberEmployerEmail: (employerId: string, email: string) =>
    request<{ contact_emails: string[] }>(
      `/api/v1/employers/${employerId}/contact-emails/${encodeURIComponent(email)}`,
      { method: "POST" }
    ),

  createInterview: (payload: Record<string, unknown>) =>
    request<Interview>("/api/v1/interviews", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  joinInterview: (token: string) => request<Interview>(`/api/v1/interviews/join/${token}`),

  uploadDocuments: (id: string, jd?: File, resume?: File) => {
    const fd = new FormData();
    if (jd) fd.append("job_description", jd);
    if (resume) fd.append("resume", resume);
    return request(`/api/v1/interviews/${id}/documents`, { method: "POST", body: fd });
  },

  analyzeDocuments: (id: string) =>
    request<{ proposed_competencies: Competency[] }>(`/api/v1/interviews/${id}/analyze-documents`, {
      method: "POST",
    }),

  updateCompetencies: (id: string, competencies: Competency[]) =>
    request(`/api/v1/interviews/${id}/competencies`, {
      method: "PUT",
      body: JSON.stringify({ competencies }),
    }),

  updateFormat: (id: string, data: Record<string, unknown>) =>
    request<Interview>(`/api/v1/interviews/${id}/format`, { method: "PUT", body: JSON.stringify(data) }),

  generateLink: (id: string, frontendOrigin?: string) =>
    request<{
      candidate_link: string;
      access_token: string;
      briefing_audio_url?: string | null;
      warmup_quiz_count?: number;
      warmup_quiz_ready?: boolean;
      preparing?: boolean;
      candidate_name?: string | null;
    }>(
      `/api/v1/interviews/${id}/generate-link`,
      {
        method: "POST",
        body: JSON.stringify(
          frontendOrigin ? { frontend_origin: frontendOrigin } : {}
        ),
      },
      60_000
    ),

  cloneForCandidate: (
    sourceId: string,
    opts: { candidateName?: string; resume?: File; resumeFilename?: string }
  ) => {
    const fd = new FormData();
    if (opts.candidateName?.trim()) fd.append("candidate_name", opts.candidateName.trim());
    if (opts.resumeFilename?.trim()) fd.append("resume_filename", opts.resumeFilename.trim());
    if (opts.resume) {
      fd.append("resume", opts.resume);
      if (!opts.resumeFilename?.trim() && opts.resume.name) {
        fd.append("resume_filename", opts.resume.name);
      }
    }
    return request<Interview>(`/api/v1/interviews/${sourceId}/clone-for-candidate`, {
      method: "POST",
      body: fd,
    });
  },

  getInterview: (id: string) =>
    request<Interview>(`/api/v1/interviews/${id}`, undefined, 15_000),

  mediaStatus: (id: string, status: { camera_enabled: boolean; microphone_enabled: boolean; screenshare_enabled: boolean }) =>
    request<{ status: string; media_ready: boolean }>(`/api/v1/interviews/${id}/media-status`, {
      method: "POST",
      body: JSON.stringify(status),
    }),

  startInterview: (id: string) =>
    request(`/api/v1/interviews/${id}/start`, { method: "POST" }),

  createOpeningTurn: (id: string) =>
    request<{
      ai_message: string;
      message_id?: string;
      audio_url: string | null;
      audio_ready?: boolean;
      should_end_interview?: boolean;
      editor_content?: string;
      editor_language?: string;
    }>(`/api/v1/interviews/${id}/opening-turn`, { method: "POST" }, 120_000),

  submitAnswer: (
    id: string,
    answer_type: "voice" | "code" | "combined",
    text?: string,
    editor_content?: string,
    timeoutMs = 180_000
  ) =>
    request<{
      ai_message: string;
      audio_url: string | null;
      audio_ready?: boolean;
      should_end_interview?: boolean;
      editor_content?: string;
      editor_language?: string;
      code_actions_applied?: number;
    }>(
      `/api/v1/interviews/${id}/submit-answer`,
      {
        method: "POST",
        body: JSON.stringify({ answer_type, text, editor_content }),
      },
      timeoutMs
    ),

  stt: async (id: string, blob: Blob, filename = "answer.webm") => {
    const fd = new FormData();
    fd.append("audio", blob, filename);
    return request<{ text: string; warning?: string }>(
      `/api/v1/interviews/${id}/stt`,
      { method: "POST", body: fd },
      300_000
    );
  },

  submitWarmupQuizAnswer: (
    id: string,
    questionId: string,
    selectedIndex: number,
    timedOut = false,
    timeoutMs = 30_000
  ) =>
    request<{ recorded: boolean; is_correct?: boolean; correct_index?: number }>(
      `/api/v1/interviews/${id}/warmup-quiz/answer`,
      {
        method: "POST",
        body: JSON.stringify({
          question_id: questionId,
          selected_index: selectedIndex,
          timed_out: timedOut,
        }),
      },
      timeoutMs
    ),

  skipWarmupQuizAnswer: (id: string, questionId: string, timeoutMs = 15_000) =>
    request<{ skipped: boolean; excluded_from_score: boolean; correct_index?: number }>(
      `/api/v1/interviews/${id}/warmup-quiz/skip`,
      {
        method: "POST",
        body: JSON.stringify({
          question_id: questionId,
          selected_index: -1,
          timed_out: false,
        }),
      },
      timeoutMs
    ),

  getWarmupQuiz: (id: string) =>
    request<{ ready: boolean; questions: WarmupQuizQuestion[]; answered_signatures?: string[] }>(
      `/api/v1/interviews/${id}/warmup-quiz`
    ),

  getRuntimeDebug: (id: string) =>
    request<{
      interview_id: string;
      status: string;
      transcript_count: number;
      warmup_answers: number;
      opening_tts_ready: boolean;
      main_question_ready?: boolean;
      last_debug_phase: string | null;
      trace: { at: string; phase: string; [key: string]: unknown }[];
    }>(`/api/v1/interviews/${id}/runtime-debug`, undefined, 8_000),

  refillWarmupQuiz: (id: string) =>
    request<{ added: number; total: number; questions: WarmupQuizQuestion[] }>(
      `/api/v1/interviews/${id}/warmup-quiz/refill`,
      { method: "POST" },
      120_000
    ),

  completeInterview: (id: string) =>
    request<{
      status: string;
      farewell_message: string;
      audio_url: string | null;
      audio_ready?: boolean;
    }>(`/api/v1/interviews/${id}/complete`, { method: "POST" }),

  getReport: (id: string) => request(`/api/v1/interviews/${id}/report`),

  createTemplate: (data: Record<string, unknown>) =>
    request("/api/v1/templates", { method: "POST", body: JSON.stringify(data) }),
};
