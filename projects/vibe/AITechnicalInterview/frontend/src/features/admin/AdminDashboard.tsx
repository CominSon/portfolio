import { useEffect, useMemo, useState } from "react";
import { api, Competency, Interview } from "../../services/api";
import {
  normalizeCompetencyWeights,
  PROGRAMMING_LANGUAGES,
  weightSum,
} from "./competencies";
import {
  FORMAT_DESCRIPTIONS,
  FORMAT_MODE_HINTS,
  INTERVIEW_FORMATS,
  LIVE_CODING_AI_ASSISTANT_HINT,
  LIVE_CODING_FORMAT,
} from "./formats";
import EmailSelect from "./EmailSelect";
import AdminLogin from "./AdminLogin";
import {
  clearAdminCredentials,
  hasAdminCredentials,
} from "./adminAuth";
import {
  loadAllSavedEmails,
  loadLastEmployerId,
  rememberEmail,
  saveLastEmployerId,
} from "./savedEmails";
import { buildCandidateLink, isLocalAdminOrigin } from "../../utils/candidateLink";
import { resolveCandidateDisplayName } from "./candidateDisplayName";
import "./admin.css";

const STEP_LABELS = ["Подразделение", "Документы", "Языки", "Формат", "Ссылки"];
const MAX_CANDIDATES = 10;

type CandidateDraft = {
  key: string;
  name: string;
  resumeFile: File | null;
};

type GeneratedLink = {
  key: string;
  label: string;
  resumeFileName: string | null;
  link: string;
  interviewId: string;
};

function newCandidateDraft(): CandidateDraft {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: "",
    resumeFile: null,
  };
}

function candidateLabel(c: CandidateDraft, index: number): string {
  return resolveCandidateDisplayName({
    manualName: c.name,
    resumeFileName: c.resumeFile?.name,
    fallback: `Кандидат ${index + 1}`,
  });
}

