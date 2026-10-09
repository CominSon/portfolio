from app.services.competency_analyzer import CompetencyAnalyzer
from app.services.document_parser import DocumentParser
from app.services.resume_analyzer import ResumeAnalyzer
from app.services.text_normalizer import TextNormalizer


class DocumentAnalysisManager:
    def __init__(self) -> None:
        self.parser = DocumentParser()
        self.normalizer = TextNormalizer()
        self.competency_analyzer = CompetencyAnalyzer()
        self.resume_analyzer = ResumeAnalyzer()

    def extract_text(self, filename: str, data: bytes) -> str:
        raw = self.parser.parse_file(filename, data)
        return self.normalizer.normalize(raw)

    async def analyze_job_description(self, job_description: str) -> list[dict]:
        """Языки программирования — только из текста вакансии."""
        jd = self.normalizer.normalize(job_description)
        return await self.competency_analyzer.analyze_from_job_description(jd)

    async def analyze_resume(
        self,
        resume_text: str,
        *,
        job_description: str | None = None,
        competency_skills: list[str] | None = None,
    ) -> dict:
        text = self.normalizer.normalize(resume_text)
        return await self.resume_analyzer.analyze(
            text,
            job_description=job_description,
            competency_skills=competency_skills,
        )
