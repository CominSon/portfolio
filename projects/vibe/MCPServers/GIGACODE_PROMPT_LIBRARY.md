# GigaCode Prompt Library — WEALTHHUB MCP

Скопируйте промпты в **Settings → Tools → GigaCode → Prompt Library**  
(имя + текст; при необходимости добавьте короткий алиас для `/` в чате).

---

## 1. Справочник возможностей

**Имя:** `Справочник MCP`  
**Алиас (если поддерживается):** `/mcp`

```
Прочитай файл MCPServers/MCP_TOOLS_GUIDE.md (разделы до «Служебные функции»).
Выведи список возможностей обычными словами — без имён tools и без технических команд.
Структура: Greenplum, Git/Bitbucket, Почта, типовые сценарии.
```

---

## 2. Полный справочник (с техническими tools)

**Имя:** `Справочник MCP полный`  
**Алиас:** `/mcp-full`

```
Прочитай MCPServers/MCP_TOOLS_GUIDE.md целиком, включая «Служебные функции (доп.)».
Выведи полный список: что можно попросить + какие tools вызываются автоматически.
```

---

## 3. Как обновляется таблица / витрина

**Имя:** `Как обновляется таблица`  
**Алиас:** `/lineage`

```
Пользователь спрашивает, как обновляется или формируется таблица в Greenplum.

Сделай по шагам (без лишних вопросов, если имя таблицы уже в сообщении):
1. healthcheck (GP)
2. get_project_path — при необходимости
3. get_columns для целевой таблицы (qualified schema.table)
4. find_functions_for_table — функции и представления, зависящие от таблицы
5. Для главных кандидатов — get_function (DDL/тело процедуры)
6. Если нужна полная картина до spod_* — build_full_lineage

Ответ структурируй:
- Краткий вывод (1–2 предложения)
- Таблица: объект | роль (INSERT/UPDATE/view/ссылка)
- Цепочка «откуда → куда»
- Что смотреть в планировщике (имя процедуры, если есть)

Не используй run_select по pg_views.definition — только MCP tools.
При таймауте — упрости запрос, не повторяй тот же тяжёлый SQL.
```

---

## 4. Упавшие процедуры планировщика

**Имя:** `Ошибки планировщика`  
**Алиас:** `/failed-proc`

```
Найди упавшие процедуры планировщика Greenplum за период из запроса пользователя
(если период не указан — сегодня).

1. healthcheck
2. run_select по logs_procedure WHERE status = 'FAILED' за период
3. Для интересных записей — покажи procedure_name, date_start, logs_text (кратко)

Ответ: таблица procedure | время | суть ошибки (первая строка logs_text).
```

---

## 5. PXF / переливка ext → in

**Имя:** `Ошибки PXF`  
**Алиас:** `/pxf-failed`

```
Покажи неуспешные PXF-перегрузки (ext → in.smd_*) за период из запроса
(по умолчанию — сегодня).

1. healthcheck
2. run_select по logs_pxf_table WHERE status = 'FAILED' за период
3. Кратко: таблица ext, целевая smd_*, время, текст ошибки

Если пользователь назвал конкретную таблицу — отфильтруй по ней.
```

---

## 6. Мои активные запросы в GP

**Имя:** `Мои активные запросы`  
**Алиас:** `/my-sessions`

```
Покажи мои активные запросы в Greenplum.

Вызови list_sessions с scope=self, include_idle=false.
Выведи таблицу: pid | state | query_start | усечённый query.
Не используй run_select по pg_stat_activity.
```

---

## 7. Выгрузить в файл и отправить себе

**Имя:** `Выгрузка и почта себе`  
**Алиас:** `/export-mail`

```
Задача: выгрузить данные из Greenplum и отправить файл мне на почту.

1. healthcheck, healthcheck_mail
2. get_project_path — если needs_set_project_path, спроси путь к проекту IDEA один раз
3. export_query_csv (или xlsx, если просили Excel) — SQL из запроса пользователя
4. get_mail_profile — если my_email=null, спроси email и set_my_email
5. send_email: to=[my_email], attachment_paths=[export_path из ответа export]

Перед отправкой покажи recipients. Можно dry_run=true для проверки.
```

