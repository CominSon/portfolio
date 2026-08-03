import datetime
import json
import locale
import os
import shutil
import tempfile
import threading
import time
from typing import Any
import logging
from requests import Session, Response
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver import DesiredCapabilities, FirefoxProfile
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.webdriver import WebDriver

from settings import SeleniumSettings, UsersInfo, LoggingSetting


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


class Main:
    def __init__(self):
        self.logger_setting: Logging = Logging()
        self.selenium_settings: SeleniumSettings = SeleniumSettings()
        self.user_info: UsersInfo = UsersInfo()
        self.desired_capabilities: Any = DesiredCapabilities().FIREFOX
        # self.profile_browser: FirefoxProfile = webdriver.FirefoxProfile()
        self.options: Options = webdriver.FirefoxOptions()
        self.browser_actual: Any = None
        self.fist_start = True

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
                time.sleep(3)
                continue

    def do_anything_by_xpath_with_stop(self, xpath: str, browser: WebDriver) -> Any:
        timer = 0
        timer_stop = False
        while range(12):
            try:
                time.sleep(4)
                return browser.find_element_by_xpath(xpath)
            except (NoSuchElementException, ElementClickInterceptedException) as e:
                if timer > 5:
                    if not self.fist_start:
                        if not timer_stop:
                            time.sleep(600)
                            timer = 0
                        elif timer_stop:
                            raise CriticalError
                        timer_stop = True
                        continue
                    raise CriticalError

                timer += 1
                time.sleep(1)
                browser.get(self.selenium_settings.url_spod)
                time.sleep(3)
                browser.refresh()
                time.sleep(3)
                continue

    def create_profile_for_browser(self):
        my_profile = self.selenium_settings.profile_user
        if not os.path.exists(my_profile):
            os.makedirs(my_profile)
            # Создаем временный профиль
            # my_profile = tempfile.mkdtemp()
            return False, my_profile
        return True, my_profile

    def launching_the_browser(self, logger) -> WebDriver:
        try:
            profile_browser = self.set_preference_to_firefox(profile=webdriver.FirefoxProfile())
            options: Options = self.set_options_to_firefox(options=self.options)
            browser: WebDriver = webdriver.Firefox(desired_capabilities=self.desired_capabilities,
                                                   executable_path=self.selenium_settings.chromedriver,
                                                   options=options,
                                                   service_log_path=self.selenium_settings.webdriver_log_file,
                                                   firefox_profile=profile_browser)
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на старте браузера]")
            logger.exception(e)
            raise CriticalError from e

        return browser

    def get_url(self, url: str, session: Any, logger):
        try:
            response: Response = session.get(url=url, verify=False)
            return response
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии выполнения запросе типа - GET]")
            logger.exception(e)
            raise CriticalError from e

    def post_url(self, url: str, headers: dict, session: Any, logger):
        try:
            response: Response = session.post(url=url, headers=headers, json={}, verify=False)
            return response
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии выполнения запросе типа - POST]")
            logger.exception(e)
            raise CriticalError from e

    def connect_in_request(self, selenium_cookies: Any, session: Any, logger):
        try:
            logger.info(f"[{self.user_info.username}][Обрабатываем куки пользователя]")
            for cookie in selenium_cookies:
                # session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
                session.cookies.set(cookie['name'], cookie['value'])
            logger.info(f"[{self.user_info.username}][Куки пользователя добавлены в сессию.]")
            return session
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии обработки куков]")
            logger.exception(e)
            raise CriticalError from e

    # Функция для загрузки cookies из файла
    @staticmethod
    def load_cookies(filename: str):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                return json.load(file)
        return {}

    # Функция для загрузки cookies конкретного пользователя

    def get_user_cookies(self, logger):
        all_cookies = self.load_cookies(filename=self.selenium_settings.cookie_file)
        return all_cookies.get(self.user_info.username, [])

    # Функция для сохранения cookies в файл
    @staticmethod
    def save_cookies(username, cookies, filename):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                all_cookies = json.load(file)
        else:
            all_cookies = {}

        all_cookies[username] = cookies

        with open(filename, 'w') as file:
            json.dump(all_cookies, file)

    def run_cookie_with_selenium(self, browser, logger):
        try:
            # browser: WebDriver = self.launching_the_browser(profile_path=profile_path, logger=logger)
            time.sleep(3)
            browser.get(self.selenium_settings.url_spod)
            time.sleep(3)
            browser.refresh()
            time.sleep(3)
            browser.refresh()
            # self.do_anything_by_xpath(xpath='//*[text()=\'Ввод\']', browser=browser).click()
            # time.sleep(3)
            # browser.refresh()
            time.sleep(3)

            # Сохранение cookies в файл (повторно)

            self.save_cookies(self.user_info.username, browser.get_cookies(), self.selenium_settings.cookie_file)

            # browser.quit()
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии поддержания действующей сессии]")
            logger.exception(e)
            print(e)
            try:
                browser.quit()
            except:
                pass
            pass

    def keep_session_alive(self, session, browser, logger):
        try:
            # Шаг 1: Проверяем наличие активных куки
            cookies = self.get_user_cookies(logger=logger)
            logger.info(f"[{self.user_info.username}][Получаем куки из файла]")
            if not cookies:
                print(f"Куки для пользователя {self.user_info.username} не найдены.")
                logger.info(f"[{self.user_info.username}][Куки пользователя не найдены.]")
                return False

            # Шаг 2: Поддержка сессии (через selenium)

            if browser is None:
                print(f"Активного браузера нет.")
                logger.info(f"[{self.user_info.username}][Браузер не найден]")
                return False

            self.run_cookie_with_selenium(browser=browser, logger=logger)

            # Шаг 3: Записываем данные с куки в текущую сессию.
            # session = self.connect_in_request(selenium_cookies=cookies, session=session, logger=logger)

            # Шаг 4: Проверка активности сессии

            # response = self.get_url(url=self.selenium_settings.url_spod, session=session, logger=logger)
            authorized = self.check_done_authorization(browser=browser, logger=logger)

            logger.info(f"[{self.user_info.username}][Переходим к активной странице СПОДа]")

            if not authorized:
                print(f"Сессия пользователя {self.user_info.username} не активна. Требуется повторная авторизация")
                logger.info(
                    f"[{self.user_info.username}][Сессия пользователя не активна. Требуется повторная авторизация]")
                return False

            if authorized:
                print(f"Сессия пользователя {self.user_info.username} поддерживается.")
                logger.info(f"[{self.user_info.username}][Сессия поддерживается]")
                return True
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии проверки активности сессии]")
            logger.exception(e)
            raise CriticalError from e

    def opt_counts(self, browser, logger):
        try:
            otp: str = input('Введите OTP пароль: ')
            logger.info(f"[{self.user_info.username}][Пароль OTP введен]")

            for key, otp_num in enumerate(otp):
                self.do_anything_by_xpath(xpath=f'//*[@data-index-number="{key + 5}"]',
                                          browser=browser).send_keys(otp_num)
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии ввода OTP]")
            logger.exception(e)
            raise CriticalError from e

    def app_and_pin(self, browser, logger):
        """Новый блок, отвечающий за выбор аппаратного токена и ввод пин"""
        try:
            self.do_anything_by_xpath(xpath='//*[@id="login-by-ngam-hwotp-authenticator"]',
                                      browser=browser).click()
            # Шаг 3: Вводим PIN
            pin: str = input('Введите PIN пароль: ')

            time.sleep(3)
            for key, pin_num in enumerate(pin):
                self.do_anything_by_xpath(xpath=f'//*[@data-index-number="{key + 1}"]',
                                          browser=browser).send_keys(pin_num)
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии ввода PIN]")
            logger.exception(e)
            raise CriticalError from e

    def authorization_in_sudir_first(self, browser: WebDriver, logger):
        try:
            time.sleep(4)
            self.do_anything_by_xpath(xpath='//*[@id="username"]', browser=browser).send_keys(self.user_info.username)
            self.do_anything_by_xpath(xpath='//*[@id="password"]', browser=browser).send_keys(self.user_info.password)
            self.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()
            time.sleep(3)
        except Exception as e:
            logger.info(f"[Ошибка на стадии авторизации]")
            logger.exception(e)
            raise CriticalError from e

    def authorization_in_sudir(self, browser: WebDriver, logger):
        try:
            time.sleep(1)
            # self.main.do_anything_by_xpath(xpath='//*[@id="password"]',
            # browser=browser).send_keys(self.user_info.user_code)
            # time.sleep(1)

            # Новое - вводим PIN
            self.app_and_pin(browser=browser, logger=logger)

            # Шаг 3: Вводим OTP
            self.opt_counts(browser=browser, logger=logger)

            self.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()

            browser.get(self.selenium_settings.url_spod)
            time.sleep(3)
        except Exception as e:
            logger.info(f"[Ошибка на стадии авторизации]")
            logger.exception(e)
            raise CriticalError from e

    # Используется только для первого создания профиля
    def create_path_profiles(self, profiles, logger):
        try:
            shutil.copytree(profiles, self.selenium_settings.profile_user)

            logger.info(f"[{self.user_info.username}][Профиль пользователя создан]")
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии создании папки с профилем]")
            logger.exception(e)
            raise CriticalError from e

    def check_done_authorization(self, browser, logger):
        try:
            time.sleep(10)
            # browser.find_element_by_xpath('//*[text()=\'Целевые адреса АС ECM.Lite:\']')
            # browser.find_element_by_xpath('//*[text()=\'Тематические данные УБ GP\']')
            self.do_anything_by_xpath_with_stop(xpath='//*[text()=\'Тематические данные УБ GP\']', browser=browser)

            print("Пароль OTP принят. Авторизация пройдена.")
            logger.info(f"[{self.user_info.username}][Пароль OTP принят. Авторизация пройдена.]")

            # Сохранение cookies в файл
            self.save_cookies(self.user_info.username, browser.get_cookies(), self.selenium_settings.cookie_file)
            logger.info(f"[{self.user_info.username}][Куки авторизации сохранены]")

            # Сохраняем профиль Firefox в нужной папке (только при первом создании профиля)
            # if not prof_status:
            # self.create_path_profiles(profiles=profile_path, logger=logger)
            # browser.quit()

            return True
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Пароль OTP не принят]")
            logger.exception(e)
            logger.info(f"Текущая ссылка: {browser.current_url}")
            self.fist_start = False
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

                    # Шаг 3 #: Авторизация
                    self.authorization_in_sudir(browser=browser, logger=logger)

            # browser.quit()
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии авторизации через OTP]")
            logger.exception(e)
            raise CriticalError from e

    def smd_auth(self, browser, logger):
        try:
            browser.get("https://sm.data.ca.sbrf.ru/home")
            time.sleep(5)
            # self.do_anything_by_xpath(xpath='//*[@id="username"]', browser=browser).send_keys(self.user_info.username)
            browser.find_element_by_xpath('//*[@id="username"]').send_keys(self.user_info.username)
            time.sleep(1)
            # self.do_anything_by_xpath(xpath='//*[@id="password"]', browser=browser).send_keys(self.user_info.password)
            browser.find_element_by_xpath('//*[@id="password"]').send_keys(self.user_info.password)
            time.sleep(1)
            # self.do_anything_by_xpath(xpath='//*[@id="login"]', browser=browser).click()
            browser.find_element_by_xpath('//*[@id="login"]').send_keys(self.user_info.password)
            time.sleep(5)
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии авторизации в СМД]")
            logger.exception(e)
            browser.get(self.selenium_settings.url_spod)
        finally:
            return browser

    def authorization_with_session(self, logger, browser=None):
        try:
            # Шаг 1: Запускаем сессию
            session: Session = Session()
            logger.info(f"[{self.user_info.username}][Новая сессия активна]")

            # Формируем или проверяем профиль
            # prof_status, profile_path = self.create_profile_for_browser()

            # Проверяем наличие действующих куков в системе по активному юзеру

            if not self.keep_session_alive(session=session, browser=browser, logger=logger):

                # Шаг 1: Идем до окна авторизации СУДИР
                if browser is not None:
                    browser.quit()

                browser: WebDriver = self.launching_the_browser(logger=logger)
                time.sleep(3)
                # browser = self.smd_auth(browser=browser, logger=logger)

                browser.get(self.selenium_settings.url_spod)

                # Шаг 3: Пробуем авторизоваться через OTP

                self.otp_sends_and_auth(browser=browser, logger=logger)

            session.close()
            return browser
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка на стадии общей авторизации]")
            logger.exception(e)
            raise CriticalError from e

    def remove_cookies(self, logger):
        try:
            os.remove(self.selenium_settings.cookie_file)
            logger.info(f"[{self.user_info.username}][Файла с куками удален]")
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Файла с куками пока нет]")
            logger.exception(e)

    def work_in(self, logger):
        try:
            print(f"Первая авторизация [{datetime.datetime.now()}]")
            count_stat = 0
            self.remove_cookies(logger=logger)

            # Шаг 1: Запускаем основной цикл
            while True:
                if count_stat == 0:
                    self.browser_actual = self.authorization_with_session(logger=logger)
                elif count_stat == 1:
                    self.browser_actual = self.authorization_with_session(browser=self.browser_actual, logger=logger)
                timers = 600
                minutes = timers / 60
                logger.info(f"[{self.user_info.username}][Следующая проверка через {int(minutes)} минут]")
                print(f"Следующая проверка через {int(minutes)} минут")
                count_stat = 1
                time.sleep(timers)  # Отправка запроса каждые 10 минут
        except Exception as e:
            logger.info(f"[{self.user_info.username}][Ошибка основного запуска]")
            logger.exception(e)

    def main(self):
        logger = self.logger_setting.basic_configuration(table_name=f"{self.user_info.username}_otp_logs")
        logger.info(f"[{self.user_info.username}][START SCRIPT]")
        self.work_in(logger=logger)


if __name__ == '__main__':
    start_script: Main = Main()
    start_script.main()
