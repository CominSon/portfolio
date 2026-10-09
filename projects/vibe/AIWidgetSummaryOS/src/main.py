import os
from dotenv import load_dotenv

from modules.common.logger_manager import LoggerManager
from modules.common.trace_manager import TraceManager, TraceContext
from modules.common.checkpoint_manager import CheckpointManager

from modules.db.postgres_manager import PostgresManager
from modules.db.repositories import MetadataRepository, NavDataRepository

from modules.llm.prompt_loader import PromptLoader
from modules.llm.fake_llm_manager import FakeLLMManager
from modules.llm.gigachat_llm_manager import GigaChatLLMManager

from modules.core.evidence_builder import EvidenceBuilder
from modules.llm.summary_agent import SummaryAgent
from modules.core.widget_analyzer import WidgetAnalyzer
from modules.core.report_renderer import ReportRenderer
from modules.llm.final_report_agent import FinalReportAgent
from modules.llm.final_quality_agent import FinalQualityAgent
from modules.db.results_repository import ResultsRepository


class App:
    def __init__(self):
        load_dotenv()

        self.logger = LoggerManager(
            log_dir="src/logs",
            level=os.getenv("LOG_LEVEL"),
            name="AIWidgetSummary"
        ).get_logger()

        self.trace = TraceManager(trace_dir=os.getenv("TRACE_DIR"), logger=self.logger)
        self.checkpoint = CheckpointManager(
            checkpoint_dir=os.getenv("CHECKPOINT_DIR") or "src/checkpoints",
            logger=self.logger,
        )

        self.pg = PostgresManager(self.logger)
        self.pg.connect()
        self.meta_repo = MetadataRepository(self.pg, self.logger)
        self.nav_repo = NavDataRepository(self.pg, self.logger)
        self.results_repo = ResultsRepository(self.pg, self.logger)

        self.prompts = PromptLoader(self.meta_repo, self.logger, default_template_id=1)

        provider = os.getenv("LLM_PROVIDER").strip().lower()
        self.llm = GigaChatLLMManager(provider="gigachat", logger=self.logger) if provider == "gigachat" else FakeLLMManager(provider="fake", logger=self.logger)

        self.evidence_builder = EvidenceBuilder(self.logger, self.trace)
        self.summary_agent = SummaryAgent(self.llm, self.prompts, self.logger, self.trace)
        self.final_report_agent = FinalReportAgent(self.llm, self.prompts, self.logger, self.trace)
        self.final_quality_agent = FinalQualityAgent(self.llm, self.prompts, self.logger, self.trace)
        self.analyzer = WidgetAnalyzer(
            self.meta_repo,
            self.nav_repo,
            self.evidence_builder,
            self.summary_agent,
            self.logger,
            self.trace,
            checkpoint_manager=self.checkpoint,
        )
        self.renderer = ReportRenderer(
            result_dir=os.getenv("RESULT_DIR") or "src/result",
            logger=self.logger,
        )

    def start(self, group_widget: str, force_restart: bool = False):
        ctx = TraceContext(group_widget=group_widget)

        self.logger.info("=== СТАРТ ===")
        self.logger.info(f"Группа: {group_widget} | run_id={ctx.run_id} | трасса={self.trace.path(ctx)}")
        self.logger.info(f"LLM_PROVIDER={os.getenv('LLM_PROVIDER', 'fake')}")
        self.logger.info(f"force_restart={force_restart}")

        if force_restart:
            self.checkpoint.clear(group_widget)
        elif self.checkpoint.has_checkpoint(group_widget):
            self.logger.info(
                f"Найден checkpoint для группы '{group_widget}' — "
                f"продолжу с места остановки (для полного перезапуска добавьте ! в конце ввода)."
            )

        self.pg.init_tables()

        results = self.analyzer.run_group(
            ctx,
            group_widget=group_widget,
            force_restart=force_restart,
        )
        # Analyzer уже сохранил checkpoint (stage=widgets_done).
        # Если упадём на финальных LLM — при следующем запуске той же группы
        # виджеты подхватятся из checkpoint, без повторных вызовов.

        final_report = self.final_report_agent.build_final_report(
            ctx=ctx,
            group_widget=group_widget,
            widget_results=results,
        )
        final_report = self.final_quality_agent.review(
            ctx=ctx,
            group_widget=group_widget,
            final_report=final_report,
        )
        report_path = self.renderer.render_group_txt(group_widget, results, final_report)
        if not report_path:
            raise RuntimeError(
                "render_group_txt не вернул путь к файлу отчёта. Проверьте RESULT_DIR и права на запись."
            )

        self.results_repo.insert_result(group_name=group_widget, report_path=report_path)

        # Успешный финал — checkpoint больше не нужен
        self.checkpoint.clear(group_widget)

        self.logger.info(f"Готовый отчёт: {report_path}")
        self.logger.info("=== ГОТОВО ===")

    def close(self):
        self.pg.close()

    def parse_launch_input(self, raw_input_value: str) -> tuple[list[str], bool]:
        """
        Возвращает (группы, force_restart).

        Примеры:
          Ключевые метрики      -> resume этой группы, если есть checkpoint
          Ключевые метрики!     -> принудительный перезапуск этой группы
          all                   -> все группы, resume по каждой
          all!                  -> все группы, принудительный перезапуск
        """
        value = (raw_input_value or "").strip()
        if not value:
            raise ValueError("Пустое значение группы. Введите точное название группы или all.")

        force_restart = False
        if value.endswith("!"):
            force_restart = True
            value = value[:-1].strip()
            if not value:
                raise ValueError("После '!' нужно указать название группы или all.")

        if value.lower() == "all":
            groups = self.meta_repo.get_all_groups()
            if not groups:
                raise RuntimeError("В ai_os_ub_widget_meta не найдено ни одной группы.")
            return groups, force_restart

        return [value], force_restart


if __name__ == "__main__":
    app = App()
    try:
        print("Введите точное название группы из ai_os_ub_widget_meta или 'all'.")
        print("Для принудительного перезапуска добавьте ! в конце (пример: Ключевые метрики! или all!).")
        print("Без ! скрипт продолжит с checkpoint, если он есть для выбранной группы.")
        raw_group = input(">>> ").strip()
        groups, force_restart = app.parse_launch_input(raw_group)
        for group_name in groups:
            app.start(group_widget=group_name, force_restart=force_restart)
    finally:
        app.close()
