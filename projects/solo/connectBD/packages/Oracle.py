from packages.Settings import *
from packages.Protection import Logon

import os
import sqlalchemy as sa

class OracleUB:
    """
        List with BD:
            1) [UBHQ_USR_DM] - BLAGO BD;
            2) [UBHQ_USR_SRC_K2] - BLAGO BD;
            3) [UBHQ_USR_SRC] - BLAGO BD;
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
        self.jdbc_driver_name: str = "oracle+cx_oracle"
        
        self.schema_names: dict = {"dm":"[UBHQ_USR_DM]",
                                   "src_k2":"[UBHQ_USR_SRC_K2]",
                                   "src":"[UBHQ_USR_SRC]"}

        self.tns_names: dict = {"dm":"PKAPUB_PROM.ca.sbrf.ru",
                                "src_k2":"PKAPUB_PROM.ca.sbrf.ru",
                                "src":"PKAPUB_PROM.ca.sbrf.ru"}


    """
        Method for best engine in Oracle BD
        return query
    """
    def return_full_query(self, connect_name: str) -> str:
        schema = self.gen_methods.get_schema(connect_name, self.schema_names)
        tns = self.gen_methods.get_host(connect_name, self.tns_names)
        query = f"{self.jdbc_driver_name}://{schema}:@{tns}"
        return query

    @staticmethod
    def text_from_kerb_query(kinit_pass: str, cache_kerb: str, login: str) -> str:
        return f"echo {kinit_pass} | /usr/bin/kinit -c FILE:{cache_kerb} {login}"

    def kerberos_auth_query(self) -> str:
        kinit_pass: str = self.logon.decoding_pass(self.login)
        cache_kerb: str  = self.logon.cache_kerb_ora
        return self.text_from_kerb_query(kinit_pass, cache_kerb, self.kinit_login)

    
    def full_connect(self, connect_name: str):
        # Auth with kerberos
        os.system(self.kerberos_auth_query())

        #Return engine
        all_args: str = self.return_full_query(connect_name=connect_name)
        return sa.create_engine(all_args)

class OracleElse:
    """
        List with BD:
            1) odc - Server ODC;
            2) bdsm - Server BDSM;
    """
    def __init__(self):
        # Main Settings
        self.gen_methods: GeneralMethods = GeneralMethods()
        self.logon: Logon = Logon()

        # Server value
        self.jdbc_driver_name: str = "oracle+cx_oracle"
        
        self.login_names: dict = {"odc":"TECH_BS",
                                  "bdsm":"ASM_SANDBOX_BLG"}
        self.login_pass: str = None

        
        self.tns_info: dict = { "odc":"""
                                        (DESCRIPTION=
                                            (ADDRESS_LIST=
                                                (ADDRESS=
                                                    (PROTOCOL=TCP)
                                                    (Host=odsp1-scan1.exa.df.sbrf.ru)
                                                    (Port=1521)
                                                )
                                            )
                                            (CONNECT_DATA=
                                                (SERVICE_NAME=PROD_SERVICE)
                                                (SERVER=DEDICATED)
                                            )
                                        )
                                        """,
                                "bdsm":"""
                                        (DESCRIPTION = 
                                            (ADDRESS_LIST = 
                                                (ADDRESS = 
                                                    (PROTOCOL = TCP)
                                                    (Host = bdsm2.ca.sbrf.ru)
                                                    (Port = 1521)
                                                )
                                            )
                                            (CONNECT_DATA =
                                                (SID = bdsm2)
                                                (SERVER = dedicated)
                                            )
                                        )
                                        """
                              }

    def password_for_bd(self, login: str) -> str:
        login_pass: str = self.logon.decoding_pass(login)
        return login_pass

    """
        Method for best engine in Oracle BD
        return query
    """
    def return_full_query(self, connect_name: str) -> str:
        login = self.gen_methods.get_login(connect_name, self.login_names)
        password = self.password_for_bd(login=login)
        tns = self.gen_methods.get_host(connect_name, self.tns_info)
        query = f"{self.jdbc_driver_name}://{login}:{password}@{tns}"
        return query

    def full_connect(self, connect_name: str):

        #Return engine
        all_args: str = self.return_full_query(connect_name=connect_name)
        return sa.create_engine(all_args)

    
