from __future__ import annotations 
import json
from typing import Any, Dict, Optional, Union

class PromptLoader:
    def __init__(self, prompts_source: Union[str, Any], logger, default_template_id: int = 1):
        """
        prompts_source:
          - str: путь до prompts.json (старый режим)
          - MetadataRepository: чтение prompt_json из таблицы ai_os_ub_prompt_templates (новый режим)
        """
        self.prompts_source = prompts_source
        self.logger = logger
        self.default_template_id = default_template_id

        self._cache: Dict[int, Dict[str, Any]] = {}

        # Старый режим (файл)
        if isinstance(prompts_source, str):
            with open(prompts_source, "r", encoding="utf-8") as f:
                self._file_data = json.load(f)
            self.logger.info(f"Промпты загружены: {prompts_source}")
            return

        # Новый режим (БД): сразу грузим дефолтный template_id
        self._file_data = None
        self._cache[default_template_id] = self.prompts_source.get_prompt_template(default_template_id)
        self.logger.info(f"Промпты загружены из БД: template_id={default_template_id}")

    def _get_template(self, template_id: Optional[int]) -> Dict[str, Any]:
        # Если работаем в режиме файла
        if self._file_data is not None:
            return self._file_data

        tid = template_id or self.default_template_id
        if tid not in self._cache:
            self._cache[tid] = self.prompts_source.get_prompt_template(tid)
            self.logger.info(f"Промпты догружены из БД: template_id={tid}")
        return self._cache[tid]

    def get_system(self, key: str, template_id: Optional[int] = None) -> str:
        t = self._get_template(template_id)
        return t[key]

    def get_user_template(self, key: str, template_id: Optional[int] = None) -> Any:
        t = self._get_template(template_id)
        return t[key]

    def get_schema(self, key: str, template_id: Optional[int] = None) -> Any:
        t = self._get_template(template_id)
        return t[key]
