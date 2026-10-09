import platform
import subprocess
from datetime import datetime


class Common:
    def __init__(self):
        pass

    @staticmethod
    def return_time_now():
        return str(datetime.today()).rpartition('.')[0]

    def text_for_logs(self, table_name: str, text: str):
        return f"[{table_name}][{text}][{self.return_time_now()}]"

    @staticmethod
    def chose_system_start():
        """Определяем какая система запускает скрипт"""
        return platform.system()

    @staticmethod
    def handle_browser_error(error_text: str, logger):
        """
        Проверяет текст ошибки и при необходимости убивает процессы SberBrowser.
        Работает только в Windows.
        """
        keywords = [
            "no such window: target window already closed",
            "web view not found"
        ]

        if any(kw in error_text.lower() for kw in keywords):
            try:
                # убиваем процессы браузера и драйвера
                subprocess.run(
                    ["taskkill", "/F", "/IM", "sberbrowser.exe"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                subprocess.run(
                    ["taskkill", "/F", "/IM", "SberBrowserDriver.exe"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                logger.warning("[BrowserRecovery] Убиты процессы SberBrowser и Driver")
            except Exception as e:
                logger.error(f"[BrowserRecovery] Ошибка при завершении процессов: {e}")
                pass
