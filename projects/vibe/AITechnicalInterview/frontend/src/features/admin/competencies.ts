import type { Competency } from "../../services/api";

export const PROGRAMMING_LANGUAGES = [
  "Python",
  "SQL",
  "Java",
  "JavaScript",
  "TypeScript",
  "Go",
  "C++",
  "C#",
  "Rust",
  "Kotlin",
  "Swift",
  "PHP",
  "Ruby",
  "Scala",
  "R",
  "Dart",
  "Lua",
  "Perl",
  "Objective-C",
  "Haskell",
  "Elixir",
] as const;

/** Перераспределить веса так, чтобы сумма была ровно 100%. */
export function normalizeCompetencyWeights(items: Competency[]): Competency[] {
  if (items.length === 0) return [];
  const total = items.reduce((s, c) => s + Math.max(1, c.weight), 0);
  let acc = 0;
  return items.map((c, i) => {
    if (i === items.length - 1) {
      return { ...c, weight: 100 - acc };
    }
    const w = Math.max(1, Math.round((Math.max(1, c.weight) * 100) / total));
    acc += w;
    return { ...c, weight: w };
  });
}

export function weightSum(items: Competency[]): number {
  return items.reduce((s, c) => s + c.weight, 0);
}
