import io
from abc import ABC, abstractmethod
from pathlib import Path

from docx import Document
from pypdf import PdfReader


class BaseDocumentParser(ABC):
    @abstractmethod
    def parse(self, data: bytes) -> str:
        pass


class PdfParser(BaseDocumentParser):
    def parse(self, data: bytes) -> str:
        reader = PdfReader(io.BytesIO(data))
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts)


class WordParser(BaseDocumentParser):
    def parse(self, data: bytes) -> str:
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


class DocumentParser:
    SUPPORTED = {".pdf", ".docx", ".doc"}

    def __init__(self) -> None:
        self._pdf = PdfParser()
        self._word = WordParser()

    def parse_file(self, filename: str, data: bytes) -> str:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return self._pdf.parse(data)
        if ext in (".docx", ".doc"):
            return self._word.parse(data)
        raise ValueError(f"Unsupported format: {ext}")
