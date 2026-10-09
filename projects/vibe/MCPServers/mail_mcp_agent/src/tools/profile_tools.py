from mail_mcp_agent.src.mail import profile_store
from mail_mcp_agent.src.tools.base import BaseTool


class GetMailProfileTool(BaseTool):
    name = "get_mail_profile"
    description = "Текущий авто-профиль (my_email, mail_login). Обычно после healthcheck_mail."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        profile_store.sync_from_noterball()
        data = profile_store.load_profile()
        my_email = profile_store.get_my_email() or None
        return {
            "my_email": my_email,
            "mail_login": profile_store.get_mail_login_saved() or None,
            "auto_configured": data.get("auto_configured", False),
            "email_configured": bool(my_email),
            "needs_user_input": not bool(my_email),
            "ask_user": (
                "Укажите ваш корпоративный email для отправки писем (From)."
                if not my_email
                else None
            ),
            "hint": (
                "Вызовите set_my_email(email='...') после ответа пользователя."
                if not my_email
                else None
            ),
            "profile": data,
        }


class SetMyEmailTool(BaseTool):
    name = "set_my_email"
    description = (
        "Задать email отправителя (From). Обязателен, если healthcheck_mail вернул "
        "my_email=null или needs_user_input=true — сначала спросите адрес у пользователя."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
            },
            "required": ["email"],
        }

    def execute(self, arguments):
        return profile_store.set_my_email(arguments.get("email"))
