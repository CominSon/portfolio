import os


class CriticalError(Exception):
    pass


class SeleniumSettings:
    def __init__(self):
        self.base_path = os.path.dirname(__file__)
        self.START_URL = os.getenv("START_URL")
        self.HEADLESS = True


class Path:
    def __init__(self):
        self.BLOCK_NAME = 'logs_pdf'
        self.PDF_TEMP_FOLDER = os.path.abspath('result/temp_pdf')
        self.PDF_FINAL_FOLDER = os.path.abspath('result/final_pdf')
