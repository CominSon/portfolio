# Руководство по использованию Greenplum MCP в GigaCode

Документ для аналитиков и разработчиков: как работать с MCP-сервером `greenplum` через окно агента GigaCode после того, как в настройках **Tools → GigaCode → MCP** сервер в статусе **Running**.

---

## 1. Как это работает

```
┌─────────────────┐     текст задачи      ┌──────────────────┐
│  Вы (чат       │ ────────────────────► │  GigaCode Agent  │
│  GigaCode)     │                       │  (LLM)           │
└─────────────────┘                       └────────┬─────────┘
                                                   │
                     при необходимости             │ tools/call
                                                   ▼
                                          ┌──────────────────┐
                                          │  gp_mcp_agent    │
                                          │  (MCP STDIO)     │
                                          └────────┬─────────┘
                                                   │ SQLAlchemy
                                                   ▼
                                          ┌──────────────────┐
                                          │  Greenplum       │
                                          │  (connectBD)     │
                                          └──────────────────┘
```

**Вам не нужно:**

- вручную вызывать JSON-RPC;
- писать имена tools в специальном синтаксисе;
- настраивать SQL в конфиге MCP.

**Вам нужно:**

- сформулировать задачу **обычным языком** (русский или английский);
- при необходимости указать схему, таблицу, фрагмент SQL.

Агент сам выберет подходящий tool (`healthcheck`, `run_select`, …), вызовет его через MCP и покажет результат в чате.

---

## 2. Список инструментов (tools)

| Tool | Назначение | Когда просить агента |
|------|------------|----------------------|
| `healthcheck` | Проверка подключения к БД | «Проверь подключение к Greenplum» |
| `search_tables` | Поиск таблиц по части имени | «Найди таблицы, где в имени есть …» |
| `get_columns` | Список колонок и типов | «Какие колонки у таблицы …» |
| `run_select` | Безопасный SELECT/WITH | «Выполни запрос …», логи PXF/процедур, любая аналитика |
| `export_query_csv` | Выгрузка результата SQL в файл | Большие списки, отчёты по логам |
| `explain` | План выполнения запроса | «Сделай EXPLAIN …», «Как выполнится запрос …» |
| `get_table_ddl` | DDL таблицы + OWNER | «DDL …» |
| `get_function` | DDL функции + OWNER (`full_ddl`) | «Покажи код функции …» |
| `get_procedure_schedule` | Типичное время запуска процедуры | Расписание для lineage |
| `compare_tables` | Сравнение external vs `smd_*` | «Сравни external и materialized …» |
| **`list_sessions`** | **Сессии со столбцом `state`** | см. раздел **2.0** |
| `find_blocking` | Кто блокирует сессию (любая УЗ) | см. раздел 2.2 |
| `find_functions_for_table` | Функции/процедуры, где упоминается таблица | «Чем наполняется таблица …» |
| `compare_field_values` | Значения в левой таблице, которых нет в правой | «Сравни поле A с полем B …» |
| `build_full_lineage` | Полная картина зависимостей с альтернативными ветками | «Построй полное дерево от витрины до источников …» |

---

## 2.0. Своя УЗ vs планировщик Максима (18764734)

**Критично не путать:**

| Вопрос пользователя | Tool | Параметры |
|---------------------|------|-----------|
| «Мои запросы», «моя УЗ», «что я выполняю» | `list_sessions` | `"scope": "self"` |
| «Максима», «Павленко», «планировщик», «18764734», «что в планировщиках активно» | `list_sessions` | `"scope": "scheduler"` |

Планировщик: **18764734** — **Павленко Максим Юрьевич** (основной пул, `manage_backend`).

Ответ **всегда** содержит таблицу `sessions_table` с колонками (первые — `pid`, **`state`**, `usename`, …) и `status_legend`.

Примеры:

```
Покажи мои активные сессии в БД (list_sessions scope=self).
```

