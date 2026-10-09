import os
import shutil
import time
import uuid
from pathlib import Path as pathlib

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from modules.pdf.pdf_generator import PDFGenerator
from modules.pdf.pdf_manager import SeleniumSettings, CriticalError, Path
from modules.pdf.pdf_common import Common


class BrowserManager:
    def __init__(self):
        self.settings: SeleniumSettings = SeleniumSettings()
        self.common: Common = Common()
        self.pdf_generator: PDFGenerator = PDFGenerator()
        self.path: Path = Path()
        self.browser = None
        self.handles_in_order = []
        self.prev_temp_dir = None
        self.active_task_temp_dir = None
        self.temp_dir = self.path.PDF_TEMP_FOLDER

    def _enter_task_temp(self, job_id: str | None) -> str:
        """
        Создаёт и переключает self.temp_dir на папку задачи: <root>/<job_id>/.
        Возвращает путь к папке задачи.
        """
        root = pathlib(self.temp_dir)
        task_id = (job_id or uuid.uuid4().hex)[:12]
        task_dir = root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        self.prev_temp_dir = self.temp_dir
        self.active_task_temp_dir = str(task_dir)
        self.temp_dir = self.active_task_temp_dir
        return self.active_task_temp_dir

    def _exit_task_temp(self, cleanup: bool = True) -> None:
        """
        Возвращает self.temp_dir обратно и при необходимости удаляет папку задачи.
        """
        try:
            if cleanup and self.active_task_temp_dir:
                shutil.rmtree(self.active_task_temp_dir, ignore_errors=True)
        finally:
            if self.prev_temp_dir is not None:
                self.temp_dir = self.prev_temp_dir
            self._prev_temp_dir = None
            self._active_task_temp_dir = None

    def set_attr_browser(self, system, profile_path, logger):
        try:
            chrome_options = Options()

            # Определяем пути к бинарникам
            if system == "Windows":
                driver_path = os.getenv("CHROME_DRIVER_WIN")
                browser_path = os.getenv("CHROME_WIN")
            elif system == "Linux":
                driver_path = os.getenv("CHROME_DRIVER_LINUX", "chromedriver")
                browser_path = os.getenv("CHROME_LINUX", "chrome")
            else:
                raise Exception(f"Неподдерживаемая ОС: {system}")

            if not driver_path or not browser_path:
                raise FileNotFoundError("Не найдены пути до chromedriver или браузера.")

            chrome_options.binary_location = browser_path

            # Подключаем сертификаты
            chrome_options.add_argument(f"--cert-type=client")
            chrome_options.add_argument(f"--ignore-certificate-errors")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument(f"""--user-data-dir={profile_path}""")
            chrome_options.add_argument(f"--start-maximized")
            # chrome_options.add_argument(f"--window-size=1920,1200")
            # chrome_options.add_argument(f"--headless")
            if self.settings.HEADLESS:
                chrome_options.add_argument(f"--headless=new")

            service = ChromeService(executable_path=driver_path)
            return webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии настройки подключения для браузера]")
            logger.exception(e)
            raise CriticalError

    def use_white_theme(self, logger):
        """Включаем белую тему"""
        try:
            time.sleep(7)
            self.browser.find_element(By.CSS_SELECTOR, '.right.menu.d-flex').click()
            time.sleep(1)
            #self.browser.find_element(By.CSS_SELECTOR,
            #                          '.clickable-bg.border-bottom.ellipsis.va-center.ha-between.--appearance-settings.text-accent').click()
            self.browser.find_element(By.CSS_SELECTOR, 'div.popup-body.p-0.flex-col.hide-overflow > div > div:nth-child(5)').click()
            time.sleep(1)
            #self.browser.find_element(By.XPATH, '/html/body/div[7]/div/div/div[2]/div[3]/div[2]/div/div[2]/div').click()
            self.browser.find_element(By.CSS_SELECTOR, 'div.popup-body.p-0.main-profile.child-px-15.child-py-1.noselect.flex-col.autoscroll-y > div.flex-col.text-accent > div.ta-center.flex-col.child-mb-1.child-my > div > div:nth-child(2) > div').click()
            time.sleep(1)
            self.browser.refresh()
            status_now = f"[Белая тема успешно установлена]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
        except Exception as e:
            logger.info(f"[Ошибка на стадии смены темы на светлую]")
            logger.exception(e)
            pass

    def use_black_theme(self, logger):
        """Включаем темную тему"""
        try:
            time.sleep(7)
            self.browser.find_element(By.CSS_SELECTOR, '.right.menu.d-flex').click()
            time.sleep(1)
            #self.browser.find_element(By.CSS_SELECTOR,
            #                          '.clickable-bg.border-bottom.ellipsis.va-center.ha-between.--appearance-settings.text-accent').click()
            self.browser.find_element(By.CSS_SELECTOR, 'div.popup-body.p-0.flex-col.hide-overflow > div > div:nth-child(5)').click()
            time.sleep(1)
            #self.browser.find_element(By.XPATH, '/html/body/div[9]/div/div/div[2]/div[2]/div[2]/div/div[1]/div').click()
            self.browser.find_element(By.CSS_SELECTOR, 'div.popup-body.p-0.main-profile.child-px-15.child-py-1.noselect.flex-col.autoscroll-y > div.flex-col.text-accent > div.ta-center.flex-col.child-mb-1.child-my > div > div:nth-child(1) > div').click()
            time.sleep(1)
            self.browser.refresh()
            status_now = f"[Темная тема успешно установлена]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
        except Exception as e:
            logger.info(f"[Ошибка на стадии смены темы на темную]")
            logger.exception(e)
            pass

    def chose_theme(self, color_theme, logger):
        print(color_theme)
        if color_theme:
            self.use_white_theme(logger=logger)  # Устанавливаем белую тему
        else:
            self.use_black_theme(logger=logger) # Устанавливаем темную тему

    def click_preview_mode(self, logger):
        try:
            self.browser.find_element(By.CSS_SELECTOR, '.right.menu.d-flex').click()
            time.sleep(1)
            self.browser.find_element(By.CSS_SELECTOR,
                                      '.text-accent.clickable-bg.va-center.ha-between.--data-preview-selector').click()
        except Exception as e:
            logger.info(f"[Ошибка на стадии нажатия кнопки переключения превью]")
            logger.exception(e)
            pass

    def use_preview_mode(self, preview, logger):
        """Включаем режим предпросмотра"""
        try:
            time.sleep(7)

            css_sel = ".absolute.bottom.bg-primary.rounded-full.text-line-1"
            if preview and self.browser.find_elements(By.CSS_SELECTOR, css_sel):
                status_now = f"[Режим предпросмотра уже включен]"
                logger.info(status_now)
                print(self.common.text_for_logs(table_name="", text=status_now))
            elif not preview and self.browser.find_elements(By.CSS_SELECTOR, css_sel):
                status_now = f"[Режим предпросмотра выключен]"
                logger.info(status_now)
                print(self.common.text_for_logs(table_name="", text=status_now))
                self.click_preview_mode(logger=logger)
            elif preview and not self.browser.find_elements(By.CSS_SELECTOR, css_sel):
                status_now = f"[Режим предпросмотра включен]"
                logger.info(status_now)
                print(self.common.text_for_logs(table_name="", text=status_now))
                self.click_preview_mode(logger=logger)

        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии переключения в режим предпросмотра]")
            logger.exception(e)
            pass

    def move_cursor_out(self, offset_x: int, offset_y: int, logger):
        """Уводит виртуальный курсор из области графиков в серую зону"""
        try:
            body = self.browser.find_element(By.TAG_NAME, "body")
            actions = ActionChains(self.browser)

            # 1. Сначала ставим курсор в центр body
            center_x = body.size['width'] // 2
            center_y = body.size['height'] // 2
            actions.move_to_element_with_offset(body, center_x, center_y).perform()

            # 2. Потом смещаем от центра в нужное место
            actions.move_by_offset(offset_x, offset_y).perform()

            print(f"[Browser] Курсор смещён в ({center_x + offset_x}, {center_y + offset_y})")
        except Exception as e:
            logger.info(f"[Browser] Ошибка при смещении курсора в центр: {e}")
            logger.exception(e)

    def _move_abs(self, x: int, y: int):
        # абсолютное перемещение мыши без клика
        self.browser.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": int(x), "y": int(y), "buttons": 0},
        )

    def use_without_mouse_v2(self, logger, dx: int = -65, dy: int = -222):
        """
        dx: int = 65, dy: int = 222 - вправо край
        Надёжно уводит виртуальный курсор:
        1) ставит его в центр viewport (по данным window.innerWidth/innerHeight),
        2) смещает на dx, dy с учётом границ окна.
        Работает в headless стабильно (через DevTools Protocol).
        """
        try:
            # 1) размеры видимой области окна
            size = self.browser.execute_script(
                "return {w: window.innerWidth, h: window.innerHeight};"
            )
            w = int(size.get("w", 1200))
            h = int(size.get("h", 800))

            cx, cy = w // 2, h // 2

            # 2) сначала — ровно в центр
            self._move_abs(cx, cy)

            # Разница смещения
            dx_new = dx - cx
            dy_new = dy - cy
            # 3) затем — смещаем, но не выходим за границы
            x = max(1, min(w - 2, cx + dx_new))
            y = max(1, min(h - 2, cy + dy_new))
            self._move_abs(x, y)

            logger.info(f"[Browser] Курсор смещён в ({x}, {y}) из центра ({cx}, {cy}), dx={dx_new}, dy={dy_new}")
        except Exception as e:
            logger.info(f"[Browser][Ошибка на стадии увода мышки с экрана]")
            logger.exception(e)

    def use_without_mouse(self, logger):
        try:
            # сначала двинем “якорь” к началу документа (0,0),
            # затем сдвинемся на размер окна – 5px (чтобы оказаться у края)
            body = self.browser.find_element(By.TAG_NAME, "body")
            actions = ActionChains(self.browser)
            # уведём курсор
            actions.move_to_element_with_offset(body, -100, 0).perform()
            # self.move_cursor_out(offset_x=-400, offset_y=0, logger=logger)
            logger.info("[Browser] Курсор уведен влево")
        except Exception as e:
            logger.info(f"[Browser][Ошибка на стадии увода мышки с экрана]")
            logger.exception(e)

    @staticmethod
    def drop_all_windows(browser, logger):
        try:
            if browser.window_handles:
                for handle in browser.window_handles[1:]:
                    browser.switch_to.window(handle)
                    browser.close()
                browser.switch_to.window(browser.window_handles[0])
                logger.info("[Browser] Все лишние вкладки закрыты")
                time.sleep(3)
        except Exception as e:
            logger.info(f"[Browser][Не смогли закрыть вкладки]")
            logger.exception(e)

    def start_browser(self, system, preview, color_theme, profile_path, logger):
        try:
            status_now = f"[Запуск браузера]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))

            self.browser = self.set_attr_browser(system=system, profile_path=profile_path, logger=logger)
            self.browser.set_page_load_timeout(600)
            time.sleep(3)
            self.drop_all_windows(browser=self.browser, logger=logger)
            print(self.settings.START_URL)
            self.browser.refresh()
            time.sleep(3)
            self.browser.get(self.settings.START_URL)
            time.sleep(1)
            self.browser.get(self.settings.START_URL)
            time.sleep(1)
            self.chose_theme(color_theme=color_theme, logger=logger)
            #self.use_white_theme(logger=logger)  # Устанавливаем белую тему
            #self.browser.refresh()
            time.sleep(3)
            self.use_preview_mode(preview=preview, logger=logger)  # Переключаемся на предпросмотр (Если нужно)
            status_now = f"[Открыта стартовая страница: {self.settings.START_URL}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))

            return self.browser
        except Exception as e:
            try:
                self.common.handle_browser_error(error_text=str(e), logger=logger)
                self.start_browser(system=system, preview=preview,
                                   profile_path=profile_path, color_theme=color_theme, logger=logger)
            except Exception as e:
                print(e)
                logger.info(f"[Ошибка на стадии запуска браузера]")
                logger.exception(e)
                raise CriticalError

    def close_browser(self, logger):
        if self.browser:
            self.browser.quit()
            status_now = f"[Браузер закрыт]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))

    def wait_func(self, idx, logger):
        try:
            WebDriverWait(self.browser, 90).until(
                EC.invisibility_of_element_located((By.CLASS_NAME, "loader-progress"))
            )
            status_now = f"[Вкладка {idx + 1} загружена]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
            time.sleep(3)
        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии ожидания загрузки]")
            logger.exception(e)
            raise CriticalError

    def switch_links(self, idx, handle, logger, step=1):
        """Функция отвечает за переход между вкладками"""
        try:
            time.sleep(2)
            self.browser.switch_to.window(handle)
            status_now = f"[Ожидание загрузки вкладки {idx + 1}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
        except Exception as e:
            new_step = step
            if new_step == 4:
                print(e)
                logger.info(f"[Ошибка на стадии перехода между вкладками]")
                logger.exception(e)
                raise CriticalError
            new_step += 1
            status_now = f"[Попытка перехода между вкладками: {new_step}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
            self.switch_links(idx=idx, handle=handle, logger=logger, step=new_step)

    def open_links_in_tabs(self, links, logger):
        """Функция отвечает за открытие вкладок"""
        try:
            status_now = f"[Открываем вкладки по ссылкам]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
            for idx, url in enumerate(links):
                if idx == 0:
                    self.browser.get(url)
                    self.handles_in_order.append(self.browser.current_window_handle)
                else:
                    #self.browser.execute_script(f"window.open('{url}', '_blank');")
                    print(url)
                    self.browser.execute_script("window.open(arguments[0], '_blank');",url)
                    time.sleep(1)
                    all_handles = self.browser.window_handles
                    new_handle = list(set(all_handles) - set(self.handles_in_order))[0]
                    self.handles_in_order.append(new_handle)
                    self.browser.switch_to.window(new_handle)
                    self.browser.get(url)
        except Exception as e:
            logger.info(f"[Ошибка на стадии открытия вкладок]")
            logger.exception(e)
            raise CriticalError

    def click_rate_later(self, logger):
        try:
            time.sleep(4)
            wait = WebDriverWait(self.browser, 10)

            # wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.FeedBack-skip > div'))).click()

            self.browser.find_element(By.XPATH, '/html/body/div[7]/div/div/div/div[3]/div').click()
            time.sleep(1)
            # wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.FeedBack-skip > div:nth-child(2)'))).click()
            self.browser.find_element(By.CSS_SELECTOR, '.FeedBack-skip > div:nth-child(2)').click()

            logger.info("[Browser] Нажата кнопка 'Оценить позже'")
        except Exception as e:
            logger.info(f"[Ошибка на стадии отключения баннера оценки дешборда]")
            logger.exception(e)
            pass

    @staticmethod
    def drop_nav_ii(browser, logger):
        """Удаляет всплывающее окно помощника навигатора."""
        try:
            browser.execute_script("""
                const el = document.querySelector('.screen-label');
                        if (el) el.remove();
            """)
            logger.info(f"[Иконка помощника навигатора удалена]")
            time.sleep(2)
        except Exception as e:
            logger.info("[Ошибка при удалении иконки помощника навигатора]")
            logger.exception(e)
            raise CriticalError

    def work_with_links(self, links, job_id, logger):
        """Работаем с вкладками"""
        try:
            self._enter_task_temp(job_id=job_id)
            # Шаг 1: Открываем все ссылки на отдельных вкладках
            self.open_links_in_tabs(links=links, logger=logger)
            time.sleep(3)  # was 3

            # Шаг 2: Переключение на вкладки по очереди и ожидание загрузки
            for idx, handle in enumerate(self.handles_in_order):
                self.switch_links(idx=idx, handle=handle, logger=logger)
                time.sleep(30)  # Ручное ожидание ,было 20
                # Шаг 3: Ожидание подгрузки страницы
                self.wait_func(idx=idx, logger=logger)

                # Шаг 3.1 Пробуем пропустить оценку дешборда
                self.click_rate_later(logger=logger)

                self.drop_nav_ii(browser=self.browser, logger=logger)
                self.use_without_mouse_v2(logger=logger)

                # Шаг 4: Модуль работы с PNG
                self.pdf_generator.make_png_from_page(browser=self.browser, page_index=idx,
                                                      temp_dir=self.temp_dir, logger=logger)

            # Шаг 5: Объеденяем все PNG в одну PDF
            output_pdf_name = self.pdf_generator.build_pdf_from_fullshots_v2(temp_dir=self.temp_dir, logger=logger)

            # Шаг 6: Возвращаем статус выполнения работы и путь к файлу
            return {"status": "success", "file_path": output_pdf_name}

        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии работы с вкладками]")
            logger.exception(e)
            return {"status": "error", "file_path": None}
        finally:
            try:
                self.browser.quit()
            except:
                pass
            self._exit_task_temp(cleanup=True)
