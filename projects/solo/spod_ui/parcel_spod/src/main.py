import datetime
import json
import os
import subprocess
from queue import Queue
from typing import Optional, Any
import logging
import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, \
    ElementClickInterceptedException
from selenium.webdriver import FirefoxProfile, DesiredCapabilities
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.webdriver import WebDriver
from sqlalchemy import text
from sqlalchemy.engine import Engine
import time
import threading
import locale
import sys
from connectBD import use_new_engine
import schedule

# from parcel_spod.src.settings import Settings, SeleniumSettings, UsersInfo
from sqlalchemy.engine.reflection import Inspector
from concurrent.futures import ThreadPoolExecutor
from settings import Settings, SeleniumSettings, UsersInfo, SchedulerSettings


class CriticalError(Exception):
    pass


class Logging:
    def __init__(self):
        self.logger = None
        self.lock = threading.Lock()
        self.setting: Settings = Settings()

    def basic_configuration(self, table_name: str):
        logger = logging.getLogger(table_name)
        logger.setLevel(logging.INFO)

        with self.lock:  # <-- начало блокировки
            # Проверьте, есть ли уже handlers у этого логгера
            if not any(isinstance(handler, logging.FileHandler) for handler in logger.handlers):
                file_handler = logging.FileHandler(f"{self.setting.logs_path}{table_name}.log", mode='a')
                file_handler.setFormatter(logging.Formatter(self.setting.format))
                logger.addHandler(file_handler)
        # <-- конец блокировки

        if locale.getpreferredencoding().upper() != 'UTF-8':
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

        return logger


