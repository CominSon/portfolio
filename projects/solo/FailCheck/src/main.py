from sqlalchemy.engine import Engine
from typing import Optional, Any, Iterator
import pandas as pd
import os
import time
import glob
import smtplib
import locale
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from sqlalchemy import types
import getpass
from noterball import noterball
import datetime
import numpy as np
import threading
from settings import EngineSetting, Path, SendingsSetting


class Common:
    def __init__(self):
        self.path: Path = Path()
        self.engine_setting: EngineSetting = EngineSetting()

    @staticmethod
    def read_excel(path: Optional[str], sheet_name: str = 'list1') -> pd.DataFrame:
        return pd.read_excel(path, sheet_name=sheet_name, engine='openpyxl')

    @staticmethod
    def read_sql(query: Optional[str], engine: Engine, chunksize: Any = None) -> pd.DataFrame:
        return pd.read_sql(sql=query, con=engine, chunksize=chunksize)

    @staticmethod
    def read_query_in_file_sql(query: Optional[str]) -> str:
        return open(query, 'r').read()

    def connectings(self, schema_name: str, logger):
        try:
            return self.engine_setting.return_best_engine(active_schema=schema_name)
        except Exception as e:
            logger.exception(e)
            print(e)

    def check_in_sql_base(self, query: str,
                          table_name: str,
                          engine,
                          number_query: int,
                          logger,
                          chunksize: Any = None):
        """ Multi Step
                        This method use next methods and var:
                            1) read_query_in_file_sql;
                            2)read_sql
                        :return: dataframe
        """
        try:
            best_query: str = self.read_query_in_file_sql(query).split(';')[number_query].format(table_name)
            return self.read_sql(best_query, engine, chunksize)
        except Exception as e:
            logger.exception(e)
            pass

    @staticmethod
    def execute_in_gp(engine: Engine, query: str):
        with engine.connect() as conn:
            conn.execute(text(query).execution_options(autocommit=True))

    @staticmethod
    def convert_to_best_dtype(dataframe):
        for column in dataframe.columns[dataframe.dtypes == 'datetime64[ns]']:
            dataframe[column] = pd.to_datetime(dataframe[column])
            dataframe[column] = dataframe[column].dt.date.apply(lambda x: str(x))
            dataframe[column] = dataframe[column].replace('NaT', np.nan)

        dtyp = {c: types.VARCHAR(500) for c in
                dataframe.columns[dataframe.dtypes == 'object'].tolist()}
        return dataframe, dtyp


class Logging:
    def __init__(self):
        self.logger = None
        self.lock = threading.Lock()
        self.setting: Path = Path()

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


