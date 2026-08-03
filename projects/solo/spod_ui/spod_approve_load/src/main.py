import json
import os
import time
from datetime import datetime
from typing import Optional, Any

import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy import text
import threading
import locale
import logging
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, \
    InvalidSessionIdException, NoSuchWindowException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver import FirefoxProfile, DesiredCapabilities
from selenium import webdriver
from selenium.webdriver.firefox.webdriver import WebDriver
from settings import EngineSettings, LoggingSetting, SpodAPISettings, UsersInfo, SeleniumSettings
from requests import Response, Session


class CriticalError(Exception):
    pass


class Logging:
    def __init__(self):
        self.logger = None
        self.lock = threading.Lock()
        self.setting: LoggingSetting = LoggingSetting()

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
    def execute_in_gp(engine: Engine, query: str):
        try:
            with engine.connect() as conn:
                conn.execute(text(query).execution_options(autocommit=True))
        except Exception as e:
            print(e)
            raise CriticalError from e

    @staticmethod
    def return_time_now():
        return str(datetime.today()).rpartition('.')[0]

    @staticmethod
    def read_sql(query: str, engine: Engine) -> pd.DataFrame:
        return pd.read_sql(sql=query, con=engine)

    @staticmethod
    def read_excel(path: Optional[str], sheet_name: str = 'tables') -> pd.DataFrame:
        return pd.read_excel(path, sheetname=sheet_name)

    def text_for_logs(self, text: str):
        return f"[{text}][{self.return_time_now()}]"

    @staticmethod
    def is_time_between(start_time, end_time):
        # Если время для проверки не указано, используем текущее время
        time_now = datetime.now().time()
        if start_time <= time_now <= end_time:
            return True
        else:
            return False