class All:
    def __init__(self):
        pass

    @staticmethod
    def execute_in_gp(engine: Engine, query: str, table_name: str, logger):
        try:
            with engine.connect() as conn:
                conn.execute(text(query).execution_options(autocommit=True))
        except Exception as e:
            logger.info(f"[Ошибка при проверке шага запуска]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def return_time_now():
        return str(datetime.datetime.today()).rpartition('.')[0]

    @staticmethod
    def read_sql(query: Optional[str], engine: Engine, chunksize: Any = None) -> pd.DataFrame:
        return pd.read_sql(sql=query, con=engine, chunksize=chunksize)

    @staticmethod
    def read_excel(path: Optional[str], sheet_name: str = 'tables') -> pd.DataFrame:
        return pd.read_excel(path, sheetname=sheet_name)


class Check:
    def __init__(self):
        self.settings: Settings = Settings()
        self.user_info: UsersInfo = UsersInfo()
        self.all: All = All()
        self.table_logs = self.settings.logs_spod_process
        self.user_name = self.user_info.username

    def delete_old_logs(self, table_name: str, table_logs: str, engine: Engine, logger):
        query = f"""delete from {table_logs} where source_table_name = '{table_name}'"""
        self.all.execute_in_gp(engine=engine, query=query, table_name=table_name, logger=logger)

    def insert_into_table_log(self, user_name: str, table_name: str,
                              date_start, date_end, step: int, serving_count: int, status: str,
                              table_logs: str, engine: Engine, logger):
        # Формируем запрос для первичных данных
        args_1 = f"'{user_name}', '{table_name}', '{date_start}'::timestamp,"
        args_2 = f" '{date_end}'::timestamp, {step}, '{serving_count}', '{status}'"
        args = args_1 + args_2
        query = f"""insert into {table_logs} values ({args})"""
        # Записываем первичные данные
        self.all.execute_in_gp(engine=engine, query=query, table_name=table_name, logger=logger)

    def safe_process_logs_first_time(self, table_name: str, date_start,
                                     date_end, step: int, status: str, engine: Engine, logger, serving_count: int = 0):
        # Этап 1: Очищаем данные по таблице
        self.delete_old_logs(table_name=table_name, table_logs=self.table_logs, engine=engine, logger=logger)

        # Этап 2: Записываем обновленную информацию
        self.insert_into_table_log(user_name=self.user_name, table_name=table_name, date_start=date_start,
                                   date_end=date_end, step=step, serving_count=serving_count,
                                   status=status, table_logs=self.table_logs,
                                   engine=engine, logger=logger)
        # Этап 3: Запись в лог файл
        logger.info(f"[{status}]")


class Main:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.settings: Settings = Settings()
        self.logger_setting: Logging = Logging()
        self.selenium_settings: SeleniumSettings = SeleniumSettings()
        self.user_info: UsersInfo = UsersInfo()
        self.check: Check = Check()
        self.all: All = All()
        self.desired_capabilities: Any = DesiredCapabilities().FIREFOX
        self.profile_browser: FirefoxProfile = webdriver.FirefoxProfile()
        self.options: Options = webdriver.FirefoxOptions()
        self.otp = None

    # --------------------
    # --------------------
    """БЛОК Работа с Greenplum"""

    def text_for_logs(self, table_name: str, text: str):
        return f"[{table_name}][{text}][{self.all.return_time_now()}]"

    def return_function(self, table_name: str, logger) -> str:
        query = f"SELECT {self.settings.func_spod}('{table_name.lower()}')"
        print(query)
        logger.info(f"[{query}]")
        return query

    def return_function_for_big(self, table_name: str, size_for_part, logger) -> str:
        str_size = f"{size_for_part}"
        if ".0" not in str_size:
            str_size = f"{str_size}.0"
        query = f"SELECT {self.settings.func_spod_big}('{table_name.lower()}'::text, '{str_size}'::text)"
        print(query)
        logger.info(f"[{query}]")
        return query

    def return_logs_info(self, table_name: str):
        query = f"SELECT * " \
                f"from {self.settings.logs_spod_func} ts where source_table_name ='{table_name}'" \
                f"and start_time_login = (" \
                f"SELECT max(start_time_login) from {self.settings.logs_spod_func} ts2 " \
                f"where ts2.source_table_name =('{table_name}'))"
        return query

    def count_in_table_true(self, table_name: str, engine: Engine, size_for_part, logger):
        try:
            logger.info(f"[Проверяем условие более 6 млн. строк в загрузочной таблице]")
            good_limit = False
            query = f"select count(1) as counts from s_grnplm_ld_blago_ubhq_2prod.spod_{table_name}"
            dataframe = self.all.read_sql(query=query, engine=engine)
            if dataframe['counts'][0] > size_for_part:
                good_limit = True
            logger.info(f"[Проверка на более установленного ограничения в загрузочной таблице строк прошла успешно]")
            print(good_limit)
            return good_limit
        except Exception as e:
            logger.info(f"[Ошибка на проверке более установленного ограничения в оригинальной таблице]")
            logger.exception(e)
            raise CriticalError from e

    def find_and_check_spod_table(self, table_name: str, engine: Engine, logger):
        try:
            logger.info(f"[Проверяем для исходной маленькой таблицы наличие порций в таблице СПОД]")
            good_limit = False
            spod_schema: str = "s_grnplm_ld_blago_ubhq_2prod"
            spod_table_name: str = f"spod_{table_name}"
            inspector = Inspector.from_engine(engine)
            tables_in_schema = inspector.get_table_names(schema=spod_schema)
            if spod_table_name in tables_in_schema:
                if self.check_portion_spod_in_table(table_name=table_name, engine_work=engine, logger=logger):
                    good_limit = True
            logger.info(f"[Проверка для исходной маленькой таблицы наличие порций в таблице СПОД прошла успешно]")
            return good_limit
        except Exception as e:
            logger.info(f"[Ошибка на проверке загрузочной таблицы для выбора функции обработки]")
            logger.exception(e)
            raise CriticalError from e

    def count_in_original_table_true(self, table_name: str, engine: Engine, size_for_part, logger):
        try:
            logger.info(f"[Проверяем условие более установленного ограничения в оригинальной таблице]")
            good_limit = False
            query = f"select count(1) as counts from s_grnplm_ld_blago_ubhq_work.{table_name}"
            dataframe = self.all.read_sql(query=query, engine=engine)
            if dataframe['counts'][0] > size_for_part:
                good_limit = True
            elif self.find_and_check_spod_table(table_name=table_name, engine=engine, logger=logger):
                good_limit = True
            logger.info(f"[Проверка на более установленного ограничения в оригинальной таблице строк прошла успешно]")
            return good_limit
        except Exception as e:
            logger.info(f"[Ошибка на проверке более установленного ограничения в оригинальной таблице]")
            logger.exception(e)
            raise CriticalError from e

    def start_function_for_spod(self, table_name: str, engine_work: Engine, size_for_part, logger):
        # Этап 1: Проверяем общий объем исходной таблицы и выбираем дальнейшую ветку действий
        if self.count_in_original_table_true(table_name=table_name, engine=engine_work,
                                             size_for_part=size_for_part, logger=logger):
            self.all.execute_in_gp(engine=engine_work,
                                   query=self.return_function_for_big(table_name=table_name,
                                                                      size_for_part=size_for_part,
                                                                      logger=logger),
                                   table_name=table_name, logger=logger)
        else:
            self.all.execute_in_gp(engine=engine_work,
                                   query=self.return_function(table_name=table_name, logger=logger),
                                   table_name=table_name, logger=logger)

    def check_portion_spod_in_table(self, table_name: str, engine_work: Engine, logger):
        try:
            logger.info(f"[Проверяем наличие столбца для порций в загрузочной таблице]")
            have_column = True
            '''
            query_portion: str = f"SELECT count(1)::int as counts, 'text' as textss from information_schema_columns " \
                                    f"where table_schema = 's_grnplm_ld_blago_ubhq_2prod' " \
                                    f"and table_name like ('%{table_name.lower()}%') and column_name = 'portion_spod'"
            '''
            query_portion = f"select portion_spod " \
                            f"from s_grnplm_ld_blago_ubhq_2prod.spod_{table_name.lower()} limit 1"
            self.all.read_sql(query=query_portion, engine=engine_work)
            logger.info(f"[Проверка наличие столбца для порций в загрузочной таблице прошла успешно")
            return have_column
        except Exception as e:
            best_text = "UndefinedColumn"
            if best_text in str(e):
                have_column = False
                logger.info(f"[Проверка наличие столбца для порций в загрузочной таблице прошла успешно, но поле не "
                            f"найдено]")
                return have_column
            else:
                logger.info(f"[Ошибка на проверке наличие столбца для порций в загрузочной таблице]")
                logger.exception(e)
                raise CriticalError from e

    def check_many_size_and_portion(self, table_name: str, size_for_part, verify_in: str, engine_work: Engine, logger):
        try:
            logger.info(f"[Проверяем таблицу на большое количество загрузок]")
            have_column = True
            if size_for_part == 6000000:
                # Определяем количество порций
                list_with_portion = self.take_count_portion_in_table(table_name=table_name,
                                                                     engine_work=engine_work, logger=logger)
                max_portion: int = max(list_with_portion)
                if max_portion >= 5 and verify_in != "YES":
                    have_column = False
            return have_column
        except Exception as e:
            logger.info(f"[Ошибка на стадии определения больших перегрузок]")
            logger.exception(e)
            raise CriticalError from e

    def first_step_in_greenplum(self, table_name: str, date_start, engine_work: Engine, size_for_part, logger):

        # Этап 1: Запускаем функцию на greenplum

        status_now = 'Запускаем процесс для загрузки в СПОД'
        print(self.text_for_logs(table_name=table_name, text=status_now))
        self.check.safe_process_logs_first_time(table_name=table_name,
                                                date_start=date_start, date_end=self.all.return_time_now(),
                                                step=0, status=status_now, engine=engine_work, logger=logger)

        status_now = 'Запускаем функцию для подготовки данных'
        print(self.text_for_logs(table_name=table_name, text=status_now))
        self.check.safe_process_logs_first_time(table_name=table_name,
                                                date_start=date_start, date_end=self.all.return_time_now(),
                                                step=0, status=status_now, engine=engine_work, logger=logger)

        self.start_function_for_spod(table_name=table_name, engine_work=engine_work,
                                     size_for_part=size_for_part, logger=logger)

        status_now = 'Функция отработала'
        print(self.text_for_logs(table_name=table_name, text=status_now))
        self.check.safe_process_logs_first_time(table_name=table_name,
                                                date_start=date_start, date_end=self.all.return_time_now(),
                                                step=1, status=status_now, engine=engine_work, logger=logger)

    def second_step_in_greenplum(self, table_name: str, date_start, engine_work: Engine, size_for_part, verify, logger):
        try:
            # Этап 2: Получаем информацию по успехам отработки функции
            status_now = 'Получаем информацию по результату работы функции'
            print(self.text_for_logs(table_name=table_name, text=status_now))
            self.check.safe_process_logs_first_time(table_name=table_name,
                                                    date_start=date_start, date_end=self.all.return_time_now(),
                                                    step=1, status=status_now, engine=engine_work, logger=logger)

            logs_frame = self.all.read_sql(query=self.return_logs_info(table_name=table_name), engine=engine_work)

            # Этап 2.1: Проверяем статус логов

            if logs_frame['status_log'][0] != 'Success':
                status_now = f"Ошибка на стадии выполнения функции для генерации таблицы. Процесс остановлен. " \
                             f"См. таблицу {self.settings.logs_spod_func}"
                print(self.text_for_logs(table_name=table_name, text=status_now))
                self.check.safe_process_logs_first_time(table_name=table_name,
                                                        date_start=date_start, date_end=self.all.return_time_now(),
                                                        step=0, status=status_now, engine=engine_work, logger=logger)

                continue_spod = 0
            elif int(logs_frame['count_edit'][0]) == 0:
                # Этап 2.2: Проверяем количество изменений
                status_now = 'Записано 0 изменений - Процесс остановлен'
                print(self.text_for_logs(table_name=table_name, text=status_now))
                self.check.safe_process_logs_first_time(table_name=table_name,
                                                        date_start=date_start, date_end=self.all.return_time_now(),
                                                        step=0, status=status_now, engine=engine_work, logger=logger)

                continue_spod = 0

            elif self.count_in_table_true(table_name=table_name, engine=engine_work,
                                          size_for_part=size_for_part, logger=logger):
                # Этап 2.3: Проверяем на наличие превышения ограничения в 6 млн. строк и отсутвие поля portion_spod
                if self.check_portion_spod_in_table(table_name=table_name, engine_work=engine_work, logger=logger):
                    if not self.check_many_size_and_portion(table_name=table_name,
                                                            size_for_part=size_for_part, verify_in=verify,
                                                            engine_work=engine_work, logger=logger):
                        status_now = 'Объект для загрузки слишком большой. Требуется подтверждение - Процесс остановлен'
                        print(self.text_for_logs(table_name=table_name, text=status_now))
                        self.check.safe_process_logs_first_time(table_name=table_name,
                                                                date_start=date_start,
                                                                date_end=self.all.return_time_now(),
                                                                step=1, status=status_now, engine=engine_work,
                                                                logger=logger)
                        continue_spod = 0

                    else:
                        status_now = 'Таблица для загрузки имеет поле portion_spod, огр. нет - Продолжаем загрузку'
                        print(self.text_for_logs(table_name=table_name, text=status_now))
                        self.check.safe_process_logs_first_time(table_name=table_name,
                                                                date_start=date_start,
                                                                date_end=self.all.return_time_now(),
                                                                step=1, serving_count=0,
                                                                status=status_now, engine=engine_work,
                                                                logger=logger)

                        continue_spod = 2
                else:
                    status_now = 'В таблице загрузки более 6 млн. записей и таблица не имеет поля portion_spod - ' \
                                 'Процесс остановлен'
                    print(self.text_for_logs(table_name=table_name, text=status_now))
                    self.check.safe_process_logs_first_time(table_name=table_name,
                                                            date_start=date_start, date_end=self.all.return_time_now(),
                                                            step=1, status=status_now, engine=engine_work,
                                                            logger=logger)

                    continue_spod = 0
            else:
                continue_spod = 1
            print(continue_spod)
            return continue_spod
        except Exception as e:
            logger.info(f"[Ошибка на стадии проверок таблицы]")
            logger.exception(e)
            raise CriticalError from e

            # Часть для получения количества порций в объекте

    def take_count_portion_in_table(self, table_name: str, engine_work: Engine, logger):
        try:
            query = f"""SELECT distinct portion_spod
                            from s_grnplm_ld_blago_ubhq_2prod.spod_{table_name} order by portion_spod"""
            dataframe = self.all.read_sql(query=query, engine=engine_work)
            return dataframe['portion_spod'].tolist()
        except Exception as e:
            logger.info(f"[Ошибка на стадии определения количества порций]")
            logger.exception(e)
            raise CriticalError from e

    # --------------------
    # --------------------
    """БЛОК Работа с Selenium"""

    @staticmethod
    def set_preference_to_firefox(profile: FirefoxProfile) -> FirefoxProfile:
        [profile.set_preference(f[0], f[1]) for f in SeleniumSettings().preferences]
        return profile

    @staticmethod
    def set_options_to_firefox(options: Options) -> Options:
        options.binary_location = SeleniumSettings().browser_path
        [options.add_argument(f) for f in SeleniumSettings().option_arguments]
        return options

    @staticmethod
    def do_anything_by_xpath(xpath: str, browser: WebDriver) -> Any:
        while range(5):
            try:
                time.sleep(3)
                return browser.find_element_by_xpath(xpath)
            except (NoSuchElementException, ElementClickInterceptedException) as e:
                print(e)
                time.sleep(3)
                continue

    def launching_the_browser(self, logger) -> WebDriver:
        try:
            profile_browser: FirefoxProfile = self.set_preference_to_firefox(profile=self.profile_browser)
            options: Options = self.set_options_to_firefox(options=self.options)
            browser: WebDriver = webdriver.Firefox(desired_capabilities=self.desired_capabilities,
                                                   executable_path=self.selenium_settings.chromedriver,
                                                   options=options,
                                                   service_log_path=self.selenium_settings.webdriver_log_file,
                                                   firefox_profile=profile_browser
                                                   )
        except Exception as e:
            logger.info(f"[Ошибка на старте браузера]")
            logger.exception(e)
            raise CriticalError from e

        return browser

    @staticmethod
    def check_created_structure(browser: WebDriver):
        check = ""
        try:
            check = browser.find_element_by_xpath('//*[text()=\'Нет данных\']').text
        except Exception as e:
            pass
        return check

    def run_to_page_with_load(self, browser: WebDriver, table_name: str, logger):
        try:
            time.sleep(2)
            self.do_anything_by_xpath(xpath='//*[text()=\'Ответственный за загрузку и структуры данных\']',
                                      browser=browser).click()
            time.sleep(2)
            self.do_anything_by_xpath(xpath='//*/input', browser=browser).send_keys(table_name)
            time.sleep(2)
            check = self.check_created_structure(browser=browser)
            time.sleep(2)
            if check == 'Нет данных':
                print(self.text_for_logs(table_name=table_name, text='Структура не найдена'))
            else:
                # self.do_anything_by_xpath(xpath='//*/mark', browser=browser).click()
                self.do_anything_by_xpath(xpath='//*/h5/div/span/span', browser=browser).click()
                time.sleep(2)
            return check
        except Exception as e:
            logger.info(f"[Ошибка на пути к загрузке данных]")
            logger.exception(e)
            raise CriticalError from e

    def run_load(self, browser: WebDriver, logger):
        try:
            self.do_anything_by_xpath(xpath='//*[text()=\'Загрузить данные\']', browser=browser).click()
            time.sleep(2)
            '''
            self.do_anything_by_xpath(
                xpath='/html/body/div[2]/div/div[2]/div/div[2]/div[2]/div/div[2]/label/span[1]/input',
                browser=browser).click()
            '''

            self.do_anything_by_xpath(xpath=f"//*[contains(text(), 'Я ознакомлен(а)')]", browser=browser).click()

            time.sleep(2)
            self.do_anything_by_xpath(xpath='//*[text()=\'Продолжить\']', browser=browser).click()
            time.sleep(1)
            self.do_anything_by_xpath(xpath='//*[@id="waitReview"]', browser=browser).click()  # Выкл проверку
            time.sleep(1)
            self.do_anything_by_xpath(xpath='//*[text()=\'Загрузить\']', browser=browser).click()
        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки данных через СПОД]")
            logger.exception(e)
            raise CriticalError from e

    def find_and_click_element_with_cycle(self, browser: WebDriver, element_col: str,
                                          element_find: str, logger, full=0):
        try:
            time.sleep(1)
            dropdown_xpath = element_col
            dropdown_button = self.do_anything_by_xpath(xpath=dropdown_xpath, browser=browser)
            dropdown_button.click()
            time.sleep(1)
            if full == 1:
                portion_spod_xpath = f'//*[text()=\'{element_find}\']'
                portion_spod_xpath_small = f'//*[text()=\'{element_find.lower()}\']'
            else:
                portion_spod_xpath = f"//*[contains(text(), '{element_find}')]"
                portion_spod_xpath_small = f"//*[contains(text(), '{element_find.lower()}')]"
            while True:
                try:
                    dropdown_button.send_keys(Keys.DOWN)  # Отправляем клавишу "вниз" для прокрутки списка
                    time.sleep(0.2)
                    try:
                        portion_spod_found = browser.find_element_by_xpath(portion_spod_xpath)
                    except NoSuchElementException as e:
                        portion_spod_found = browser.find_element_by_xpath(portion_spod_xpath_small)
                    time.sleep(0.2)
                    portion_spod_found.click()  # Нажимаем на элемент, когда он найден
                    break
                except NoSuchElementException as e:
                    continue  # Если элемент не найден, продолжаем прокрутку
        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки порции]")
            logger.exception(e)
            raise CriticalError from e

    def find_and_click_element_with_cycle_old(self, browser: WebDriver, element_col: str,
                                              element_find: str, logger, full=0):
        try:
            time.sleep(1)
            dropdown_xpath = element_col
            dropdown_button = self.do_anything_by_xpath(xpath=dropdown_xpath, browser=browser)
            dropdown_button.click()
            time.sleep(1)
            if full == 1:
                portion_spod_xpath = f'//*[text()=\'{element_find}\']'
            else:
                portion_spod_xpath = f"//*[contains(text(), '{element_find}')]"
            while True:
                try:
                    # dropdown_button.send_keys(Keys.DOWN)  # Отправляем клавишу "вниз" для прокрутки списка
                    time.sleep(0.2)
                    dropdown_button.send_keys(Keys.ENTER)
                    '''
                    portion_spod_found = browser.find_element_by_xpath(portion_spod_xpath)
                    time.sleep(1)
                    portion_spod_found.click()  # Нажимаем на элемент, когда он найден
                    '''
                    # break
                    '''
                    except ElementNotInteractableException as e:
                        print("Попытка 2")
                        time.sleep(1)
                        portion_spod_found.click()
                        break
                    '''
                    break
                except NoSuchElementException as e:
                    continue  # Если элемент не найден, продолжаем прокрутку
        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки порции]")
            logger.exception(e)
            raise CriticalError from e

    def run_load_big(self, browser: WebDriver, table_name: str, date_start,
                     engine_work: Engine, logger, serving_count: int, partition_number: int):
        try:
            status_now = f'Старт загрузки {partition_number} порции'
            print(self.text_for_logs(table_name=table_name, text=status_now))
            self.check.safe_process_logs_first_time(table_name=table_name,
                                                    date_start=date_start, date_end=self.all.return_time_now(),
                                                    step=1, serving_count=serving_count,
                                                    status=status_now, engine=engine_work, logger=logger)

            self.do_anything_by_xpath(xpath='//*[text()=\'Загрузить данные\']', browser=browser).click()
            time.sleep(2)
            '''
            self.do_anything_by_xpath(
                xpath='/html/body/div[2]/div/div[2]/div/div[2]/div[2]/div/div[2]/label/span[1]/input',
                browser=browser).click()
            '''
            self.do_anything_by_xpath(xpath=f"//*[contains(text(), 'Я ознакомлен(а)')]", browser=browser).click()
            time.sleep(1)
            self.do_anything_by_xpath(xpath='//*[text()=\'Продолжить\']', browser=browser).click()
            time.sleep(1)
            self.do_anything_by_xpath(xpath='//*[@id="waitReview"]', browser=browser).click()  # Выкл проверку
            time.sleep(1)
            self.do_anything_by_xpath(xpath='//*[@id="useFilter"]', browser=browser).click()  # Вкл разбивку по порциям
            time.sleep(1)
            self.do_anything_by_xpath(xpath='//*[text()=\'Добавить\']', browser=browser).click()
            time.sleep(1)
            # Ищем поле партиции и выставляем фильтр
            self.find_and_click_element_with_cycle(browser=browser,
                                                   element_col='//*[@id="filters_0_columnName"]',
                                                   element_find='PORTION_SPOD', logger=logger)
            # Ищем поле "=" и выставляем фильтр
            self.find_and_click_element_with_cycle_old(browser=browser,
                                                       element_col='//*[@id="filters_0_operator"]',
                                                       element_find='=', logger=logger, full=1)

            # Вписываем номер партиции
            self.do_anything_by_xpath(xpath='//*[@id="filters_0_columnValue"]',
                                      browser=browser).send_keys(str(partition_number))

            time.sleep(1)
            # self.do_anything_by_xpath(xpath='//*/body', browser=browser).send_keys(Keys.ESCAPE)  # УБРАТЬ после
            # тестов и раскомитить следующую строчку
            self.do_anything_by_xpath(xpath='//*[text()=\'Загрузить\']', browser=browser).click()
            status_now = f'Порция {partition_number} установлена на загрузку'
            print(self.text_for_logs(table_name=table_name, text=status_now))
            self.check.safe_process_logs_first_time(table_name=table_name,
                                                    date_start=date_start, date_end=self.all.return_time_now(),
                                                    step=1, serving_count=serving_count,
                                                    status=status_now, engine=engine_work, logger=logger)

        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки данных через СПОД (Большие объекты)]")
            logger.exception(e)
            raise CriticalError from e

    # Доп. функция которая принимает кол-во порций и делает фильтр
    def in_cycle_add_portion_filter(self, browser: WebDriver, table_name: str, engine_work: Engine, date_start, logger):
        # Этап 1: Создаем список порций
        status_now = 'Определяем количество порций объекта'
        print(self.text_for_logs(table_name=table_name, text=status_now))
        self.check.safe_process_logs_first_time(table_name=table_name,
                                                date_start=date_start, date_end=self.all.return_time_now(),
                                                step=1, status=status_now, engine=engine_work, logger=logger)

        list_with_portion = self.take_count_portion_in_table(table_name=table_name,
                                                             engine_work=engine_work, logger=logger)
        # Этап 2: В цикле повторяем парсинг
        status_now = 'Запускаем цикл запуска загрузки по порциям (ВАЖНО !! Не рекомендуется прерывать процесс)'
        print(self.text_for_logs(table_name=table_name, text=status_now))
        self.check.safe_process_logs_first_time(table_name=table_name,
                                                date_start=date_start, date_end=self.all.return_time_now(),
                                                step=1, serving_count=len(list_with_portion),
                                                status=status_now, engine=engine_work, logger=logger)

        [self.run_load_big(browser=browser, table_name=table_name,
                           date_start=date_start, engine_work=engine_work, logger=logger,
                           serving_count=len(list_with_portion),
                           partition_number=int(part)) for part in list_with_portion]
        return len(list_with_portion)

    def open_new_window(self, main_browser, lock, logger):
        try:

            # Открытие нового окна
            handles_before = set(main_browser.window_handles)
            main_browser.execute_script("window.open('');")

            # Подождем немного, чтобы новое окно открылось
            time.sleep(2)

            # Найдем новое окно
            handles_after = set(main_browser.window_handles)
            new_windows = handles_after - handles_before
            if new_windows:
                new_window_handle = new_windows.pop()
                main_browser.switch_to.window(new_window_handle)
            else:
                raise Exception("Не найдено новое окно")

            # Новое окно — это разница между текущими окнами и окнами до открытия нового
            # new_window_handle = list(set(main_browser.window_handles) - handles_before)[0]
            # main_browser.switch_to.window(new_window_handle)
            logger.info(f"[Отдельное окно браузера открыто]")
            return main_browser
        except Exception as e:
            logger.info(f"[Ошибка на стадии открытия отдельного окна")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def close_new_window(new_window_handle, main_browser, initial_window_handle, logger):
        try:
            # Убедимся, что окно закроется в случае ошибки
            if new_window_handle and new_window_handle in main_browser.window_handles:
                main_browser.close()
                main_browser.switch_to.window(initial_window_handle)
            logger.info(f"[Отдельное окно закрыто]")
        except Exception as e:
            logger.info(f"[Ошибка на стадии закрытия отдельного окна")
            logger.exception(e)
            raise CriticalError from e

    def selenium_parcel(self, table_name: str, date_start, engine_work, continue_spod: int, main_browser, lock, logger):
        serving_count = 0
        """
        new_window_handle = None
        try:
            print(main_browser)
            initial_window_handle = main_browser.current_window_handle
        except AttributeError as e:
            logger.info(f"[Ошибка на стадии поиска текущего окна")
            logger.exception(e)
            raise CriticalError from e
        """
        if main_browser is None:
            logger.error("main_browser передан как None")
        try:

            # Проверяем активность браузера и в случае отсутствия авторизации, замораживаем очередь

            self.otp.otp_sends_and_auth(browser=main_browser, logger=logger)

            # Этап 0: Передаем окно для работы из активного браузера
            status_now = 'Открываем окно активного браузера'
            print(self.text_for_logs(table_name=table_name, text=status_now))
            self.check.safe_process_logs_first_time(table_name=table_name,
                                                    date_start=date_start, date_end=self.all.return_time_now(),
                                                    step=1, status=status_now, engine=engine_work, logger=logger)
            browser = main_browser
            # browser = self.open_new_window(main_browser=main_browser, lock=lock, logger=logger)
            # new_window_handle = browser.current_window_handle

            time.sleep(2)
            browser.get(self.selenium_settings.url_spod)

            # Этап 1: Прожимаем кнопки до загрузки
            status_now = 'Переходим до нужной структуры данных'
            print(self.text_for_logs(table_name=table_name, text=status_now))
            self.check.safe_process_logs_first_time(table_name=table_name,
                                                    date_start=date_start, date_end=self.all.return_time_now(),
                                                    step=1, status=status_now, engine=engine_work, logger=logger)

            check_structure: str = self.run_to_page_with_load(browser=browser, table_name=table_name, logger=logger)
            if check_structure == 'Нет данных':
                status_now = 'Процесс загрузки остановлен, просьба создать структуру и запустить скрипт снова'
                print(self.text_for_logs(table_name=table_name, text=status_now))
                self.check.safe_process_logs_first_time(table_name=table_name,
                                                        date_start=date_start, date_end=self.all.return_time_now(),
                                                        step=1, status=status_now, engine=engine_work, logger=logger)


            # Этап 2: Загрузка данных (Далее развилка в зависимости от того большой объект или нет)
            else:
                status_now = 'Начинаем загрузку данных'
                print(self.text_for_logs(table_name=table_name, text=status_now))
                self.check.safe_process_logs_first_time(table_name=table_name,
                                                        date_start=date_start, date_end=self.all.return_time_now(),
                                                        step=1, status=status_now, engine=engine_work, logger=logger)

                if continue_spod == 1:
                    self.run_load(browser=browser, logger=logger)
                    serving_count = 1
                if continue_spod == 2:
                    serving_count = self.in_cycle_add_portion_filter(browser=browser, table_name=table_name,
                                                                     engine_work=engine_work, date_start=date_start,
                                                                     logger=logger)

            # browser.close()
            # status_now = 'Процесс загрузки СПОД завершен'
            status_now = 'Данные отправлены на загрузку'
            print(self.text_for_logs(table_name=table_name, text=status_now))
            self.check.safe_process_logs_first_time(table_name=table_name,
                                                    date_start=date_start, date_end=self.all.return_time_now(),
                                                    step=3, serving_count=serving_count,
                                                    status=status_now, engine=engine_work, logger=logger)
            time.sleep(1)
            browser.get(self.selenium_settings.url_spod)
        except Exception as e:
            logger.info(f"[Ошибка на стадии работы с Selenium]")
            logger.exception(e)
            raise CriticalError from e
        """
        finally:
            self.close_new_window(new_window_handle=new_window_handle, main_browser=main_browser,
                                  initial_window_handle=initial_window_handle, logger=logger)
        """

    def check_and_start_step(self, table_name: str, engine: Engine, logger):
        try:
            # Проверяем на каком шаге запускать
            query = f"""select final_step from {self.settings.logs_spod_process} 
                        where source_table_name ='{table_name}'"""
            dataframe = self.all.read_sql(query=query, engine=engine)
            try:
                final_steps = dataframe['final_step'][0]
            except IndexError as e:
                logger.info(f"[Записи на таблицу логирования прогресса не существует. Стартовый шаг = 0]")
                final_steps = 0
            logger.info(f"[Шаг для старта определен]")
            return final_steps
        except Exception as e:
            logger.info(f"[Ошибка при проверке шага запуска]")
            logger.exception(e)
            raise CriticalError from e

    def start(self, table_name: str, size_for_part: int, verify, engine_work, date_start, main_browser, lock, logger):

        # Этап 0: Передаем подключение и другие предварительные настройки
        step = self.check_and_start_step(table_name=table_name, engine=engine_work, logger=logger)
        # Этап 0.1: Проверка на полный цикл работы загрузки (Если прошлая версия не подтвердилась, то нужно закончить
        if step == 3:
            status_now = 'ОШИБКА !!! Объект находится в предфинальном статусе, требуется завершить загрузку'
            print(self.text_for_logs(table_name=table_name, text=status_now))
            logger.info(f"[ОШИБКА !!! Объект находится в предфинальном статусе, требуется завершить загрузку]")
        else:
            # Этап первый - Запуск функции на Greenplum
            if step in (0, 2):
                self.first_step_in_greenplum(table_name=table_name,
                                             date_start=date_start, engine_work=engine_work,
                                             size_for_part=size_for_part, logger=logger)

            # Этап второй: Проверка логов отработки функции
            continue_spod = self.second_step_in_greenplum(table_name=table_name,
                                                          date_start=date_start, engine_work=engine_work,
                                                          size_for_part=size_for_part, verify=verify, logger=logger)

            if continue_spod in (1, 2):
                # Этап третий - Работа с веб=версией СПОДа
                """
                self.selenium_parcel(table_name=table_name, date_start=date_start, engine_work=engine_work,
                                     continue_spod=continue_spod, main_browser=main_browser, lock=lock, logger=logger)
                """
                self.scheduler.queue.put((self.selenium_parcel,
                                          (table_name, date_start, engine_work, continue_spod, main_browser, lock,
                                           logger)))

        logger.info(f"[--------------------------------------------------------------------------------]")
        logger.info(f"[--------------------------------------------------------------------------------]")


