import re 

_ALLOWED = re.compile(r"^(value([1-9]|[12]\d|30)|date_update)$")

def safe_col(col: str) -> str:
    col = (col or "").strip()
    if not _ALLOWED.match(col):
        raise ValueError(f"Недопустимое имя поля: {col}")
    return col
