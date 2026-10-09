import queue
import uuid
from typing import Optional, Dict, Any

import email.utils

from modules.db.postgres_profiles_manager import PostgresProfileManager
from modules.core.pofiles_config import ProfilesConfig
from modules.mail.smtp_manager import SMTPManager


class ProfileOrchestrator:
    def __init__(self, logger):
        self.logger = logger
        self.postgres_profile_manager: PostgresProfileManager = PostgresProfileManager(logger=self.logger)
        self.smtp_manager: SMTPManager = SMTPManager(logger=self.logger)  # Модуль отправки сообщений
        self.profiles_config: ProfilesConfig = ProfilesConfig()

        # Очереди обмена сообщениями с фоновым циклом
        self.request_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.response_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

    # --------- приватно ---------
    def _wait_reply(self, corr_id: str, timeout_sec: float) -> Optional[dict]:
        """Ждём конкретный ответ с нужным correlation_id, с таймаутом."""
        try:
            while True:
                resp = self.response_queue.get(timeout=timeout_sec)
                if resp.get("correlation_id") == corr_id:
                    return resp.get("result")
        except queue.Empty:
            self.logger.warning("[ProfileOrchestrator] Таймаут ожидания ответа")
            return None

    # --------- Внешний API (удобные хелперы для агента) ---------
    def reserve(self, *, task_type: str, payload: dict, email: str, timeout_sec: float = 10.0
                ) -> Optional[dict]:
        """
        Синхронный helper. Кладём запрос на резервирование и ждём ответ (или таймаут).
        Возвращает {"process_id","profile_name","profile_path"} или None.
        """
        try:
            corr_id = str(uuid.uuid4())
            self.request_queue.put({
                "action": "reserve",
                "task_type": task_type,
                "payload": payload,
                "email": email,
                "correlation_id": corr_id
            })
            return self._wait_reply(corr_id, timeout_sec)
        except Exception as e:
            self.logger.error(f"[ProfileOrchestrator] Ошибка запроса на резервирование: {e}")

    def release(self, *, process_id: str, status: str) -> None:
        """Асинхронный helper — отправляет запрос на освобождение профиля (ответ не ждём)."""
        self.request_queue.put({
            "action": "release",
            "process_id": process_id,
            "status": status
        })

    def get_load(self, timeout_sec: float = 5.0) -> Optional[dict]:
        """Вернуть текущую загрузку по профилям: {profile_name: count_active_tasks}."""
        corr_id = str(uuid.uuid4())
        self.request_queue.put({"action": "get_load", "correlation_id": corr_id})
        return self._wait_reply(corr_id, timeout_sec)

    # --------- Неблокирующая итерация для ThreadPoolManager.run_orchestrator ---------
    def run_loop(self) -> None:
        """
        Обрабатывает все накопившиеся запросы из request_queue и кладёт ответы в response_queue.
        НИЧЕГО не блокирует. Вызывается часто из ThreadPoolManager.run_orchestrator().
        """
        processed = 0
        while True:
            try:
                req = self.request_queue.get_nowait()
            except queue.Empty:
                break

            processed += 1
            action = req.get("action")
            corr_id = req.get("correlation_id")

            try:
                if action == "reserve":
                    result = self.postgres_profile_manager.reserve_profile(
                        task_type=req["task_type"],
                        payload=req["payload"],
                        customer_email=req["email"]
                    )
                    # дополним путём к профилю (если бронирование удалось)
                    if result:
                        prof = result.get("profile_name")
                        result["profile_path"] = self.profiles_config.get_profile_path(prof)
                    if corr_id:
                        self.response_queue.put({"correlation_id": corr_id, "result": result})

                elif action == "release":
                    self.postgres_profile_manager.update_task_status(req["process_id"], req["status"])

                elif action == "get_load":
                    active = self.postgres_profile_manager.get_active_tasks() or []
                    load = {p: 0 for p in self.profiles_config.list_profiles()}
                    # ожидаем dict с key "profile_name" (или кортеж с именем на [0], если так возвращает менеджер)
                    for row in active:
                        name = (row.get("profile_name") if isinstance(row, dict)
                                else row[0] if isinstance(row, tuple) and len(row) > 0
                        else None)
                        if name in load:
                            load[name] += 1
                    if corr_id:
                        self.response_queue.put({"correlation_id": corr_id, "result": load})

                else:
                    self.logger.warning(f"[ProfileOrchestrator] Неизвестное действие: {action}")

            except Exception as e:
                self.logger.error(f"[ProfileOrchestrator] Ошибка при обработке {action}: {e}")
                if corr_id:
                    self.response_queue.put({"correlation_id": corr_id, "result": None})

        if processed:
            self.logger.debug(f"[ProfileOrchestrator] Обработано запросов: {processed}")

    def use_loop(self, name, urls, mode_int, color_int, mail_context):
        """делаем резервирование"""
        process_id = None
        profile_path = None
        addr = mail_context.get("from_email")
        if not addr and "from" in mail_context:
            addr = email.utils.parseaddr(mail_context["from"])[1]
        else:
            addr = mail_context.get("From")
        try:
            # резерв профиля
            info = self.reserve(
                    task_type=name,
                    payload={"urls": urls, "mode": mode_int, "color": color_int},
                    email=addr
                )
            if not info:
                # сразу отвечаем заказчику
                self.smtp_manager.send_reply(
                    original_msg=mail_context,
                    text="Все профили заняты. Пожалуйста, повторите запрос позже."
                )
                return process_id, profile_path
            process_id = info["process_id"]
            profile_path = info["profile_path"]
            return process_id, profile_path
        except Exception as e:
            self.logger.error(f"[ProfileOrchestrator] Ошибка: {e}")
            if process_id:
                try:
                    self.release(process_id=process_id, status="failed")
                except Exception as re:
                    self.logger.error(f"[ProfileOrchestrator] Ошибка release после исключения: {re}")


