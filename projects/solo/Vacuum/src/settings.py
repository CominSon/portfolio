import logging
import threading
import locale

class Settings:
    def __init__(self):

        # Logs Setting
        self.logs_path: str = 'logs/'
        self.format: str = '%(asctime)s %(name)s %(levelname)s:%(message)s'
        #self.table_name_logs: str = 'logs_vacuum_result'

        # Список схем для обработки
        self.SCHEMAS = ['s_grnplm_ld_blago_ubhq_2prod', 
                        's_grnplm_ld_blago_ubhq_ext', 
                        's_grnplm_ld_blago_ubhq_in', 
                        's_grnplm_ld_blago_ubhq_work'
                        ]



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
