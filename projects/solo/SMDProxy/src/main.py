from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any, Callable, Tuple, List
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.sql import text
from datetime import datetime
import pandas as pd
import locale
import logging
import re
from sqlalchemy.exc import DataError

# from connectBD import use_new_engine
from connectBD_v2 import Main


class CriticalError(Exception):
    pass


class Settings:
    def __init__(self):
        self.path: str = 'resources/objects.xlsx'
        self.SCHEMA: str = 'SCHEMA'
        self.TABLE_NAME: str = 'TABLE_NAME'
        self.SYSTEM_NAME: str = 'SYSTEM_NAME'
        self.COLUMN_NAME: str = 'COLUMN_NAME'
        self.TYPE_COLUMN: str = 'TYPE_COLUMN'

        # Type
        self.PXF: str = 'PXF'
        self.PROXY: str = 'PROXY'
        self.PROXY_V2: str = 'PROXY_V2'

        # Thread Setting
        self.THREAD_3 = 3
        self.THREAD_10 = 10

        # Logs Setting
        self.logs_path: str = 'logs/'
        self.format: str = '%(asctime)s %(name)s %(levelname)s:%(message)s'

        # Info Setting
        self.info_path: str = 'result/'
        self.SCRIPT_NAME: str = 'SMD_PROXY'
        self.DATE_NOW: str = str(datetime.today()).rpartition('.')[0]

    @staticmethod
    def read_excel(path: Optional[str], sheet_name: str) -> pd.DataFrame:
        return pd.read_excel(path, sheet_name=sheet_name, engine='openpyxl')
        # return pd.read_excel(path, sheetname=sheet_name)  # Это для python 3.6.3

    @staticmethod
    def good_login(login):
        new_log: str = str(login)
        if len(new_log) < 8:
            return f"0{new_log}"
        else:
            return new_log

    def grant_list(self):
        df_list = self.read_excel(path=self.path, sheet_name='GRANT_USER')
        df_list['USERS'] = df_list['USERS'].apply(self.good_login)
        df_list = df_list['USERS'].tolist()
        return df_list


class Logging:
    def __init__(self):
        self.logger = None
        self.setting: Settings = Settings()

    '''
    def basic_configuration(self, table_name: str):
        logging.basicConfig(level=logging.INFO,
                            format=self.setting.format,
                            filename=f"{self.setting.logs_path}{table_name}.log",
                            filemode='w')
        if locale.getpreferredencoding().upper() != 'UTF-8':
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        return logging.getLogger(table_name)
    '''

    def basic_configuration(self, table_name: str):
        logger = logging.getLogger(table_name)
        logger.setLevel(logging.INFO)

        file_handler = logging.FileHandler(f"{self.setting.logs_path}{table_name}.log", mode='w')
        file_handler.setFormatter(logging.Formatter(self.setting.format))

        logger.addHandler(file_handler)

        if locale.getpreferredencoding().upper() != 'UTF-8':
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

        return logger


class SaveInfo:
    def __init__(self):
        self.settings: Settings = Settings()

    @staticmethod
    def save_in_file(open_path: str, type_name: str, text_f: str):
        with open(f"{open_path}{type_name}.txt", 'a') as f:
            print(f"{text_f}", file=f)

    def save_info_in_file_good(self, type_name: str, table_name: str, error_list: list, new_name: str = None):
        status: int = 0
        for error in error_list:
            if table_name.upper() in error.upper():
                status: int = 1
        date_now: str = self.settings.DATE_NOW
        if type_name == self.settings.PROXY:
            if status == 0:
                text_f: str = f"[{self.settings.PROXY}  | {new_name} | {table_name} - DONE][{date_now}]"
                print(f"Успешно PROXY- {new_name}")
            else:
                text_f: str = f"[{self.settings.PROXY}  | {new_name} | {table_name} - FAILED][{date_now}]"
                print(f"Ошибка PROXY- {new_name}")
            self.save_in_file(open_path=self.settings.info_path, type_name=type_name, text_f=text_f)

        elif type_name == self.settings.PXF:
            if status == 0:
                text_f: str = f"[{self.settings.PXF}  | {table_name} - DONE][{date_now}]"
                print(f"Успешно PXF- {table_name}")
            else:
                text_f: str = f"[{self.settings.PXF}  | {table_name} - FAILED][{date_now}]"
                print(f"Ошибка PXF- {table_name}")
            self.save_in_file(open_path=self.settings.info_path, type_name=type_name, text_f=text_f)


