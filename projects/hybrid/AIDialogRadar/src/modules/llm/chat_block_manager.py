from src.modules.llm.llm_config import LLMConfig
from src.modules.db.message_loader import MessageLoader
from src.modules.llm.faiss_manager import FaissManager
from src.modules.gigachat.gigachat_manager import GigaChatEmbeddingsManager
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ChatBlockManager:
    """Модуль обработки Чатов через LLM """
    def __init__(self, logger):
        self.logger = logger
        self.message_loader: MessageLoader = MessageLoader(logger=self.logger)
        self.embedding_model = GigaChatEmbeddingsManager(logger=self.logger).get_model()
        self.faiss = FaissManager(logger=self.logger, embedding_dim=LLMConfig.EMBEDDING_DIM)

    def group_messages_by_chat(self):
        """Группирует сообщения по chat_id и лимиту символов"""
        try:
            messages = self.message_loader.load_recent_messages()
            grouped = {}
            for chat_id, date, text in messages:
                grouped.setdefault(chat_id, []).append({'date': date, 'text': text})

            blocked_by_chat = {}
            for chat_id, msg_list in grouped.items():
                blocks = []
                current_block = []
                current_len = 0

                for msg in msg_list:
                    msg_len = len(msg['text'])

                    if current_len + msg_len > LLMConfig.MAX_BLOCK_CHARS:
                        # Если блок уже есть, закрываем его и начинаем новый
                        if current_block:
                            blocks.append(current_block)
                            current_block = []
                            current_len = 0

                    current_block.append(msg)
                    current_len += msg_len

                # Добавляем финальный блок, если остались сообщения
                if current_block:
                    blocks.append(current_block)

                blocked_by_chat[chat_id] = blocks

            self.logger.info("Сообщения успешно сгруппированы по лимиту символов.")
            return blocked_by_chat

        except Exception as e:
            self.logger.error(f"Ошибка при группировке сообщений: {e}")
            return {}

    def build_faiss_index_from_blocks(self):
        """Строит FAISS-индекс по чанкам сообщений из чатов"""
        try:
            documents = []
            blocked_by_chat = self.group_messages_by_chat()
            splitter = RecursiveCharacterTextSplitter(chunk_size=LLMConfig.CHUNK_SIZE,
                                                      chunk_overlap=LLMConfig.CHUNK_OVERLAP)

            for chat_id, blocks in blocked_by_chat.items():
                for block in blocks:
                    combined_text = "\n".join(msg['text'] for msg in block)
                    chunks = splitter.create_documents([combined_text])
                    documents.extend(chunks)

            if not documents:
                self.logger.info("Нет данных для векторизации и индексации.")
                return None

            embeddings = self.embedding_model.embed_documents([doc.page_content for doc in documents])
            self.faiss.build_index(embeddings, [doc.page_content for doc in documents])
            self.faiss.save_index(f"{LLMConfig.CHAT_FAISS_INDEX_PATH}chat_faiss.index")
            self.logger.info("FAISS-индекс по чатам успешно создан и сохранён.")

        except Exception as e:
            self.logger.error(f"Ошибка при создании FAISS-индекса: {e}")

    def get_index(self):
        """Выгружаем индексты чатов"""
        try:
            faiss_index_bool = self.faiss.load_index(f"{LLMConfig.CHAT_FAISS_INDEX_PATH}chat_faiss.index")
            return faiss_index_bool
        except Exception as e:
            self.logger.error(f"Ошибка при создании FAISS-индекса: {e}")
            return False