class WorkList:
    def __init__(self, scheduler, table_name_schedule=None, size_name_schedule=None, verify=None, days=None, hour=None,
                 minute=None):
        self.scheduler = scheduler
        self.logger_setting: Logging = Logging()
        self.main: Main = scheduler.main
        self.all: All = All()
        self.settings: Settings = Settings()
        self.table_name_schedule = table_name_schedule
        self.size_name_schedule = size_name_schedule
        self.verify = verify
        self.days = days
        self.hour = hour
        self.minute = minute
        self.executor = ThreadPoolExecutor(max_workers=3)

    def start_kkd_check(self, table_name: str, logger):
        try:
            status_now = 'Объект отправлен на анализ ККД'
            print(self.main.text_for_logs(table_name=table_name, text=status_now))
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            subprocess.run(f"{self.settings.path_for_kkd} {table_name}", startupinfo=si)
            status_now = 'Проверка ККД закончена'
            print(self.main.text_for_logs(table_name=table_name, text=status_now))
        except Exception as e:
            status_now = 'Запуск проверки ККД не выполнен'
            print(self.main.text_for_logs(table_name=table_name, text=status_now))
            logger.info(f"[Запуск проверки ККД не выполнен]")
            logger.exception(e)
            pass

    def apply_func(self, table_name, size_name, verify, engine_work, date_start, main_browser, lock, logger):
        self.start_kkd_check(table_name=table_name, logger=logger)
        if pd.isnull(size_name):
            size_name = 6000000
        self.main.start(table_name=table_name, size_for_part=size_name, engine_work=engine_work,
                        date_start=date_start, verify=verify, main_browser=main_browser, lock=lock, logger=logger)

    def apply_with_pool(self, table_name, size_name, verify, main_browser, lock):
        logger = self.logger_setting.basic_configuration(table_name=f"{table_name}")
        try:
            date_start = self.all.return_time_now()
            logger.info(f"[--------------------------------------------------------------------------------]")
            logger.info(f"[--------------------------------------------------------------------------------]")
            engine_work: Engine = self.settings.engine_work
            self.executor.submit(self.apply_func, table_name, size_name, verify, engine_work,
                                 date_start, main_browser, lock, logger)
        except Exception as e:
            status_now = 'Проблема фонового запуска функций'
            print(self.main.text_for_logs(table_name=table_name, text=status_now))
            logger.info(f"[Проблема фонового запуска функций]")
            logger.exception(e)
            pass

    # Временно под старый запуск
    """
    def open_and_start_script(self, sheet_name: str):
        dataframe = self.all.read_excel(path=self.settings.path_objects, sheet_name=sheet_name)
        [self.apply_func(row['table_name'], row['size_for_part']) for index, row in dataframe.iterrows()]
    """


