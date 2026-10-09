from packages.Settings import *
from packages.Protection import Logon

import os
import sqlalchemy as sa


class HiveJDBC:
    """
        List with BD:
            1) sdp_landric - SDP Cluster lyandres;
            2) sdp_kocheihin - SDP Cluster kocheihin;
            4) sdp_ukhanova3 - SDP Cluster ukhanova3;
    """

    def __init__(self):
        # Main Settings
        self.users_info: UsersInfo = UsersInfo()
        self.gen_methods: GeneralMethods = GeneralMethods()
        self.logon: Logon = Logon()

        # Users value
        self.login: str = self.users_info.username.upper()
        self.kinit_login: str = self.login

        # Server value
        self.jdbc_driver_name: str = "hive"
        self.hosts_dict: dict = {"sdp_landric":"pklis-ldub00028.labiac.df.sbrf.ru",
                                 "sdp_kocheihin":"pklas-ldub00043.labiac.df.sbrf.ru",
                                 "sdp_ukhanova3":"pklis-ldub00063.labiac.df.sbrf.ru"}

        self.PORT: int = 10000

        self.CONN_ARGS = {'auth':'KERBEROS','kerberos_service_name':'hive'}


    """
        Method for best engine in GreenPlum BD
        return query
    """
    def return_full_query(self, connect_name: str):
        host = self.gen_methods.get_host(connect_name, self.hosts_dict)
        query = f"{self.jdbc_driver_name}://{self.login}@{host}:{self.PORT}"
        return query

    def kerberos_auth_query(self) -> str:
        kinit_pass: str = self.logon.decoding_pass(self.kinit_login)
        return f"echo {kinit_pass} | {self.logon.path_to_kinit} {self.kinit_login}"

    
    def full_connect(self, connect_name: str):
        # Auth with kerberos
        os.system(self.kerberos_auth_query())

        #Return engine
        all_args: list = self.return_full_query(connect_name=connect_name)
        return sa.create_engine(all_args, connect_args=self.CONN_ARGS)