```
Что сейчас активно в планировщиках у Максима / УЗ 18764734?
(list_sessions scope=scheduler)
```

Для своей УЗ с idle-транзакциями: `"scope": "self", "include_idle": true`.

---

## 2.1. Задача compare_tables (напоминание)

Изначальная постановка:

- **External-таблица** в схеме `s_grnplm_ld_blago_ubhq_ext` — имя `table_name`
- **Materialized** в схеме `s_grnplm_ld_blago_ubhq_in` — имя `smd_` + `table_name`
- Tool сравнивает **структуру** (колонки, типы, лишние/отсутствующие), **без** `COUNT(*)`, чтобы не нагружать external
- В tool передаётся имя **без** префикса `smd_`, например `"table": "customer_data"`

Пример в чате:

```
Сравни external-таблицу customer_data с materialized smd_customer_data (compare_tables).
```

---

## 2.2. find_blocking по pid (любая учётная запись)

Параметр **`pid`** — процесс, который **ждёт** (не обязательно ваша УЗ `18764734`).
Блокирующий backend тоже может быть **любым пользователем**.

Ответ tool `by_pid` содержит:

| Поле | Смысл |
|------|--------|
| `summary` | Краткий вывод текстом |
| `session` | Сессия из `pg_stat_activity` для pid |
| `ungranted_locks` | Lock'и pid без `granted` |
| `direct_blockers` | Кто **напрямую** держит lock (pid, user, query, объект) |
| `blocking_chain` | Цепочка вверх (A ждёт B, B ждёт C, …) |
| `sessions_blocked_by_target_pid` | Кого блокирует **этот** pid |

Пример в чате:

```
Кто блокирует процесс pid 2847191? Покажи цепочку и учётные записи.
Используй find_blocking — pid может быть не моей УЗ.
```

Без `pid` tool показывает только ожидающие сессии **вашей** УЗ планировщика.

---

## 2.3. Новые аналитические tools

### find_functions_for_table

```
Какими функциями наполняется s_grnplm_ld_blago_ubhq_work.my_mart?
```

Ответ: список функций с `usage_hint` (`likely_insert`, `likely_update`, …) + views.

Дальше: `get_function` по выбранной функции.

### compare_field_values

```
Сравни значения col_a в work.table_left с col_b в in.table_right,
где нет в правой; фильтр слева: day_id = 20250101.
```

Если расхождений > 100: `missing_count` + `preview_values` (10 шт.).

### build_full_lineage

```
Построй полное дерево зависимостей от s_grnplm_ld_blago_ubhq_work.final_mart до источников.
```

Tool учитывает все кандидатные функции (INSERT/UPDATE/MERGE/ссылки), не выбирая одну «лучшую».
Для каждого узла формируются альтернативные ветки, рекурсия идет до `spod_*` в схеме `*_in`
или до ограничения `max_depth`.

### Логи планировщика и PXF

```
Покажи упавшие процедуры планировщика за сегодня.
```

```
По списку витрин — когда была последняя успешная PXF-загрузка за месяц.
```

Имена `schema.table` можно передавать одной строкой в `qualified` или в `search_tables` / `get_table_ddl`.

### Выгрузка в CSV (любой объём)

Папка: **`<cwd>/gp_mcp_exports/`**, где `cwd` — `mcpServers.greenplum.cwd` (корень проекта).
Переопределение: env **`GP_MCP_EXPORT_DIR`**.

| Tool | Как выгрузить |
|------|----------------|
| `export_query_csv` | Любой SELECT/WITH → полный CSV |
| `compare_field_values` | `export_csv=true` — все `missing_value` |
| `run_select` | `export_csv=true` — все строки запроса |

В ответе: **`export_path`**, **`exports_directory`**, **`exported_rows`**, **`working_directory`**.
Формат CSV UTF-8 с BOM (открывается в Excel). `export_txt` устарел → используйте `export_csv`.

---

## 2.4. Умный редактор IDE и MCP

