from __future__ import annotations

import json
import os
from typing import Type, Optional, List, Dict, Any, Callable
from pydantic import BaseModel, Field
from langchain.tools import BaseTool

from modules.mail.smtp_manager import SMTPManager
from modules.pdf.pdf_starter import PDFStarter


# ---------- PDF: одиночная ссылка ----------

class PdfSinglePageInput(BaseModel):
    urls: List[str] = Field(
        default=[],
        description=(
            "Список http/https ссылок на страницы Навигатора, найденных в письме пользователя. "
            "Если найдена одна ссылка — передай список из одного элемента.")
    )
    """
    mode: Optional[str] = Field(
        default=None,
        description=(
            "Режим просмотра: 'пром'|'промышленный режим' — боевой режим (0); "
            "'предпром'|'предпросмотр'|'режим предпросмотра' — предпросмотр (1). "
            "Если в письме режим не указан, параметр можно опустить — по умолчанию ПРОМ (0)."
        )
    )
    """
    mode: Optional[str] = Field(
        default='0',
        description=(
            "Режим просмотра:\n"
            "'0' = пром / промышленный режим\n"
            "'1' = предпросмотр / предпром\n"
            "Никогда не передавай текст кроме 0 или 1"
        )
    )
    """
    color: Optional[str] = Field(
        default=None,
        description=(
            "Фон|Тема: 'светлый'|'белый'|'светлая' — светлая тема (0); "
            "'темный'|'синий'|'черный' — темная тема (1). "
            "Если в письме режим не указан, параметр можно опустить — по умолчанию Светлая тема (0)."
        )
    )
    """
    color: Optional[str] = Field(
        default='1',
        description=(
            "Цветовая схема:\n"
            "'0' = светлая тема\n"
            "'1' = темная тема\n"
            "Никогда не передавай текст кроме 0 или 1"
        )
    )


class PdfSinglePage(BaseTool):
    """
    Преобразует вход от агента (urls + mode + color) в словарь {url: {mode_int, color_int}},
    где mode_int: 0 = ПРОМ, 1 = ПРЕДПРОСМОТР.
    Если mode не указан — используем ПРОМ (0).

    где color_int: 0 = Светлая тема, 1 = Темная тема.
    Если color не указан — используем ПРОМ (0).

    """
    name: str = "pdf_single_page"
    description: str = (
        "Подготовка PDF из Навигатора. Прими от агента список ссылок (urls), режим (mode), фон (color). "
        "mode: 'пром'|'промышленный режим' -> 0; 'предпром'|'предпросмотр'|'режим предпросмотра' -> 1. "
        "Если режим не указан в письме — его можно не передавать, tool примет ПРОМ (0) по умолчанию. "
        "color: 'светлый фон | тема'|'белый фон|тема' -> 0; 'темный фон|тема'|'синий фон|тема'|'черный фон|тема' -> 1. "
        "Если фон не указан в письме — его можно не передавать, tool примет фон белый (0) по умолчанию. "
        "Возвращает JSON-словарь {url: {preview: 0|1, color_theme: 0|1}}. Если ссылок нет — вернёт подсказку с описанием режимов."

    )
    args_schema: Type[BaseModel] = PdfSinglePageInput

    logger: Any = Field(default=None, exclude=True)
    pdf_starter: Any = Field(default=None, exclude=True)
    smtp_manager: Any = Field(default=None, exclude=True)
    mail_context: Any = Field(default=None, exclude=True)
    pdf_callback: Optional[Callable[[dict, dict], None]] = Field(default=None, exclude=True)
    profile_orchestrator: Any = Field(default=None, exclude=True)

    def __init__(self, logger, mail_context, pdf_callback, profiles_orchestrator):
        super().__init__()
        self.logger = logger
        self.mail_context = mail_context
        self.pdf_callback = pdf_callback
        self.profile_orchestrator = profiles_orchestrator  # Модуль профилей
        self.pdf_starter: PDFStarter = PDFStarter(logger=self.logger)  # Модуль формирования PDF
        self.smtp_manager: SMTPManager = SMTPManager(logger=self.logger)  # Модуль отправки сообщений

    def _run(self, urls: List[str], mode: Optional[str] = '0', color: Optional[str] = '0') -> str:
        process_id, profile_path, result = None, None, None
        try:
            print(f"[PdfSinglePage] DEBUG: urls={urls}, mode={mode}, , color={color}")
            if not urls:
                # дружелюбная подсказка с перечислением режимов
                return "[PdfSinglePage] Не нашёл ссылку. Пришлите http/https ссылку на страницу Навигатора. "

            # дефолт по умолчанию — ПРОМ (0), Фон белый (0)
            mode_int = 0 if (mode is None or str(mode) == '0' or mode == "prom") else 1
            color_int = 0 if (color is None or str(color) == '0' or color == "white") else 1
            mapping: Dict[str, Dict[str, int]] = {u: {"preview": mode_int, "color_theme": color_int} for u in urls}
            # предварительное уведомление
            self.smtp_manager.notify_pdf_start(original_msg=self.mail_context, urls=urls, mode_int=mode_int,
                                               color_int=color_int)

            # делаем резервирование
            process_id, profile_path = self.profile_orchestrator.use_loop(name=self.name, urls=urls,
                                                                          mode_int=mode_int,
                                                                          color_int=color_int,
                                                                          mail_context=self.mail_context)
            if not process_id:
                return "[PdfSinglePage] Нет свободных профилей"

            # вызываем PDF-reader
            result = self.pdf_starter.start(dict_links=mapping, job_id=process_id, profile_path=profile_path)

            try:
                if process_id:
                    status_new = "done" if (
                                isinstance(result, dict) and result.get("status") == "success") else "failed"
                    self.profile_orchestrator.release(process_id=process_id, status=status_new)
            except Exception as re:
                self.logger.error(f"[PdfSinglePage] Ошибка release профиля: {re}")

            # возвращаем callback
            self.pdf_callback(result, self.mail_context)
            self.logger.info(f"[PdfSinglePage] Tool выполнен полностью")
            return "[PdfSinglePage] Tool выполнен полностью"
        except Exception as e:
            self.logger.error(f"[PdfSinglePage] Ошибка выполнения: {e}")
            return f"[PdfSinglePage] Ошибка выполнения: {e}"

    async def _arun(self, *args, **kwargs) -> str:
        raise NotImplementedError


