# Bitbucket MCP — краткая инструкция

Git для репозиториев WEALTHHUB (`df-bitbucket.ca.sbrf.ru`).

## Первый запуск

1. **`set_project_path`** — путь к открытому клону в IDEA (например `U:\BDProjects\users_scripts`).
2. **`get_project_path`** — проверить привязку.

## Основные команды

| Задача | Что вызвать |
|--------|-------------|
| Что изменилось | `git_status`, `git_diff` |
| Закоммить и отправить | **`commit_and_push`** (одним шагом) |
| Только коммит | `git_commit` с `message` |
| История | `git_log` |
| Ветки | `list_branches`, `checkout_branch` |
| Обновить локальные MCP Servers | **`update_mcp_servers`** |

## Важно

- Dot-файлы (`.idea`, `.gigacode`) **не коммитятся** — автоматически.
- `git push --force` **запрещён**.
- Push в master dashboards **запрещён**.
- Пароль — через noterball, не спрашивать в чате.

## Полный справочник

См. [MCP_TOOLS_GUIDE.md](../MCP_TOOLS_GUIDE.md) в корне `MCPServers`.
