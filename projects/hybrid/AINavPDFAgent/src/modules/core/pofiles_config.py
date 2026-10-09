import os
from pathlib import Path


class ProfilesConfig:
    """Конфигурация необходимая для обработки профилей Браузера"""
    BROWSER_PROFILES_PATH = os.getenv("BROWSER_PROFILES_PATH")
    PROFILES_LIST = os.getenv("PROFILES_LIST").split(",")
    PROFILES_LIST = [p.strip() for p in PROFILES_LIST if p.strip()]

    def get_profile_path(self, profile_name: str) -> str:
        """
        Возвращает полный путь к профилю.
        """
        return str(Path(self.BROWSER_PROFILES_PATH) / profile_name)

    def list_profiles(self) -> list[str]:
        """
        Возвращает список имён профилей из конфигурации.
        """
        return self.PROFILES_LIST
