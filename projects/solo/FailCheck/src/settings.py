from connectBD_v2 import Main


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


class Path:
    def __init__(self):
        # Tables name
        self.logs_pxf_table = 'logs_pxf_table'  # Таблица с логами pxf-перегрузок
        self.logs_procedure = 'logs_procedure'  # Таблица с логами запуска процедур
        self.logs_backup_all_schedule = 'logs_backup_all_schedule'  # Общий бэкап для отслеживания актуальности по скриптам (pxf + procedure)

        # Other
        self.query: str = 'resources/query.sql'  # Универсальнгый запрос по статусу - FAILED
        self.logs_path: str = 'logs/'
        self.format: str = '%(asctime)s %(name)s %(levelname)s:%(message)s'

        # setting in sql
        self.pxf_table_name_column = 'table_name'
        self.procedure_name_column = 'procedure_name'


class SendingsSetting:
    def __init__(self):
        # Settings from Outlook
        self.outlook_columns: list = ['script', 'mail_to', 'mail_cc', 'mail_sub', 'mail_html', 'mail_attachment']

        # for PXF error
        self.pxf_outlook_name: str = 'logs_pxf_failed'

        self.pxf_outlook_mail_to: str = """Yazdovsky.Vl.Va@omega.sbrf.ru; TNSidorina@omega.sbrf.ru;
                                           EYNazarov@omega.sbrf.ru; SSPopkov@omega.sbrf.ru;
                                           Kryachun.Vl.Vl@omega.sbrf.ru; RNShafigullin@omega.sbrf.ru;
                                           dvkuprienko@omega.sbrf.ru; Ufimtsev.D.Vla@omega.sbrf.ru;
                                           Kozlov-AE@mail.ca.sbrf.ru; OKoSubbotina@omega.sbrf.ru; 
                                           MYuPavlenko@omega.sbrf.ru; AViGavryushin@omega.sbrf.ru;
                                           Shulga.E.Aleksan@omega.sbrf.ru"""

        self.pxf_outlook_mail_copy: str = """MYuPavlenko@sberbank.ru; vlvyazdovskiy@sberbank.ru;
                                             TNSidorina@sberbank.ru; Shulga.E.Aleksan@sberbank.ru; 
                                             EYNazarov@sberbank.ru; SSPopkov@sberbank.ru;
                                             vvkryachun@sber.ru; RNShafigullin@sberbank.ru;
                                             DVKuprienko@sberbank.ru; vvpolyanskiy@sberbank.ru; 
                                             Ufimtsev.D.Vla@sberbank.ru; AEKozlov@sberbank.ru;
                                             OKoSubbotina@sberbank.ru; AViGavryushin@sberbank.ru"""

        # self.pxf_outlook_mail_to: str = """MYuPavlenko@omega.sbrf.ru"""
        # self.pxf_outlook_mail_copy: str = """MYuPavlenko@sberbank.ru"""
        self.pxf_outlook_topic: str = "Список FAILED PXF перегрузок"

        # for PROCEDURE error
        self.procedure_outlook_name: str = 'logs_procedure_failed'

        self.procedure_outlook_mail_to: str = """Yazdovsky.Vl.Va@omega.sbrf.ru; TNSidorina@omega.sbrf.ru;
                                                 EYNazarov@omega.sbrf.ru; SSPopkov@omega.sbrf.ru;
                                                 Kryachun.Vl.Vl@omega.sbrf.ru; RNShafigullin@omega.sbrf.ru; 
                                                 Ufimtsev.D.Vla@omega.sbrf.ru;
                                                 Kozlov-AE@mail.ca.sbrf.ru; OKoSubbotina@omega.sbrf.ru;
                                                 MYuPavlenko@omega.sbrf.ru; AViGavryushin@omega.sbrf.ru;
                                                 Shulga.E.Aleksan@omega.sbrf.ru; dvkuprienko@omega.sbrf.ru"""

        self.procedure_outlook_mail_copy: str = """MYuPavlenko@sberbank.ru; vlvyazdovskiy@sberbank.ru;
                                                   TNSidorina@sberbank.ru; Shulga.E.Aleksan@sberbank.ru;
                                                   EYNazarov@sberbank.ru; SSPopkov@sberbank.ru;
                                                   vvkryachun@sber.ru; RNShafigullin@sberbank.ru;
                                                   vvpolyanskiy@sberbank.ru; 
                                                   Ufimtsev.D.Vla@sberbank.ru; AEKozlov@sberbank.ru;
                                                   OKoSubbotina@sberbank.ru; AViGavryushin@sberbank.ru; 
                                                   DVKuprienko@sberbank.ru"""

        # self.procedure_outlook_mail_to: str = """MYuPavlenko@omega.sbrf.ru"""
        # self.procedure_outlook_mail_copy: str = """MYuPavlenko@sberbank.ru"""
        self.procedure_outlook_topic: str = "Список FAILED PROCEDURE перегрузок"
