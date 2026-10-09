import schedule
import time
import os
import pandas as pd
import locale
import logging
from datetime import datetime
from typing import Optional, Any, Callable, Tuple, List
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.sql import text
from sqlalchemy import types
import threading
from concurrent.futures import ThreadPoolExecutor

from connectBD_v2 import Main
 
class CriticalError(Exception):
    pass

class Settings:
    def __init__(self):
        self.path: str = 'resources/objects.xlsx'

        # Logs Setting
        self.logs_path: str = 'logs/'
        self.format: str = '%(asctime)s %(name)s %(levelname)s:%(message)s'
        self.table_name_logs: str = 'logs_pxf_table'

        # Info Setting
        self.info_path: str = 'result/'
        self.SCRIPT_NAME: str = 'SCHEDULE_PXF'
        self.func_name: str = 's_grnplm_ld_blago_ubhq_in.pxf_truncate_and_insert'
        self.DATE_START: str = str(datetime.today()).rpartition('.')[0]


class Logging:
    def __init__(self):
        self.logger = None
        self.lock =threading.Lock()
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

class EngineSetting:
    def __init__(self):
        """Return best connect to BD Oracle"""
        self.connect_name_dict: dict = {
            'S_GRNPLM_LD_BLAGO_UBHQ_IN': 'capgp1',
            'S_GRNPLM_LD_BLAGO_UBHQ_WORK': 'capgp1',
            'S_GRNPLM_LD_BLAGO_UBHQ_EXT': 'capgp1'
        }

    def return_connect_name(self, active_schema: str):
        try:
            return self.connect_name_dict[active_schema.upper()]
        except Exception:
            return ''

    def return_best_engine(self, active_schema: str):
        connect_name: str = self.return_connect_name(active_schema=active_schema)
        engine = Main().use_new_engine(connect_name=connect_name, schema=active_schema.upper())
        return engine


class GreenplumPXF:
    def __init__(self, table_name, days, hour, minute):
        self.engine_setting: EngineSetting = EngineSetting()
        self.logger_setting: Logging = Logging()
        self.setting: Settings = Settings()
        self.table_name = table_name
        self.days = days
        self.hour = hour
        self.minute = minute
        self.executor = ThreadPoolExecutor(max_workers=3)
    
    @staticmethod
    def date_now():
        return str(datetime.today()).rpartition('.')[0]

    @staticmethod
    def execute_in_gp(engine: Engine, query: str):
        with engine.connect() as conn:
            conn.execute(text(query).execution_options(autocommit=True))

    @staticmethod
    def query_truncate_table(table_name: str) -> str:
        return f"TRUNCATE TABLE s_grnplm_ld_blago_ubhq_in.{table_name.lower()}"

    @staticmethod
    def query_insert_table(table_name: str, new_table_name: str):
        start_query: str = f"INSERT INTO s_grnplm_ld_blago_ubhq_in.{new_table_name.lower()} \n"
        end_query: str = f"SELECT * FROM s_grnplm_ld_blago_ubhq_ext.{table_name.lower()}"
        return f"{start_query}{end_query}"  

    def query_func_procedure(self, table_name: str):
        query_func: str = f"select {self.setting.func_name}('{table_name}')"
        return query_func

    def create_with_execute(self, query: str, engine: Engine, logger: Any):
        try:
            self.execute_in_gp(engine=engine, query=query)
        except Exception as e:
            logger.exception(e)
            raise CriticalError from e

    @staticmethod
    def convert_to_best_dtype(dataframe):
        for column in dataframe.columns[dataframe.dtypes == 'datetime64[ns]']:
            dataframe[column] = pd.to_datetime(dataframe[column])
            dataframe[column] = dataframe[column].dt.date.apply(lambda x: str(x))
            dataframe[column] = dataframe[column].replace('NaT', np.nan)

        dtyp = {c: types.VARCHAR(500) for c in
                     dataframe.columns[dataframe.dtypes == 'object'].tolist()}
        return dataframe, dtyp
 

    def insert_into_log_table(self, table_name: str, status: str, logs_text: str, date_start: str, date_end: str, engine, logger):
        try:
            dataframe = pd.DataFrame(columns=['table_name', 'status', 'logs_text', 'date_start', 'date_end'])
            dataframe.loc[0, 'table_name'] = table_name
            dataframe.loc[0, 'status'] = status
            dataframe.loc[0, 'logs_text'] = logs_text
            dataframe.loc[0, 'date_start'] = date_start
            dataframe.loc[0, 'date_end'] = date_end

            dataframe, dtyp = self.convert_to_best_dtype(dataframe)

            dataframe.to_sql(name=self.setting.table_name_logs,
                             dtype=dtyp,
                             con=engine,
                             if_exists="append",
                             index=False,
                             method="multi")
        except Exception as e:
            logger.exception(e)
            pass

    def run_insert(self, table_name: str, logger, engine_gp_in, date_start):
        try:
             # Init for Logs
            #logger = self.logger_setting.basic_configuration(table_name=f"{table_name}")

            #engine_gp_in: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_IN')

            new_table_name: str = f"smd_{table_name}"
            #date_start = self.date_now()
            """
            # Truncate table
            truncate_query: str = self.query_truncate_table(table_name=new_table_name)

            #self.create_with_execute(engine=engine_gp_in, query=truncate_query, logger=logger)
            self.execute_in_gp(engine=engine_gp_in, query=truncate_query)

            # Insert table 
            query_insert: str = self.query_insert_table(table_name=table_name, new_table_name=new_table_name)
            """

            # Truncate and Insert table
            query_insert: str = self.query_func_procedure(table_name=table_name)

            print(f"Перегрузка таблицы {table_name} запущена || {date_start}")
            logger.info(f"[{table_name}][INSERT TABLE START]")

            self.execute_in_gp(engine=engine_gp_in, query=query_insert)
            date_end = self.date_now()
            print(f"Перегрузка таблицы {table_name} выполнена || {date_end}")
            logger.info(f"[{table_name}][INSERT TABLE DONE]")

            # Safe logs in base
            self.insert_into_log_table(table_name=table_name, 
                                       status='DONE',
                                       logs_text='DONE',
                                       date_start=date_start, 
                                       date_end=date_end, 
                                       engine=engine_gp_in,
                                       logger=logger)

        except Exception as e:
            logger.info(f"[{query_insert}][INSERT TABLE ERROR]")
            logger.exception(e)
            date_end = self.date_now()
            print(f"Перегрузка таблицы {query_insert} - Ошибка || {date_end}")
            # Safe logs in base
            self.insert_into_log_table(table_name=table_name, 
                                       status='FAILED',
                                       logs_text = str(e),
                                       date_start=date_start, 
                                       date_end=date_end, 
                                       engine=engine_gp_in,
                                       logger=logger)
            pass
    
    def execute_insert(self, query_insert: str):
        try:
             # Init for Logs
            logger = self.logger_setting.basic_configuration(table_name=f"{query_insert}")
            engine_gp_in: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_IN')
            date_start = self.date_now()
            self.executor.submit(self.run_insert, query_insert, logger, engine_gp_in, date_start)
        except Exception as e:
            logger.info(f"[{query_insert}][INSERT TABLE ERROR]")
            logger.exception(e)
            date_end = self.date_now()
            print(f"Перегрузка таблицы {query_insert} - Ошибка || {date_end}")
            # Safe logs in base
            self.insert_into_log_table(table_name=query_insert, 
                                       status='FAILED',
                                       logs_text = str(e), 
                                       date_start=date_start, 
                                       date_end=date_end, 
                                       engine=engine_gp_in,
                                       logger=logger)
            pass
 
