import os
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path as pathlib
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from PIL import Image
import img2pdf
from modules.pdf.pdf_common import Common
from modules.pdf.pdf_manager import Path, CriticalError


class PDFGenerator:
    def __init__(self):
        self.common = Common()
        self.path: Path = Path()
        self.full_path = []

    @staticmethod
    def force_metrics_like_baseline(browser, width=1920, height=1200, dpr=1.0, zoom=1.0):
        # 1) окно
        browser.set_window_size(width, height)

        # 2) эмуляция девайса (CDP), чтобы CSS-метрики совпадали
        try:
            browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": width,
                "height": height,
                "deviceScaleFactor": dpr,  # обычно 1.0 на «эталоне»
                "mobile": False
            })
        except Exception:
            pass

        # 3) zoom страницы (чтобы визуально было 100% эталона)
        try:
            browser.execute_script(f"document.body.style.zoom='{zoom}'")
        except Exception:
            pass



    def capture_full_page_screenshot(self, browser, page_index, temp_dir, logger):
        """Функция сохраняет мини скриншоты"""
        try:
            status_now = f"[Делаем малые скриншоты страницы {page_index + 1}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))

            self.force_metrics_like_baseline(browser=browser)
            # Сбор диагностики по экрану (уберем потом)
            # diag = EnvDiagnostics(temp_dir=self.path.PDF_TEMP_FOLDER)
            # diag.collect_env_snapshot(browser=browser, logger=logger, label="baseline")
            # browser.set_window_size(1920, 1200)
            # time.sleep(1)
            # browser.maximize_window()
            scrollable_div_selector = "div.ScreenLayout.autoscroll-y"
            scroll_pause = 0.5
            overlap = 0  # Перекрытие между скроллами
            try:
                scrollable = browser.find_element(By.CSS_SELECTOR, scrollable_div_selector)
            except:
                status_now = f"[{page_index + 1}: Не найден скролл, запускаем 2 попытку через 20 секунд]"
                logger.info(status_now)
                print(self.common.text_for_logs(table_name="", text=status_now))
                time.sleep(20)
                scrollable = browser.find_element(By.CSS_SELECTOR, scrollable_div_selector)
                """
                for idx in range(4):
                    #time.sleep(100)
                    #scrollable_div_selector = 'div.Dashboard.grow-1.flex-col.autoscroll-y'
                    status_now = f"[{page_index + 1}: Не найден скролл, запускаем попытку - {idx+2} через 20 секунд]"
                    logger.info(status_now)
                    print(self.common.text_for_logs(table_name="", text=status_now))
                    time.sleep(20)
                    try:
                        scrollable = browser.find_element(By.CSS_SELECTOR, scrollable_div_selector)
                    except Exception as e:
                        if idx == 3:
                            print(e)
                            logger.info(f"[Ошибка при создании малых скриншотов]")
                            logger.exception(e)
                            raise CriticalError
                        pass
                """

            total_height = browser.execute_script("return arguments[0].scrollHeight", scrollable)
            viewport_height = browser.execute_script("return arguments[0].clientHeight", scrollable)
            # logger.info(f"Общая высота: {total_height}, Высота видимой области: {viewport_height}")
            # print(f"[DEBUG] total_height={total_height}, viewport_height={viewport_height}")

            # Условие если не требуется сшивать скриншоты
            if total_height <= viewport_height + 5:
                browser.execute_script("arguments[0].scrollTop = 0", scrollable)
                time.sleep(scroll_pause)
                one_shot_path = os.path.join(temp_dir, f"full_shot_{page_index + 1}.png")
                browser.save_screenshot(one_shot_path)
                status_now = f"[Единичный скриншот сохранен: {one_shot_path}]"
                logger.info(status_now)
                print(self.common.text_for_logs(table_name="", text=status_now))
                return self.stitch_images([one_shot_path], logger, temp_dir,
                                          f"full_shot_{page_index + 1}.png",
                                          0, viewport_height, total_height, viewport_height, 1, page_index)
                # return one_shot_path

            step = viewport_height - overlap
            num_scrolls = total_height // step
            last_crop = total_height - (num_scrolls * step)
            # print(f"[DEBUG] step={step}, num_scrolls={num_scrolls}, last_crop={last_crop}")

            screenshots = []
            for i in range(num_scrolls):
                scroll_position = i * step
                browser.execute_script("arguments[0].scrollTop = arguments[1]", scrollable, scroll_position)
                time.sleep(scroll_pause)
                screenshot_path = os.path.join(temp_dir, f"shot_{i}.png")
                browser.save_screenshot(screenshot_path)
                screenshots.append(screenshot_path)

                status_now = f"[Скриншот сохранен: {screenshot_path}]"
                logger.info(status_now)
                print(self.common.text_for_logs(table_name="", text=status_now))
                # print(f"[DEBUG] scroll_position={scroll_position}, saved={screenshot_path}")

            # Последний скриншот и обрезка сверху на `last_crop`
            browser.execute_script("arguments[0].scrollTop = arguments[1]", scrollable, total_height)
            time.sleep(scroll_pause)
            last_screenshot_path = os.path.join(temp_dir, f"shot_{num_scrolls}.png")
            browser.save_screenshot(last_screenshot_path)
            screenshots.append(last_screenshot_path)

            status_now = f"[Финальный скриншот сохранен: {last_screenshot_path}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
            # print(f"[DEBUG] final_scroll_position={total_height}, saved={last_screenshot_path}")

            return self.stitch_images(screenshots, logger, temp_dir, f"full_shot_{page_index + 1}.png",
                                      last_crop, viewport_height, total_height, step, num_scrolls, page_index)

        except Exception as e:
            print(e)
            logger.info(f"[Ошибка при создании малых скриншотов]")
            logger.exception(e)
            raise CriticalError

    def cleanup_temp_screenshots(self, screenshot_paths, prefix, logger):
        """Удаляем скриншоты"""
        try:
            deleted = 0
            for path in screenshot_paths:
                if os.path.basename(path).startswith(prefix) and os.path.exists(path):
                    os.remove(path)
                    deleted += 1
                    status_now = f"[Cкриншот удален: {path}]"
                    logger.info(status_now)
                    print(self.common.text_for_logs(table_name="", text=status_now))
        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии удаления png]")
            logger.exception(e)
            raise CriticalError

    def stitch_images(self, screenshot_paths, logger, save_dir, output_filename, last_crop,
                      viewport_height, total_height, step, num_scrolls, page_index):
        """Функция обрезает скриншоты и делает единую картинку"""
        try:
            status_now = f"[Делаем цельный скриншоты страницы {page_index + 1}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
            images = [Image.open(p) for p in screenshot_paths]
            header_height = 170  # Обрезаем шапку
            right_trim = 0  # Срезаем справа (85 было)
            cropped_images = []
            first_crop = images[0].crop((0, 0, images[0].width - right_trim, images[0].height))
            cropped_images.append(first_crop)
            for i, img in enumerate(images[1:-1], start=1):
                cropped = img.crop((0, header_height, img.width - right_trim, img.height))
                cropped_images.append(cropped)

            # Последний — отдельно, с обрезкой сверху на last_crop
            if len(images) > 1:
                last_img = images[-1]
                adjusted_crop = viewport_height - (total_height - step * num_scrolls)
                cropped_last = last_img.crop((0, header_height + adjusted_crop,
                                              last_img.width - right_trim,
                                              last_img.height))
                cropped_images.append(cropped_last)
                # print(f"[DEBUG] Cropping last image: header={header_height}, last_crop={last_crop}")

            total_height = sum(img.height for img in cropped_images)
            max_width = max(img.width for img in cropped_images)

            final_image = Image.new('RGB', (max_width, total_height))
            y_offset = 0
            for i, img in enumerate(cropped_images):
                final_image.paste(img, (0, y_offset))
                y_offset += img.height
                # print(f"[DEBUG] Image {i} pasted at y={y_offset}")

            final_path = os.path.join(save_dir, output_filename)
            final_image.save(final_path)

            status_now = f"[Сшитое изображение сохранено: {final_path}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))

            # Модуль удаления мелких скриншотов
            self.cleanup_temp_screenshots(screenshot_paths=screenshot_paths, prefix=f"shot_", logger=logger)
            self.full_path.append(final_path)
            return final_path
        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии обрезки изображений]")
            logger.exception(e)
            raise CriticalError

    def build_pdf_from_fullshots_v2(self, temp_dir, logger):
        """
        Собирает все PNG вида full_shot_{index}.png в один PDF по возрастанию index.
        Возвращает путь к созданному PDF.
        """
        try:
            tmp_folder = temp_dir
            output_pdf_path = self.path.PDF_FINAL_FOLDER
            pattern = re.compile(r"full_shot_(\d+)\.png$", re.IGNORECASE)
            pairs = []
            for name in os.listdir(tmp_folder):
                m = pattern.match(name)
                if m:
                    pairs.append((int(m.group(1)), os.path.join(tmp_folder, name)))
            pairs.sort(key=lambda x: x[0])

            if not pairs:
                return None
            paths = [p for _, p in pairs]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_pdf_name = os.path.join(output_pdf_path, f"{ts}.pdf")
            with open(output_pdf_name, "wb") as f:
                f.write(img2pdf.convert(paths))

            status_now = f"[PDF готов: {ts}.pdf]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))

            # Модуль удаления крупных скриншотов
            self.cleanup_temp_screenshots(screenshot_paths=self.full_path, prefix=f"full_shot_", logger=logger)

            # Возвращаем полный путь к файлу pdf
            return output_pdf_name
        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии сборки всех png в pdf]")
            logger.exception(e)
            raise CriticalError

    def make_png_from_page(self, browser: WebDriver, page_index: int, temp_dir, logger):
        """
        Делает скриншот всей страницы и сохраняет как PNG.
        """
        try:

            status_now = f"[Снимаем скриншот со страницы {page_index + 1}]"
            logger.info(status_now)
            print(self.common.text_for_logs(table_name="", text=status_now))
            # Шаг 1: Получаем полный скриншот вкладки
            self.capture_full_page_screenshot(browser=browser, page_index=page_index, temp_dir=temp_dir, logger=logger)

        except Exception as e:
            print(e)
            logger.info(f"[Ошибка на стадии сохранения png]")
            logger.exception(e)
            raise CriticalError
