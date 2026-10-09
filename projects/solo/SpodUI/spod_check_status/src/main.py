import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import json
from datetime import datetime, timedelta
from datetime import time as tm
from io import StringIO

import numpy as np
import pandas as pd
from requests import Response, Session
import warnings
from typing import Optional, Any
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, \
    InvalidSessionIdException, NoSuchWindowException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver import FirefoxProfile, DesiredCapabilities
from selenium import webdriver
from sqlalchemy.engine import Engine
from settings import UsersInfo, SeleniumSettings, SpodAPISettings, EngineSettings, SettingsDataLoading, SendingSetting, \
    LoggingSetting
from selenium.webdriver.firefox.webdriver import WebDriver
import time
from sqlalchemy import types, text
import threading
import locale
import logging

# warnings.filterwarnings("ignore", message="Unverified HTTPS request")
warnings.filterwarnings('ignore')


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
            # self.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()
            self.do_anything_by_xpath(xpath='//*[@id="submitInter"]', browser=browser).click()
            browser.get(self.selenium_settings.url_spod)
            time.sleep(6)
        except Exception as e:
            logger.info(f"[Ошибка на стадии ввода логина и пароля]")
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
                    time.sleep(3)
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
    def get_url(url: str, session: Any, logger, headers=None):
        try:
            response: Response = session.get(url=url, verify=False)
            return response
        except Exception as e:
            logger.info(f"[Ошибка на стадии выполнения запросе типа - GET]")
            logger.exception(e)
            raise CriticalError from e

    def return_list_with_structure(self, session: Any, logger) -> list:
        try:
            logger.info(f"[Выгружаем в Json список всех структур]")

            headers = self.spod_api_settings.headers
            headers["Cookie"] = self.extract_cookies(session=session, logger=logger)

            # Create Json with all structure
            response_json = self.get_url(url=self.spod_api_settings.list_all_structure,
                                         session=session, headers=headers, logger=logger).json()
            logger.info(f"[Json получен]")
            # Return list with filter
            logger.info(f"[Формируем список активных структур]")
            list_with_structure: list = [item['datasetId'] for item in response_json if item['isActive'] == 'Y']
            return list_with_structure
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования списка активных структур]")
            logger.exception(e)
            raise CriticalError from e

    def create_url_for_all_loading(self, logger):
        try:
            # Форматируем даты в соответствии с требуемым форматом
            date_end = datetime.now()
            date_begin = date_end - timedelta(days=15)
            date_begin_str = date_begin.strftime('%Y-%m-%dT00:00:00.000')
            date_end_str = date_end.strftime('%Y-%m-%dT23:59:59.999')

            # Возвращаем готовый запрос для api
            api_sss = self.spod_api_settings.url_template_full.format(date_begin_str, date_end_str)
            logger.info(f"[API структуры {api_sss}]")
            return api_sss
        except Exception as e:
            logger.info(f"[Ошибка на этапе формирования запроса к API]")
            logger.exception(e)
            raise CriticalError from e

    def return_dataframe_with_loading(self, session: Any, logger):
        try:
            all_loads = []
            logger.info(f"[Формируем список текущих загрузок и статусов]")

            # Получаем URL для текущего проекта
            url = self.create_url_for_all_loading(logger=logger)

            # Отправляем запрос
            response = self.get_url(url=url, session=session, logger=logger)
            loads_info = response.json()

            # Добавляем информацию о загрузках в общий список
            all_loads.extend(loads_info)
            time.sleep(2)
            logger.info(f"[Список текущих загрузок и статусов сформирован]")
            # Создаем DataFrame из полученных данных
            loads_df = pd.DataFrame(all_loads)
            logger.info(f"[Список текущих загрузок и статусов переработан в Dataframe]")
            return loads_df
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования списка текущих загрузок и статусов]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def covert_date_to_timestamp_format(date: Any):
        return pd.to_datetime(date).strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def extract_column_value(load_param):
        check_param = 0
        if isinstance(load_param, str):
            try:
                column_name = "columnValue"
                load_param_list = json.loads(load_param)
                if load_param_list and column_name in load_param_list[0]:
                    check_param = load_param_list[0][column_name]
                else:
                    check_param = 0
            except json.JSONDecodeError as ee:
                check_param = 0
        return check_param

    @staticmethod
    def save_in_base(dataframe: pd.DataFrame, table_name: str, dtyp: dict, engine: Engine):
        dataframe.to_sql(name=table_name, dtype=dtyp, con=engine, if_exists='append', index=False)

    @staticmethod
    def convert_to_best_dtype(dataframe):
        try:
            for column in dataframe.columns[dataframe.dtypes == 'datetime64[ns]']:
                dataframe[column] = pd.to_datetime(dataframe[column])
                dataframe[column] = dataframe[column].dt.date.apply(lambda x: str(x))
                dataframe[column] = dataframe[column].replace('NaT', np.nan)

            dtyp = {c: types.VARCHAR(500) for c in
                    dataframe.columns[dataframe.dtypes == 'object'].tolist()}
            return dataframe, dtyp
        except Exception as e:
            print(e)

    @staticmethod
    def convert_bad_name_structure(active_name: str):
        good_name = active_name
        dict_with_good_name = {"QS_T_SALES_MISS_SMD_QLIK": "SPOD_QS_T_SALES_MISS_SMD_QLIK",
                               "QS_T_REPORT_PREMIAL_SUP_PAY_QLIK": "SPOD_QS_T_REPORT_PREMIAL_SUP_PAY_QLIK",
                               "QS_T_BB_MOTIV_REPEAT_QLIK": "SPOD_QS_T_BB_MOTIV_REPEAT_QLIK",
                               "QS_T_CRED_INS_GROUP": "SPOD_QS_T_CRED_INS_GROUP",
                               "QS_T_PLAN_FACT": "SPOD_QS_T_PLAN_FACT",
                               "SPOD__QS_T_SVOD_TB_IPOTEKA": "SPOD_QS_T_SVOD_TB_IPOTEKA",
                               "QS_T_QLIK_IM_AUM": "SPOD_QS_T_QLIK_IM_AUM"}

        if good_name.upper() in dict_with_good_name:
            good_name = dict_with_good_name[good_name.upper()]
        return good_name

    def convert_dataframe(self, dataframe, logger):
        try:
            logger.info(f"[Старт обработки данных по загрузкам]")
            today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            dataframe = dataframe.loc[:, ['datasetId', 'datasetName', 'loadParam', 'createDate', 'loadingStatus']]
            dataframe['createDate'] = dataframe['createDate'].apply(self.covert_date_to_timestamp_format)
            logger.info(f"[Поле createDate обработано]")
            dataframe['loadParam'] = dataframe['loadParam'].apply(self.extract_column_value)
            logger.info(f"[Поле loadParam обработано]")
            dataframe['datasetName'] = dataframe['datasetName'].apply(self.convert_bad_name_structure)
            logger.info(f"[Поле datasetName обработано]")
            dataframe['date_update'] = today
            dataframe = dataframe.rename(columns={'datasetId': 'dataset_id',
                                                  'datasetName': 'dataset_name',
                                                  'loadParam': 'load_param',
                                                  'createDate': 'create_date',
                                                  'loadingStatus': 'loading_status'})

            dataframe = dataframe.drop_duplicates()
            logger.info(f"[Дубликаты удалены]")
            logger.info(f"[Данные по загрузкам обработы успешно]")
            return dataframe
        except Exception as e:
            logger.info(f"[Ошибка на стадии обработки данных по загрузкам]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def create_table_if_not_exists(engine, df, table_name, logger):
        try:
            if not engine.dialect.has_table(engine, table_name):
                print(f"Создаем таблицу {table_name}")
                df.head(0).to_sql(table_name, engine, index=False)
                logger.info(f"[Таблица - {table_name} создана]")
        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки данных в БД]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def copy_from_stringio(conn, df, table, logger):
        try:
            buffer = StringIO()
            df.to_csv(buffer, index=False, header=False)
            buffer.seek(0)
            logger.info(f"[Буфер с данными сформирован]")
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования буфера с данными]")
            logger.exception(e)
            raise CriticalError from e

        with conn.connection.cursor() as cursor:
            try:
                cursor.copy_expert(f"COPY {table} FROM STDIN WITH CSV", buffer)
                conn.connection.commit()
                logger.info(f"[Буфер с данными успешно записан в БД]")
            except Exception as error:
                print("Ошибка: %s" % error)
                conn.connection.rollback()
                logger.info(f"[Ошибка на стадии записи буфера через COPY]")
                logger.exception(error)
                return 1
            finally:
                buffer.close()

    def load_with_portion(self, dataframe, engine, table_name, logger):
        try:
            with engine.connect() as conn:
                for i in range(0, dataframe.shape[0], 100000):
                    part_df = dataframe.iloc[i:i + 100000]
                    logger.info(f"[Что за часть]{part_df}")
                    self.copy_from_stringio(conn, part_df, table_name, logger)
                print(f"Данные добавлены в {table_name}")
                logger.info(f"[Данные успешно загружены в {table_name}]")
        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки через copy]")
            logger.exception(e)
            raise CriticalError from e

    def load_info_in_base_new(self, dataframe, engine: Engine, logger):
        try:
            table_name = self.spod_api_settings.logs_spod_loading
            dataframe, dtyp = self.convert_to_best_dtype(dataframe)

            # Создаем таблицу логирования если ее нет
            self.create_table_if_not_exists(engine=engine, df=dataframe, table_name=table_name, logger=logger)

            # Записываем данные в таблицу
            self.load_with_portion(dataframe=dataframe, engine=engine, table_name=table_name, logger=logger)

            logger.info(f"[Информация по статусам загрузки записаны в БД]")
        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки данных в БД]")
            logger.exception(e)
            raise CriticalError from e

    def load_info_in_base(self, dataframe, engine: Engine, logger):
        try:
            dataframe, dtyp = self.convert_to_best_dtype(dataframe)
            dataframe.to_sql(name=self.spod_api_settings.logs_spod_loading,
                             dtype=dtyp,
                             con=engine,
                             if_exists="append",
                             index=False)
            logger.info(f"[Информация по статусам загрузки записаны в БД]")
        except Exception as e:
            logger.info(f"[Ошибка на стадии загрузки данных в БД]")
            logger.exception(e)
            raise CriticalError from e