# ---------- Fallback ----------
class FallbackReplyInput(BaseModel):
    reason: Optional[str] = Field(default=None, description="Необязательное пояснение")


class FallbackReply(BaseTool):
    """
    Ответ по умолчанию, если запрос не распознан как PDF-задача.
    """
    name: str = "fallback_reply"
    description: str = "Возвращает дефолтный ответ, если задача не распознана как поддерживаемая."
    args_schema: Type[BaseModel] = FallbackReplyInput

    logger: Any = Field(default=None, exclude=True)
    mail_context: Any = Field(default=None, exclude=True)
    smtp_manager: Any = Field(default=None, exclude=True)

    def __init__(self, logger, mail_context):
        super().__init__()
        self.logger = logger
        self.mail_context = mail_context
        self.smtp_manager: SMTPManager = SMTPManager(logger=self.logger)  # Модуль отправки сообщений

    def _send_(self, text):
        try:
            subject_override = "Не удалось обработать запрос"
            self.smtp_manager.send_reply(
                original_msg=self.mail_context,
                text=text,
                subject_override=subject_override
            )
            self.logger.info("[FallbackReply] Письмо-пояснение отправлено")
        except Exception as e:
            self.logger.error(f"[FallbackReply] Ошибка отправки письма-пояснения: {e}")

    def _run(self, text) -> str:
        base = """"Ваш запрос мне непонятен. Прошу ознакомиться с функциями, которые я могу выполнить:\n            - Отправь ссылку или ссылки на страницу Навигатора и я сформирую PDF этой страницы (Можно выбрать режим предпросмотра или пром);"""
        result = text
        if not result:
            result = base
        self._send_(text=result)
        return result

    async def _arun(self, *args, **kwargs) -> str:
        raise NotImplementedError


# ---------- PdfSendResult ----------
class PdfSendResultInput(BaseModel):
    status: str = Field(..., description="'success' или 'error'")
    file_path: Optional[str] = Field(None, description="Путь к PDF, если статус success")


class PdfSendResult(BaseTool):
    name: str = "pdf_send_result"
    description: str = (
        "Отправляет результат генерации PDF заказчику в ту же переписку. "
        "Если status='success', прикрепляет PDF. "
        "Если status='error', отправляет вежливое уведомление о проблеме."
    )
    args_schema: Type[BaseModel] = PdfSendResultInput

    logger: Any = Field(default=None, exclude=True)
    mail_context: Any = Field(default=None, exclude=True)
    smtp_manager: Any = Field(default=None, exclude=True)

    def __init__(self, logger, mail_context):
        super().__init__()
        self.logger = logger
        self.mail_context = mail_context
        self.smtp_manager: SMTPManager = SMTPManager(logger=self.logger)  # Модуль отправки сообщений

    def _send_failure(self):
        try:
            subject_override = "Ошибка формирования PDF"
            text = "К сожалению, возникла ошибка при формировании PDF. Попробуйте повторить позже."
            self.smtp_manager.send_reply(
                original_msg=self.mail_context,
                text=text,
                subject_override=subject_override
            )
            self.logger.info("[PdfSendResult] Письмо-ошибка отправлено")
        except Exception as e:
            self.logger.error(f"[PdfSendResult] Ошибка отправки письма-ошибки: {e}")

    def _send_success(self, file_path: str):
        try:
            subject_override = "Результат формирования PDF"
            text = "Ваш PDF успешно сформирован. Файл во вложении."
            self.smtp_manager.send_reply_with_attachment(
                original_msg=self.mail_context,
                subject_override=subject_override,
                text=text,
                attachments=[file_path]
            )
            self.logger.info("[PdfSendResult] Письмо с PDF отправлено")
        except Exception as e:
            self.logger.error(f"[PdfSendResult] Ошибка отправки PDF: {e}")

    def _run(self, status: str, file_path: Optional[str] = None) -> str:
        try:
            # --- Блок защиты от повторных вызовов ---
            if getattr(self, "_already_ran", False):
                self.logger.warning("[PdfSendResult] Повторный запуск блокирован — метод уже выполнялся ранее.")
                return "Повторный вызов отклонён (дубликат)"
            self._already_ran = True

            self.logger.info(f"[PdfSendResult] status={status}, file_path={file_path}")

            if status.lower() == "success" and file_path and os.path.exists(file_path):
                self._send_success(file_path)
                return "Результат отправлен (успех)"
            else:
                self._send_failure()
                return "Результат отправлен (ошибка)"
        except Exception as e:
            self.logger.error(f"[PdfSendResult] Ошибка при отправке результата: {e}")
            return f"Ошибка отправки: {e}"
