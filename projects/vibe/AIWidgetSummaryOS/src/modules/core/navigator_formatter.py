from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# Цвета и размеры для АС Навигатора ({color:...}...{color}, {size:...}...{size})
RED = "#ff3300"
GREEN = "#008000"
SECTION_SIZE = "130%"
SUBSECTION_SIZE = "120%"


@dataclass(frozen=True)
class FormatContext:
    section_title: str
    subsection_title: Optional[str] = None


LineFormatter = Callable[[str], str]
SectionMatcher = Callable[[FormatContext], bool]


def _normalize_title(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_color_tag(text: str) -> bool:
    return "{color:" in text


def _has_size_tag(text: str) -> bool:
    return "{size:" in text


def _already_tagged(text: str) -> bool:
    return _has_color_tag(text) or _has_size_tag(text)


def wrap_color(text: str, color: str) -> str:
    if not text or _has_color_tag(text):
        return text
    return f"{{color:{color}}}{text}{{color}}"


def _has_bold_markdown(text: str) -> bool:
    return "**" in text


def _has_underline_tag(text: str) -> bool:
    return "++" in text


def wrap_bold(text: str) -> str:
    if not text or _has_bold_markdown(text):
        return text
    return f"**{text}**"


def wrap_underline(text: str) -> str:
    if not text or _has_underline_tag(text):
        return text
    return f"++{text}++"


def wrap_size(text: str, size: str) -> str:
    if not text or _has_size_tag(text):
        return text
    return f"{{size:{size}}}{text}{{size}}"


def bold_leading_metric_title(text: str) -> str:
    """Жирным выделяет название показателя до первого двоеточия."""
    if _has_bold_markdown(text) or ":" not in text:
        return text
    title, rest = text.split(":", 1)
    title = title.strip()
    if not title:
        return text
    return f"**{title}:**{rest}"


def _parse_pct_value(pct: str) -> Optional[float]:
    raw = str(pct or "").replace("%", "").replace(",", ".").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def color_pct(pct: str, *, green_gte: float = 100.0) -> str:
    if _already_tagged(pct):
        return pct
    value = _parse_pct_value(pct)
    color = GREEN if value is not None and value >= green_gte else RED
    return wrap_color(pct, color)


def colorize_execution_pct(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"выполнение {color_pct(match.group(1))}"

    return re.sub(r"выполнение\s+(\d+(?:[.,]\d+)?%)", repl, text, flags=re.IGNORECASE)


def format_attention_line(line: str) -> str:
    if _already_tagged(line):
        return line
    match = re.match(r"^(.+?)\s*\((\d+(?:[.,]\d+)?%)\)\s*$", line.strip())
    if not match:
        return line
    title, pct = match.group(1), match.group(2).replace(",", ".")
    return f"{title} ({wrap_color(pct, RED)})"


def format_transition_line(line: str) -> str:
    if _already_tagged(line):
        return line

    def red_zone(match: re.Match[str]) -> str:
        return f"переход в {wrap_color(match.group(1), RED)} зону"

    def green_zone(match: re.Match[str]) -> str:
        return f"переход в {wrap_color(match.group(1), GREEN)} зону"

    text = re.sub(r"переход в (красную) зону", red_zone, line, flags=re.IGNORECASE)
    text = re.sub(r"переход в (зел[ёе]ную) зону", green_zone, text, flags=re.IGNORECASE)
    return colorize_execution_pct(text)


def _normalize_trend_phrase_order(text: str) -> str:
    """
    WOW-дельта должна идти раньше фразы про тренд.
    LLM иногда ставит «Тренд недельного снижения...» перед «снижение на N п.п.» — возвращаем прежний порядок.
    """
    trend_re = re.compile(r"\s*Тренд недельного снижения сохраняется\.?\s*", re.IGNORECASE)
    decrease_re = re.compile(
        r"([Сс]нижение на \d+(?:[.,]\d+)?\s*п\.?\s*п\.?\.?)",
        re.IGNORECASE,
    )

    trend_match = trend_re.search(text)
    decrease_match = decrease_re.search(text)
    if not trend_match or not decrease_match:
        return text
    if trend_match.start() > decrease_match.start():
        return text

    trend_part = trend_match.group(0).strip()
    without_trend = trend_re.sub(" ", text, count=1)
    without_trend = re.sub(r"\s+", " ", without_trend).strip()

    decrease_match = decrease_re.search(without_trend)
    if not decrease_match:
        return text

    decrease_part = decrease_match.group(1).rstrip()
    if not decrease_part.endswith("."):
        decrease_part = f"{decrease_part}."

    before = without_trend[: decrease_match.start()].rstrip()
    after = without_trend[decrease_match.end() :].lstrip()
    rebuilt = f"{before} {decrease_part} {trend_part}".strip()
    if after:
        rebuilt = f"{rebuilt} {after}"
    return re.sub(r"\s+", " ", rebuilt).strip()


def format_trends_line(line: str) -> str:
    if line.strip().startswith("**") and _has_color_tag(line):
        return line

    text = bold_leading_metric_title(line)
    text = _normalize_trend_phrase_order(text)
    text = colorize_execution_pct(text)

    text = re.sub(
        r"рост на \d+(?:[.,]\d+)?\s*п\.?\s*п\.?",
        lambda match: wrap_color(match.group(0), GREEN),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"снижение на \d+(?:[.,]\d+)?\s*п\.?\s*п\.?",
        lambda match: wrap_color(match.group(0), RED),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"Переход из красной зоны в зел[ёе]ную\.?",
        lambda match: wrap_color(match.group(0).rstrip("."), GREEN) + ("." if match.group(0).endswith(".") else ""),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"Переход из зел[ёе]ной зоны в красную\.?",
        lambda match: wrap_color(match.group(0).rstrip("."), RED) + ("." if match.group(0).endswith(".") else ""),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"Тренд недельного снижения сохраняется\.?",
        lambda match: wrap_color(match.group(0).rstrip("."), RED) + ("." if match.group(0).endswith(".") else ""),
        text,
        flags=re.IGNORECASE,
    )
    return text


def format_section_title(title: Any) -> str:
    raw = str(title or "").strip()
    if not raw or _has_size_tag(raw):
        return raw
    return wrap_size(wrap_bold(raw), SECTION_SIZE)


def format_subsection_title(title: Any) -> str:
    raw = str(title or "").strip()
    if not raw or _has_size_tag(raw):
        return raw
    return wrap_size(wrap_underline(raw), SUBSECTION_SIZE)


def _matches_attention(ctx: FormatContext) -> bool:
    title = _normalize_title(ctx.section_title)
    return "зона" in title and "вниман" in title


def _matches_transition(ctx: FormatContext) -> bool:
    title = _normalize_title(ctx.section_title)
    return "переход" in title and "зон" in title


def _matches_trends(ctx: FormatContext) -> bool:
    title = _normalize_title(ctx.section_title)
    keywords = ("динамика", "тренд", "инсайт", "показател", "ключев")
    return any(keyword in title for keyword in keywords)


LINE_RULES: List[tuple[SectionMatcher, LineFormatter]] = [
    (_matches_attention, format_attention_line),
    (_matches_transition, format_transition_line),
    (_matches_trends, format_trends_line),
]


class NavigatorFormatter:
    """Post-processor: добавляет теги форматирования АС Навигатора к финальному отчёту."""

    def __init__(self, line_rules: Optional[List[tuple[SectionMatcher, LineFormatter]]] = None):
        self.line_rules = line_rules if line_rules is not None else LINE_RULES

    def format_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(report, dict):
            return report

        sections = report.get("sections")
        if not isinstance(sections, list):
            return report

        for section in sections:
            if not isinstance(section, dict):
                continue

            section["title"] = format_section_title(section.get("title"))
            ctx = FormatContext(section_title=str(section.get("title") or ""))

            section["lines"] = [
                self.format_line(ctx, line) for line in (section.get("lines") or [])
            ]

            subsections = section.get("subsections")
            if not isinstance(subsections, list):
                continue

            for subsection in subsections:
                if not isinstance(subsection, dict):
                    continue
                subsection["title"] = format_subsection_title(subsection.get("title"))
                sub_ctx = FormatContext(
                    section_title=_strip_navigator_tags(str(section.get("title") or "")),
                    subsection_title=str(subsection.get("title") or ""),
                )
                subsection["lines"] = [
                    self.format_line(sub_ctx, line) for line in (subsection.get("lines") or [])
                ]

        return report

    def format_line(self, ctx: FormatContext, line: Any) -> str:
        text = str(line or "")
        if not text.strip():
            return text

        plain_ctx = FormatContext(
            section_title=_strip_navigator_tags(ctx.section_title),
            subsection_title=_strip_navigator_tags(ctx.subsection_title or ""),
        )

        for matcher, formatter in self.line_rules:
            if matcher(plain_ctx):
                return formatter(text)
        return text


def _strip_navigator_tags(text: str) -> str:
    """Убирает теги Навигатора для сопоставления правил по названию раздела."""
    cleaned = re.sub(r"\{color:[^}]+\}", "", text)
    cleaned = re.sub(r"\{size:[^}]+\}", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("++", "")
    return cleaned.strip()