class Connect:
    def __init__(self):
        self.user_info: UsersInfo = UsersInfo()
        self.all: All = All()
        # Selenium
        self.selenium_settings: SeleniumSettings = SeleniumSettings()
        self.desired_capabilities: Any = DesiredCapabilities().FIREFOX
        self.profile_browser: FirefoxProfile = webdriver.FirefoxProfile()
        self.options: Options = webdriver.FirefoxOptions()

        # Api Spod
        self.spod_api_settings: SpodAPISettings = SpodAPISettings()

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
                return browser.find_element_by_xpath(xpath)
            except (NoSuchElementException, ElementClickInterceptedException) as e:
                print(e)
                time.sleep(1)
                continue

    def launching_the_browser(self) -> WebDriver:
        try:
            profile_browser: FirefoxProfile = self.set_preference_to_firefox(profile=self.profile_browser)
            options: Options = self.set_options_to_firefox(options=self.options)
            browser: WebDriver = webdriver.Firefox(desired_capabilities=self.desired_capabilities,
                                                   executable_path=self.selenium_settings.chromedriver,
                                                   options=options,
                                                   service_log_path=self.selenium_settings.webdriver_log_file,
                                                   firefox_profile=profile_browser
                                                   )
            return browser
        except Exception as e:
            print(e)

    # Функция для загрузки cookies из файла
    @staticmethod
    def load_cookies(filename: str):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                return json.load(file)
        return {}

    # Функция для загрузки cookies конкретного пользователя

    def get_user_cookies(self, logger):
        try:
            all_cookies = self.load_cookies(filename=self.selenium_settings.cookie_file)
            return all_cookies.get(self.user_info.username, [])
        except Exception as e:
            logger.info(f"[Ошибка на стадии получения куки из файла поддержки otp]")
            logger.exception(e)
            raise CriticalError from e

    def authorization_in_sudir(self, browser: WebDriver, logger):
        try:
            time.sleep(1)
            self.do_anything_by_xpath(xpath='//*[@id="username"]', browser=browser).send_keys(self.user_info.username)
            self.do_anything_by_xpath(xpath='//*[@id="password"]', browser=browser).send_keys(self.user_info.password)
            #self.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()
            self.do_anything_by_xpath(xpath='//*[@id="submitInter"]', browser=browser).click()
            browser.get(self.selenium_settings.url_spod)
            time.sleep(3)
        except Exception as e:
            logger.info(f"[Ошибка на стадии ввода логина и пароля]")
            logger.exception(e)
            raise CriticalError from e

    def authorization_selenium(self, logger):
        try:
            logger.info(f"[Пробуем авторизоваться в СУДИР]")
            autor_count: int = 1
            while range(5):
                try:
                    logger.info(f"[Попытка авторизации №{autor_count}]")
                    browser: WebDriver = self.launching_the_browser()
                    browser.get(self.selenium_settings.url_spod)
                    self.authorization_in_sudir(browser=browser, logger=logger)
                    logger.info(f"[Пробуем получить куки результатов авторизации]")
                    selenium_cookies = browser.get_cookies()
                    browser.close()
                    logger.info(f"[Авторизация пройдена успешно]")
                    return selenium_cookies
                except (InvalidSessionIdException, NoSuchWindowException):
                    time.sleep(1)
                    try:
                        browser.close()
                    except Exception:
                        pass
                    autor_count += 1
                    continue
        except Exception as e:
            logger.info(f"[Ошибка на стадии авторизации]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def connect_in_request(selenium_cookies: Any, session: Any, logger):
        try:
            logger.info(f"[Обрабатываем куки для парсинга]")
            for cookie in selenium_cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
            logger.info(f"[Куки для парсинга успешно обработаны]")
            return session
        except Exception as e:
            logger.info(f"[Ошибка на стадии обработки куков]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def get_url(url: str, session: Any, logger):
        try:
            response: Response = session.get(url=url, verify=False)
            return response
        except Exception as e:
            logger.info(f"[Ошибка на стадии выполнения запросе типа - GET]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def post_url(url: str, headers: dict, json: dict, session: Any, logger):
        try:
            response: Response = session.post(url=url, headers=headers, json=json, verify=False)
            print(response)
        except Exception as e:
            logger.info(f"[Ошибка на стадии выполнения запросе типа - POST]")
            logger.exception(e)
            raise CriticalError from e

    def return_dict_with_structure(self, session: Any, logger) -> dict:
        try:
            logger.info(f"[Выгружаем в Json список всех структур]")
            # Create Json with all structure
            response_json = self.get_url(url=self.spod_api_settings.list_all_structure,
                                         session=session, logger=logger).json()

            logger.info(f"[Json получен]")
            # Return dict with filter
            logger.info(f"[Формируем словарь активных структур]")
            dict_with_structure: dict = {item['datasetName']: item['datasetId'] for item in response_json if
                                         item['isActive'] == 'Y'}
            return dict_with_structure
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования словаря активных структур]")
            logger.exception(e)
            raise CriticalError from e

    def return_list_with_all_loading(self, structure_id, session: Any, logger) -> list:
        try:
            logger.info(f"[Выгружаем в Json список всех загрузок]")

            # Create Json with all structure

            response_json = self.get_url(url=self.spod_api_settings.url_log.format(structure_id),
                                         session=session, logger=logger).json()
            logger.info(f"[Json получен]")
            # Return dict with filter
            logger.info(f"[Формируем список загрузок структуры]")
            loading_id_count = {}
            loading_id_list = []
            good_status = {'OP_F_SEND_APPROVE', 'OP_F_GETDATA_WAIT', 'OP_F_GETDATA'}
            for item in response_json:
                try:
                    print(item["loadingId"])
                except:
                    print(item)
                loading_id = item["loadingId"]

                if loading_id in loading_id_count:
                    loading_id_count[loading_id] += 1
                else:
                    loading_id_count[loading_id] = 1
            for item in response_json:
                if loading_id_count[item["loadingId"]] in (1, 2):
                    if item["operation"] in good_status:
                        loading_id_list.append(item['loadingId'])
            return loading_id_list
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования словаря активных структур]")
            logger.exception(e)
            raise CriticalError from e

    def update_step_in_logs_spod_process(self, source_table_name: str, final_step: int, engine: Engine):
        query = f"""update {self.spod_api_settings.schema_in}.{self.spod_api_settings.logs_spod_process}
                        set final_step = {final_step}
                        where source_table_name = '{source_table_name.lower()}'"""
        self.all.execute_in_gp(engine=engine, query=query)

    def update_status_in_logs_spod_process(self, source_table_name: str, new_status_log: str, engine: Engine):
        query = f"""update {self.spod_api_settings.schema_in}.{self.spod_api_settings.logs_spod_process}
                        set status_log = '{new_status_log}'
                        where source_table_name = '{source_table_name.lower()}'"""
        self.all.execute_in_gp(engine=engine, query=query)
        #self.update_step_in_logs_spod_process(source_table_name=source_table_name, final_step=2, engine=engine)



class Main:
    def __init__(self):
        self.all: All = All()
        self.engine_settings: EngineSettings = EngineSettings()
        self.logger_setting: Logging = Logging()
        self.connect: Connect = Connect()
        self.spod_api_settings: SpodAPISettings() = SpodAPISettings()

    def dict_logs_spod_approve(self, engine: Engine, logger) -> dict:
        try:
            logger.info(f"[Выгружаем структуры ожидающие подтверждения (Роль - Подтверждающий)]")
            query = f"""select distinct source_table_name,serving_count  
                            from {self.spod_api_settings.schema_in}.{self.spod_api_settings.logs_spod_process} 
                            where status_log = 'Структура ожидает подтверждения от подтверждающего'"""
            dataframe = self.all.read_sql(query=query, engine=engine)
            logger.info(f"[ Структуры ожидающие подтверждения (Роль - Подтверждающий) выгружены]")
            dataframe['serving_count'] = dataframe['serving_count'].apply(lambda x: int(x))
            logger.info(f"[Поле serving_count отредактировано]")
            active_dict: dict = dataframe.set_index('source_table_name')['serving_count'].to_dict()
            logger.info(f"[Dataframe структур переработан в словарь]")
            return active_dict
        except Exception as e:
            logger.info(f"[Ошибка на стадии обработки данных по структурам на подтверждении (Роль - Подтверждающий)]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def extract_cookies(session, logger):
        try:
            cookies = session.cookies.get_dict()
            cookie_header = "; ".join([f"{key}={value}" for key, value in cookies.items()])
            logger.info(f"[Куки для шапки получены]")
            return cookie_header
        except Exception as e:
            logger.info(f"[Ошибка на стадии получения куки]")
            logger.exception(e)
            raise CriticalError from e

    def update_headers(self, loading_id: int, actual_session, logger):
        try:
            headers = self.spod_api_settings.headers
            headers["Referer"] = headers["Referer"].format(loading_id)
            headers["Cookie"] = self.extract_cookies(session=actual_session, logger=logger)
            logger.info(f"[Шапка запроса сформирована]")
            return headers
        except Exception as e:
            logger.info(f"[Ошибка на стадии обновления headers]")
            logger.exception(e)
            raise CriticalError from e

    def load_approve(self, loading_id: int, actual_session, logger):
        try:
            logger.info(f"[{loading_id}][Формируем информацию для шапки запроса]")
            url: str = self.spod_api_settings.load_approve
            data: dict = {"loadingId": loading_id}
            headers = self.update_headers(loading_id=loading_id, actual_session=actual_session, logger=logger)
            self.connect.post_url(url=url, headers=headers, json=data, session=actual_session, logger=logger)
            logger.info(f"[{loading_id}][POST-запрос на подтверждение отправлен]")
            time.sleep(2)
        except Exception as e:
            logger.info(f"[{loading_id}][Ошибка на стадии передачи POST-запроса]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def convert_bad_name_structure(active_name: str):
        good_name = active_name
        dict_with_good_name = {"SPOD_QS_T_SALES_MISS_SMD_QLIK": "QS_T_SALES_MISS_SMD_QLIK",
                               "SPOD_QS_T_REPORT_PREMIAL_SUP_PAY_QLIK": "QS_T_REPORT_PREMIAL_SUP_PAY_QLIK",
                               "SPOD_QS_T_BB_MOTIV_REPEAT_QLIK": "QS_T_BB_MOTIV_REPEAT_QLIK",
                               "SPOD_QS_T_CRED_INS_GROUP": "QS_T_CRED_INS_GROUP",
                               "SPOD_QS_T_PLAN_FACT": "QS_T_PLAN_FACT",
                               "SPOD_QS_T_SVOD_TB_IPOTEKA": "SPOD__QS_T_SVOD_TB_IPOTEKA",
                               "SPOD_QS_T_QLIK_IM_AUM": "QS_T_QLIK_IM_AUM",
                               "SPOD_QS_T_OM_FINAL": "QS_T_OM_FINAL",
                               "SPOD_QS_T_PD_TB_PRED_GOSB_KD_ALL_V2": "QS_T_PD_TB_PRED_GOSB_KD_ALL",
                               "SPOD_QS_T_PD_TB_PRED_GOSB_KD_CORP_V2": "QS_T_PD_TB_PRED_GOSB_KD_CORP",
                               "SPOD_QS_T_PD_TB_PRED_GOSB_KD_MASS_V3": "QS_T_PD_TB_PRED_GOSB_KD_MASS",
                               "SPOD_QS_T_PD_TB_PRED_GOSB_KD_SB1_V2": "QS_T_PD_TB_PRED_GOSB_KD_SB1",
                               "SPOD_QS_T_PD_TB_PRED_GOSB_KD_SBP_V2": "QS_T_PD_TB_PRED_GOSB_KD_SBP",
                               "SPOD_QS_T_OM_DRAFT": "QS_T_OM_DRAFT"}

        if good_name[:5].upper() != 'SPOD_':
            good_name = f"SPOD_{good_name}"
        if good_name.upper() in dict_with_good_name:
            good_name = dict_with_good_name[good_name.upper()]
        return good_name

    def find_structure_id(self, structure: str, dict_: dict, logger):
        try:
            new_name: str = self.convert_bad_name_structure(active_name=structure.upper()).upper()
            structure_id = dict_.get(new_name)
            return structure_id
        except Exception as e:
            logger.info(f"[Ошибка на стадии поиска id структуры]")
            logger.exception(e)
            raise CriticalError from e

    def approve_structure(self, structure: str, all_structure_dict: dict, actual_session, engine):
        # Step 0: Create logger
        logger = self.logger_setting.basic_configuration(table_name=structure)
        logger.info(f"------------------------------------------------------------------")
        logger.info(f"------------------------------------------------------------------")
        try:
            # Step 1: Find in dict id structure:
            structure_id = self.find_structure_id(structure=structure, dict_=all_structure_dict, logger=logger)

            # Step 2: Create list id loadings:
            list_with_loading_id: list = self.connect.return_list_with_all_loading(structure_id=structure_id,
                                                                                   session=actual_session,
                                                                                   logger=logger)
            print(list_with_loading_id)
            # Step 3: Post to approve load
            for loading_id in list_with_loading_id:
                self.load_approve(loading_id=loading_id, actual_session=actual_session, logger=logger)

            new_status: str = "Загрузки были подтверждены автоматически"  # Временный статус
            self.connect.update_status_in_logs_spod_process(source_table_name=structure,
                                                            new_status_log=new_status,
                                                            engine=engine)
        except Exception as e:
            logger.info(f"[Ошибка на стадии подтверждения загрузок]")
            logger.exception(e)
            raise CriticalError from e

    def start(self):
        """Step 0: Create engine and log file"""
        status_now: str = "Скрипт запущен"
        print(self.all.text_for_logs(text=status_now))
        engine_in: Engine = self.engine_settings.engine_in

        logger_for_all = self.logger_setting.basic_configuration(table_name="spod_approve_all")
        logger_for_all.info(f"------------------------------------------------------------------")
        logger_for_all.info(f"------------------------------------------------------------------")
        logger_for_all.info(f"[START]")

        """Step 1: Create list for approve"""
        active_dict: dict = self.dict_logs_spod_approve(engine=engine_in, logger=logger_for_all)
        status_now: str = "Подготовлен список готовых структур к подтверждению"
        print(self.all.text_for_logs(text=status_now))
        if len(active_dict) > 0:
            """Step 2: Authorization with Selenium in SPOD and return cookies"""
            #actual_cookies = self.connect.authorization_selenium(logger=logger_for_all)
            actual_cookies = self.connect.get_user_cookies(logger=logger_for_all)

            status_now: str = "Куки сессии получены"
            print(self.all.text_for_logs(text=status_now))
            actual_session: Session = Session()
            actual_session = self.connect.connect_in_request(selenium_cookies=actual_cookies,
                                                             session=actual_session, logger=logger_for_all)
            status_now: str = "Сессия API активна"
            print(self.all.text_for_logs(text=status_now))

            """Step 3: Return dict with all structure in project"""
            dict_with_structure: dict = self.connect.return_dict_with_structure(session=actual_session,
                                                                                logger=logger_for_all)
            status_now: str = "Список активных структур выгружен"
            print(self.all.text_for_logs(text=status_now))
            """Step 4: Approve for all structure in table"""
            logger_for_all.info(f"[Запуск подтверждений индивидуально для каждой структуры]")
            for active_wait_structure in active_dict:
                self.approve_structure(structure=active_wait_structure,
                                       all_structure_dict=dict_with_structure,
                                       actual_session=actual_session,
                                       engine=engine_in)
                status_now: str = f"Загрузки структуры {active_wait_structure} подтверждены"
                print(self.all.text_for_logs(text=status_now))

        status_now: str = "Скрипт отработан"
        print(self.all.text_for_logs(text=status_now))
        engine_in.dispose()
        logger_for_all.info(f"[DONE]")


if __name__ == '__main__':
    main: Main = Main()
    main.start()