class Scheduler:
    def __init__(self):
        self.setting: Settings = Settings()
        self.jobs =[]
        self.last_mtime = os.path.getmtime(self.setting.path) # сохранить время последнего изменения файла
        
    def clear_all_jobs(self):
        del schedule.default_scheduler.jobs[:]

    def load_jobs_from_excel(self):
        self.jobs.clear()
        df = pd.read_excel(self.setting.path, sheet_name='PXF', engine='openpyxl', converters={'HOUR':str, 'MINUTE':str})
        df = df[df['TABLE_NAME'].apply(lambda x: pd.isnull(x) != True)]
        for _, row in df.iterrows():
            table_name = str(row['TABLE_NAME']).upper()
            hour = str(row['HOUR']).zfill(2)
            minute = str(row['MINUTE']).zfill(2)

            if row['EVERY_DAY'] == 'YES':
                days: list = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
            else:
                days: list = [day for day in ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'] if row[day] == 'YES']
            self.jobs.append(GreenplumPXF(table_name, days, hour, minute))
    
 
    def schedule_jobs(self):
            try:
                schedule.clear()
            except Exception as e:
                logger.exception(e)
            for job in self.jobs:
                try:
                    job_time = f"{job.hour}:{job.minute}"
                    for day in job.days:
                        if day.lower() == 'monday':
                            schedule.every().monday.at(job_time).do(job.execute_insert, job.table_name.upper())
                        elif day.lower() == 'tuesday':
                            schedule.every().tuesday.at(job_time).do(job.execute_insert, job.table_name.upper())
                        elif day.lower() == 'wednesday':
                            schedule.every().wednesday.at(job_time).do(job.execute_insert, job.table_name.upper())
                        elif day.lower() == 'thursday':
                            schedule.every().thursday.at(job_time).do(job.execute_insert, job.table_name.upper())
                        elif day.lower() == 'friday':
                            schedule.every().friday.at(job_time).do(job.execute_insert, job.table_name.upper())
                        elif day.lower() == 'saturday':
                            schedule.every().saturday.at(job_time).do(job.execute_insert, job.table_name.upper())
                        elif day.lower() == 'sunday':
                            schedule.every().sunday.at(job_time).do(job.execute_insert, job.table_name.upper())
                except Exception as e:
                    print(f"Перегрузка таблицы {job.table_name.upper()} - Ошибка || {self.date_now()}")
                    pass

    def watch_excel_file(self):
        while True:
            try:
                new_mtime = os.path.getmtime(self.setting.path)
                if new_mtime != self.last_mtime: # если время изменения файла изменилось
                    print("Excel file has been updated. Reloading jobs...")
                    self.clear_all_jobs()
                    self.load_jobs_from_excel()
                    self.schedule_jobs()
                    self.last_mtime = new_mtime
    
                time.sleep(1) # проверять каждую секунду (можно установить другой интервал)
            except Exception as e:
                pass



    def run(self):
        print(f"START SCRIPT- {self.setting.SCRIPT_NAME}")
        self.load_jobs_from_excel()
        self.schedule_jobs()
        
        # Watch edits file
        watcher_thread = threading.Thread(target=self.watch_excel_file)
        watcher_thread.start()

        while True:
            schedule.run_pending()
            time.sleep(1)
 
if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.run()