См. **[IDE_SMART_EDITOR.md](IDE_SMART_EDITOR.md)** — можно ли заставить автодополнение в файле использовать MCP (кратко: агент — да, inline completion — через Database tool + rules).

---

## 3. Ограничения и правила безопасности

### 3.1. Разрешённые SQL-операции

| Разрешено | Запрещено |
|-----------|-----------|
| `SELECT` | `INSERT`, `UPDATE`, `DELETE` |
| `WITH` (CTE) | `DROP`, `TRUNCATE`, `ALTER`, `CREATE` |
| `EXPLAIN` | `GRANT`, `REVOKE`, `COPY`, … |

Любая попытка выполнить запрещённую операцию завершится ошибкой в ответе tool.

### 3.2. Разрешённые схемы

Работа только в этих схемах (для метаданных и анализа):

| Схема | Назначение |
|-------|------------|
| `s_grnplm_ld_blago_ubhq_ext` | External-таблицы |
| `s_grnplm_ld_blago_ubhq_in` | Materialized-таблицы (`smd_*`) |
| `s_grnplm_ld_blago_ubhq_work` | Рабочие объекты |
| `s_grnplm_ld_blago_ubhq_2prod` | Prod-объекты |

Запросы к другим схемам через `get_columns` / `get_function` будут отклонены. В произвольном SQL агент теоретически может указать другую схему — **следите за формулировками** и просите только разрешённые схемы.

### 3.3. Лимиты

| Параметр | Значение |
|----------|----------|
| Строк в `run_select` | не более **100** за один вызов |
| Результатов `search_tables` | не более **50** |
| Таймаут запроса к БД | **120 секунд** (`statement_timeout`) |

### 3.4. Соглашение external / materialized

| Тип | Имя таблицы | Схема |
|-----|-------------|--------|
| External | `table_name` | `…_ext` |
| Materialized | `smd_table_name` | `…_in` |

Для tool **`compare_tables`** передаётся имя **без** префикса `smd_`:

- правильно: `"table": "customer_data"`
- неправильно: `"table": "smd_customer_data"`

Сравниваются: наличие обеих таблиц, список колонок, типы, лишние/отсутствующие колонки, флаг `identical`. **Без** `COUNT(*)` (чтобы не нагружать external).

---

## 4. Как писать задачи в окне агента

### 4.1. Общие принципы

1. **Конкретика:** схема + таблица + что нужно (колонки, фильтр, сортировка).
2. **Пошаговость:** для сложных задач разбивайте на пункты — агент вызовет несколько tools.
3. **Явное указание MCP:** если агент «фантазирует» без БД, напишите: *«используй MCP tools greenplum»*.
4. **Только чтение:** не просите обновлять/удалять данные — сервер это не выполнит.

### 4.2. Шаблоны формулировок

**Проверка связи**
```
Проверь подключение к Greenplum (MCP healthcheck).
```

**Поиск объектов**
```
Найди в разрешённых схемах все таблицы, в имени которых есть "ubhq".
```

**Метаданные**
```
Покажи колонки и типы данных для таблицы
s_grnplm_ld_blago_ubhq_work.<имя_таблицы>.
```

**Выборка данных**
```
Выполни SELECT (через MCP run_select) и покажи результат:

SELECT col1, col2, col3
FROM s_grnplm_ld_blago_ubhq_work.<таблица>
WHERE <условие>
```

**План запроса**
```
Построй EXPLAIN для запроса:

SELECT ...
FROM s_grnplm_ld_blago_ubhq_work.<таблица>
WHERE ...
```

**Функции**
```
Получи определение функции <имя_функции> в схеме s_grnplm_ld_blago_ubhq_work.
```

**Сравнение таблиц**
```
Сравни external-таблицу <имя> с материализованной smd_<имя>
(compare_tables, имя без префикса smd_).
```

**Активные процессы планировщика (УЗ 18764734)**
```
Покажи активные сессии планировщика Максима (УЗ 18764734).
```

