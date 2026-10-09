/** Вспомогательные функции UI комнаты интервью. */

/** Мини-тест во время ожидания: не бесконечно, но и не слишком коротко. */
export const QUIZ_MAX_QUESTIONS = 5;
export const QUIZ_BLOCKING_SESSION_MS = 240_000;
export const QUIZ_STT_SESSION_MS = 120_000;

const STT_JUNK = /субтитр|корректор\s|редактор\s+субтитр|а\.синецкая|а\.егорова|subtitles?/i;

function collapseSttRepetition(text: string): string {
  const parts = text
    .split(/[\n\r]+|(?<=[.!?…])\s+/)
    .map((p) => p.trim())
    .filter(Boolean);
  const merged = parts.join(" ").trim();
  const words = merged.split(/\s+/).filter(Boolean);
  if (words.length < 4) return merged;

  let i = 0;
  while (i < words.length) {
    let collapsed = false;
    for (let n = 1; n <= Math.min(4, words.length - i); n++) {
      const phrase = words.slice(i, i + n).map((w) => w.toLowerCase());
      let reps = 1;
      let j = i + n;
      while (j + n <= words.length) {
        const next = words.slice(j, j + n).map((w) => w.toLowerCase());
        if (next.join(" ") !== phrase.join(" ")) break;
        reps += 1;
        j += n;
      }
      if (reps >= (n <= 2 ? 2 : 3)) {
        words.splice(i + n, j - i - n);
        collapsed = true;
        break;
      }
    }
    if (!collapsed) i += 1;
  }
  return words.join(" ");
}

export function sanitizeSttDisplay(text: string): string {
  const cleaned = collapseSttRepetition(text);
  const parts = cleaned
    .split(/[\n\r]+|(?<=[.!?…])\s+/)
    .map((p) => p.trim())
    .filter((p) => p && !STT_JUNK.test(p) && !/^субтитры субтитров/i.test(p));
  return parts.join(" ").trim();
}

export function wantsEndInterview(text: string): boolean {
  const t = text.toLowerCase();
  return [
    "закончить интервью",
    "завершить интервью",
    "закончи интервью",
    "давайте закончим",
    "можно заканчивать",
    "end interview",
    "finish interview",
  ].some((p) => t.includes(p));
}

export function buildAgentPayloadPreview(voiceText: string, editorCode: string): string {
  const parts: string[] = [];
  const voice = voiceText.trim();
  const code = editorCode.trim();
  if (voice) parts.push(voice);
  if (code) parts.push(`[Код в редакторе]\n${code}`);
  return parts.join("\n\n") || "(пустой ответ)";
}

export function appendUniqueEntry<T extends { speaker: string; text: string }>(
  prev: T[],
  speaker: string,
  text: string
): T[] {
  const trimmed = text.trim();
  if (!trimmed) return prev;
  const last = prev[prev.length - 1];
  if (last && last.speaker === speaker && last.text.trim() === trimmed) {
    return prev;
  }
  return [...prev, { speaker, text: trimmed } as T];
}
