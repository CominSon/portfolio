from dialog_bot_sdk.bot import DialogBot
from src.modules.db.chat_uploader import ChatUploader
from src.modules.sberchat.sbechat_config import SberChatConfig


class SberChatManager:
    def __init__(self, logger):
        self.logger = logger
        self.group_ids = SberChatConfig.GROUP_IDS

        # Доп. Модули
        self.chat_uploader: ChatUploader = ChatUploader(logger=self.logger)  # Модуль записи сообщений в БД

    def connect_bot(self):
        """Возвращаем слепок подключенного бота Сбер-чата"""
        try:
            config_dict = {
                "endpoint": SberChatConfig.ENDPOINT,
                "token": SberChatConfig.TOKEN,
                "is_secure": SberChatConfig.IS_SECURE
            }
            bot = DialogBot.create_bot(config_dict)
            self.logger.info(f"СберЧат-бот успешно подключен")
            return bot
        except Exception as e:
            self.logger.error(f"Ошибка подключения СберЧат-бота: {e}")
            raise

    def return_info_group(self, bot, group_id):
        """Поиск группы по ID"""
        try:
            group_info = bot.groups.find_group_by_id_sync(int(group_id))
            self.logger.info(f"{group_id}: информация найдена")
            return group_info
        except Exception as e:
            self.logger.error(f"{group_id}: Ошибка получения информации по группе: {e}")
            raise

    def return_history_group(self, bot, group_info, group_id):
        """Возвращаем историю сообщений группы"""
        try:
            cursor_date = 0  # стартовая позиция чата
            limit = 100  # максимальный лимит на одну порцию
            history = bot.messaging.load_message_history_sync(group_info.peer, date=cursor_date, limit=limit)
            self.logger.info(f"{group_id}: История сообщений найдена")
            return history
        except Exception as e:
            self.logger.error(f"{group_id}: Ошибка получения истории группы: {e}")
            raise

    def return_dict_with_message(self, messages, history, group_id):
        """Возвращаем ограниченный словарь с сообщениями в группе"""
        try:
            for msg in history:
                sender_id = group_id
                date = getattr(msg, "date", None)
                text = getattr(msg.message.text_message, "text", None)
                if text and sender_id and date:
                    entry = {"date": date, "text": text}
                    messages.setdefault(sender_id, []).append(entry)
            for mg_list in messages.values():
                mg_list.sort(key=lambda x: x["date"])
            self.logger.info(f"{group_id}: Сообщения группы успешно обработаны")
            return messages
        except Exception as e:
            self.logger.error(f"{group_id}: Ошибка обработки сообщений группы: {e}")
            raise

    def collect_chats(self) -> dict:
        """Возвращаем сообщения в формате словаря"""
        try:
            messages = {}  # Пустой общий словарь для сообщений

            # Инициализация бота
            bot = self.connect_bot()

            # Формируем списки сообщений по группам
            for group_id in self.group_ids:
                # Поиск информации по ID группы
                group_info = self.return_info_group(bot=bot, group_id=group_id)

                # Выгружаем историю чата
                history = self.return_history_group(bot=bot, group_info=group_info, group_id=group_id)

                # Обработка результата в формат списка
                messages = self.return_dict_with_message(messages=messages, history=history, group_id=group_id)
            return messages
        except Exception as e:
            self.logger.error(f"Ошибка подключения СберЧат-бота: {e}")
            raise

    def safe_chat_in_base(self):
        """Записываем сообщения в таблицы  БД"""
        messages = self.collect_chats()
        self.chat_uploader.upload_all(messages_dict=messages)
