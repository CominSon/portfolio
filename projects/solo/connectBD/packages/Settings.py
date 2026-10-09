import warnings
warnings.filterwarnings('ignore')
from noterball import noterball
import getpass


class UsersInfo:
    def __init__(self):
        self.username: str = getpass.getuser()



class GeneralMethods:
    def __init__(self):
        self.dict_with_all_connects_name: dict = {}
    
    @staticmethod
    def get_host(connect_name: str, hosts_dict: dict) -> str:
        try:
            return hosts_dict[connect_name]
        except Exception as e:
            pass

    @staticmethod
    def get_schema(connect_name: str, schema_names: dict) -> str:
        try:
            return schema_names[connect_name]
        except Exception as e:
            pass
    
    @staticmethod
    def get_login(connect_name: str, login_names: dict) -> str:
        try:
            return login_names[connect_name]
        except Exception as e:
            pass
