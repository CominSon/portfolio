import getpass
import pathlib

import pandas as pd
from connectBD import use_new_engine
from noterball import noterball
from sqlalchemy.engine import Engine


class LoggingSetting:
    def __init__(self):
        self.logs_path: str = f'{UsersInfo().main_path}logs/'
        self.format: str = '%(asctime)s %(name)s %(levelname)s:%(message)s'


class UsersInfo:
    @staticmethod
    def read_excel_users(path: str, user: str):
        df = pd.read_excel(path, sheetname='Лист1')
        df = df[df['PPT'].apply(lambda x: x.upper()) == user.upper()]
        tim2 = df['PPZ'][(df['PPX'] == max(df['PPX']))]
        return tim2

    def __init__(self):
        self.basic_path: str = 'Z:/Exchange/Maksim'
        str_path_to_user_info = f"{self.basic_path}/Python Scripts/Рабочие области/"
        self.path_to_user_info: str = str(pathlib.Path(f"{str_path_to_user_info}working/kkts/pen_is.xlsx"))
        self.username: str = getpass.getuser()
        self.password: str = noterball(self.read_excel_users(path=self.path_to_user_info,
                                                             user=self.username))
        self.my_mail_dict: dict = {'18764734': "MYuPavlenko@omega.sbrf.ru",
                                   '22652991': "YESakhno@omega.sbrf.ru",
                                   '19658533': "VMTarakanov@omega.sbrf.ru",
                                   '19465270': "RNShafigullin@omega.sbrf.ru",
                                   '23091135': "agervasilyev@omega.sbrf.ru"}

        self.main_path = "Z:/Exchange/Maksim/DfProjects/spod_with_otp/spod_approve_load/src/"


class SeleniumSettings:
    def __init__(self):
        """All Setting for Outlook mailing"""

        # Settings from browser
        # self.browser_path: str = "C:\\Program Files\\Mozilla Firefox\\firefox.exe"
        self.browser_path: str = "Z:\\Exchange\\Maksim\\Mozilla Firefox\\firefox.exe"
        self.basic_path: str = 'Z:/Exchange/Maksim'
        self.chromedriver = str(pathlib.Path(f'{self.basic_path}/Chromdriver/geckodriver.exe'))
        self.webdriver_log_file: str = str(pathlib.Path(f'{self.basic_path}/Auto/geckodriver.log'))
        # self.url_spod: str = "https://sudir004.ca.sbrf.ru/SberDataCorr/"
        self.url_spod: str = "https://pvlos-sys000001.omega.sbrf.ru/SberDataCorr/"  # Новая ссылка СПОДа
        self.preferences: dict = {
            "network.negotiate-auth.trusted-uris": "pvlos-sys000001.omega.sbrf.ru, auth.ca.sbrf.ru, ecml-df.ca.sbrf.ru",
            "privacy.history.custom": False,
            "network.cookie.cookieBehavior": 0,
            "browser.link.open_newwindow": 2,
            "browser.download.folderList": 2,
            "browser.download.dir": str(pathlib.Path(f'{self.basic_path}/Download//')),
            "browser.download.manager.alertOnEXEOpen": False,
            "browser.download.manager.showWhenStarting": False,
            "browser.download.manager.useWindow": False,
            "browser.download.manager.focusWhenStarting": False,
            "browser.download.manager.showAlertOnComplete": False,
            "browser.download.manager.closeWhenDone": True,
            "browser.helperApps.neverAsk.saveToDisk":
                """application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;charset=utf-8,
                   application/vnd.ms-excel;charset=windows-1251,
                   application/vnd.ms-excel,
                   application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
                   application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
                   application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
                   text/csv,
                   application/x-msexcel,
                   application/excel,
                   application/x-excel,
                   application/vnd.ms-excel,
                   image/png,
                   image/jpeg,
                   text/html,
                   text/plain,
                   application/msword,
                   application/xml
                """,
            "browser.helperApps.neverAsk.openFile":
                """application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
                   application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
                   text/csv,application/x-msexcel,
                   application/excel,
                   application/x-excel,
                   application/vnd.ms-excel,
                   image/png,image/jpeg,
                   text/html,
                   text/plain,
                   application/msword,
                   application/xml
                """
        }
        self.option_arguments: list = ["--headless"]
        # self.option_arguments: list = [""]

        # self.cookie_file: str = "Z:/Exchange/Maksim/DfProjects/spod_otp_support/src/results/cookies.json"
        self.cookie_file: str = f"Z:/Exchange/Maksim/DfProjects/spod_otp_support/src/results/{UsersInfo().username}_cookies.json"


class EngineSettings:
    def __init__(self):
        self.engine_in: Engine = use_new_engine('capgp1_in')  # Схема WORK


class SpodAPISettings:
    """
    Класс формирует профиль для POST-запроса Авторизации СУДИР
    """

    def __init__(self):
        self.selenium_settings: SeleniumSettings = SeleniumSettings()
        self.url_api = f"{self.selenium_settings.url_spod}api/v1/data_load/"  # Общий URL API
        # Список всех структур нашего проекта
        self.list_all_structure = f"{self.url_api}dataset/load_list?projectAreaId=1781"

        # Шаблон для получения загрузок по api
        self.url_template = self.url_api + "dataset/load_list?datasetId={}&dateBegin={}&dateEnd={}"

        # Шаблон для получения logID, loadingId
        self.url_log = self.url_api + "dataset/load_log?datasetId={}"

        # Шаблон для подтверждения
        self.load_approve = f'{self.url_api}load/operation/approve'

        # Шаблон для заголовка запроса
        self.headers = {
            "Host": "pvlos-sys000001.omega.sbrf.ru"
            , "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0"
            , "Accept": "application/json"
            , "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3"
            , "Accept-Encoding": "gzip, deflate, br"
            ,
            "Referer": "https://pvlos-sys000001.omega.sbrf.ru/SberDataCorr/UBHQ_LD/data-load/datasets/35824/approve/{}"
            , "Content-Type": "application/json"
            , "Content-Length": "19"
            , "Origin": "https://pvlos-sys000001.omega.sbrf.ru"
            , "Connection": "keep-alive"
            , "Cookie": "{}"
            , "Sec-Fetch-Dest": "empty"
            , "Sec-Fetch-Mode": "cors"
            , "Sec-Fetch-Site": "same-origin"
        }

        # Таблица с логами загрузок
        self.schema_in = 's_grnplm_ld_blago_ubhq_in'
        self.logs_spod_loading = 'logs_spod_loading'
        # Таблица с логами и промежуточными статусами в части работы всего процесса
        self.logs_spod_process = 'logs_spod_process'
