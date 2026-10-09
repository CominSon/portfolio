from mail_mcp_agent.src.mail import profile_store, smtp_client
from mail_mcp_agent.src.tools.base import BaseTool
from mail_mcp_agent.src.utils.arg_coerce import coerce_bool


class SendEmailTool(BaseTool):
    name = "send_email"
    description = (
        "Отправить письмо через SMTP. "
        "Всегда указывайте to с явными email-адресами (получите из get_mail_profile или resolve_recipients) — "
        "чтобы адресаты были видны в окне подтверждения RUN. "
        "send_to_self дополнительно добавит my_email. "
        "dry_run=true — только показать получателей без отправки."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Явные email получателей (обязательно для окна подтверждения)",
                },
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "attachment_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Пути к файлам для вложения",
                },
                "send_to_self": {
                    "type": "boolean",
                    "description": "Добавить my_email к получателям",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Только показать получателей, не отправлять",
                },
            },
            "required": ["subject"],
        }

    def _resolve_recipients(self, arguments):
        to = list(arguments.get("to") or [])
        cc = list(arguments.get("cc") or [])
        if coerce_bool(arguments.get("send_to_self")):
            my = profile_store.get_my_email()
            if not my:
                raise ValueError("Сначала вызовите healthcheck_mail или set_my_email")
            if my not in to:
                to.append(my)
        if not to:
            raise ValueError(
                "Укажите to с явными email (из get_mail_profile / resolve_recipients) "
                "или send_to_self=true после healthcheck_mail"
            )
        return to, cc

    def execute(self, arguments):
        to, cc = self._resolve_recipients(arguments)
        payload = {
            "recipients": {
                "to": to,
                "cc": cc,
            },
            "subject": arguments.get("subject") or "",
            "body": arguments.get("body") or "",
            "attachment_paths": arguments.get("attachment_paths") or [],
        }

        if coerce_bool(arguments.get("dry_run")):
            return {
                "ok": True,
                "dry_run": True,
                "message": "Письмо не отправлено — проверьте recipients перед send_email без dry_run.",
                **payload,
            }

        result = smtp_client.send_email(
            to_addresses=to,
            subject=payload["subject"],
            body=payload["body"],
            cc=cc or None,
            attachment_paths=payload["attachment_paths"] or None,
        )
        result["recipients"] = payload["recipients"]
        return result