class SendMail:
    """Use SMTP"""

    def __init__(self):
        self.path: Path = Path()
        self.dataframe_for_outlook: pd.DataFrame = pd.DataFrame()
        self.today: str = str(datetime.datetime.today()).rpartition('.')[0]
        self.sending_settings: SendingsSetting = SendingsSetting()

    @staticmethod
    def create_body_html(html_dataframe, today: str, pxf: int) -> str:
        if pxf == 1:
            text_in_list: str = 'Список таблиц, которые не перегрузились из PXF: '
        elif pxf == 0:
            text_in_list: str = 'Список процедур, которые не отработали: '
        body_html_list: list = ['<html><body>', 'Выгрузка от ',
                                today, '<br>',
                                text_in_list,
                                '<br>', html_dataframe, '<html><body>']
        return ''.join(body_html_list)

    def create_dataframe_to_send(self, pxf: int, dataframe):

        dataframe_mail = pd.DataFrame(columns=self.sending_settings.outlook_columns)
        if pxf == 1:
            dataframe_mail.loc[0, 'script'] = self.sending_settings.pxf_outlook_name
            dataframe_mail.loc[0, 'mail_to'] = self.sending_settings.pxf_outlook_mail_to
            dataframe_mail.loc[0, 'mail_cc'] = self.sending_settings.pxf_outlook_mail_copy
            dataframe_mail.loc[0, 'mail_sub'] = self.sending_settings.pxf_outlook_topic
        elif pxf == 0:
            dataframe_mail.loc[0, 'script'] = self.sending_settings.procedure_outlook_name
            dataframe_mail.loc[0, 'mail_to'] = self.sending_settings.procedure_outlook_mail_to
            dataframe_mail.loc[0, 'mail_cc'] = self.sending_settings.procedure_outlook_mail_copy
            dataframe_mail.loc[0, 'mail_sub'] = self.sending_settings.procedure_outlook_topic

        dataframe_mail.loc[0, 'mail_html'] = self.create_body_html(today=self.today,
                                                                   pxf=pxf,
                                                                   html_dataframe=dataframe.to_html())
        return dataframe_mail

    @staticmethod
    def send_email_smtp(sender, receiver, cc, subject, body, attachments, server):
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

    @staticmethod
    def connect_smtp(server_name, server_port, user_name, password):
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
        return server

    @staticmethod
    def disconnect_smtp(server):
        try:
            server.quit()
        except Exception as e:
            print(f"DISCONNECT_ERROR: \n{e}")
            time.sleep(5)

    def sending(self, dataframe, server, my_mail):
        sender = my_mail
        mail_to = dataframe.loc[0, 'mail_to'].split(';')
        mail_cc = dataframe.loc[0, 'mail_cc'].split(';')
        receiver = str(", ".join(mail_to))
        cc = str(", ".join(mail_cc)) if 'mail_cc' in dataframe.columns else ""
        subject = str(dataframe.loc[0, 'mail_sub']) if 'mail_sub' in dataframe.columns else ""
        body = str(dataframe.loc[0, 'mail_html']) if 'mail_html' in dataframe.columns else ""
        attachments = [
            str(dataframe.loc[0, 'mail_attachment'])] if 'mail_attachment' in dataframe.columns and not pd.isna(
            dataframe.loc[0, 'mail_attachment']) else []
        self.send_email_smtp(sender, receiver, cc, subject, body, attachments, server)
        print('Рассылка сформирована: ' + str(dataframe.loc[0, 'script']) + ' ' +
              str(datetime.datetime.today()).rpartition('.')[0])

    def start_send(self, pxf: int, dataframe, logger):
        try:
            go_to = r'/data/workspace/18764734_omega-sbrf-ru/system_need/pen_is.xlsx'
            data_list = pd.read_excel(go_to, sheet_name='Лист1', engine='openpyxl')
            data_list = data_list[
                data_list['PPT'].apply(lambda x: x.upper()) == getpass.getuser().upper().replace('_OMEGA-SBRF-RU', '')]
            tim2 = data_list['PPZ'][(data_list['PPX'] == max(data_list['PPX']))]

            # my_mail = 'info_shtab_ub@omega.sbrf.ru'
            my_mail = 'MYuPavlenko@omega.sbrf.ru'
            user_name = '18764734'
            password = noterball(tim2)
            server_name = 'Smtp.omega.sbrf.ru'
            server_port = 2525  # 587
            OUTPUT = 0
            dataframe = self.create_dataframe_to_send(pxf=pxf, dataframe=dataframe)
            server = self.connect_smtp(server_name, server_port, user_name, password)
            self.sending(dataframe, server, my_mail)
            self.disconnect_smtp(server)
        except Exception as e:
            logger.exception(e)
            pass