**Блокировки**
```
Кто блокирует процесс с pid 12345? (find_blocking)
```
```
Покажи все блокировки для моей УЗ 18764734.
```

**DDL с владельцем (OWNER)**
```
Покажи DDL таблицы s_grnplm_ld_blago_ubhq_in.logs_procedure (get_table_ddl, qualified).
```
```
Покажи DDL функции s_grnplm_ld_blago_ubhq_in.manage_backend_18764734 (get_function).
```
В ответе: `owner`, `full_ddl` (в конце `ALTER ... OWNER TO`).

---

## 5. Примеры диалогов

### Пример 1: разведка по каталогу

**Вы:**
```
1. Проверь, что MCP-сервер Greenplum доступен.
2. Найди таблицы с "prompt" в имени в разрешённых схемах.
3. Для первой найденной таблицы выведи список колонок.
```

**Ожидаемое поведение агента:** `healthcheck` → `search_tables` → `get_columns` → текстовый ответ с таблицей колонок.

---

### Пример 2: анализ запроса

**Вы:**
```
Сделай EXPLAIN для запроса:

SELECT *
FROM s_grnplm_ld_blago_ubhq_work.ai_os_ub_widget_meta
WHERE widget_code = 'sales'
LIMIT 100
```

**Ожидаемое поведение:** `explain` → план в виде текста/списка строк.

---

### Пример 3: сверка external и materialized

**Вы:**
```
Сравни структуру external-таблицы orders с materialized smd_orders.
Покажи отсутствующие колонки, лишние колонки и расхождения по типам.
```

**Ожидаемое поведение:** `compare_tables` с `table: "orders"` → JSON с полями `missing_in_materialized`, `extra_in_materialized`, `type_mismatches`, `identical`.

---

### Пример 4: выборка с интерпретацией

**Вы:**
```
Выполни SELECT и кратко опиши результат (не больше 100 строк):

SELECT template_code, is_active
FROM s_grnplm_ld_blago_ubhq_work.ai_os_ub_prompt_templates
WHERE is_active = true
```

**Ожидаемое поведение:** `run_select` → таблица/JSON + краткий комментарий агента.

---

## 6. Технические детали для продвинутых пользователей

### 6.1. Что агент «видит» при вызове tool

Результат каждого tool приходит как **текст JSON** в поле `content`. Агент парсит его и пересказывает вам. Имеет смысл просить: *«покажи сырой JSON, если есть расхождения»* — для `compare_tables`.

### 6.2. Параметры tools (если настраиваете вручную / для отладки)

<details>
<summary>healthcheck</summary>

```json
{}
```
</details>

<details>
<summary>run_select</summary>

```json
{
  "sql": "SELECT col1 FROM s_grnplm_ld_blago_ubhq_work.my_table LIMIT 10"
}
```
</details>

<details>
<summary>explain</summary>

```json
{
  "sql": "SELECT * FROM s_grnplm_ld_blago_ubhq_work.my_table WHERE id = 1"
}
```
</details>

<details>
<summary>search_tables</summary>

```json
{
  "name": "customer"
}
```
</details>

<details>
<summary>get_columns</summary>

```json
{
  "schema": "s_grnplm_ld_blago_ubhq_work",
  "table": "my_table"
}
```
</details>

<details>
<summary>get_function</summary>

```json
{
  "schema": "s_grnplm_ld_blago_ubhq_work",
  "name": "my_function"
}
```
</details>

<details>
<summary>compare_tables</summary>

```json
{
  "table": "customer_data"
}
```
</details>

### 6.3. Подключение к БД

- Используется только `connectBD.use_new_engine("capgp1_in")`.
- Прямой `psycopg2` не применяется.
- Первое обращение к БД (например, `healthcheck`) инициализирует соединение — может занять несколько секунд.

### 6.4. Логи

