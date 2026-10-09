from app.services.competency_utils import filter_programming_languages
from app.services.llm_orchestrator import LlmOrchestrator


class CompetencyAnalyzer:
    def __init__(self, orchestrator: LlmOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or LlmOrchestrator()

    async def analyze_from_job_description(self, job_description: str) -> list[dict]:
        raw = await self.orchestrator.infer_competencies_from_job_description(job_description)
        return filter_programming_languages(raw)
