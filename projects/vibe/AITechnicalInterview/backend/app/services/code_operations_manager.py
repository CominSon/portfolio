from app.services.editor_synchronization_manager import EditorSynchronizationManager


class CodeOperationsManager:
    def __init__(self) -> None:
        self.sync = EditorSynchronizationManager()

    def apply_operation(self, content: str, op_type: str, range_data: dict, text: str = "") -> str:
        sl = range_data.get("startLine", 1)
        sc = range_data.get("startColumn", 1)
        el = range_data.get("endLine", sl)
        ec = range_data.get("endColumn", sc)
        if op_type in ("code_insert", "insert_code", "code_insert"):
            return self.sync.apply_insert(content, sl, sc, text)
        if op_type in ("code_replace", "replace_code"):
            return self.sync.apply_replace_range(content, sl, sc, el, ec, text)
        if op_type in ("code_delete", "delete_code"):
            return self.sync.apply_delete_range(content, sl, sc, el, ec)
        return content