class CheckPXF:
    def __init__(self):
        self.common: Common = Common()
        self.engine_setting: EngineSetting = EngineSetting()
        self.path: Path = Path()
        self.send_mail: SendMail = SendMail()
        self.logger_setting: Logging = Logging()

    def insert_into_backup_pxf(self, dataframe, engine, logger):
        try:
            logger.info("[PXF][Start insert into logs_backup_all_schedule]")
            dataframe = dataframe.rename(columns={'table_name': 'objects_name'})
            dataframe['scripts'] = 'PXF'
            dataframe = dataframe[['scripts', 'objects_name', 'date_start']]
            # dataframe, dtyp = self.convert_to_best_dtype(dataframe)
            dataframe.to_sql(name=self.path.logs_backup_all_schedule,
                             # dtype=dtyp,
                             con=engine,
                             if_exists="append",
                             index=False,
                             method="multi")
            print('Запись в backup прошла успешно...')
            logger.info("[PXF][Finish insert into logs_backup_all_schedule]")
        except Exception as e:
            logger.exception(e)
            pass

    def check_failed(self):
        # Init for Logs
        logger = self.logger_setting.basic_configuration(table_name=f"PXF")

        logger.info("[START][PXF LOGS]")
        # Connect to LD Greenplum
        engine_gp_in: Engine = self.common.connectings(schema_name='S_GRNPLM_LD_BLAGO_UBHQ_IN', logger=logger)

        # Inits
        number_query = 1
        query_logs = self.path.query
        # Read Actual Failed PXF
        logger.info("[PXF][DATAFRAME START]")
        dataframe_pxf = self.common.check_in_sql_base(query=self.path.query,
                                                      table_name=self.path.logs_pxf_table,
                                                      engine=engine_gp_in,
                                                      logger=logger,
                                                      number_query=0)
        logger.info("[PXF][DATAFRAME DONE]")

        # Send Mail
        self.send_mail.start_send(pxf=1, dataframe=dataframe_pxf, logger=logger)
        logger.info("[PXF][MAIL SENDING]")
        # Insert dataframe in backup
        self.insert_into_backup_pxf(dataframe=dataframe_pxf, engine=engine_gp_in, logger=logger)
        logger.info("[DONE][PXF LOGS]")


class CheckPROCEDURE:
    def __init__(self):
        self.common: Common = Common()
        self.engine_setting: EngineSetting = EngineSetting()
        self.path: Path = Path()
        self.send_mail: SendMail = SendMail()
        self.logger_setting: Logging = Logging()

    def insert_into_backup_procedure(self, dataframe, engine, logger):
        try:
            logger.info("[PROCEDURE][Start insert into logs_backup_all_schedule]")
            dataframe = dataframe.rename(columns={'procedure_name': 'objects_name'})
            dataframe['scripts'] = 'PROCEDURE'
            dataframe = dataframe[['scripts', 'objects_name', 'date_start']]
            # dataframe, dtyp = self.convert_to_best_dtype(dataframe)
            dataframe.to_sql(name=self.path.logs_backup_all_schedule,
                             # dtype=dtyp,
                             con=engine,
                             if_exists="append",
                             index=False,
                             method="multi")
            print('Запись в backup прошла успешно...')
            logger.info("[PROCEDURE][Finish insert into logs_backup_all_schedule]")
        except Exception as e:
            logger.exception(e)
            pass

    def check_failed(self):
        # Init for Logs
        logger = self.logger_setting.basic_configuration(table_name=f"PROCEDURE")

        logger.info("[START][PROCEDURE LOGS]")
        # Connect to LD Greenplum
        engine_gp_in: Engine = self.common.connectings(schema_name='S_GRNPLM_LD_BLAGO_UBHQ_IN', logger=logger)

        # Inits
        number_query = 1
        query_logs = self.path.query
        # Read Actual Failed PROCEDURE
        logger.info("[PROCEDURE][DATAFRAME START]")
        dataframe_procedure = self.common.check_in_sql_base(query=self.path.query,
                                                            table_name=self.path.logs_procedure,
                                                            engine=engine_gp_in,
                                                            logger=logger,
                                                            number_query=1)
        logger.info("[PROCEDURE][DATAFRAME DONE]")

        # Send Mail
        self.send_mail.start_send(pxf=0, dataframe=dataframe_procedure, logger=logger)
        logger.info("[PROCEDURE][MAIL SENDING]")
        # Insert dataframe in backup
        self.insert_into_backup_procedure(dataframe=dataframe_procedure, engine=engine_gp_in, logger=logger)
        logger.info("[DONE][PROCEDURE LOGS]")


class Main:
    def __init__(self):
        self.check_pxf: CheckPXF = CheckPXF()
        self.check_procedure: CheckPROCEDURE = CheckPROCEDURE()

    def main_start(self):
        what_start = input('Выберите PROCEDURE или PXF...\n')
        if what_start == 'PROCEDURE':
            self.check_procedure.check_failed()
        elif what_start == 'PXF':
            self.check_pxf.check_failed()


if __name__ == '__main__':
    main: Main = Main()
    main.main_start()
