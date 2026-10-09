"""Поиск по тексту письма — по словам, не только подстрока."""

import re


def _tokens(text):
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", (text or "").lower())
    return [w for w in words if len(w) >= 2]


def query_matches(query, *text_parts):
    query = (query or "").strip()
    if not query:
        return False

    haystack = " ".join(part for part in text_parts if part).lower()
    if not haystack:
        return False

    if query.lower() in haystack:
        return True

    words = _tokens(query)
    if not words:
        return query.lower() in haystack

    if len(words) == 1:
        return words[0] in haystack

    matched = sum(1 for word in words if word in haystack)
    required = max(2, len(words) - 1)
    return matched >= required