class OTP:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.user_info: UsersInfo = UsersInfo()
        self.selenium_settings: SeleniumSettings = SeleniumSettings()
        self.main = scheduler.main
        # self.main = None

    def do_anything_by_xpath_with_stop(self, xpath: str, browser: WebDriver) -> Any:
        timer = 0
        while range(5):
            try:
                return browser.find_element_by_xpath(xpath)
            except (NoSuchElementException, ElementClickInterceptedException) as e:
                if timer > 5:
                    raise CriticalError
                timer += 1
                time.sleep(1)
                browser.get(self.selenium_settings.url_spod)
                time.sleep(1)
                browser.refresh()
                time.sleep(3)
                continue

    def opt_counts(self, browser, logger):
        try:
            otp: str = input('Введите OTP пароль: ')
            logger.info(f"[{self.user_info.username}][Пароль OTP введен]")

            for key, otp_num in enumerate(otp):
                self.main.do_anything_by_xpath(xpath=f'//*[@data-index-number="{key + 5}"]',
                                               browser=browser).send_keys(otp_num)
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии ввода OTP]")
            logger.exception(e)
            raise CriticalError from e

    def app_and_pin(self, browser, logger):
        """Новый блок, отвечающий за выбор аппаратного токена и ввод пин"""
        try:
            self.main.do_anything_by_xpath(xpath='//*[@id="login-by-ngam-hwotp-authenticator"]',
                                           browser=browser).click()
            # Шаг 3: Вводим PIN
            pin: str = input('Введите PIN пароль: ')

            time.sleep(3)
            for key, pin_num in enumerate(pin):
                self.main.do_anything_by_xpath(xpath=f'//*[@data-index-number="{key + 1}"]',
                                               browser=browser).send_keys(pin_num)
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии ввода PIN]")
            logger.exception(e)
            raise CriticalError from e

    def authorization_in_sudir_first(self, browser: WebDriver, logger):
        try:
            time.sleep(4)
            self.main.do_anything_by_xpath(xpath='//*[@id="username"]', browser=browser).send_keys(self.user_info.username)
            self.main.do_anything_by_xpath(xpath='//*[@id="password"]', browser=browser).send_keys(self.user_info.user_code)
            self.main.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()
            time.sleep(3)
        except Exception as e:
            logger.info(f"[Ошибка на стадии авторизации]")
            logger.exception(e)
            raise CriticalError from e

    def authorization_in_sudir(self, browser: WebDriver, logger):
        try:
            time.sleep(2)
            # self.main.do_anything_by_xpath(xpath='//*[@id="password"]',
            # browser=browser).send_keys(self.user_info.user_code)
            # time.sleep(1)

            # Новое - вводим PIN
            self.app_and_pin(browser=browser, logger=logger)

            # Шаг 3: Вводим OTP
            self.opt_counts(browser=browser, logger=logger)

            self.main.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()

            browser.get(self.selenium_settings.url_spod)
            time.sleep(3)
        except Exception as e:
            logger.info(f"[Ошибка на стадии авторизации]")
            logger.exception(e)
            raise CriticalError from e

    def check_done_authorization(self, browser, logger):
        try:
            time.sleep(10)
            self.do_anything_by_xpath_with_stop(xpath='//*[text()=\'Тематические данные УБ GP\']', browser=browser)
            print("Пароль OTP принят. Авторизация пройдена.")
            logger.info(f"[{self.user_info.username}][Пароль OTP принят. Авторизация пройдена.]")
            return True
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Пароль OTP не принят]")
            logger.exception(e)
            logger.info(f"Текущая ссылка: {browser.current_url}")
            print("Неверный пароль, попробуйте снова")
            return False

    def otp_sends_and_auth(self, browser, logger):
        try:
            authorized = False
            while not authorized:

                # Шаг 1: Проверяем статус авторизации
                authorized = self.check_done_authorization(browser=browser, logger=logger)
                if not authorized:
                    print("------------------------------------------------------------------------")
                    print("------------------------------------------------------------------------")
                    print("------------------------------------------------------------------------")
                    # Шаг 2: Делаем перевичную авторизацию
                    self.authorization_in_sudir_first(browser=browser, logger=logger)
                    # Шаг #: Заполняем логин
                    #self.main.do_anything_by_xpath(xpath='//*[@id="username"]',
                    #                               browser=browser).send_keys(self.user_info.username)
                    # Шаг 3 #: Авторизация
                    self.authorization_in_sudir(browser=browser, logger=logger)

        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии авторизации через OTP]")
            logger.exception(e)
            raise CriticalError from e

    def run_cookie_with_selenium(self, browser, logger):
        try:
            time.sleep(3)
            browser.get(self.selenium_settings.url_spod)
            time.sleep(3)
            browser.refresh()
            """
            time.sleep(3)
            browser.refresh()
            self.main.do_anything_by_xpath(xpath='//*[text()=\'Ввод\']', browser=browser).click()
            time.sleep(3)
            browser.refresh()
            time.sleep(3)
            browser.get(self.selenium_settings.url_spod)
            time.sleep(3)
            browser.refresh()
            """
            #logger.info(f"Текущая ссылка: {browser.current_url}")
            logger.info(f"[{self.user_info.username}][Браузер обновлен]")
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии поддержания действующей сессии]")
            logger.exception(e)
            print(e)
            try:
                browser.quit()
            except:
                pass
            pass


