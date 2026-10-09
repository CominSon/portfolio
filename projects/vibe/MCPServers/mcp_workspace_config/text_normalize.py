"""Нормализация текста при записи в файлы проекта."""

import re


def decode_json_escaped_text(text):
    """Литералы \\n \\t из JSON/чата → реальные переводы строк (битый DDL)."""
    if not text:
        return ""
    literal_n = text.count("\\n")
    real_n = text.count("\n")
    if literal_n >= 2 and literal_n > real_n:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    return text


def normalize_line_endings(text):
    """Убирает CRLF и литералы \\r/\\n из SQL/DDL."""
    if not text:
        return ""
    text = decode_json_escaped_text(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\\r" in text:
        text = text.replace("\\r\\n", "\n").replace("\\r", "\n")
    return text


def normalize_file_content(content, relative_path=None):
    rel = (relative_path or "").replace("\\", "/").lower()
    if rel.endswith(".sql") or rel.endswith(".md"):
        return normalize_line_endings(content)
    return content or ""


def ddl_looks_corrupted(content):
    """Эвристика: DDL обрезан или заполнен литералами \\n\\t."""
    if not content:
        return True
    if content.count("\\n\\t") > 20:
        return True
    if re.search(r"FROM\s+\S+\s+as\s+\w+\s*;\s*\\n", content, re.I):
        return True
    return False
