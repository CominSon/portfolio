from dataclasses import dataclass


@dataclass
class EditorState:
    content: str
    language: str
    version: int
    seq: int


class EditorSynchronizationManager:
    """MVP: sequential op application. CRDT/OT hook point for future."""

    def apply_insert(self, content: str, line: int, column: int, text: str) -> str:
        lines = content.split("\n")
        idx = max(0, line - 1)
        while len(lines) <= idx:
            lines.append("")
        row = lines[idx]
        col = max(0, column - 1)
        inserted_lines = text.split("\n")
        if len(inserted_lines) == 1:
            lines[idx] = row[:col] + text + row[col:]
        else:
            before = row[:col]
            after = row[col:]
            lines[idx] = before + inserted_lines[0]
            for i, mid in enumerate(inserted_lines[1:-1], start=1):
                lines.insert(idx + i, mid)
            lines[idx + len(inserted_lines) - 1] += inserted_lines[-1] + after
        return "\n".join(lines)

    def apply_replace_range(
        self, content: str, start_line: int, start_col: int, end_line: int, end_col: int, text: str
    ) -> str:
        lines = content.split("\n")
        s_idx, e_idx = max(0, start_line - 1), max(0, end_line - 1)
        s_col, e_col = max(0, start_col - 1), max(0, end_col - 1)
        if s_idx == e_idx:
            row = lines[s_idx] if s_idx < len(lines) else ""
            lines[s_idx] = row[:s_col] + text + row[e_col:]
            return "\n".join(lines)
        prefix = lines[s_idx][:s_col] if s_idx < len(lines) else ""
        suffix = lines[e_idx][e_col:] if e_idx < len(lines) else ""
        new_middle = [prefix + text.split("\n")[0]] if text else [prefix]
        if text and "\n" in text:
            parts = text.split("\n")
            new_middle = [prefix + parts[0]] + parts[1:-1] + [parts[-1] + suffix]
        else:
            new_middle = [prefix + text + suffix]
        return "\n".join(lines[:s_idx] + new_middle + lines[e_idx + 1 :])

    def apply_delete_range(
        self, content: str, start_line: int, start_col: int, end_line: int, end_col: int
    ) -> str:
        return self.apply_replace_range(content, start_line, start_col, end_line, end_col, "")
