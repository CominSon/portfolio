import time

from langgraph.prebuilt import create_react_agent

from modules.db.postgres_roles_manager import PostgresRolesManager
from modules.gigachat.gigachat_manager import GigaChatAPIManager
from modules.gigachat.gigachat_promt_loader import GigaChatPromptLoader
from modules.gigachat.gigachat_tools import PdfSinglePage, FallbackReply, PdfSendResult
from modules.mail.imap_manager import IMAPManager


class LLMAgent:
    """
    Почтовый агент: по письму решает, какой tool вызвать.
    Сейчас:
      - если в письме просьба «пришли pdf» и есть ссылка → pdf_single_page(url)
      - иначе → fallback_reply()
    """

    def __init__(self, orchestrator, logger):
        self.logger = logger
        self.profiles_orchestrator = orchestrator
        self.postgres_roles_manager: PostgresRolesManager = PostgresRolesManager(logger=self.logger)
        self.imap_manager: IMAPManager = IMAPManager(logger=self.logger)
        self.prompt_loader = GigaChatPromptLoader(logger=self.logger)
        self.gigachat_api_model = GigaChatAPIManager(logger=self.logger).get_model()

        self.system_prompt = self.prompt_loader.build_system_text("system_mail_router")
        self.system_prompt_pdf = self.prompt_loader.build_system_text("system_pdf_result")
        self.tools_names = ["pdf_single_page", "pdf_send_result"]

    def _extract_text(self, result) -> str:
        """
        Возвращает человекочитаемый текст ответа из результата LangChain-агента.
        Покрывает варианты: result['output'] (AgentExecutor), result['messages'] (chat).
        """
        try:
            # самый частый случай у AgentExecutor: есть ключ 'output'
            if isinstance(result, dict) and isinstance(result.get("output"), str):
                return result["output"].strip()

            # иногда возвращается список сообщений
            if isinstance(result, dict) and isinstance(result.get("messages"), list):
                for msg in reversed(result["messages"]):
                    # берем последнее AI-сообщение
                    if getattr(msg, "type", "") in ("ai", "ai_message", "assistant"):
                        content = getattr(msg, "content", "")
                        if content:
                            return content.strip()

            # иногда приходит прямо AIMessage
            content = getattr(result, "content", None)
            if isinstance(content, str):
                return content.strip()
        except Exception as e:
            self.logger.error(f"[Roles] Ошибка при формировании ответа LLM: {e}")
            pass
        # запасной вариант
        return str(result)

    def _check_user_access(self, msg: dict, user_text: str):
        """
        Проверяет наличие email в таблице ролевой модели.
        Возвращает текст пользователя, если доступ разрешен,
        иначе возвращает специальный тег для остановки агента.
        """
        time.sleep(1)
        user_email = self.imap_manager.return_mail_from(msg=msg)
        try:
            result = self.postgres_roles_manager.get_user_by_email(user_email)
            if result and len(result) > 0:
                self.logger.info(f"[Roles] Пользователь найден в ролевой модели: {user_email}")
                return user_text
            else:
                self.logger.info(f"[Roles] Пользователь {user_email} не найден в ролевой модели. Доступ запрещен.")
                return "ACCESS_DENIED_USER"
        except Exception as e:
            self.logger.error(f"[Roles] Ошибка при проверке доступа пользователя {user_email}: {e}")
            return "ACCESS_DENIED_USER"

    def _on_pdf_result(self, result, mail_context):
        """
        Универсальная точка для обработки результата генерации PDF.
        Здесь можно вызвать новый агент или напрямую tool.
        """
        try:
            # Формируем контекст для агента
            user_text = f"Результат PDF генерации: {result['status']}, file_path={result['file_path']}"
            print("-----------------------------------------")
            self.logger.info(self.system_prompt_pdf)
            print(self.system_prompt_pdf)
            self.logger.info(user_text)
            print(user_text)
            print("-----------------------------------------")
            # Создаём новый агент
            tools = [
                PdfSendResult(
                    logger=self.logger,
                    mail_context=mail_context
                )
            ]
            agent = create_react_agent(model=self.gigachat_api_model, tools=tools, debug=False)

            result = agent.invoke({"messages": [self.system_prompt_pdf, user_text]})
            print(result)
        except Exception as e:
            self.logger.error(f"[LLMAgent] Ошибка при обработке результата PDF: {e}")
            # fallback — отправляем сразу
            PdfSendResult(
                logger=self.logger,
                mail_context=mail_context
            ).run(result)

    def handle_message(self, msg: dict) -> str | None:
        try:
            # Формируем контекст для агента
            user_text_full = f"Тема: {msg.get('subject', '')}\nТело:\n{msg.get('body', '')}"

            # Проверяем доступ пользователя к агенту (возвращаем результат)
            #user_text = self._check_user_access(msg=msg, user_text=user_text_full)
            user_text = user_text_full
            tools = [
                PdfSinglePage(logger=self.logger,
                              mail_context=msg,
                              pdf_callback=self._on_pdf_result,
                              profiles_orchestrator=self.profiles_orchestrator)
            ]
            agent = create_react_agent(self.gigachat_api_model, tools=tools, debug=False)
            result = agent.invoke({"messages": [self.system_prompt, user_text]})
            print(result)
            tags_result = self._extract_text(result)
            self.logger.info(f"[LLM] Ответ агента: {tags_result}")

            # Запускаем FallbackReply если ни один tools не отработал
            if not any(tool in tags_result for tool in self.tools_names):
                text_result = self.prompt_loader.get_prompt("system_mail_router").get("responses", {}).get(tags_result)
                FallbackReply(logger=self.logger, mail_context=msg).run(text_result)
            return result
        except Exception as e:
            self.logger.error(f"[LLM] Ошибка работы агента: {e}")
            return None

    def handler_fn(self, msg: dict):
        self.handle_message(msg)
