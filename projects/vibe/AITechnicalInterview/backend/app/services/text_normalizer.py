import re
import unicodedata


class TextNormalizer:
    def normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\x00", "")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