| Куда | Что |
|------|-----|
| `U:\MCP Servers\gp_mcp_agent\logs\gp_mcp_*.log` | Подробный лог вызовов и SQL |
| stderr процесса MCP | Краткие сообщения (видны при отладке IDE) |

При ошибке tool сначала смотрите ответ в чате, затем последний файл в `logs\`.

---

## 7. Типичные проблемы в работе (не путать с запуском сервера)

| Симптом в чате | Возможная причина | Что сделать |
|----------------|-------------------|-------------|
| Агент не обращается к БД | Не распознал задачу как SQL | Явно: «через MCP greenplum» |
| «Схема не разрешена» | Другая схема в запросе | Использовать только 4 схемы из раздела 3.2 |
| «Запрещённая операция» | UPDATE/DELETE и т.д. в SQL | Переформулировать как SELECT |
| Пустой результат SELECT | Нет строк / неверная таблица | Проверить `search_tables`, `get_columns` |
| Ошибка connectBD / SQLAlchemy | Нет VPN или БД недоступна | VPN, `healthcheck`, логи |
| `'Connection' object has no attribute 'commit'` | Старая версия db_manager | Обновить `src/db/db_manager.py` (commit убран для SELECT) |
| `'list' object has no attribute 'values'` | Баг в fetch_scalar | Обновить `db_manager.py` (исправлено) |
| Обрезано 100 строк | Лимит `run_select` | Уточнить фильтр или разбить запрос |
| compare_tables: таблица не найдена | Неверное имя или нет `smd_*` | Проверить имена в `…_ext` и `…_in` |

---

## 8. Чего MCP-сервер **не** умеет (пока)

- Запись/изменение данных (DML/DDL).
- `manage_backend` с action=`D` (terminate) — **намеренно не exposed** в MCP.
- Запросы вне whitelist схем (жёстко для metadata-tools).
- Произвольное число строк в `run_select` (максимум 100).
- `COUNT(*)` при сравнении external/materialized.
- Гарантированный доступ ко всем системным каталогам GP — `find_blocking` может вернуть пусто при нехватке прав.
- Каталог «всех ваших самописных функций» — пока только через `get_function` по имени; общий реестр — в планах.

Расширение: новые tools в `src/tools/` + `tool_registry.py` — см. [README.md](README.md).

### Планы (ваши кейсы)

- Реестр персональных функций / подсказки агенту.
- Анализ логов в конкретных таблицах.
- Дополнительные обёртки над `manage_backend` и блокировками по мере появления прав на каталоги.

---

## 9. Чеклист перед рабочим использованием

- [ ] MCP **greenplum** в GigaCode: статус **Running**
- [ ] VPN / корпоративная сеть (если требуется для Greenplum)
- [ ] В чате: `Проверь подключение к Greenplum` → успешный `healthcheck`
- [ ] Вы знаете схему и примерное имя таблицы (или просите `search_tables`)
- [ ] Для сверки ext/in помните про префикс `smd_` и tool `compare_tables`

---

## 10. Быстрая шпаргалка (копировать в чат)

```
# Разведка
Проверь MCP healthcheck к Greenplum.
Найди таблицы с "<фрагмент_имени>" в разрешённых схемах.

# Метаданные
Покажи колонки s_grnplm_ld_blago_ubhq_work.<таблица>.

# Данные (только SELECT, до 100 строк)
Выполни через MCP:
SELECT ... FROM s_grnplm_ld_blago_ubhq_work.<таблица> WHERE ...

# План
Сделай EXPLAIN для: SELECT ... FROM ...

# Функция
Код функции <имя> в схеме s_grnplm_ld_blago_ubhq_work.

# Сверка ext / mat
Сравни external <имя> и materialized smd_<имя> (compare_tables).
```

---

## Связанные документы

- [README.md](README.md) — установка, конфиг MCP на Windows 10, архитектура, диагностика запуска.
- [resources/settings.py](resources/settings.py) — схемы, лимиты, имя подключения `capgp1_in`.
