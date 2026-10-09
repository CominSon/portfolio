/** Человекочитаемое ФИО из имени файла резюме / сырого имени. */

export function humanizeResumeFileName(fileName: string | null | undefined): string | null {
  if (!fileName) return null;
  let base = fileName
    .replace(/\.(pdf|docx?|txt)$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!base) return null;

  // АбдуллинаР / НикишинВА / КузнецовАИ → «Абдуллина Р.» / «Никишин В.А.»
  const glued = base.match(/^([А-ЯЁA-Z][а-яёa-z]+)([А-ЯЁA-Z]{1,4})$/u);
  if (glued) {
    const surname = glued[1];
    const initials = glued[2].split("").join(".") + ".";
    return `${surname} ${initials}`;
  }

  // Уже с пробелом: «Сидоренко Анна»
  return base;
}

/** Не показывать «АбдуллинаР.pdf» как ФИО. */
export function looksLikeFileName(value: string | null | undefined): boolean {
  if (!value) return false;
  return /\.(pdf|docx?|txt)$/i.test(value.trim()) || /^[^\s]+\.(pdf|docx?)$/i.test(value.trim());
}

export function resolveCandidateDisplayName(opts: {
  apiName?: string | null;
  manualName?: string | null;
  resumeFileName?: string | null;
  fallback?: string;
}): string {
  const manual = (opts.manualName || "").trim();
  if (manual && !looksLikeFileName(manual)) return manual;

  const api = (opts.apiName || "").trim();
  if (api && !looksLikeFileName(api)) {
    // API иногда возвращает первую строку резюме с мусором — обрежем до разумного
    if (api.length <= 80 && !/[0-9@]/.test(api.slice(0, 3))) return api;
  }
  if (api && looksLikeFileName(api)) {
    return humanizeResumeFileName(api) || api;
  }

  const fromFile = humanizeResumeFileName(opts.resumeFileName);
  if (fromFile) return fromFile;

  return opts.fallback || "Кандидат";
}
