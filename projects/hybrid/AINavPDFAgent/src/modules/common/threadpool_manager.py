import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Callable, Iterable, Any, List


class ThreadPoolManager:
    """
    Универсальный менеджер пула потоков.
    - reader_fn: функция без аргументов, возвращает Iterable[dict] (список новых задач/писем)
    - handler_fn: функция обработки одного элемента (dict) — выполняется в пуле
    - interval: пауза между опросами reader_fn (сек)
    """

    def __init__(self, logger, max_workers: int = 4, handler_max_workers: int = 4):
        self.logger = logger
        self.executor = ThreadPoolExecutor(max_workers=max_workers)  # пул для поиска новых сообщений
        self.handler_executor = ThreadPoolExecutor(max_workers=handler_max_workers)  # пул для обработки писем

    def _process_messages(self, items: List[dict], handler_fn: Callable[[dict], Any]):
        """Запускает обработку пачки сообщений параллельно"""
        for item in items:
            try:
                print("---------------------------------------")
                print(item)
                self.handler_executor.submit(handler_fn, item)
                self.logger.info(f"[ThreadPool] Сообщение обработано. Результат: {item.get('subject', '')}")
            except Exception as e:
                self.logger.error(f"[ThreadPool] Ошибка обработки письма: {e}")

    def run_pool(self, reader_fn: Callable[[], Iterable[dict]],
                 handler_fn: Callable[[dict], Any],
                 interval: int):
        self.logger.info(f"ThreadPool запущен")
        while True:
            try:
                items = list(reader_fn() or [])
                if items:
                    self.logger.info(f"ThreadPool: получено {len(items)} новых элементов")
                    # обработка в пуле
                    self._process_messages(items, handler_fn)
            except Exception as e:
                self.logger.error(f"ThreadPool.run: ошибка цикла: {e}")
            time.sleep(interval)

    def run_orchestrator(self, orchestrator_fn: Callable[[], None], interval: int):
        """
        Отдельный цикл для профилей.
        orchestrator_fn — функция, которая проверяет очередь запросов и обрабатывает их.
        interval — пауза между проверками очереди (чтобы не грузить процессор).
        """
        self.logger.info("ThreadPool (оркестратор) запущен")
        while True:
            try:
                orchestrator_fn()
            except Exception as e:
                self.logger.error(f"ThreadPool.run_orchestrator: ошибка цикла: {e}")
            time.sleep(interval)

    def run_thread(self, target_fn: Callable, *args, **kwargs):
        try:
            threading.Thread(target=target_fn, args=args, kwargs=kwargs, daemon=True).start()
        except Exception as e:
            self.logger.error(f"ThreadPool.run_thread: ошибка запуска потока: {e}")

    def run_block_loop(self):
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            self.logger.error(f"ThreadPool.run_block_loop: Остановка процесса")