export default function AdminDashboard() {
  const [authed, setAuthed] = useState(() => hasAdminCredentials());
  const [employerId, setEmployerId] = useState<string | null>(null);
  const [departmentName, setDepartmentName] = useState("");
  const [employerEmail, setEmployerEmail] = useState("");
  const [extraContactEmails, setExtraContactEmails] = useState<string[]>([]);
  const [newContactEmail, setNewContactEmail] = useState("");
  const [savedEmails, setSavedEmails] = useState<string[]>([]);
  const [serverContactEmails, setServerContactEmails] = useState<string[]>([]);
  const [interview, setInterview] = useState<Interview | null>(null);
  const [competencies, setCompetencies] = useState<Competency[]>([]);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [candidates, setCandidates] = useState<CandidateDraft[]>([newCandidateDraft()]);
  const [allowedFormats, setAllowedFormats] = useState<string[]>(["Live Coding", "Code Review"]);
  const [formatMode, setFormatMode] = useState("auto");
  const [selectedFormat, setSelectedFormat] = useState("");
  const [liveCodingAiAssistant, setLiveCodingAiAssistant] = useState(false);
  const [sessionMode, setSessionMode] = useState<"test" | "full">("test");
  const [generatedLinks, setGeneratedLinks] = useState<GeneratedLink[]>([]);
  const [linkGenHint, setLinkGenHint] = useState<string | null>(null);
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const emailSuggestions = useMemo(() => {
    const merged = [...new Set([...serverContactEmails, ...savedEmails])];
    return merged.filter(Boolean);
  }, [serverContactEmails, savedEmails]);

  useEffect(() => {
    setSavedEmails(loadAllSavedEmails(null));
  }, []);

  useEffect(() => {
    setSavedEmails(loadAllSavedEmails(employerId));
  }, [employerId]);

  useEffect(() => {
    if (!authed) return;
    void api.adminMe().catch(() => {
      clearAdminCredentials();
      setAuthed(false);
    });
  }, [authed]);

  useEffect(() => {
    if (!authed) return;
    const lastId = loadLastEmployerId();
    if (!lastId) return;
    setEmployerId(lastId);
    void api
      .getEmployer(lastId)
      .then((e) => {
        setServerContactEmails(e.contact_emails || []);
        setSavedEmails(loadAllSavedEmails(lastId));
      })
      .catch(() => undefined);
  }, [authed]);

  useEffect(() => {
    if (!authed || !employerId) return;
    void api.getEmployer(employerId).then((e) => setServerContactEmails(e.contact_emails || []));
  }, [authed, employerId]);

  useEffect(() => {
    if (!liveCodingAiAssistant) return;
    setAllowedFormats([LIVE_CODING_FORMAT]);
    if (formatMode === "manual") {
      setSelectedFormat(LIVE_CODING_FORMAT);
    }
  }, [liveCodingAiAssistant, formatMode]);

  if (!authed) {
    return (
      <AdminLogin
        onSuccess={() => {
          setAuthed(true);
          setError(null);
        }}
      />
    );
  }

  const logout = () => {
    clearAdminCredentials();
    setAuthed(false);
  };

  const goBack = () => {
    setError(null);
    if (step > 1) setStep(step - 1);
  };

  const setCompetenciesNormalized = (items: Competency[]) => {
    setCompetencies(normalizeCompetencyWeights(items));
  };

  const addExtraContactEmail = () => {
    const e = newContactEmail.trim().toLowerCase();
    if (!e || extraContactEmails.includes(e) || e === employerEmail.trim().toLowerCase()) return;
    setExtraContactEmails((list) => [...list, e]);
    setNewContactEmail("");
  };

  const rememberEmailLocally = (email: string) => {
    setSavedEmails(rememberEmail(email, employerId));
    if (employerId) void api.rememberEmployerEmail(employerId, email).catch(() => undefined);
  };

  const updateCandidate = (key: string, patch: Partial<CandidateDraft>) => {
    setCandidates((list) => list.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  };

  const addCandidate = () => {
    setCandidates((list) => (list.length >= MAX_CANDIDATES ? list : [...list, newCandidateDraft()]));
  };

  const removeCandidate = (key: string) => {
    setCandidates((list) => (list.length <= 1 ? list : list.filter((c) => c.key !== key)));
  };

  const createEmployer = async () => {
    if (!employerEmail.trim()) {
      setError("Укажите основной email");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const e = await api.createEmployer(departmentName, employerEmail.trim(), extraContactEmails);
      setEmployerId(e.id);
      saveLastEmployerId(e.id);
      setServerContactEmails(e.contact_emails || []);
      rememberEmail(employerEmail, e.id);
      extraContactEmails.forEach((x) => rememberEmail(x, e.id));
      setSavedEmails(loadAllSavedEmails(e.id));
      setStep(2);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const createInterview = async () => {
    if (!employerId) return;
    if (!jdFile) {
      setError("Загрузите файл вакансии — языки программирования извлекаются только из неё");
      return;
    }
    if (candidates.length < 1 || candidates.length > MAX_CANDIDATES) {
      setError(`Укажите от 1 до ${MAX_CANDIDATES} кандидатов`);
      return;
    }
    for (let i = 0; i < candidates.length; i++) {
      const c = candidates[i];
      if (!c.resumeFile && !c.name.trim()) {
        setError(`Кандидат ${i + 1}: загрузите резюме или укажите ФИО (если резюме нет)`);
        return;
      }
    }
    setLoading(true);
    setError(null);
    try {
      const feedbackEmails = [
        employerEmail.trim().toLowerCase(),
        ...extraContactEmails.map((e) => e.trim().toLowerCase()),
      ].filter(Boolean);
      const first = candidates[0];
      const inv = await api.createInterview({
        employer_id: employerId,
        feedback_emails: [...new Set(feedbackEmails)],
        ...(first.name.trim() ? { candidate_name: first.name.trim() } : {}),
      });
      setInterview(inv);
      setGeneratedLinks([]);
      await api.uploadDocuments(inv.id, jdFile, first.resumeFile ?? undefined);
      const analyzed = await api.analyzeDocuments(inv.id);
      setCompetenciesNormalized(analyzed.proposed_competencies);
      setStep(3);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const confirmCompetencies = async () => {
    if (!interview) return;
    if (competencies.length === 0) {
      setError("Добавьте хотя бы один язык программирования");
      return;
    }
    const normalized = normalizeCompetencyWeights(competencies);
    setCompetencies(normalized);
    setLoading(true);
    try {
      await api.updateCompetencies(interview.id, normalized);
      setStep(4);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const configureFormat = async () => {
    if (!interview) return;
    setLoading(true);
    try {
      const res = await api.updateFormat(interview.id, {
        format_selection_mode: formatMode,
        allowed_formats: allowedFormats,
        selected_format: formatMode === "manual" ? selectedFormat : undefined,
        live_coding_ai_assistant: liveCodingAiAssistant,
        session_mode: sessionMode,
        test_max_turns: sessionMode === "test" ? 2 : undefined,
      });
      setInterview({
        ...interview,
        selected_format: (res.selected_format as string) || interview.selected_format,
        live_coding_ai_assistant: Boolean(res.live_coding_ai_assistant),
        session_mode: (res.session_mode as "test" | "full") || sessionMode,
        duration_minutes: Number(res.duration_minutes) || interview.duration_minutes,
      });
      setStep(5);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const generateLinks = async () => {
    if (!interview) return;
    setLoading(true);
    setError(null);
    setLinkGenHint(`Готовим ссылки для ${candidates.length} кандидат(ов)…`);
    const origin = window.location.origin;
    const results: GeneratedLink[] = [];
    try {
      for (let i = 0; i < candidates.length; i++) {
        const draft = candidates[i];
        const label = candidateLabel(draft, i);
        setLinkGenHint(`Ссылка ${i + 1}/${candidates.length}: ${label}…`);

        let interviewId = interview.id;
        let accessToken = interview.access_token;

        if (i === 0) {
          const res = await api.generateLink(interviewId, origin);
          accessToken = res.access_token || accessToken;
          const displayName = resolveCandidateDisplayName({
            apiName: res.candidate_name,
            manualName: draft.name,
            resumeFileName: draft.resumeFile?.name,
            fallback: label,
          });
          results.push({
            key: draft.key,
            label: displayName,
            resumeFileName: draft.resumeFile?.name ?? null,
            link: res.candidate_link || buildCandidateLink(accessToken, origin),
            interviewId,
          });
          if (res.preparing) void pollSessionPrep(interviewId);
        } else {
          const cloned = await api.cloneForCandidate(interview.id, {
            candidateName: draft.name.trim() || undefined,
            resume: draft.resumeFile ?? undefined,
            resumeFilename: draft.resumeFile?.name,
          });
          interviewId = cloned.id;
          const res = await api.generateLink(interviewId, origin);
          accessToken = res.access_token || cloned.access_token;
          const displayName = resolveCandidateDisplayName({
            apiName: res.candidate_name || cloned.candidate_name,
            manualName: draft.name,
            resumeFileName: draft.resumeFile?.name,
            fallback: label,
          });
          results.push({
            key: draft.key,
            label: displayName,
            resumeFileName: draft.resumeFile?.name ?? null,
            link: res.candidate_link || buildCandidateLink(accessToken, origin),
            interviewId,
          });
          if (res.preparing) void pollSessionPrep(interviewId);
        }
      }
      setGeneratedLinks(results);
      setLinkGenHint(`Готово: ${results.length} ссылок. Скопируйте и отправьте каждому кандидату свою.`);
    } catch (err) {
      setGeneratedLinks(results);
      setLinkGenHint(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const pollSessionPrep = async (interviewId: string) => {
    for (let i = 0; i < 80; i++) {
      await new Promise((r) => window.setTimeout(r, 3000));
      try {
        const data = await api.getInterview(interviewId);
        const count = data.warmup_quiz?.length ?? 0;
        if (count > 0 && data.briefing_audio_url) {
          return;
        }
      } catch {
        /* polling optional */
      }
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  };

  const formatLinksForHr = (rows: GeneratedLink[]) =>
    rows.map((r) => `${r.label}\n${r.link}`).join("\n\n");

  const copyAllLinksForHr = async () => {
    if (!generatedLinks.length) return;
    const ok = await copyText(formatLinksForHr(generatedLinks));
    setLinkGenHint(
      ok
        ? `Скопирован список из ${generatedLinks.length} ссылок (ФИО + URL) — можно вставить в письмо HR.`
        : "Не удалось скопировать в буфер — выделите текст вручную."
    );
  };

  const updateCompetency = (index: number, field: keyof Competency, value: string | number) => {
    setCompetencies((prev) =>
      prev.map((c, i) => (i === index ? { ...c, [field]: value, source: "confirmed" } : c))
    );
  };

  const addCompetency = () => {
    setCompetenciesNormalized([
      ...competencies,
      { skill: "Python", level: "Middle", weight: 10, source: "manual" },
    ]);
  };

  const removeCompetency = (index: number) => {
    setCompetenciesNormalized(competencies.filter((_, i) => i !== index));
  };

  const rebalanceWeights = () => {
    setCompetenciesNormalized(competencies);
  };

  const totalWeight = weightSum(competencies);

  return (
    <div className="admin">
      <header className="admin-header">
        <div className="admin-header-row">
          <div>
            <h1>AI Technical Interview Platform</h1>
            <p>Admin — настройка интервью без человека-интервьюера</p>
          </div>
          <button type="button" className="btn-secondary" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>

      {error && <div className="admin-error">{error}</div>}

      <nav className="steps">
        {STEP_LABELS.map((label, i) => (
          <span key={label} className={step === i + 1 ? "step active" : "step"}>
            {i + 1}. {label}
          </span>
        ))}
      </nav>

      {step === 1 && (
        <section className="card admin-section">
          <h2>Подразделение</h2>
          <div className="form-grid">
            <div>
              <label>Название подразделения</label>
              <input
                value={departmentName}
                onChange={(e) => setDepartmentName(e.target.value)}
                placeholder="Например: Отдел разработки платформы"
              />
            </div>
            <EmailSelect
              label="Основной email HR / обратной связи"
              value={employerEmail}
              options={emailSuggestions}
              onChange={setEmployerEmail}
              onRemember={rememberEmailLocally}
            />
            <div className="full-width">
              <label>Дополнительные email для отчётов (необязательно)</label>
              {emailSuggestions.filter(
                (e) =>
                  e !== employerEmail.trim().toLowerCase() && !extraContactEmails.includes(e)
              ).length > 0 && (
                <select
                  className="email-select"
                  value=""
                  onChange={(e) => {
                    const picked = e.target.value.trim().toLowerCase();
                    if (!picked) return;
                    if (
                      picked === employerEmail.trim().toLowerCase() ||
                      extraContactEmails.includes(picked)
                    ) {
                      return;
                    }
                    setExtraContactEmails((list) => [...list, picked]);
                    rememberEmailLocally(picked);
                    setNewContactEmail("");
                  }}
                >
                  <option value="">— Выбрать сохранённый email —</option>
                  {emailSuggestions
                    .filter(
                      (e) =>
                        e !== employerEmail.trim().toLowerCase() &&
                        !extraContactEmails.includes(e)
                    )
                    .map((e) => (
                      <option key={e} value={e}>
                        {e}
                      </option>
                    ))}
                </select>
              )}
              <div className="email-chip-row">
                <input
                  type="email"
                  list="extra-email-suggestions"
                  value={newContactEmail}
                  placeholder="hr2@company.ru"
                  onChange={(e) => setNewContactEmail(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addExtraContactEmail();
                    }
                  }}
                />
                <datalist id="extra-email-suggestions">
                  {emailSuggestions.map((e) => (
                    <option key={`extra-${e}`} value={e} />
                  ))}
                </datalist>
                <button type="button" className="btn-secondary" onClick={addExtraContactEmail}>
                  Добавить
                </button>
              </div>
              <ul className="email-chips">
                {[employerEmail.trim().toLowerCase(), ...extraContactEmails]
                  .filter(Boolean)
                  .map((e) => (
                    <li key={e} className="email-chip">
                      {e}
                      {e !== employerEmail.trim().toLowerCase() && (
                        <button
                          type="button"
                          aria-label="Удалить"
                          onClick={() => setExtraContactEmails((xs) => xs.filter((x) => x !== e))}
                        >
                          ✕
                        </button>
                      )}
                    </li>
                  ))}
              </ul>
              <p className="hint">
                Отчёт уйдёт только на email из списка выше (основной + добавленные). Подсказки из
                прошлых интервью — в выпадающем списке выше и при вводе.
              </p>
            </div>
          </div>
          <div className="actions">
            <button className="btn-primary" disabled={loading} onClick={() => void createEmployer()}>
              Продолжить
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section className="card admin-section">
          <h2>Документы и кандидаты</h2>
          <p className="hint">
            Одна вакансия на всех. Языки/скиллы настраиваются один раз. На каждого кандидата (до{" "}
            {MAX_CANDIDATES}) в конце будет своя ссылка. Можно загрузить резюме и/или указать ФИО
            вручную (если резюме нет — ФИО обязательно).
          </p>
          <div className="form-grid">
            <div className="full-width">
              <label>Вакансия (PDF, DOCX, DOC) — обязательно</label>
              <input
                type="file"
                accept=".pdf,.doc,.docx"
                onChange={(e) => setJdFile(e.target.files?.[0] ?? null)}
              />
            </div>
          </div>

          <h3 className="candidates-heading">
            Кандидаты ({candidates.length}/{MAX_CANDIDATES})
          </h3>
          <div className="candidates-list">
            {candidates.map((c, index) => (
              <div key={c.key} className="candidate-row">
                <div className="candidate-row-title">Кандидат {index + 1}</div>
                <div className="form-grid candidate-fields">
                  <div>
                    <label>Резюме (опционально)</label>
                    <input
                      type="file"
                      accept=".pdf,.doc,.docx"
                      onChange={(e) =>
                        updateCandidate(c.key, { resumeFile: e.target.files?.[0] ?? null })
                      }
                    />
                    {c.resumeFile && <p className="hint file-name">{c.resumeFile.name}</p>}
                  </div>
                  <div>
                    <label>
                      {c.resumeFile ? "ФИО (необязательно — иначе из резюме)" : "ФИО кандидата"}
                    </label>
                    <input
                      value={c.name}
                      onChange={(e) => updateCandidate(c.key, { name: e.target.value })}
                      placeholder="Иванов Иван Иванович"
                      maxLength={255}
                    />
                  </div>
                </div>
                {candidates.length > 1 && (
                  <button
                    type="button"
                    className="btn-secondary candidate-remove"
                    onClick={() => removeCandidate(c.key)}
                  >
                    Удалить кандидата
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="actions">
            <button type="button" className="btn-secondary" onClick={goBack}>
              ← Назад
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={candidates.length >= MAX_CANDIDATES}
              onClick={addCandidate}
            >
              + Добавить кандидата
            </button>
            <button className="btn-primary" disabled={loading} onClick={() => void createInterview()}>
              Загрузить и проанализировать
            </button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="card admin-section">
          <h2>Языки программирования</h2>
          <p className="hint">
            Общие для всех {candidates.length} кандидат(ов). Только языки из вакансии (не более 6).
            Сумма весов:{" "}
            <strong className={totalWeight === 100 ? "weight-ok" : "weight-warn"}>{totalWeight}%</strong>
            {totalWeight !== 100 && (
              <>
                {" "}
                —{" "}
                <button type="button" className="link-btn" onClick={rebalanceWeights}>
                  пересчитать до 100%
                </button>
              </>
            )}
          </p>
          <table className="comp-table">
            <thead>
              <tr>
                <th>Язык</th>
                <th>Уровень</th>
                <th>Вес %</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {competencies.map((c, i) => (
                <tr key={i}>
                  <td>
                    <select value={c.skill} onChange={(e) => updateCompetency(i, "skill", e.target.value)}>
                      {PROGRAMMING_LANGUAGES.map((lang) => (
                        <option key={lang} value={lang}>
                          {lang}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select value={c.level} onChange={(e) => updateCompetency(i, "level", e.target.value)}>
                      {["Junior", "Middle", "Senior", "Lead"].map((l) => (
                        <option key={l}>{l}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={c.weight}
                      onChange={(e) => updateCompetency(i, "weight", Number(e.target.value))}
                    />
                  </td>
                  <td>
                    <button type="button" className="btn-secondary" onClick={() => removeCompetency(i)}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="actions">
            <button type="button" className="btn-secondary" onClick={goBack}>
              ← Назад
            </button>
            <button type="button" className="btn-secondary" onClick={addCompetency}>
              + Добавить язык
            </button>
            <button className="btn-primary" disabled={loading} onClick={() => void confirmCompetencies()}>
              Подтвердить
            </button>
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="card admin-section">
          <h2>Формат интервью</h2>
          <p className="hint">{FORMAT_MODE_HINTS[formatMode]}</p>
          <div className="form-grid">
            <div>
              <label>Режим выбора</label>
              <select value={formatMode} onChange={(e) => setFormatMode(e.target.value)}>
                <option value="auto">AI выбирает автоматически</option>
                <option value="restricted">Ограничить список (AI выберет один)</option>
                <option value="manual">Вручную (один формат)</option>
              </select>
            </div>
            {formatMode === "manual" && (
              <div>
                <label>Формат</label>
                <select
                  value={selectedFormat || INTERVIEW_FORMATS[0]}
                  onChange={(e) => setSelectedFormat(e.target.value)}
                  disabled={liveCodingAiAssistant}
                >
                  {INTERVIEW_FORMATS.map((f) => (
                    <option key={f} value={f} disabled={liveCodingAiAssistant && f !== LIVE_CODING_FORMAT}>
                      {f}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          {formatMode === "manual" && (
            <p className="format-desc">
              {FORMAT_DESCRIPTIONS[(selectedFormat || INTERVIEW_FORMATS[0]) as keyof typeof FORMAT_DESCRIPTIONS]}
            </p>
          )}
          {(formatMode === "manual"
            ? (selectedFormat || INTERVIEW_FORMATS[0]) === LIVE_CODING_FORMAT
            : allowedFormats.includes(LIVE_CODING_FORMAT)) && (
            <div className="format-option ai-assistant-option">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={liveCodingAiAssistant}
                  onChange={(e) => setLiveCodingAiAssistant(e.target.checked)}
                />
                Live Coding с AI-помощником в редакторе
              </label>
              <p className="format-desc-inline">{LIVE_CODING_AI_ASSISTANT_HINT}</p>
            </div>
          )}
          {formatMode !== "manual" && (
            <div className="format-checkboxes">
              <label>Допустимые форматы (AI выберет один из отмеченных)</label>
              {INTERVIEW_FORMATS.map((f) => (
                <div key={f} className="format-option">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={allowedFormats.includes(f)}
                      onChange={(e) => {
                        if (e.target.checked) setAllowedFormats((a) => [...a, f]);
                        else setAllowedFormats((a) => a.filter((x) => x !== f));
                      }}
                    />
                    {f}
                  </label>
                  <p className="format-desc-inline">{FORMAT_DESCRIPTIONS[f]}</p>
                </div>
              ))}
            </div>
          )}
          <div className="session-mode-block">
            <h3>Режим прогона</h3>
            <p className="hint">
              Временно: выберите тестовый прогон или полноценное интервью. Сохраняется вместе с
              форматом.
            </p>
            <div className="session-mode-options">
              <label className="checkbox-label">
                <input
                  type="radio"
                  name="sessionMode"
                  checked={sessionMode === "test"}
                  onChange={() => setSessionMode("test")}
                />
                Тестовый прогон (2 ответа кандидата → автозавершение)
              </label>
              <label className="checkbox-label">
                <input
                  type="radio"
                  name="sessionMode"
                  checked={sessionMode === "full"}
                  onChange={() => setSessionMode("full")}
                />
                Полное интервью (~60 минут, без лимита на число ответов)
              </label>
            </div>
          </div>
          <div className="actions">
            <button type="button" className="btn-secondary" onClick={goBack}>
              ← Назад
            </button>
            <button className="btn-primary" disabled={loading} onClick={() => void configureFormat()}>
              Сохранить формат и режим
            </button>
          </div>
          {interview?.selected_format && (
            <p className="selected-format">
              Выбран: <strong>{interview.selected_format}</strong>
              {interview.live_coding_ai_assistant && (
                <>
                  {" "}
                  · <strong>с AI-помощником</strong>
                </>
              )}
              {" · "}
              Режим:{" "}
              <strong>{sessionMode === "test" ? "тестовый (2 ответа)" : "полный (~60 мин)"}</strong>
            </p>
          )}
        </section>
      )}

      {step === 5 && (
        <section className="card admin-section">
          <h2>Ссылки для кандидатов</h2>
          <p className="hint">
            Режим:{" "}
            <strong>
              {interview?.session_mode === "full" || sessionMode === "full"
                ? "полное интервью (~60 мин)"
                : "тестовый прогон (2 ответа)"}
            </strong>
            . Будет создано {candidates.length} отдельн
            {candidates.length === 1 ? "ая ссылка" : "ых ссылок"} — у каждой свой кандидат.
          </p>
          {isLocalAdminOrigin(window.location.origin) && (
            <p className="hint">
              Админка открыта с localhost — ссылки будут с localhost и не откроются у кандидата.
              Откройте админку по публичному URL, затем сгенерируйте ссылки снова.
            </p>
          )}
          <ul className="candidates-preview">
            {candidates.map((c, i) => (
              <li key={c.key}>
                <strong>{candidateLabel(c, i)}</strong>
                {c.resumeFile ? ` · резюме: ${c.resumeFile.name}` : " · без резюме"}
              </li>
            ))}
          </ul>
          {linkGenHint && <p className="hint">{linkGenHint}</p>}
          <div className="actions">
            <button type="button" className="btn-secondary" onClick={goBack}>
              ← Назад
            </button>
            <button className="btn-primary" disabled={loading} onClick={() => void generateLinks()}>
              {loading
                ? "Готовим…"
                : candidates.length > 1
                  ? `Сгенерировать ${candidates.length} ссылок`
                  : "Сгенерировать ссылку"}
            </button>
          </div>
          {generatedLinks.length > 0 && (
            <div className="links-table-wrap">
              <div className="links-toolbar">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => void copyAllLinksForHr()}
                >
                  Скопировать весь список для HR
                </button>
              </div>
              <table className="links-table">
                <thead>
                  <tr>
                    <th>Кандидат</th>
                    <th>Резюме</th>
                    <th>Ссылка</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {generatedLinks.map((row) => (
                    <tr key={row.key}>
                      <td>
                        <strong>{row.label}</strong>
                      </td>
                      <td>{row.resumeFileName || "—"}</td>
                      <td className="link-cell">
                        <a href={row.link} target="_blank" rel="noreferrer">
                          {row.link}
                        </a>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => void copyText(`${row.label}\n${row.link}`)}
                        >
                          Копировать
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <pre className="links-hr-preview" aria-label="Список для HR">
                {formatLinksForHr(generatedLinks)}
              </pre>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