class Working:
    def __init__(self):
        self.spod_api_settings: SpodAPISettings = SpodAPISettings()
        self.all: All = All()
        self.connect: Connect = Connect()
        self.sdl: SettingsDataLoading = SettingsDataLoading()

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
        if new_status_log == "Структура ожидает подтверждения от подтверждающего":
            self.update_step_in_logs_spod_process(source_table_name=source_table_name, final_step=3, engine=engine)
        elif new_status_log == "Процесс загрузки СПОД завершен":
            self.update_step_in_logs_spod_process(source_table_name=source_table_name, final_step=2, engine=engine)

    def dict_logs_spod_process(self, engine: Engine, logger) -> dict:
        try:
            logger.info(f"[Выгружаем активные статусы загрузок]")
            query = f"""select distinct source_table_name,serving_count  
                            from {self.spod_api_settings.schema_in}.{self.spod_api_settings.logs_spod_process} 
                            where status_log in('Данные отправлены на загрузку', 
                                                'Структура ожидает подтверждения от подтверждающего',
                                                'Загрузки были подтверждены автоматически')"""
            dataframe = self.all.read_sql(query=query, engine=engine)
            logger.info(f"[Активные статусы выгружены]")
            dataframe['serving_count'] = dataframe['serving_count'].apply(lambda x: int(x))
            logger.info(f"[Поле serving_count отредактировано]")
            active_dict: dict = dataframe.set_index('source_table_name')['serving_count'].to_dict()
            logger.info(f"[Dataframe активных статусов переработан в словарь]")
            return active_dict
        except Exception as e:
            logger.info(f"[Ошибка на стадии обработки данных по активным статусам]")
            logger.exception(e)
            raise CriticalError from e

    def dataframe_for_all_table(self, engine: Engine, logger):
        try:
            logger.info(f"[Выгружаем сводные данные для оценки статусов]")
            query_for_filter: str = f"""with lsp as (
                                select * 
                                from {self.spod_api_settings.schema_in}.{self.spod_api_settings.logs_spod_process}
                                ),

                                lsl as(
                                select * 
                                from {self.spod_api_settings.schema_in}.{self.spod_api_settings.logs_spod_loading}
                                where date_update = (
                                    select max(date_update) 
                                    from {self.spod_api_settings.schema_in}.{self.spod_api_settings.logs_spod_loading}) 
                                ),
                                 lsllsp as (                         
                                    select 
                                        lsp.source_table_name,
                                        lsl.load_param,
                                        lsl.loading_status,
                                        lsl.create_date
                                        from lsl
                                        join lsp
                                        on position(upper(lsl.dataset_name) in concat('SPOD_', upper(lsp.source_table_name))) > 0
                                        and lsl.create_date >= lsp.start_time_login
                                ),
                                final_code as (
                                select source_table_name::text,
                                        load_param::numeric,
                                        loading_status::text,
                                        create_date::timestamp
                                    from lsllsp val1
                                    where val1.create_date = (select max(create_date) from lsllsp 
                                                                where val1.source_table_name = lsllsp.source_table_name
                                                                and val1.load_param = lsllsp.load_param))
            select * from final_code"""

            dataframe = self.all.read_sql(query=query_for_filter, engine=engine)

            logger.info(f"[Сводные данные для оценки статусов успешно записаны в Dataframe]")
            return dataframe
        except Exception as e:
            logger.info(f"[Ошибка на стадии обработки сводных данных для оценки статусов]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def dict_query_for_table(table_name: str, dataframe, logger) -> dict:
        try:
            dataframe = dataframe[dataframe['source_table_name'] == table_name.lower()]
            dataframe = dataframe.loc[:, ['load_param', 'loading_status']]
            dataframe['load_param'] = dataframe['load_param'].apply(lambda x: int(x))
            dict_with_portion: dict = dataframe.set_index('load_param')['loading_status'].to_dict()
            return dict_with_portion
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования справочника сводных активных загрузок]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def check_true_count_active_loading(count_in_logs: int, count_in_api: int):
        good = False
        if count_in_logs == count_in_api:
            good = True
        return good

    @staticmethod
    def find_way_for_table(dict_loading: dict):
        """Проверка на выбор пути оценки - для порцционных загрузок или цельных"""
        try:
            portion_way = True
            if len(dict_loading) == 1 and next(iter(dict_loading)) == 0:
                portion_way = False
            return portion_way
        except Exception as e:
            print(e)

    def use_best_way_in_check(self, dict_with_portion: dict, count_in_logs: int):
        count_in_api: int = len(list(dict_with_portion.values()))

        # Check count active portion  == real loading portion

        if self.check_true_count_active_loading(count_in_logs=count_in_logs, count_in_api=count_in_api):
            # Check portion table or not (Choose Way)
            if self.find_way_for_table(dict_loading=dict_with_portion):
                return 1  # Portion
            else:
                return 0  # Whole

    def way_for_portion(self, data_dict: dict, structure_name: str, engine: Engine, logger):
        try:
            statuses = set(data_dict.values())

            # Таблица с информацией для загружающего по структурам готовым на отправку
            if statuses == {"STF_WAIT_SEND_APPROVE"}:
                # Записываем данные в таблицу для информационной рассылки
                self.sdl.dataframe_approve_send = self.sdl.dataframe_approve_send.append(
                    {"Наименование структуры": structure_name}, ignore_index=True)

                # Меняем статус в таблице прогресса (На время тестов выключено)

                # new_status: str = "Процесс загрузки СПОД завершен"
                # self.update_status_in_logs_spod_process(source_table_name=structure_name,
                # new_status_log=new_status,
                # engine=engine)

            # Таблица с информацией для загружающего по таблицам с ошибками
            elif "STF_ERROR" in statuses:
                failed_count = list(data_dict.values()).count("STF_ERROR")
                total_count = len(data_dict)

                # Записываем данные в таблицу для информационной рассылки
                self.sdl.dataframe_error = self.sdl.dataframe_error.append(
                    {"Наименование структуры": structure_name,
                     "Количество отправленных на загрузку порций": total_count,
                     "Количество порций с ошибкой": failed_count}, ignore_index=True)

                # Меняем статус в таблице прогресса (На время тестов выключено)

                # new_status: str = "Процесс загрузки СПОД упал с ошибкой. Требуется перезагрузка"
                # self.update_status_in_logs_spod_process(source_table_name=structure_name,
                # new_status_log=new_status,
                # engine=engine)

            # Таблица с информацией для подтверждающего по таблицам на подтверждении
            elif statuses == {"STF_ON_USER_APPROVE"}:

                #  Записываем данные в таблицу для информационной рассылки
                self.sdl.dataframe_approve_user = self.sdl.dataframe_approve_user.append(
                    {"Наименование структуры": structure_name}, ignore_index=True)

                # Меняем статус в таблице прогресса (На время тестов выключено)

                new_status: str = "Структура ожидает подтверждения от подтверждающего"
                self.update_status_in_logs_spod_process(source_table_name=structure_name,
                                                        new_status_log=new_status,
                                                        engine=engine)

            elif "STF_COMPLETED_ERROR" in statuses:
                self.sdl.dataframe_error_approve = self.sdl.dataframe_error_approve.append(
                    {"Наименование структуры": structure_name}, ignore_index=True)
                # new_status: str = "Ошибка на стадии подтверждения. Требуется ручной перезапуск"
                # self.update_status_in_logs_spod_process(source_table_name=structure_name,
                # new_status_log=new_status,
                # engine=engine)

            # Таблица с информацией по готовым загрузкам (сообщение не формируется)
            elif statuses == {"STF_COMPLETED"}:
                # Меняем статус в таблице прогресса (На время тестов выключено)

                new_status: str = "Процесс загрузки СПОД завершен"  # Временный статус
                self.update_status_in_logs_spod_process(source_table_name=structure_name,
                                                        new_status_log=new_status,
                                                        engine=engine)
                logger.info(f"[{structure_name} - изменен на финальный статус]")

            # Таблица с информацией по активным загрузкам (сообщение на загружающего)
            elif "STF_GETDATA" in statuses:
                work_count = list(data_dict.values()).count("STF_GETDATA")
                total_count = len(data_dict)

                #  Записываем данные в таблицу для информационной рассылки

                self.sdl.dataframe_working = self.sdl.dataframe_working.append(
                    {"Наименование структуры": structure_name,
                     "Количество отправленных на загрузку порций": total_count,
                     "Количество порций на загрузке": work_count}, ignore_index=True)
        except Exception as e:
            logger.info(f"[Ошибка на стадии определения пути структукры - {structure_name}]")
            logger.exception(e)
            raise CriticalError from e

    def check_active_loading(self, table_name: str, dataframe, engine: Engine, logger):

        # Step 1: Read query with active part to dict
        dict_with_portion: dict = self.dict_query_for_table(table_name=table_name, dataframe=dataframe, logger=logger)
        # Step 2: Check true count active loading

        # next_way: int = self.use_best_way_in_check(dict_with_portion=dict_with_portion, count_in_logs=count_in_logs)

        # Step 3: Use Checks for way
        # if next_way == 1:
        self.way_for_portion(data_dict=dict_with_portion, structure_name=table_name, engine=engine, logger=logger)

    def work_with_all_active_structure(self, engine: Engine, logger):
        try:
            logger.info(f"[Старт этапа работы с активными структурами]")
            # Step 1: Return all_active process
            active_dict: dict = self.dict_logs_spod_process(engine=engine, logger=logger)

            # Step 2: Create dataframe_with group loading
            dataframe_with_portion = self.dataframe_for_all_table(engine=engine, logger=logger)
            # Step 3: For all active process check info
            logger.info(f"[Старт ряда проверок статусов по каждой активной структуре]")
            for active_structure, count_in_logs in active_dict.items():
                self.check_active_loading(table_name=active_structure, dataframe=dataframe_with_portion,
                                          engine=engine, logger=logger)

            logger.info(f"[Этап работы с активными структурами успешно закончен]")
            return self.sdl.dataframe_approve_send, self.sdl.dataframe_working, \
                   self.sdl.dataframe_error, self.sdl.dataframe_approve_user, self.sdl.dataframe_error_approve

        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования списка текущих загрузок и статусов]")
            logger.exception(e)
            raise CriticalError from e


