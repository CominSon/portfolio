from packages.Settings import *
from packages.Protection import Logon

import os
import sqlalchemy as sa

class GreenPlum:
    """
        List with BD:
            1) gp_mis2 - ПКАП АС MIS;
            2) capgp1 - GP ПКАП ЛД УБ;
            3) gp_rozn2 - GP_PROM_ROZN2;
    """
    def __init__(self):
        # Main Settings
        self.users_info: UsersInfo = UsersInfo()
        self.gen_methods: GeneralMethods = GeneralMethods()
        self.logon: Logon = Logon()

        # Users value
        self.login: str = self.users_info.username.replace('_omega-sbrf-ru', '')
        self.kinit_login: str = self.users_info.username.replace('_omega-sbrf-ru', '@omega.sbrf.ru')


        # Server value
        self.jdbc_driver_name: str = "postgresql+psycopg2"
        self.hosts_dict: dict = {"gp_mis2":"pplas-kaprp00040.cloud.df.sbrf.ru",
                                 "capgp1":"gp_dns_pkap1005_ubhq.gp.df.sbrf.ru",
                                 "gp_rozn2":"pplas-pkarb0100.cloud.df.sbrf.ru",
				 "capgp2":"gp_dns_pkap1005_cib_gm.gp.df.sbrf.ru"}

        self.PORT: int = 5432

    """
        Method for best engine in GreenPlum BD
        return query
    """
    def return_full_query_with_coon_args(self, connect_name: str, schema: str):
        conn_args = {'database': connect_name}
        if schema is not None:
            conn_args['options'] = f"-csearch_path={schema.lower()}"
        host = self.gen_methods.get_host(connect_name, self.hosts_dict)
        query = f"{self.jdbc_driver_name}://{self.login}@{host}:{self.PORT}"
        return query, conn_args

    def kerberos_auth_query(self) -> str:
        kinit_pass: str = self.logon.decoding_pass(self.login)
        return f"echo {kinit_pass} | {self.logon.path_to_kinit} {self.kinit_login}"

    
    def full_connect(self, connect_name: str, schema: str = None):
        # Auth with kerberos
        os.system(self.kerberos_auth_query())

        #Return engine
        all_args: list = self.return_full_query_with_coon_args(connect_name=connect_name, schema=schema)
        return sa.create_engine(all_args[0], connect_args=all_args[1])



    