class Scheduler:
    def __init__(self):
        self.scheduler_setting: SchedulerSettings = SchedulerSettings()
        self.queue = Queue()  # Очередь для управления выполнением selenium_parcel
        self.main: Main = Main(self)
        self.otp: OTP = OTP(self)
        # self.otp.main = self.main
        self.main.otp = self.otp
        self.jobs = []
        self.last_mtime = os.path.getmtime(self.scheduler_setting.path)  # сохранить время последнего изменения файла
        self.all: All = All()
        self.main_browser = None  # Переменная для основного браузера
        self.lock = threading.Lock()
        self.active_windows = 0
        self.condition = threading.Condition(self.lock)
        self.refreshing = False
        self.user_info: UsersInfo = UsersInfo()

    def process_queue(self, logger):
        while True:
            time.sleep(3)
            func, args = self.queue.get()
            try:
                with self.condition:
                    while self.refreshing:
                        self.condition.wait()
                        time.sleep(3)
                    self.active_windows += 1
                if self.main_browser is None:
                    logger.error("main_browser инициализирован как None при формировании очереди")
                func(*args)
            except Exception as e:
                print(f"Ошибка при работе с очередью веб-браузера: {datetime.datetime.now()}")
                logger.info(f"[Ошибка при работе с очередью веб-браузера]")
                logger.exception(e)
            finally:
                with self.condition:
                    self.active_windows -= 1
                    self.condition.notify_all()
                    time.sleep(3)

            self.queue.task_done()

    @staticmethod
    def clear_all_jobs():
        del schedule.default_scheduler.jobs[:]

    def load_jobs_from_excel(self):
        self.jobs.clear()
        df = pd.read_excel(self.scheduler_setting.path, sheetname='objects', converters={'HOUR': str, 'MINUTE': str})
        df = df[df['OBJECT_NAME'].apply(lambda x: pd.isnull(x) != True)]
        for _, row in df.iterrows():
            table_name_schedule = str(row['OBJECT_NAME'])
            size_name_schedule = row['SIZE_NAME']
            verify = row['VERIFY_FOR_LOAD']
            hour = str(row['HOUR']).zfill(2)
            minute = str(row['MINUTE']).zfill(2)

            if row['EVERY_DAY'] == 'YES':
                days: list = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
            else:
                days: list = [day for day in
                              ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'] if
                              row[day] == 'YES']
            self.jobs.append(WorkList(self, table_name_schedule, size_name_schedule, verify, days, hour, minute))

    def schedule_jobs(self):
        try:
            schedule.clear()
        except Exception as e:
            print(e)
        if self.main_browser is None:
            print("main_browser инициализирован как None после авторизации")

        for job in self.jobs:
            try:
                job_time = f"{job.hour}:{job.minute}"
                for day in job.days:
                    if day.lower() == 'monday':
                        schedule.every().monday.at(job_time).do(job.apply_with_pool,
                                                                job.table_name_schedule, job.size_name_schedule,
                                                                job.verify, self.main_browser, self.lock)
                    elif day.lower() == 'tuesday':
                        schedule.every().tuesday.at(job_time).do(job.apply_with_pool,
                                                                 job.table_name_schedule, job.size_name_schedule,
                                                                 job.verify, self.main_browser, self.lock)
                    elif day.lower() == 'wednesday':
                        schedule.every().wednesday.at(job_time).do(job.apply_with_pool,
                                                                   job.table_name_schedule,
                                                                   job.size_name_schedule,
                                                                   job.verify, self.main_browser, self.lock)
                    elif day.lower() == 'thursday':
                        schedule.every().thursday.at(job_time).do(job.apply_with_pool,
                                                                  job.table_name_schedule,
                                                                  job.size_name_schedule,
                                                                  job.verify, self.main_browser, self.lock)
                    elif day.lower() == 'friday':
                        schedule.every().friday.at(job_time).do(job.apply_with_pool,
                                                                job.table_name_schedule, job.size_name_schedule,
                                                                job.verify, self.main_browser, self.lock)
                    elif day.lower() == 'saturday':
                        schedule.every().saturday.at(job_time).do(job.apply_with_pool,
                                                                  job.table_name_schedule,
                                                                  job.size_name_schedule,
                                                                  job.verify, self.main_browser, self.lock)
                    elif day.lower() == 'sunday':
                        schedule.every().sunday.at(job_time).do(job.apply_with_pool,
                                                                job.table_name_schedule, job.size_name_schedule,
                                                                job.verify, self.main_browser, self.lock)
            except Exception as e:
                print(f"Запуск по плану объекта СПОД {job.table_name.upper()} - Ошибка || {self.all.return_time_now()}")
                print(e)
                pass

    def watch_excel_file(self, logger):
        while True:
            try:
                new_mtime = os.path.getmtime(self.scheduler_setting.path)
                if new_mtime != self.last_mtime:  # если время изменения файла изменилось
                    print("Excel file has been updated. Reloading jobs...")
                    self.clear_all_jobs()
                    self.load_jobs_from_excel()
                    self.schedule_jobs()
                    self.last_mtime = new_mtime

                time.sleep(1)  # проверять каждую секунду (можно установить другой интервал)
            except Exception as e:
                print(f"Ошибка при обновлении JOBs: {datetime.datetime.now()}")
                logger.info(f"[Ошибка при обновлении JOBs]")
                logger.exception(e)
                pass

    def smd_auth(self, browser, logger):
        try:
            browser.get("https://sm.data.ca.sbrf.ru/home")
            time.sleep(3)
            self.main.do_anything_by_xpath(xpath='//*[@id="username"]', browser=browser).send_keys(
                self.user_info.username)
            time.sleep(1)
            self.main.do_anything_by_xpath(xpath='//*[@id="password"]', browser=browser).send_keys(
                self.user_info.user_code)
            time.sleep(1)
            self.main.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()
            time.sleep(5)
            return browser
        except Exception as e:
            logger.info(f"[{UsersInfo().username}][Ошибка на стадии авторизации в СМД]")
            logger.exception(e)
            raise CriticalError from e

    def authorize_and_get_browser(self, logger):
        try:
            browser: WebDriver = self.main.launching_the_browser(logger=logger)

            # browser = self.smd_auth(browser=browser, logger=logger)

            browser.get(self.main.selenium_settings.url_spod)

            self.otp.otp_sends_and_auth(browser=browser, logger=logger)
            return browser
        except Exception as e:
            print(f"[Ошибка на стадии авторизации] {e}")
            logger.info(f"[Ошибка на стадии авторизации]")
            logger.exception(e)
            raise CriticalError from e

    def refresh_browser(self, logger):
        while True:
            with self.condition:
                while self.active_windows > 0 or not self.queue.empty():
                    self.condition.wait()
                    time.sleep(3)
                self.refreshing = True
            try:
                if self.main_browser is None:
                    logger.error("main_browser инициализирован как None при обновлении")

                self.otp.run_cookie_with_selenium(browser=self.main_browser, logger=logger)

                print(f"Браузер обновлен: {datetime.datetime.now()}")
            except Exception as e:
                print(f"Ошибка при обновлении браузера: {datetime.datetime.now()}")
                logger.info(f"[Ошибка при обновлении браузера]")
                logger.exception(e)
            finally:
                with self.condition:
                    self.refreshing = False
                    self.condition.notify_all()
                    time.sleep(3)
            time.sleep(600)  # каждые 20 минут

    def run(self):
        print(f"START SCRIPT- {self.scheduler_setting.SCRIPT_NAME}")
        main_logger = self.main.logger_setting.basic_configuration('main_logger')
        self.load_jobs_from_excel()
        self.schedule_jobs()

        # Authorize with selenium

        self.main_browser = self.authorize_and_get_browser(logger=main_logger)
        if self.main_browser is None:
            main_logger.error("main_browser инициализирован как None после авторизации")

        # Refresh browser
        refresh_thread = threading.Thread(target=self.refresh_browser, args={main_logger, })
        refresh_thread.start()

        # Watch edits file
        watcher_thread = threading.Thread(target=self.watch_excel_file, args={main_logger, })
        watcher_thread.start()

        # Watch pool for spod browser
        queue_thread = threading.Thread(target=self.process_queue, args={main_logger, })
        queue_thread.start()

        while True:
            schedule.run_pending()
            time.sleep(1)


if __name__ == '__main__':
    # work_list: WorkList = WorkList()
    # sheet_name_work = sys.argv[1] if len(sys.argv) > 1 else 'objects'  # По умолчанию 'objects'
    # work_list.open_and_start_script(sheet_name_work)

    scheduler_main = Scheduler()
    scheduler_main.run()