class EngineSetting:
    def __init__(self):
        """Return best connect to BD Oracle"""
        self.connect_name_dict: dict = {
            'UBHQ_USR_DM': 'dm',
            'UBHQ_USR_SRC_K2': 'src_k2',
            'UBHQ_USR_SRC': 'src',
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


class Pool:
    def __init__(self):
        pass

    '''
    @staticmethod
    def thread_pool_executor(func: Callable[..., Any],
                             args_list: List[Tuple],
                             max_threads: int):
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [executor.submit(func, *args) for args in args_list]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(e)
    '''

    @staticmethod
    def thread_pool_executor_for_all(func: Callable[..., Any],
                                     args_list: List[Tuple],
                                     dataframe,
                                     max_threads: int):
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            executor.map(func, args_list, dataframe)

    @staticmethod
    def thread_pool_executor(func: Any,
                             tables: list,
                             dataframe,
                             max_threads: int):
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for table_name in tables:
                executor.submit(func, table_name, dataframe)


class CreatePXF:
    def __init__(self):
        self.settings: Settings = Settings()
        self.engine_setting: EngineSetting = EngineSetting()
        self.logger_setting: Logging = Logging()
        self.save_info: SaveInfo = SaveInfo()
        self.error_list: list = []

    def open_file(self):
        # Open Excel-file
        dataframe: pd.DataFrame = self.settings.read_excel(path=self.settings.path, sheet_name=self.settings.PXF)
        return dataframe

    def return_args_for_pool(self, dataframe: pd.DataFrame) -> list:
        args_list: list = [table_name for table_name in dataframe[self.settings.TABLE_NAME].drop_duplicates()]
        return args_list

    @staticmethod
    def drop_external_table(table_name: str) -> str:
        return f"DROP EXTERNAL TABLE s_grnplm_ld_blago_ubhq_ext.{table_name.lower()}"

    @staticmethod
    def execute_in_gp(engine: Engine, query: str):
        with engine.connect() as conn:
            conn.execute(text(query).execution_options(autocommit=True))

    def create_with_execute(self, query: str, engine: Engine, logger: Any, method: int = 0):
        try:
            self.execute_in_gp(engine=engine, query=query)
        except Exception as e:
            if method == 0:
                logger.exception(e)
                self.status_for_info = 1
                self.error_list.append(str(e))
                raise CriticalError from e
            else:
                print(e)
                pass

    @staticmethod
    def seach_error(error_message: str, ddl_query: str, table_name: str):
        match = re.search(r"For field (\w+) schema requires type \w+ but input record has type (\w+)", error_message)
        if match:
            field_name = match.group(1)
            new_type = match.group(2)

            # Поиск и замена типа в DDL
            # ddl_query_new = re.sub(r'(?i)('+re.escape(field_name)+r'\s+\w+)', r'\1 {}'.format(new_type), ddl_query)
            ddl_query_new = re.sub(r'(?i)(' + re.escape(field_name) + r'\s+)\w+', r'\1{}'.format(new_type), ddl_query)
            print("[{1}] Обнаружена ошибка в поле '{0}'. Попробую исправить и повторить запрос...".format(field_name,
                                                                                                          table_name))
        else:
            print("[{0}] Неизвестная ошибка. Завершаю выполнение запроса.".format(table_name))

        return ddl_query_new

    def execute_with_retry(self, table_name, engine_gp_ext, engine_gp_in, ddl_query_ext, ddl_query_in, logger,
                           retries: int = 300):
        fix_t: int = 0
        try:
            ddl_query_new = ddl_query_ext
            while retries:
                try:
                    self.execute_in_gp(engine=engine_gp_in, query=ddl_query_in)
                    break
                except DataError as e:
                    error_message = str(e)

                    # Seach error and return ddl
                    ddl_query_new = self.seach_error(error_message=error_message, ddl_query=ddl_query_new,
                                                     table_name=table_name)

                    # Try create external
                    self.create_with_execute_v2(query=ddl_query_new, engine=engine_gp_ext,
                                                table_name=table_name, logger=logger, method=1)
                    continue
                '''
                except Exception as e:
                    if "HTTP status code is 500 but" in str(e) and fix_t < 10:
                        print(ddl_query_new)
                        fix_t =+ 1
                        print(fix_t)
                        continue
                    else:
                        logger.exception(e)
                        self.status_for_info = 1
                        self.error_list.append(str(e))
                        raise CriticalError from e
                '''

        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def create_with_execute_v2(self, query: str, engine: Engine, table_name: str, logger: Any,
                               new_table_name: str = None, method: int = 0):
        try:
            self.execute_in_gp(engine=engine, query=query)
        except ProgrammingError as e:
            if method == 1:
                drop_query: str = self.drop_external_table(table_name=table_name)
                print(drop_query)
                self.create_with_execute(query=drop_query, engine=engine, logger=logger, method=1)
                logger.info(f"[{table_name}][CREATE EXTERNAL TABLE - DOUBLE]")
                self.create_with_execute(query=query, engine=engine, logger=logger)
                pass
            elif method == 2:
                query_insert: str = self.query_insert_table(table_name=table_name, new_table_name=new_table_name)
                self.create_with_execute(engine=engine, query=query_insert, logger=logger)
                logger.info(f"[{table_name}][INSERT TABLE - DONE]")
                pass
            else:
                logger.exception(e)
                self.status_for_info = 1
                self.error_list.append(str(e))
                raise CriticalError from e
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    @staticmethod
    def replace_string(text_: str, old_str: str, new_str: str) -> str:
        return text_.upper().replace(old_str, new_str)

    def convert_types_column(self, type_: str) -> str:
        dict_best_type: dict = {'STRING': 'TEXT ',
                                'DECIMAL': 'NUMERIC'}
        for type_old in dict_best_type:
            type_new = dict_best_type[type_old]
            type_ = self.replace_string(type_, type_old, type_new)
        return type_

    def return_standart_dict(self, dataframe: pd.DataFrame, col1: str, col2: str, logger: Any) -> dict:
        try:
            return dict(zip(dataframe[col1], dataframe[col2]))
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def return_column_dict(self, dataframe: pd.DataFrame, col1: str, col2: str, col3: str, logger: Any):
        try:
            dict_: dict = {}
            for _, row in dataframe.iterrows():
                if row[col1] not in dict_:
                    dict_[row[col1]] = []
                dict_[row[col1]].append(f"{row[col2]} {row[col3]}")
            return dict_
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    @staticmethod
    def return_start_query(table_name: str) -> str:
        return f"CREATE EXTERNAL TABLE s_grnplm_ld_blago_ubhq_ext.{table_name.lower()} ( \n"

    def return_middle_query(self, table_name: str, dict_: dict, logger: Any) -> str:
        try:
            if table_name.upper() in dict_:
                column_types: list = dict_[table_name.upper()]
                query: str = ', \n'.join([f"{col}" for col in column_types])
            else:
                query: str = ''
            return query
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def return_location_query(self, table_name: str, dict1: dict, dict2: dict, logger: Any) -> str:
        try:
            start_: str = ") \nLOCATION ('pxf://prx_"
            end_: str = "?PROFILE=hive&SERVER=cp_arnsdpsmd2_blago_ub')"
            schema_name: str = ''
            system_name: str = ''
            if table_name.upper() in dict1:
                schema_name: str = dict1[table_name.upper()]
            if table_name.upper() in dict2:
                system_name: str = dict2[table_name.upper()]
            return f"{start_}{system_name}_{schema_name}.{table_name}{end_}"
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    @staticmethod
    def return_ending_query():
        return """ ON ALL \nFORMAT 'CUSTOM' ( FORMATTER='pxfwritable_import' ) \nENCODING 'UTF8'"""

    def return_query(self, dataframe: pd.DataFrame, table_name: str, logger: Any):
        try:
            dataframe = dataframe[dataframe[self.settings.TABLE_NAME] == table_name].drop_duplicates()

            # Step 1: Return best type_column
            dataframe[self.settings.TYPE_COLUMN] = dataframe[self.settings.TYPE_COLUMN].apply(self.convert_types_column)

            # Step 2: Create all dict
            schema_dict: dict = self.return_standart_dict(dataframe=dataframe,
                                                          col1=self.settings.TABLE_NAME,
                                                          col2=self.settings.SCHEMA,
                                                          logger=logger)
            system_name_dict: dict = self.return_standart_dict(dataframe=dataframe,
                                                               col1=self.settings.TABLE_NAME,
                                                               col2=self.settings.SYSTEM_NAME,
                                                               logger=logger)
            column_dict: dict = self.return_column_dict(dataframe=dataframe,
                                                        col1=self.settings.TABLE_NAME,
                                                        col2=self.settings.COLUMN_NAME,
                                                        col3=self.settings.TYPE_COLUMN,
                                                        logger=logger)

            # Step 3: Create Start query
            start_query: str = self.return_start_query(table_name=table_name)

            # Step 4: Create Middle query
            middle_query: str = self.return_middle_query(table_name=table_name, dict_=column_dict, logger=logger)

            # Step 5: Create Location query
            loc_query: str = self.return_location_query(table_name=table_name, dict1=schema_dict,
                                                        dict2=system_name_dict, logger=logger)

            # Step 6: Create Ending for query
            end_query: str = self.return_ending_query()

            # Step 7: Create Full query
            full_query: str = f"{start_query}\n{middle_query}\n{loc_query}\n{end_query}"
            return full_query
        except CriticalError as e:
            logger.exception(e)
            # Step --: Safe Info
            self.save_info.save_info_in_file_good(type_name=self.settings.PXF,
                                                  table_name=table_name,
                                                  error_list=self.error_list)

    @staticmethod
    def query_create_copy_table(table_name: str, new_table_name: str):
        start_query: str = f"CREATE TABLE s_grnplm_ld_blago_ubhq_in.{new_table_name.lower()} as \n"
        end_query: str = f"SELECT * FROM s_grnplm_ld_blago_ubhq_ext.{table_name.lower()}"
        return f"{start_query}{end_query}"

    @staticmethod
    def query_drop_table(table_name: str) -> str:
        return f"DROP TABLE s_grnplm_ld_blago_ubhq_in.{table_name.lower()}"

    @staticmethod
    def query_truncate_table(table_name: str) -> str:
        return f"TRUNCATE TABLE s_grnplm_ld_blago_ubhq_in.{table_name.lower()}"

    @staticmethod
    def query_insert_table(table_name: str, new_table_name: str):
        start_query: str = f"INSERT INTO s_grnplm_ld_blago_ubhq_in.{new_table_name.lower()} \n"
        end_query: str = f"SELECT * FROM s_grnplm_ld_blago_ubhq_ext.{table_name.lower()}"
        return f"{start_query}{end_query}"

    def grant_to_select(self, table_name: str, engine: Engine, logger: Any):
        try:
            query: str = f"GRANT SELECT ON TABLE S_GRNPLM_LD_BLAGO_UBHQ_IN.{table_name} TO"
            users = self.settings.grant_list()
            for user in users:
                try:
                    self.execute_in_gp(engine=engine, query=f"{query} \"{user}\"")
                except Exception as e:
                    logger.exception(e)
                    # self.error_list.append(str(e))
                    pass
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def create_pxf(self, table_name: str, dataframe: pd.DataFrame):
        try:
            # Init for Logs
            logger = self.logger_setting.basic_configuration(table_name=f"{self.settings.PXF}__{table_name.upper()}")
            self.status_for_info: int = 0

            print(f"Старт PXF- {table_name}")
            logger.info(f"[{table_name}][CREATE PXF_TABLE - START]")

            # Open Engines
            engine_gp_ext: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_EXT')
            engine_gp_in: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_IN')

            # Step 1: Return query external table
            logger.info(f"[{table_name}][RETURN QUERY - START]")
            query: str = self.return_query(dataframe=dataframe, table_name=table_name, logger=logger)
            logger.info(f"[{table_name}][RETURN QUERY - DONE]")

            # Step 2: Create External Table
            logger.info(f"[{table_name}][CREATE EXTERNAL TABLE - START]")
            self.create_with_execute_v2(query=query, engine=engine_gp_ext,
                                        table_name=table_name, logger=logger, method=1)
            logger.info(f"[{table_name}][CREATE EXTERNAL TABLE - DONE]")

            # Step 3.1: Truncate or drop table
            new_table_name: str = f"smd_{table_name}"
            logger.info(f"[{table_name}][CREATE COPY OR INSERT TABLE - START]")

            # truncate_query: str = self.query_truncate_table(table_name=new_table_name)
            drop_query: str = self.query_drop_table(table_name=new_table_name)
            # self.create_with_execute(engine=engine_gp_in, query=truncate_query, logger=logger, method=1)
            self.create_with_execute(engine=engine_gp_in, query=drop_query, logger=logger, method=1)

            # Step 3.2: Create or Insert table
            query_copy: str = self.query_create_copy_table(table_name=table_name, new_table_name=new_table_name)
            """
            self.create_with_execute_v2(engine=engine_gp_in, query=query_copy, table_name=table_name, 
                                        new_table_name=new_table_name, logger=logger, method=2)
            """
            self.execute_with_retry(table_name=table_name,
                                    engine_gp_ext=engine_gp_ext,
                                    engine_gp_in=engine_gp_in,
                                    ddl_query_ext=query,
                                    ddl_query_in=query_copy,
                                    logger=logger)

            logger.info(f"[{table_name}][CREATE COPY TABLE - DONE]")

            """
            # Step 4: Grant for all
            logger.info(f"[{table_name}][GRANT TO USERS - START]")
            self.grant_to_select(table_name=new_table_name, engine=engine_gp_in, logger=logger)
            logger.info(f"[{table_name}][GRANT TO USERS - DONE]")
            """

            # Step 5: Safe Info
            self.save_info.save_info_in_file_good(type_name=self.settings.PXF,
                                                  table_name=table_name,
                                                  error_list=self.error_list)
        except CriticalError:
            # Step --: Safe Info
            self.save_info.save_info_in_file_good(type_name=self.settings.PXF,
                                                  table_name=table_name,
                                                  error_list=self.error_list)
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e


class CreatePROXY:
    def __init__(self):
        self.settings: Settings = Settings()
        self.engine_setting: EngineSetting = EngineSetting()
        self.logger_setting: Logging = Logging()
        self.save_info: SaveInfo = SaveInfo()
        self.error_list: list = []

    def open_file(self):
        # Open Excel-file
        dataframe: pd.DataFrame = self.settings.read_excel(path=self.settings.path, sheet_name=self.settings.PROXY)
        return dataframe

    def return_args_for_pool(self, dataframe: pd.DataFrame) -> list:
        args_list: list = [table_name for table_name in dataframe[self.settings.TABLE_NAME].drop_duplicates()]
        return args_list

    def find_good_prx_schema(self, engine: Engine, name_prx_schema: str, logger: Any):
        try:
            query = """select distinct schema_name 
                            from information_schema.schemata
                            where lower(schema_name) like lower(\'%{0}%\')""".format(name_prx_schema)
            df = pd.read_sql(query, engine)
            return df.to_string(index=False, header=None).strip()
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    @staticmethod
    def execute_in_gp(engine: Engine, query: str):
        with engine.connect() as conn:
            conn.execute(text(query).execution_options(autocommit=True))

    @staticmethod
    def create_key(text: str) -> str:
        first = text[len(text) - 4:len(text) - 2]
        next = text[len(text) - 8:len(text) - 6]
        last = text[len(text) - 12:len(text) - 10]
        return f"{first}{next}{last}"

    def return_new_name(self, dataframe: pd.DataFrame, table_name: str):
        try:
            dataframe = dataframe[dataframe[self.settings.TABLE_NAME] == table_name].drop_duplicates()
            schema = dataframe[self.settings.SCHEMA].to_string(index=False).strip()
            new_key_for_name: str = self.create_key(text=schema)
            return f"V_SMD_{new_key_for_name}_{table_name}"
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def return_query(self, dataframe: pd.DataFrame, table_name: str, new_name: str, engine: Engine, logger: Any):
        try:
            dataframe = dataframe[dataframe[self.settings.TABLE_NAME] == table_name].drop_duplicates()
            system_name = dataframe[self.settings.SYSTEM_NAME].to_string(index=False).strip()
            schema = dataframe[self.settings.SCHEMA].to_string(index=False).strip()
            start_query: str = f"CREATE OR REPLACE VIEW {new_name} AS \n SELECT * FROM "
            name_prx_schema_without_key: str = f"prx_{system_name}_{schema[:10]}"
            name_prx_schema_with_key: str = self.find_good_prx_schema(engine=engine,
                                                                      name_prx_schema=name_prx_schema_without_key,
                                                                      logger=logger)
            full_name_table: str = f"{name_prx_schema_with_key}.{table_name}_18764734_view"
            query_full: str = f"{start_query}{full_name_table}"
            return query_full
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def create_view(self, query: str, engine: Engine, logger: Any):
        try:
            self.execute_in_gp(engine=engine, query=query)
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def grant_to_select(self, table_name: str, engine: Engine, logger: Any):
        try:
            query: str = f"GRANT SELECT ON TABLE S_GRNPLM_LD_BLAGO_UBHQ_IN.{table_name} TO"
            users = self.settings.grant_list()
            for user in users:
                try:
                    self.execute_in_gp(engine=engine, query=f"{query} \"{user}\"")
                except Exception as e:
                    logger.exception(e)
                    pass
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def create_proxy(self, table_name: str, dataframe: pd.DataFrame):
        try:
            # Init for Logs
            logger = self.logger_setting.basic_configuration(table_name=f"{self.settings.PROXY}__{table_name.upper()}")
            self.status_for_info: int = 0

            # Step 0 Return new_name for table
            logger.info(f"[{table_name}][RETURN NEW NAME - START]")
            new_name: str = self.return_new_name(dataframe=dataframe, table_name=table_name)
            logger.info(f"[{table_name}][RETURN NEW NAME - DONE]")

            print(f"Старт PROXY- {new_name}")
            logger.info(f"[{table_name}][CREATE_VIEW - START]")
            # Open Engine
            engine_gp_ext: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_EXT')
            engine_gp_in: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_IN')

            # Step 1 Return query view
            logger.info(f"[{table_name}][RETURN QUERY - START]")
            query: str = self.return_query(table_name=table_name, new_name=new_name, dataframe=dataframe,
                                           engine=engine_gp_ext, logger=logger)
            logger.info(f"[{table_name}][RETURN QUERY - DONE]")

            # Step 2 Create view
            logger.info(f"[{table_name}][PROCESS CREATE - START]")
            self.create_view(engine=engine_gp_in, query=query, logger=logger)
            logger.info(f"[{table_name}][PROCESS CREATE - DONE]")

            """
            # Step 3 Grant for all
            logger.info(f"[{table_name}][GRANT TO USERS - START]")
            self.grant_to_select(table_name=new_name, engine=engine_gp_in, logger=logger)
            logger.info(f"[{table_name}][GRANT TO USERS - DONE]")
            """
            # Step 4 Safe Info
            self.save_info.save_info_in_file_good(type_name=self.settings.PROXY,
                                                  table_name=table_name,
                                                  new_name=new_name,
                                                  error_list=self.error_list)
        except CriticalError:
            # Step --: Safe Info
            self.save_info.save_info_in_file_good(type_name=self.settings.PROXY,
                                                  table_name=table_name,
                                                  new_name=new_name,
                                                  error_list=self.error_list)
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e


class CreatePROXY_V2:
    def __init__(self):
        self.settings: Settings = Settings()
        self.engine_setting: EngineSetting = EngineSetting()
        self.logger_setting: Logging = Logging()
        self.save_info: SaveInfo = SaveInfo()
        self.error_list: list = []

    def open_file(self):
        # Open Excel-file
        dataframe: pd.DataFrame = self.settings.read_excel(path=self.settings.path, sheet_name=self.settings.PROXY_V2)
        return dataframe

    def return_args_for_pool(self, dataframe: pd.DataFrame) -> list:
        args_list: list = [table_name for table_name in dataframe[self.settings.TABLE_NAME].drop_duplicates()]
        return args_list

    def find_good_prx_schema(self, engine: Engine, name_prx_schema: str, logger: Any):
        try:
            query = """select distinct schema_name 
                            from information_schema.schemata
                            where lower(schema_name) like lower(\'%{0}%\')""".format(name_prx_schema)
            df = pd.read_sql(query, engine)
            return df.to_string(index=False, header=None).strip()
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    @staticmethod
    def execute_in_gp(engine: Engine, query: str):
        with engine.connect() as conn:
            conn.execute(text(query).execution_options(autocommit=True))

    @staticmethod
    def create_key(text: str) -> str:
        first = text[len(text) - 4:len(text) - 2]
        next = text[len(text) - 8:len(text) - 6]
        last = text[len(text) - 12:len(text) - 10]
        return f"{first}{next}{last}"

    def return_new_name(self, dataframe: pd.DataFrame, table_name: str):
        try:
            dataframe = dataframe[dataframe[self.settings.TABLE_NAME] == table_name].drop_duplicates()
            schema = dataframe[self.settings.SCHEMA].to_string(index=False).strip()
            new_key_for_name: str = self.create_key(text=schema)
            return f"V_SMD_{new_key_for_name}_{table_name}"
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def take_columns_in_external(self, schema_name: str, table_name: str, engine: Engine, logger: Any):
        try:
            query: str = """
                 WITH column_info AS (
                            select
                                column_name,
                                data_type,
                                ordinal_position
                            FROM
                                information_schema.columns
                            WHERE
                                table_schema = lower(\'{0}\')
                                AND table_name = lower(\'{1}\')

                        )
                        SELECT
                            string_agg(column_name || ' ' || trim(replace(data_type, 'without time zone', '')), ', ' order by ordinal_position) AS columns_definition
                        FROM
                            column_info;
                                    """.format(schema_name, table_name)
            df = pd.read_sql(query, engine)
            return df.to_string(index=False, header=None).strip()
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def return_query_procedure(self, func_name:str, new_name: str, name_prx: str, table_name: str, engine: Engine,
                               logger: Any):
        try:
            start_query: str = f"create or replace function {func_name} \n"
            """
            procedure_columns: str = self.take_columns_in_external(schema_name=name_prx,
                                                                   table_name=f"{table_name}_18764734_view",
                                                                   engine=engine,
                                                                   logger=logger)
                                                                   """
            #second_query: str = f"""returns table({procedure_columns}) as $$ \n"""
            full_name_table: str = f"{name_prx}.{table_name}_18764734_view"
            second_query: str = f"""returns setof {full_name_table} as $$ \n"""
            last_query: str = f"begin \n return QUERY \n select * from {full_name_table}; \n end; \n"
            back_query: str = "$$ language plpgsql security definer"

            query_full: str = f"{start_query}{second_query}{last_query}{back_query}"
            return query_full
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def return_query(self, dataframe: pd.DataFrame, table_name: str, new_name: str, engine: Engine, logger: Any):
        try:
            dataframe = dataframe[dataframe[self.settings.TABLE_NAME] == table_name].drop_duplicates()
            system_name = dataframe[self.settings.SYSTEM_NAME].to_string(index=False).strip()
            schema = dataframe[self.settings.SCHEMA].to_string(index=False).strip()

            func_name = str(f"sdf_{new_name}()").lower()

            start_query: str = f"CREATE OR REPLACE VIEW {new_name} AS \n SELECT * FROM "
            name_prx_schema_without_key: str = f"prx_{system_name}_{schema[:10]}"
            name_prx_schema_with_key: str = self.find_good_prx_schema(engine=engine,
                                                                      name_prx_schema=name_prx_schema_without_key,
                                                                      logger=logger)

            query_procedure: str = self.return_query_procedure(func_name=func_name,
                                                               new_name=new_name, name_prx=name_prx_schema_with_key,
                                                               table_name=table_name,
                                                               engine=engine, logger=logger)

            query_full: str = f"{start_query}{func_name}"

            return query_procedure, query_full
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def create_object(self, query: str, engine: Engine, logger: Any):
        try:
            self.execute_in_gp(engine=engine, query=query)
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    def grant_to_select(self, table_name: str, engine: Engine, logger: Any):
        try:
            query: str = f"GRANT SELECT ON TABLE S_GRNPLM_LD_BLAGO_UBHQ_IN.{table_name} TO"
            users = self.settings.grant_list()
            for user in users:
                try:
                    self.execute_in_gp(engine=engine, query=f"{query} \"{user}\"")
                except Exception as e:
                    logger.exception(e)
                    pass
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e

    @staticmethod
    def drop_function(func_name: str) -> str:
        return f"DROP FUNCTION s_grnplm_ld_blago_ubhq_in.{func_name}"

    def create_proxy(self, table_name: str, dataframe: pd.DataFrame):
        try:
            # Init for Logs
            logger = self.logger_setting.basic_configuration(table_name=f"{self.settings.PROXY}__{table_name.upper()}")
            self.status_for_info: int = 0

            # Step 0 Return new_name for table
            logger.info(f"[{table_name}][RETURN NEW NAME - START]")
            new_name: str = self.return_new_name(dataframe=dataframe, table_name=table_name)
            logger.info(f"[{table_name}][RETURN NEW NAME - DONE]")

            print(f"Старт PROXY- {new_name}")
            logger.info(f"[{table_name}][CREATE_VIEW - START]")
            # Open Engine
            engine_gp_ext: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_EXT')
            engine_gp_in: Engine = self.engine_setting.return_best_engine(active_schema='S_GRNPLM_LD_BLAGO_UBHQ_IN')

            # Step 1 Return query view and procedure
            logger.info(f"[{table_name}][RETURN QUERY - START]")
            query_procedure, query_full = self.return_query(table_name=table_name, new_name=new_name,
                                                            dataframe=dataframe, engine=engine_gp_ext, logger=logger)
            print(query_procedure)
            logger.info(f"[{table_name}][RETURN QUERY - DONE]")

            # Step 2 Try drop procedure
            logger.info(f"[{table_name}][TRY DROP FUNC - START]")
            drop_query: str = self.drop_function(func_name=f"sdf_{new_name}()")

            # Step 3 Create procedure
            CreatePXF().create_with_execute(engine=engine_gp_in, query=drop_query, logger=logger, method=1)
            logger.info(f"[{table_name}][TRY DROP FUNC - DONE]")

            logger.info(f"[{table_name}][PROCESS CREATE PROCEDURE - START]")
            self.create_object(engine=engine_gp_in, query=query_procedure, logger=logger)
            logger.info(f"[{table_name}][PROCESS CREATE PROCEDURE - DONE]")

            # Step 4 Create view
            logger.info(f"[{table_name}][PROCESS CREATE VIEW- START]")
            self.create_object(engine=engine_gp_in, query=query_full, logger=logger)
            logger.info(f"[{table_name}][PROCESS CREATE VIEW - DONE]")

            """
            # Step 3 Grant for all
            logger.info(f"[{table_name}][GRANT TO USERS - START]")
            self.grant_to_select(table_name=new_name, engine=engine_gp_in, logger=logger)
            logger.info(f"[{table_name}][GRANT TO USERS - DONE]")
            """
            # Step 4 Safe Info
            self.save_info.save_info_in_file_good(type_name=self.settings.PROXY,
                                                  table_name=table_name,
                                                  new_name=new_name,
                                                  error_list=self.error_list)
        except CriticalError:
            # Step --: Safe Info
            self.save_info.save_info_in_file_good(type_name=self.settings.PROXY,
                                                  table_name=table_name,
                                                  new_name=new_name,
                                                  error_list=self.error_list)
        except Exception as e:
            logger.exception(e)
            self.status_for_info = 1
            self.error_list.append(str(e))
            raise CriticalError from e


class Start:
    def __init__(self):
        self.settings: Settings = Settings()
        self.proxy: CreatePROXY = CreatePROXY()
        self.pxf: CreatePXF = CreatePXF()
        self.proxy_v2: CreatePROXY_V2 = CreatePROXY_V2()
        self.pool: Pool = Pool()

    def start(self):
        print("Выберите PXF или PROXY или PROXY_V2")
        choose: str = input()
        print("Скрипт запущен")
        if choose == self.settings.PROXY:
            # Open xlsx-файл
            dataframe: pd.DataFrame = self.proxy.open_file()

            # Create args_list
            args_list: list = self.proxy.return_args_for_pool(dataframe=dataframe)

            # Start in pool
            self.pool.thread_pool_executor(func=self.proxy.create_proxy,
                                           tables=args_list,
                                           dataframe=dataframe,
                                           max_threads=self.settings.THREAD_10)
        elif choose == self.settings.PROXY_V2:
            # Open xlsx-файл
            dataframe: pd.DataFrame = self.proxy_v2.open_file()

            # Create args_list
            args_list: list = self.proxy_v2.return_args_for_pool(dataframe=dataframe)

            # Start in pool
            self.pool.thread_pool_executor(func=self.proxy_v2.create_proxy,
                                           tables=args_list,
                                           dataframe=dataframe,
                                           max_threads=self.settings.THREAD_3)
        elif choose == self.settings.PXF:
            # Open xlsx-файл
            dataframe: pd.DataFrame = self.pxf.open_file()

            # Create args_list
            args_list: list = self.pxf.return_args_for_pool(dataframe=dataframe)

            # Start in pool
            self.pool.thread_pool_executor(func=self.pxf.create_pxf,
                                           tables=args_list,
                                           dataframe=dataframe,
                                           max_threads=self.settings.THREAD_3)


if __name__ == '__main__':
    start: Start = Start()
    start.start()
