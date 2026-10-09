"""Фильтрация и нормализация компетенций (только языки программирования из вакансии)."""

# Допустимые языки для MVP (регистронезависимое сопоставление)
PROGRAMMING_LANGUAGES: tuple[str, ...] = (
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
)

_ALIASES: dict[str, str] = {
    "golang": "Go",
    "go lang": "Go",
    "js": "JavaScript",
    "ts": "TypeScript",
    "csharp": "C#",
    "c sharp": "C#",
    "cpp": "C++",
    "cplusplus": "C++",
    "py": "Python",
    "postgresql": "SQL",
    "plpgsql": "SQL",
    "t-sql": "SQL",
    "tsql": "SQL",
}


def canonical_language(skill: str) -> str | None:
    s = skill.strip()
    if not s:
        return None
    low = s.lower()
    if low in _ALIASES:
        return _ALIASES[low]
    for lang in PROGRAMMING_LANGUAGES:
        if lang.lower() == low or lang.lower() in low or low in lang.lower():
            return lang
    return None


def filter_programming_languages(competencies: list[dict], max_items: int = 6) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for item in competencies:
        name = canonical_language(str(item.get("skill", "")))
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(
            {
                "skill": name,
                "level": item.get("level", "Middle"),
                "weight": int(item.get("weight", 10)),
                "source": item.get("source", "inferred"),
            }
        )
        if len(result) >= max_items:
            break
    return normalize_weights(result)


_SKILL_TO_EDITOR: dict[str, str] = {
    "Python": "python",
    "SQL": "sql",
    "Java": "java",
    "JavaScript": "javascript",
    "TypeScript": "typescript",
    "Go": "go",
    "C++": "cpp",
    "C#": "csharp",
    "Rust": "rust",
    "Kotlin": "kotlin",
    "Swift": "swift",
    "PHP": "php",
    "Ruby": "ruby",
    "Scala": "scala",
    "R": "r",
    "Dart": "dart",
    "Lua": "lua",
    "Perl": "perl",
    "Objective-C": "objective-c",
    "Haskell": "haskell",
    "Elixir": "elixir",
}


def skill_to_editor_language(skill: str) -> str:
    canonical = canonical_language(skill)
    if canonical and canonical in _SKILL_TO_EDITOR:
        return _SKILL_TO_EDITOR[canonical]
    return "python"


def primary_editor_language(competencies: list[dict]) -> str:
    if not competencies:
        return "python"
    top = max(competencies, key=lambda c: int(c.get("weight", 0)))
    return skill_to_editor_language(str(top.get("skill", "Python")))


def normalize_weights(competencies: list[dict]) -> list[dict]:
    if not competencies:
        return []
    total = sum(max(1, int(c.get("weight", 1))) for c in competencies)
    normalized: list[dict] = []
    acc = 0
    for i, c in enumerate(competencies):
        if i == len(competencies) - 1:
            w = 100 - acc
        else:
            w = max(1, round(max(1, int(c.get("weight", 1))) * 100 / total))
            acc += w
        normalized.append({**c, "weight": w})
    return normalized
