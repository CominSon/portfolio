from packages.Settings import *

from noterball import noterball
import sqlalchemy as sa
import pandas as pd
from sqlalchemy import types
import pathlib
from typing import Optional, Any, Union, List


class Logon:
    def __init__(self):

        #Main
        self.users_info: UsersInfo = UsersInfo()
        self.path_to_file: str = str(pathlib.Path(r'/data/workspace/18764734_omega-sbrf-ru/system_need/pen_is.xlsx'))

        #Columns for pass
        self.cl_PPT ="PPT"
        self.cl_PPZ ="PPZ" 
        self.cl_PPX ="PPX"

        #Kerberos Settings
        self.path_to_kinit: str = "/usr/bin/kinit"
        self.cache_kerb_ora = '/data/workspace/18764734_omega-sbrf-ru/instantclient_19_13/network/tickets/krb5cache'

    @staticmethod
    def read_excel(path: str, sheet_name: str = "Лист1", engine = "openpyxl") -> pd.DataFrame:
        return pd.read_excel(path, sheet_name=sheet_name, engine=engine)


    def filter_frame(self, dataframe: pd.DataFrame, filter: str) -> pd.DataFrame:
        best_filter: str = filter.upper()
        dataframe[self.cl_PPT] = dataframe[self.cl_PPT].apply(lambda x: x.upper())
        dataframe = dataframe[dataframe[self.cl_PPT].str.upper() == best_filter]
        value = dataframe[self.cl_PPZ][(dataframe[self.cl_PPX] == max(dataframe[self.cl_PPX]))]
        return value

    def return_pass(self, filter: str ) -> str:
        dataframe_from_one: pd.DataFrame = self.read_excel(self.path_to_file)
        return self.filter_frame(dataframe=dataframe_from_one, filter=filter)
    
    def decoding_pass(self, filter: str) -> str:
        return noterball(self.return_pass(filter))

        


