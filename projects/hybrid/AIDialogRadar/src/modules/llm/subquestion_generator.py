from src.modules.gigachat.gigachat_manager import GigaChatAPIManager
from src.modules.gigachat.gigachat_promt_loader import GigaChatPromptLoader


class SubQuestionGenerator:
    def __init__(self, logger):
        self.logger = logger
        self.gigachat_api_model = GigaChatAPIManager(logger=self.logger).get_model()
        self.gigachat_prompt_loader: GigaChatPromptLoader = GigaChatPromptLoader(logger=self.logger)

    def _parse_response(self, text: str) -> list[str]:
        """Преобразует текстовый ответ модели в список строк"""
        return [line.strip().strip("1234567890. ").strip() for line in text.content.split("\n")]

    def generate_subquestions(self, user_question: str) -> list[str]:
        """Генерируем подзапросы от основного вопроса пользователя"""
        self.logger.info("Генерация подзапросов для исходного вопроса")

        system_context = self.gigachat_prompt_loader.build_system_context()
        user_prompt_template = self.gigachat_prompt_loader.get_prompt("subquestion_generation")  # Генерация подзапросов
        user_prompt = user_prompt_template["text"].replace("{question}", user_question)
        full_prompt = f"{system_context} \n\n{user_prompt}"
        try:
            result = self.gigachat_api_model.invoke(full_prompt)
            self.logger.info("Подзапросы успешно сгенерированы")
        except Exception as e:
            self.logger.error(f"Ошибка при генерации подзапросов: {e}")
            return []

        return self._parse_response(result)

    def format_context_block(self, blocks):
        """Приводим результат по подзапросам в подходящий вид для финального сообщения"""
        try:
            formatted = []
            for i, block in enumerate(blocks, start=1):
                subquery = block["subquery"]
                context = block["context"]
                context_lines = "\n".join(f". {con_}" for con_ in context)
                block_text = (
                    "Это подзапросы и наиболее подходящие сообщения из чатов.\n"
                    f"Подзапрос {i}\n{subquery}\n\n"
                    f"--- Сообщения из чатов ---\n{context_lines}\n"
                    f"{'-'*40}"
                )
                formatted.append(block_text)
            return "\n\n".join(formatted)
        except Exception as e:
            self.logger.error(f"Ошибка в процессе формирования итогов по подзапросам: {e}")
            return None


