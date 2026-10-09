from bitbucket_mcp_agent.src.git import git_runner
from bitbucket_mcp_agent.src.tools.base import BaseTool


class GetRepoInfoTool(BaseTool):
    name = "get_repo_info"
    description = "Какой репозиторий и ветка сейчас активны."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        try:
            return git_runner.get_repo_info()
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}


class HealthcheckGitTool(BaseTool):
    name = "healthcheck_git"
    description = "Проверка: путь к проекту, Bitbucket, пароль noterball."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        from bitbucket_mcp_agent.src.auth import noterball_auth
        from bitbucket_mcp_agent.src.git import project_store

        noterball_auth.get_password()
        path_status = project_store.get_project_path_status()
        result = {"windows_user": noterball_auth.get_windows_username(), **path_status}
        if not path_status.get("effective_project_path"):
            result["ok"] = False
            result["message"] = "Вызовите set_project_path."
            return result
        info = git_runner.get_repo_info()
        code, ssl, _ = git_runner.run_git(["config", "--get", "http.sslVerify"])
        result.update(info)
        result["http_ssl_verify"] = ssl if code == 0 else None
        result["ok"] = info.get("wealthhub_remote", False)
        return result


class GitStatusTool(BaseTool):
    name = "git_status"
    description = (
        "Что изменилось в репозитории. Без подтверждения. "
        "Показывает committable_paths (без dot-файлов)."
    )

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        return git_runner.git_status()


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Текст изменений (diff). Без подтверждения — выполняйте сразу по запросу."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "staged": {"type": "boolean"},
            },
        }

    def execute(self, arguments):
        return git_runner.git_diff(
            paths=arguments.get("paths"),
            staged=bool(arguments.get("staged")),
        )


class GitCompareRecentTool(BaseTool):
    name = "git_compare_recent"
    description = (
        "Сравнить последние версии (HEAD vs HEAD~N). Без подтверждения. "
        "Для «покажи разницу двух последних коммитов»."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Конкретный файл, опционально"},
                "commits_back": {
                    "type": "integer",
                    "description": "Сколько коммитов назад, по умолчанию 1",
                },
            },
        }

    def execute(self, arguments):
        return git_runner.git_compare_recent(
            path=arguments.get("path"),
            commits_back=arguments.get("commits_back") or 1,
        )


class GitLogTool(BaseTool):
    name = "git_log"
    description = "Список последних коммитов. Без подтверждения."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "max_count": {"type": "integer"},
                "path": {"type": "string"},
            },
        }

    def execute(self, arguments):
        return git_runner.git_log(
            max_count=arguments.get("max_count") or 20,
            path=arguments.get("path"),
        )


class PreviewFileAtCommitTool(BaseTool):
    name = "preview_file_at_commit"
    description = "Как выглядел файл в старом коммите (перед откатом)."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "commit": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["commit", "path"],
        }

    def execute(self, arguments):
        return git_runner.preview_file_at_commit(
            arguments["commit"], arguments["path"],
        )


class GitRestoreTool(BaseTool):
    name = "git_restore"
    description = "Откатить файл к прошлой версии."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["path"],
        }

    def execute(self, arguments):
        return git_runner.git_restore(
            arguments["path"], source=arguments.get("source"),
        )


class GitFetchTool(BaseTool):
    name = "git_fetch"
    description = "Обновить сведения о ветках с сервера (без merge)."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        return git_runner.git_fetch()


class GitPullTool(BaseTool):
    name = "git_pull"
    description = "Подтянуть изменения с сервера в текущую ветку."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        return git_runner.git_pull()


class ListBranchesTool(BaseTool):
    name = "list_branches"
    description = "Список веток."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        return git_runner.list_branches()


class CheckoutBranchTool(BaseTool):
    name = "checkout_branch"
    description = "Переключиться на другую ветку (create=true — создать)."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "create": {"type": "boolean"},
            },
            "required": ["name"],
        }

    def execute(self, arguments):
        return git_runner.checkout_branch(
            arguments["name"], create=bool(arguments.get("create")),
        )


class CommitAndPushTool(BaseTool):
    name = "commit_and_push"
    description = (
        "Один шаг: add (без dot-файлов/папок) + commit + push с noterball. "
        "Используйте когда пользователь просит закоммитить и отправить. "
        "Не требует промежуточных токенов и повторных «можно?»."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Текст коммита"},
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Конкретные файлы; пусто = все кроме dot",
                },
            },
            "required": ["message"],
        }

    def execute(self, arguments):
        return git_runner.commit_and_push(
            arguments["message"],
            paths=arguments.get("paths"),
        )


class GitCommitTool(BaseTool):
    name = "git_commit"
    description = "Только коммит (без push), без dot-файлов."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["message"],
        }

    def execute(self, arguments):
        git_runner.git_add(arguments.get("paths"), exclude_dotfiles=True)
        return git_runner.git_commit(arguments["message"])


class GitPushTool(BaseTool):
    name = "git_push"
    description = "Только push текущей ветки (noterball, без диалога Git)."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        return git_runner.git_push(force=False)