class Sending:
    def __init__(self):
        self.working: Working = Working()
        self.send_setting: SendingSetting = SendingSetting()
        self.user_info: UsersInfo = UsersInfo()

    @staticmethod
    def add_empty_row(dataframe):
        empty_row = pd.DataFrame([[""] * len(dataframe.columns)], columns=dataframe.columns)
        return dataframe.append(empty_row, ignore_index=True)

    @staticmethod
    def use_style_for_dataframe(dataframe, style: list, good_color: str):
        frame_style = dataframe.reset_index(drop=True)
        frame_style = frame_style.style.applymap(lambda x: good_color).set_table_styles(style)
        return frame_style

    @staticmethod
    def create_body_html(what_need_send: Any, today: str, username: str) -> str:
        body_html_list: list = ['<html><body>', 'Выгрузка от ',
                                today, '<br>', 'Профиль выгрузки ',
                                username, '<br>',
                                what_need_send, '<html><body>']
        return ''.join(body_html_list)

    def what_need_for_send_to_loader(self, dataframe_approve_send, dataframe_error, dataframe_working, logger) -> str:
        try:
            logger.info("[Формируем тело сообщения для загрузчика]")

            approve_send_style_frame = self.use_style_for_dataframe(dataframe=dataframe_approve_send,
                                                                    style=self.send_setting.approve_style,
                                                                    good_color="background-color: #c8e6c9")
            error_style_frame = self.use_style_for_dataframe(dataframe=dataframe_error,
                                                             style=self.send_setting.error_style,
                                                             good_color="background-color: #ffcdd2")
            working_style_frame = self.use_style_for_dataframe(dataframe=dataframe_working,
                                                               style=self.send_setting.working_style,
                                                               good_color="background-color: #bbdefb")

            loader_list = [
                '<h3 style="color: black; padding: 5px;">Ожидает подтверждения от загрузчика</h3>',
                approve_send_style_frame.render(),
                '<h3 style="color: black; padding: 5px;">Ошибки при загрузке</h3>',
                error_style_frame.render(),
                '<h3 style="color: black; padding: 5px;">Активные загрузки</h3>',
                working_style_frame.render()
            ]

            return ''.join(loader_list)
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования сообщения для загрузчика]")
            logger.exception(e)
            raise CriticalError from e

    '''
    @staticmethod
    def what_need_for_send_to_approver(dataframe_approve_user) -> str:
        loader_list: list = [dataframe_approve_user.to_html()]
        return ''.join(loader_list)
    '''

    def what_need_for_send_to_approver(self, dataframe_approve_user, dataframe_error_approve) -> str:
        approve_send_style_frame = self.use_style_for_dataframe(dataframe=dataframe_approve_user,
                                                                style=self.send_setting.approve_style,
                                                                good_color="background-color: #c8e6c9")
        error_style_frame = self.use_style_for_dataframe(dataframe=dataframe_error_approve,
                                                         style=self.send_setting.error_style,
                                                         good_color="background-color: #ffcdd2")
        loader_list = [
            '<h2 style="color: black; padding: 5px;">Ожидает подтверждения от подтверждающего</h2>',
            approve_send_style_frame.render(),
            '<h3 style="color: black; padding: 5px;">Ошибки при подтверждении</h3>',
            error_style_frame.render()]
        return ''.join(loader_list)

    def create_df_to_send(self, mail_to: str, mail_copy: str, topic: str, body: str, logger):
        try:
            dataframe_mail = pd.DataFrame(columns=self.send_setting.outlook_columns)
            dataframe_mail.loc[0, 'mail_to'] = mail_to
            dataframe_mail.loc[0, 'mail_cc'] = mail_copy
            dataframe_mail.loc[0, 'mail_sub'] = topic
            dataframe_mail.loc[0, 'mail_html'] = body
            logger.info(f"[Cообщение Outlook успешно сформировано]")
            return dataframe_mail
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования dataframe сообщения Outlook]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def send_email_smtp(sender, receiver, cc, subject, body, attachments, server, logger):
        try:
            logger.info(f"[Отправка сообщения - {subject} - СТАРТ]")
            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = receiver
            msg["Cc"] = cc
            msg["Subject"] = subject
            msg.attach(MIMEText(body, 'html'))

            for attachment in attachments:
                if attachment:
                    base_file_name = os.path.basename(attachment)
                    with open(attachment, "rb") as f:
                        attach = MIMEApplication(
                            f.read(),
                            Name=os.path.basename(base_file_name)
                        )
                    attach.add_header('Content-Disposition', 'attachment', filename=base_file_name)
                    msg.attach(attach)

            server.sendmail(sender, receiver.split(",") + cc.split(","), msg.as_string())
            logger.info(f"[Отправка сообщения - {subject} - УСПЕШНО]")
        except Exception as e:
            logger.info(f"[Ошибка на стадии отправки сообщения :{subject}]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def connect_smtp(server_name, server_port, user_name, password, logger):
        try:
            logger.info(f"[Подключаемся к серверу рассылки]")
            server = smtplib.SMTP(server_name, server_port, timeout=300)
            server.starttls()
            connected = False
            while not connected:
                try:
                    server.login(user_name, password)
                    connected = True
                except Exception as e:
                    print(f"CONNECT_ERROR: \n{e}")
                    time.sleep(5)
            logger.info(f"[Подключение к серверу рассылки проведено успешно]")
            return server
        except Exception as e:
            logger.info(f"[Ошибка на стадии открытия подключения к серверу рассылки]")
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def disconnect_smtp(server, logger):
        try:
            server.quit()
        except Exception as e:
            logger.info(f"[Ошибка на стадии отключения сервера рассылки]")
            logger.exception(e)
            time.sleep(5)

    def active_server(self, logger):
        server = self.connect_smtp(server_name=self.send_setting.host_smtp,
                                   server_port=self.send_setting.port_smtp,
                                   user_name=self.user_info.username,
                                   password=self.user_info.password,
                                   logger=logger)
        return server

    def sending(self, dataframe, server, logger):
        try:
            sender = self.user_info.my_mail_dict[self.user_info.username]
            mail_to = dataframe.loc[0, 'mail_to'].split(';')
            mail_cc = dataframe.loc[0, 'mail_cc'].split(';')
            receiver = str(", ".join(mail_to))
            cc = str(", ".join(mail_cc)) if 'mail_cc' in dataframe.columns else ""
            subject = str(dataframe.loc[0, 'mail_sub']) if 'mail_sub' in dataframe.columns else ""
            body = str(dataframe.loc[0, 'mail_html']) if 'mail_html' in dataframe.columns else ""
            attachments = []
            logger.info(f"[Тело сообщения сформировано]")

            self.send_email_smtp(sender, receiver, cc, subject, body, attachments, server, logger)
        except Exception as e:
            logger.info(f"[Ошибка на стадии работы с сообщением]")
            logger.exception(e)
            raise CriticalError from e

    def start_send(self, dataframe_approve_send, dataframe_working, dataframe_error, dataframe_approve_user,
                   dataframe_error_approve, logger):
        try:
            # Step 0: Open active server
            active_server_now = self.active_server(logger=logger)
            if not dataframe_approve_send.empty or not dataframe_working.empty or not dataframe_error.empty:
                # Step 1: Create message for loader
                body_for_send_to_loader: str = self.create_body_html(what_need_send=self.what_need_for_send_to_loader(
                    dataframe_approve_send=dataframe_approve_send,
                    dataframe_working=dataframe_working,
                    dataframe_error=dataframe_error,
                    logger=logger),
                    today=self.send_setting.today,
                    username=self.user_info.username)

                dataframe_send_loader = self.create_df_to_send(
                    mail_to=self.send_setting.info_for_loader["outlook_mail_to"],
                    mail_copy=self.send_setting.info_for_loader["outlook_mail_copy"],
                    topic=self.send_setting.info_for_loader["outlook_topic"],
                    body=body_for_send_to_loader,
                    logger=logger)

                self.sending(dataframe=dataframe_send_loader, server=active_server_now, logger=logger)
            if not dataframe_approve_user.empty:
                # Step 2: Create message for approver
                body_for_send_to_approver: str = self.create_body_html(
                    what_need_send=self.what_need_for_send_to_approver(
                        dataframe_approve_user=dataframe_approve_user,
                        dataframe_error_approve=dataframe_error_approve),
                    today=self.send_setting.today,
                    username=self.user_info.username)

                dataframe_send_approver = self.create_df_to_send(
                    mail_to=self.send_setting.info_for_approver["outlook_mail_to"],
                    mail_copy=self.send_setting.info_for_approver["outlook_mail_copy"],
                    topic=self.send_setting.info_for_approver["outlook_topic"],
                    body=body_for_send_to_approver,
                    logger=logger)

                self.sending(dataframe=dataframe_send_approver, server=active_server_now, logger=logger)

            # Step 2: Disconnect server
            self.disconnect_smtp(active_server_now, logger)
        except Exception as e:
            logger.info(f"[Ошибка на стадии формирования и отправки сообщений]")
            logger.exception(e)
            raise CriticalError from e


class Main:
    def __init__(self):
        self.connect: Connect = Connect()
        self.working: Working = Working()
        self.sending: Sending = Sending()
        self.engine_settings: EngineSettings = EngineSettings()
        self.logger_setting: Logging = Logging()
        self.all: All = All()

    def start(self):
        status_now: str = "СТАРТ скрипта"
        print(self.all.text_for_logs(text=status_now))
        """Step 0: Create logs file"""
        logger = self.logger_setting.basic_configuration(table_name="spod_check_status")
        logger.info(f"------------------------------------------------------------------")
        logger.info(f"------------------------------------------------------------------")
        """Step 1: Authorization with Selenium in SPOD and return cookies"""
        # actual_cookies = self.connect.authorization_selenium(logger=logger)
        actual_cookies = self.connect.get_user_cookies(logger=logger)
        status_now: str = "Куки сессии получены"
        print(self.all.text_for_logs(text=status_now))

        """Step 2: Connect in Request and return session"""
        actual_session: Session = Session()
        actual_session = self.connect.connect_in_request(selenium_cookies=actual_cookies,
                                                         session=actual_session, logger=logger)
        status_now: str = "Сессия API активна"
        print(self.all.text_for_logs(text=status_now))

        """Step 3: Return dict with all structure in project"""

        #list_with_structure: list = self.connect.return_list_with_structure(session=actual_session, logger=logger)
        #status_now: str = "Список структур сформирован"
        #print(self.all.text_for_logs(text=status_now))

        """Step 4: Return dataframe with all structure and all loading"""
        dataframe_structure = self.connect.return_dataframe_with_loading(session=actual_session,
                                                                         logger=logger)
        status_now: str = "Данные по загрузкам активных структур сгруппированы"
        print(self.all.text_for_logs(text=status_now))

        """Step 5: Convert dataframe"""
        dataframe_structure = self.connect.convert_dataframe(dataframe=dataframe_structure, logger=logger)
        status_now: str = "Данные по загрузкам активных структур отредактированы"
        print(self.all.text_for_logs(text=status_now))

        """Step 6: Dataframe safe in BD"""
        engine_in: Engine = self.engine_settings.engine_in
        self.connect.load_info_in_base_new(dataframe=dataframe_structure, engine=engine_in, logger=logger)
        status_now: str = "Данные по загрузкам активных структур сохранены в БД"
        print(self.all.text_for_logs(text=status_now))

        """Step 7: Work with all loading"""
        dataframe_approve_send, dataframe_working, dataframe_error, dataframe_approve_user, dataframe_error_approve = \
            self.working.work_with_all_active_structure(engine=engine_in, logger=logger)
        status_now: str = "Объекты данных для рассылок заполнены"
        print(self.all.text_for_logs(text=status_now))

        """Step 8: Create Message and Send"""
        self.sending.start_send(dataframe_approve_send, dataframe_working,
                                dataframe_error, dataframe_approve_user, dataframe_error_approve, logger)
        status_now: str = "Рассылки отправлены"
        print(self.all.text_for_logs(text=status_now))
        engine_in.dispose()

    def start_only_in_work_time(self):
        # start_time = tm(6, 0)  # 6:00
        # end_time = tm(05, 59)  # 05:59
        # if self.all.is_time_between(start_time, end_time):
        self.start()


if __name__ == '__main__':
    main: Main = Main()
    main.start_only_in_work_time()
