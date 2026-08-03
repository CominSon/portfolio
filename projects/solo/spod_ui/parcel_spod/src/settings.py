import getpass
import pathlib

import pandas as pd
from noterball import noterball
from sqlalchemy.engine import Engine
from connectBD import use_new_engine
from datetime import datetime


class Settings:
    def __init__(self):
        # Настройки подключения к БД
        # self.engine_2prod: Engine = use_new_engine('capgp1_2prod')  # Схема СПОДа
        self.engine_work: Engine = use_new_engine('capgp1_work')  # Схема WORK
        # self.engine_in: Engine = use_new_engine('capgp1_in')  # Схема WORK

        # Переменные

        self.logs_spod_func = 's_grnplm_ld_blago_ubhq_in.logs_spod_func'  # Таблица с логами отработанной функции
        self.path_objects = 'resources/objects_spod.xlsx'
        self.func_spod = 's_grnplm_ld_blago_ubhq_in.generate_temp_and_accum_tables'
        self.func_spod_big = 's_grnplm_ld_blago_ubhq_in.generate_temp_and_accum_tables_big'

        # Таблица с логами и промежуточными статусами в части работы всего процесса
        self.logs_spod_process = 's_grnplm_ld_blago_ubhq_in.logs_spod_process'

        # Для классического логирования
        # Logs Setting
        self.logs_path: str = f'{SchedulerSettings().main_path}logs/'
        self.format: str = '%(asctime)s %(name)s %(levelname)s:%(message)s'

        # KKD путь к скрипту
        self.path_for_kkd: str = str(pathlib.Path(f"Z:/Exchange/Maksim/DfProjects/kkd_scripts/kkd_scripts.bat"))


class SeleniumSettings:
    def __init__(self):
        """All Setting for Outlook mailing"""

        # Settings from browser
        # self.browser_path: str = "C:\\Program Files\\Mozilla Firefox\\firefox.exe"
        self.browser_path: str = "Z:\\Exchange\\Maksim\\Mozilla Firefox\\firefox.exe"
        self.basic_path: str = 'Z:/Exchange/Maksim'
        self.chromedriver = str(pathlib.Path(f'{self.basic_path}/Chromdriver/geckodriver.exe'))
        self.webdriver_log_file: str = str(pathlib.Path(f'{self.basic_path}/Auto/geckodriver.log'))
        # self.url_spod: str = "https://sudir004.ca.sbrf.ru/SberDataCorr"
        self.url_spod: str = "https://pvlos-sys000001.omega.sbrf.ru/SberDataCorr/"  # Новая ссылка СПОДа
        self.cookie_file: str = "results/cookies.json"
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
        #self.option_arguments: list = [""]


class UsersInfo:
    @staticmethod
    def read_excel_users(path: str, user: str):
        df = pd.read_excel(path, sheetname='Лист1')
        df = df[df['PPT'].apply(lambda x: x.upper()) == user.upper()]
        tim2 = df['PPZ'][(df['PPX'] == max(df['PPX']))]
        return tim2

    def __init__(self):
        str_path_to_user_info = f"{SeleniumSettings().basic_path}/Python Scripts/Рабочие области/"
        self.path_to_user_info: str = str(pathlib.Path(f"{str_path_to_user_info}working/kkts/pen_is.xlsx"))
        self.username: str = getpass.getuser()
        self.user_code: str = noterball(self.read_excel_users(path=self.path_to_user_info,
                                                              user=self.username))


class SchedulerSettings:
    def __init__(self):
        self.main_path = "Z:/Exchange/Maksim/DfProjects/spod_with_otp/parcel_spod/src/"
        self.path: str = f'{self.main_path}resources/objects_scheduler.xlsx'

        # Logs Setting
        self.logs_path: str = f'{self.main_path}logs/'
        self.format: str = '%(asctime)s %(name)s %(levelname)s:%(message)s'
        self.table_name_logs: str = 'logs_parcel_spod'

        # Info Setting
        self.info_path: str = f'{self.main_path}result/'
        self.SCRIPT_NAME: str = 'SCHEDULE_PARCEL_SPOD'
        self.DATE_START: str = str(datetime.today()).rpartition('.')[0]
