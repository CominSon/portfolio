from mail_mcp_agent.src.mail import mail_auth, profile_store
from mail_mcp_agent.src.tools.base import BaseTool

_EMAIL_MISSING_HINT = (
    "Автонастройка не определила email отправителя (From). "
    "Спросите у пользователя корпоративный адрес (например ivanov_iu@omega.sbrf.ru) "
    "и вызовите set_my_email(email=...). "
    "Без email отправка писем невозможна."
)


class HealthcheckMailTool(BaseTool):
    name = "healthcheck_mail"
    description = (
        "Проверка и автонастройка почты: pen_is + noterball(PPZ), login, email, POP3 SSL. "
        "Если my_email=null — спросите email у пользователя и вызовите set_my_email."
    )

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        from mail_mcp_agent.resources import settings

        creds = profile_store.sync_from_noterball()
        my_email = creds.get("email") or profile_store.get_my_email() or None
        result = {
            "protocol": "POP3",
            "pop3_host": settings.POP3_HOST,
            "pop3_port": settings.POP3_PORT,
            "smtp_host": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "ssl": True,
            "mail_login": creds["login"],
            "ppt": creds.get("ppt"),
            "my_email": my_email,
            "email_configured": bool(my_email),
            "password_source": "noterball(tim2)",
            "auto_configured": True,
        }

        if not my_email:
            result["needs_user_input"] = True
            result["ask_user"] = (
                "Укажите ваш корпоративный email для отправки писем (From)."
            )
            result["hint"] = _EMAIL_MISSING_HINT

        try:
            client, login, pwd_source = mail_auth.connect_pop3()
            msg_count, _ = client.stat()
            client.quit()
            result.update({
                "ok": True,
                "pop3_ok": True,
                "messages_on_server": msg_count,
                "mail_login": login,
                "password_source": pwd_source,
            })
        except Exception as exc:
            result["ok"] = False
            result["pop3_ok"] = False
            result["message"] = str(exc)
            result["hint"] = (
                "Проверьте pen_is.xlsx, noterball(PPZ) и MAIL_AUTH_DEBUG в logs/. "
                "Логин POP3 = mail_login (УЗ Windows)."
            )

        if result.get("ok") and not my_email:
            result["ok"] = False
            result["send_ready"] = False
            result["message"] = (
                "POP3 работает, но email отправителя не определён — нужен set_my_email."
            )
            if "hint" not in result or not result["hint"]:
                result["hint"] = _EMAIL_MISSING_HINT
        elif my_email:
            result["send_ready"] = True

        return result