---

## 8. Загрузить CSV/Excel в таблицу

**Имя:** `Загрузка файла в GP`  
**Алиас:** `/load-file`

```
Пользователь дал путь к файлу для загрузки в Greenplum.

1. healthcheck, get_project_path
2. Спроси только: полное имя таблицы (schema.table). Для Excel — имя листа.
3. load_file_to_table — кодировку и разделитель CSV определяй сам (inspect/detect в tool).

Не спрашивай кодировку и разделитель, если tool их определил.
```

---

## 9. Git: что изменилось и закоммитить

**Имя:** `Git статус и коммит`  
**Алиас:** `/git-commit`

```
Покажи изменения в текущем git-проекте и при необходимости закоммить.

1. healthcheck_git, get_project_path
2. git_status → git_diff по изменённым файлам (кратко)
3. Если пользователь просил закоммитить/отправить — commit_and_push с осмысленным message
   (не коммить dot-папки — сервер отфильтрует сам).

Укажи ветку и project_path в ответе.
```

---

## 10. Найти письмо

**Имя:** `Поиск в почте`  
**Алиас:** `/mail-search`

```
Найди письмо по критериям из запроса пользователя (отправитель, тема, текст).

1. healthcheck_mail
2. search_messages — по словам/отправителю
3. get_message для 1–3 самых релевантных

Ответ: тема, от, дата, краткое содержание (body_text), calendar_invites если есть.
```

---

## 11. Найти email коллеги

**Имя:** `Email по ФИО`  
**Алиас:** `/resolve-email`

```
Найди корпоративный email по ФИО из запроса.

1. resolve_recipients
2. Если contacts пусто или ambiguous — покажи таблицу вариантов и попроси выбрать
3. Не выдумывай адреса

Outlook должен быть запущен для GAL.
```

---

## 12. Сравнить ext и smd на in

**Имя:** `Сравнить ext и in`  
**Алиас:** `/compare-ext-in`

```
Сравни external-таблицу на ext с materialized smd_* на in.

1. healthcheck
2. compare_tables или compare_field_values — имена из запроса пользователя
3. Краткий итог: совпадают ли ключевые поля, расхождения по count/sample

Большие объёмы — export_csv=true, не тащи всё в чат.
```

---

## 13. Собрать проект отчёта

**Имя:** `Собрать проект отчёта`  
**Алиас:** `/report-project`

```
Собери проект отчёта по витрине в Greenplum.

Вход: название + финальная таблица + папка.
Пример: «УКП Недельный», qs_t_ukp_weeks, папка U:\BDProjects\...\УКП Недельный.

1. start_report_project(project_path=полный путь, report_title, final_table)
2. get_report_context — смотри gaps / playbook
3. Сам через GP: find_functions_for_table → get_function → get_link_object →
   get_table_ddl / export_function_ddl → upsert_lineage_step / write_report_file
4. render_report_docs; семплы run_select (in/smd_*) → дописать BUSINESS
5. validate_report_project

Продолжение / правки пользователя («забыл процедуру X»):
→ resume_report_project или get_report_context
→ add_report_revision(text=…) → доработать тот же проект → resolve_report_revision

Доп. словари описаний: set_extra_knowledge(items=[…]).

Нет build_report_project (v3 — agent-driven).
```

---

## Как добавить в IDEA

1. **Settings → Tools → GigaCode → Prompt Library**
2. **Add** — вставьте **Имя** и текст из блока выше (между тройными backticks)
3. Повторите для нужных промптов
4. В чате: введите `/` и выберите промпт, допишите таблицу/период/путь

> Промпт **«Как обновляется таблица»** — основной для вопросов вида «как она обновляется?», «откуда берутся данные?», «кто наполняет витрину?».

---

*Обновляйте вместе с `MCP_TOOLS_GUIDE.md` и `GIGACODE_MCP_RULES.txt`.*
