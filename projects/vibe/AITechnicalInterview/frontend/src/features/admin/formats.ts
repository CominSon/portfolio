export const INTERVIEW_FORMATS = [
  "Live Coding",
  "Code Review",
  "Architecture Interview",
] as const;

export type InterviewFormatName = (typeof INTERVIEW_FORMATS)[number];

export const LIVE_CODING_FORMAT = "Live Coding" as const;

export const FORMAT_DESCRIPTIONS: Record<InterviewFormatName, string> = {
  "Live Coding":
    "Кандидат пишет код в редакторе в реальном времени. AI задаёт задачу и оценивает решение по ходу работы.",
  "Code Review":
    "Разбор готового или фрагмента кода: поиск ошибок, улучшения, вопросы по стилю и архитектуре.",
  "Architecture Interview":
    "Обсуждение проектирования систем: компоненты, масштабирование, компромиссы, без обязательного написания кода.",
};

export const LIVE_CODING_AI_ASSISTANT_HINT =
  "Многошаговые задачи с AI в редакторе кода.";

export const LIVE_CODING_AI_ASSISTANT_FOOTNOTE =
  "* Пока работает только с Live Coding.";

export const FORMAT_MODE_HINTS: Record<string, string> = {
  auto: "AI выберет один формат из отмеченных ниже чекбоксов (или из всех, если ничего не отмечено).",
  restricted:
    "Отметьте чекбоксами допустимые форматы — AI выберет один из этого списка при сохранении.",
  manual: "Вы сами указываете единственный формат — чекбоксы не используются.",
};
