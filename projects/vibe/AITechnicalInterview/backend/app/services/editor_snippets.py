"""Запасные сниппеты для редактора, если LLM попросил код, но не прислал code_actions."""
from __future__ import annotations

from app.models.entities import Interview
from app.services.competency_utils import skill_to_editor_language


def _sql_sessions_snippet() -> str:
    return """-- Задание: для каждого user_id найти макс. число сессий, активных одновременно.
-- Учтите NULL в session_end (сессия ещё открыта) и равные timestamp.

CREATE TABLE sessions (
    user_id        INT,
    session_start  TIMESTAMP NOT NULL,
    session_end    TIMESTAMP  -- NULL = ещё активна
);

-- Sample data:
-- user_id | session_start       | session_end
-- 1       | 2024-01-01 10:00:00 | 2024-01-01 11:00:00
-- 1       | 2024-01-01 10:30:00 | 2024-01-01 12:00:00
-- 1       | 2024-01-01 11:30:00 | NULL
-- 2       | 2024-01-01 09:00:00 | 2024-01-01 09:30:00
INSERT INTO sessions (user_id, session_start, session_end) VALUES
    (1, '2024-01-01 10:00:00', '2024-01-01 11:00:00'),
    (1, '2024-01-01 10:30:00', '2024-01-01 12:00:00'),
    (1, '2024-01-01 11:30:00', NULL),
    (2, '2024-01-01 09:00:00', '2024-01-01 09:30:00');

-- Напишите запрос ниже (или найдите ошибки в черновике):
SELECT user_id, COUNT(*) AS cnt
FROM sessions
GROUP BY user_id;
"""


def _sql_orders_snippet() -> str:
    return """-- Задание: сумма заказов по каждому user_id из списка.
-- Найдите проблемы: NULL, безопасность, производительность.

CREATE TABLE orders (
    order_id  INT PRIMARY KEY,
    user_id   INT,
    amount    NUMERIC(12, 2)
);

-- Sample data:
-- order_id | user_id | amount
-- 1        | 1       | 100.00
-- 2        | 1       | 50.00
-- 3        | 2       | NULL
-- 4        | 3       | 20.00
INSERT INTO orders (order_id, user_id, amount) VALUES
    (1, 1, 100.00),
    (2, 1, 50.00),
    (3, 2, NULL),
    (4, 3, 20.00);

SELECT user_id, SUM(amount) AS total
FROM orders
WHERE user_id IN (1, 2, 3)
GROUP BY user_id;
"""


def fallback_editor_snippet(
    interview: Interview | None,
    *,
    competency_focus: str | None,
    ai_text: str = "",
) -> str:
    skill = (competency_focus or (interview.editor_language if interview else None) or "Python").strip()
    lang = skill_to_editor_language(skill)
    blob = f"{skill} {ai_text}".lower()

    if lang == "sql" or "sql" in blob:
        if "session" in blob or "сесс" in blob or "одновр" in blob or "пересек" in blob:
            return _sql_sessions_snippet()
        return _sql_orders_snippet()

    if "add_item" in blob or "мутабель" in blob or "default" in blob:
        return (
            "def add_item(item, container=None):\n"
            '    """Добавляет элемент в контейнер и возвращает его."""\n'
            "    if container is None:\n"
            "        container = []\n"
            "    container.append(item)\n"
            "    return container\n"
        )

    if "user_id" in blob or "заказ" in blob or "n+1" in blob or "totals" in blob:
        return (
            "def get_user_totals(user_ids, db_connection):\n"
            '    """Возвращает словарь {user_id: сумма заказов} для переданных id."""\n'
            "    result = {}\n"
            "    for user_id in user_ids:\n"
            "        cursor = db_connection.cursor()\n"
            "        cursor.execute(f\"SELECT SUM(amount) FROM orders WHERE user_id = {user_id}\")\n"
            "        row = cursor.fetchone()\n"
            "        result[user_id] = row[0] if row else 0\n"
            "    return result\n"
        )

    return (
        "def process(items):\n"
        '    """Обработка списка значений: вернуть min, max и среднее."""\n'
        "    if not items:\n"
        "        return None\n"
        "    return {\n"
        '        "min": min(items),\n'
        '        "max": max(items),\n'
        '        "avg": sum(items) / len(items),\n'
        "    }\n"
    )
