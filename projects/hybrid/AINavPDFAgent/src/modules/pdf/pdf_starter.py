from modules.pdf.pdf_manager import Path
from modules.pdf.pdf_common import Common
from modules.pdf.pdf_browser_manager import BrowserManager


class PDFStarter:
    def __init__(self, logger):
        self.logger = logger
        self.path: Path = Path()
        self.common: Common = Common()

        # Модули для работы с браузером
        self.browser_manager: BrowserManager = BrowserManager()

    @staticmethod
    def return_info(dict_links):
        links: list = list(dict_links.keys())
        preview = True if next(iter(dict_links.values())).get("preview") == 1 else False
        color_theme = False if next(iter(dict_links.values())).get("color_theme") == 1 else True
        return links, preview, color_theme

    def return_callback(self, callback, result):
        try:
            [callback(result) if callback else None]
        except Exception as e:
            self.logger.error(f"Ошибка вызова callback: {e}")
            return "error"

    def start(self, dict_links, job_id, profile_path: str | None = None):
        """Оркестратор запуска Reader"""
        try:
            # Шаг -1: Определяем систему запуска скрипта
            system = self.common.chose_system_start()

            # Шаг 0: Логирование скрипта
            print(f"------------------------------------------------------------------")
            print(f"------------------------------------------------------------------")
            status_now = f"[СТАРТ]"
            self.logger.info(status_now)
            print(self.common.text_for_logs(table_name=self.path.BLOCK_NAME, text=status_now))

            # Шаг 1: Получаем ссылки и режим страницы
            links, preview, color_theme = self.return_info(dict_links=dict_links)

            # Шаг 2: Подключение к Дешборду через Selenium
            self.browser_manager.start_browser(system=system, preview=preview, color_theme=color_theme,
                                               profile_path=profile_path, logger=self.logger)

            # Шаг 3: Обработка вкладок и подготовка PDF (+ возвращаем статус ссылку)
            return self.browser_manager.work_with_links(links=links, job_id=job_id, logger=self.logger)

        except Exception as e:
            self.logger.error(f"Ошибка выгрузки PDF: {e}")
            return {"status": "error", "file_path": None}

