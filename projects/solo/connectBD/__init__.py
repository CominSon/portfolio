# -*- coding: utf-8 -*-

import sqlalchemy as sa
import teradatasql as tersq
import cx_Oracle
import pandas as pd
import warnings
warnings.filterwarnings('ignore')
from noterball import noterball
import getpass
import os
import psycopg2 as pc2



#%%
warnings.filterwarnings('ignore')
pd.options.display.max_colwidth =50000000
#%%
go_to =r'/data/workspace/18764734_omega-sbrf-ru/system_need/pen_is.xlsx'

data = pd.read_excel(go_to,sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT'].apply(lambda x: x.upper())==getpass.getuser().upper().replace('_OMEGA-SBRF-RU', '')]
tim2 = data['PPZ'][(data['PPX'] == max(data['PPX']))]

data = pd.read_excel(go_to,sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT'].apply(lambda x: x.upper())==getpass.getuser().upper()]
tim2_1 = data['PPZ'][(data['PPX'] == max(data['PPX']))]

data = pd.read_excel(go_to,sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT']=='SBX_MIS_UB_ETL']
tim3 = data['PPZ'][(data['PPX'] == max(data['PPX']))]


data = pd.read_excel(go_to,sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT']=='db_dbl_infa_etl']
tim4 = data['PPZ'][(data['PPX'] == max(data['PPX']))]

data = pd.read_excel(go_to,sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT']=='db_blg']
tim = data['PPZ'][(data['PPX'] == max(data['PPX']))]


data = pd.read_excel(go_to,sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT']=='CAB-SA-TDBLG003@ca.sbrf.ru']
tim5 = data['PPZ'][(data['PPX'] == max(data['PPX']))]


data = pd.read_excel(go_to, sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT'] == 'ASM_SANDBOX_BLG']
tim9 = data['PPZ'][(data['PPX'] == max(data['PPX']))]

data = pd.read_excel(go_to, sheet_name='Лист1', engine = 'openpyxl')
data = data[data['PPT'] == 'TECH_BS']
tim10 = data['PPZ'][(data['PPX'] == max(data['PPX']))]

def use_new_engine(x:str = None):
    '''
    Types of connections:
        \n- k2, dm, src - ПКАП Oracle;
        \n- db_blg, cx_ora, etl - Old Oracle;
        \n- bdsm - ASM connects;
        \n- odc - ODC connects;
        \n- 14, 15 - Teradata;
        \n- gp_mis2,capgp1 - GreenPlum;
	\n- sdp, cdh - Hive;
    '''

    # -------------------------------------------
    if x == 'k2':
        z = sa.create_engine('oracle+cx_oracle://[UBHQ_USR_SRC_K2]:@PKAPUB_PROM.ca.sbrf.ru')
    elif x == 'dm':
        z = sa.create_engine('oracle+cx_oracle://[UBHQ_USR_DM]:@PKAPUB_PROM.ca.sbrf.ru')
    elif x == 'db_blg':
        z = sa.create_engine('oracle+cx_oracle://db_blg:' + noterball(tim) + '@modi1_wealthdb')
    elif x == 'etl':
        z = sa.create_engine('oracle+cx_oracle://db_dbl_infa_etl:' + noterball(tim4) + '@modi1_wealthdb')
    elif x == 'bdsm':
        z = sa.create_engine('oracle+cx_oracle://ASM_SANDBOX_BLG:' + noterball(tim9) + '@(description = (address_list = (address = (protocol = tcp)(host = bdsm2.ca.sbrf.ru)(port = 1521)))(connect_data =(sid = bdsm2)(server = dedicated)))')
    elif x == 'odc':
        z = sa.create_engine('oracle+cx_oracle://TECH_BS:' + noterball(tim10) + '@(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(Host=odsp1-scan1.exa.df.sbrf.ru)(Port=1521)))(CONNECT_DATA=(SERVICE_NAME=PROD_SERVICE)(SERVER=DEDICATED)))')
    elif x == 'cx_ora':
        z = cx_Oracle.connect('db_blg', noterball(tim), 'modi1_wealthdb')
    elif x == '14':
        z = tersq.connect('{"logmech":"LDAP"}', host='TDSB14.cgs.sbrf.ru', user='CAB-SA-TDBLG003',password=noterball(tim5))
    elif x == '15':
        z = tersq.connect('{"logmech":"LDAP"}', host='TDSB15.cgs.sbrf.ru', user='CAB-SA-TDBLG003',password=noterball(tim5))
    elif x == 'src':
        z = sa.create_engine('oracle+cx_oracle://[UBHQ_USR_SRC]:@PKAPUB_PROM.ca.sbrf.ru')
    elif x in('gp_mis2', 'gp_mis2_v2'):
        os.system('''echo '{1}' | /usr/bin/kinit {0}'''.format(getpass.getuser().replace('_omega-sbrf-ru', '@omega.sbrf.ru'),noterball(tim2)))
        #z = pc2.connect(user=getpass.getuser().replace('_omega-sbrf-ru', ''),host='pplas-kaprp00040.cloud.df.sbrf.ru', port='5432',database="gp_mis2")
        conn_args = {'database': 'gp_mis2'}
        z = sa.create_engine(f"postgresql+psycopg2://{getpass.getuser().replace('_omega-sbrf-ru', '')}@pplas-kaprp00040.cloud.df.sbrf.ru:5432",connect_args=conn_args)
    elif x in ('capgp1', 'capgp1_v2', 'capgp1_v3'):
        os.system('''echo '{1}' | /usr/bin/kinit {0}'''.format(getpass.getuser().replace('_omega-sbrf-ru', '@omega.sbrf.ru'),noterball(tim2)))
        #z = pc2.connect(user=getpass.getuser().replace('_omega-sbrf-ru', ''),host='pplas-kaprp00040.cloud.df.sbrf.ru', port='5432',database="gp_mis2")
        conn_args = {'database': 'capgp1'}
        z = sa.create_engine(f"postgresql+psycopg2://{getpass.getuser().replace('_omega-sbrf-ru', '')}@gp_dns_pkap1005_ubhq.gp.df.sbrf.ru:5432",connect_args=conn_args)
    elif x == 'gp_rozn2':
        os.system('''echo '{1}' | /usr/bin/kinit {0}'''.format(getpass.getuser().replace('_omega-sbrf-ru', '@omega.sbrf.ru'),noterball(tim2)))
        #z = pc2.connect(user=getpass.getuser().replace('_omega-sbrf-ru', ''),host='pplas-kaprp00040.cloud.df.sbrf.ru', port='5432',database="gp_mis2")
        conn_args = {'database': 'gp_rozn2', 'options': "-csearch_path=S_GRNPLM_LD_ROZN_ELECTRON_HQ_CORE"}
        z = sa.create_engine(f"postgresql+psycopg2://{getpass.getuser().replace('_omega-sbrf-ru', '')}@pplas-pkarb0100.cloud.df.sbrf.ru:5432",connect_args=conn_args)
    elif x == 'capgp2':
        os.system('''echo '{1}' | /usr/bin/kinit {0}'''.format(getpass.getuser().replace('_omega-sbrf-ru', '@omega.sbrf.ru'),noterball(tim2)))
        #z = pc2.connect(user=getpass.getuser().replace('_omega-sbrf-ru', ''),host='pplas-kaprp00040.cloud.df.sbrf.ru', port='5432',database="gp_mis2")
        conn_args = {'database': 'capgp2', 'options': "-csearch_path=s_grnplm_ld_blago_ubhq_in"}
        z = sa.create_engine(f"postgresql+psycopg2://{getpass.getuser().replace('_omega-sbrf-ru', '')}@gp_dns_pkap1005_cib_gm.gp.df.sbrf.ru:5432",connect_args=conn_args)
    elif x == 'sdp':
        os.system('''echo '{1}' | /usr/bin/kinit {0}'''.format(getpass.getuser(),noterball(tim2_1)))
        conn_args = {'auth':'KERBEROS','kerberos_service_name':'hive'}
        z= sa.create_engine(f"hive://{getpass.getuser()}@pklos-ldub00206.labiac.df.sbrf.ru:10000", connect_args=conn_args)
	    #z = hive.Connection(host="pklas-ldub00043.labiac.df.sbrf.ru", port=10000, username="18764734_omega-sbrf-ru", auth="KERBEROS", kerberos_service_name="hive")
    elif x == 'sdp_cx':
        os.system('''echo '{1}' | /usr/bin/kinit {0}'''.format(getpass.getuser(),noterball(tim2_1)))
        conn_args = {'auth':'KERBEROS','kerberos_service_name':'hive'}
        z= sa.create_engine(f"hive://{getpass.getuser()}@pplis-kappd0836.cloud.df.sbrf.ru:10000", connect_args=conn_args)
	    #z = hive.Connection(host="pklas-ldub00043.labiac.df.sbrf.ru", port=10000, username="18764734_omega-sbrf-ru", auth="KERBEROS", kerberos_service_name="hive")
    elif x == 'cdh':
        conn_args = {'auth':'KERBEROS','kerberos_service_name':'hive'}
        z= sa.create_engine(f"hive://{getpass.getuser()}@pklas-ldub00043.labiac.df.sbrf.ru:10000", connect_args=conn_args) 
    return z