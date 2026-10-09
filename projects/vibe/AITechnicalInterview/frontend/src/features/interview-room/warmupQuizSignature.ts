/** Сигнатура вопроса — как в backend warmup_quiz_quality */

export function warmupNormalizeQuestion(question: string): string {
  let t = question.trim().toLowerCase();
  t = t.replace(/^\[[^\]]+\]\s*/, "");
  t = t.replace(/диалект:\s*\w+\.?\s*/gi, "");
  t = t.replace(/[^\w\sа-яё]+/gi, " ");
  t = t.replace(/\s+/g, " ").trim();
  for (const prefix of [
    "какой ",
    "какая ",
    "какие ",
    "что такое ",
    "что вернет ",
    "что вернёт ",
    "что выведет ",
    "что возвращает ",
    "выберите ",
    "укажите ",
    "как ",
  ]) {
    if (t.startsWith(prefix)) {
      t = t.slice(prefix.length).trim();
      break;
    }
  }
  return t;
}

export function warmupTopicKey(question: string): string {
  const q = question.toLowerCase();
  const rules: [RegExp, string][] = [
    [/\.lower\s*\(|lower\s*\(\s*\)/, "py_str_lower"],
    [/\brange\s*\(/, "py_range"],
    [/2\s*\*\*\s*3|\*\*\s*3/, "py_pow"],
    [/список.*кортеж|в\s+кортеж/, "py_list_to_tuple"],
    [/left\s+join|лев(ой|ая|ую)\s+таблиц/, "sql_left_join"],
    [/\bltrim\b|пробел.*начал|начал.*пробел/, "sql_ltrim"],
    [/bigint|больш.*длин/, "sql_bigint"],
    [/2147483647|integer\b/, "sql_integer"],
  ];
  for (const [re, key] of rules) {
    if (re.test(q)) return key;
  }
  const tokens = warmupNormalizeQuestion(question)
    .split(" ")
    .filter((w) => w.length > 2)
    .slice(0, 5);
  return tokens.length ? `gen:${tokens.join("_")}` : "gen:empty";
}

export function warmupQuestionSignature(skill: string, question: string): string {
  return `${skill.trim().toLowerCase()}|${warmupNormalizeQuestion(question)}`;
}

export function warmupTopicSignature(skill: string, question: string): string {
  return `${skill.trim().toLowerCase()}|topic:${warmupTopicKey(question)}`;
}
