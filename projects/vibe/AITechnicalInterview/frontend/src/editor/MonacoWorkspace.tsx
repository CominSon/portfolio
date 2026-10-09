import Editor, { OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useCallback, useEffect, useRef } from "react";

export type EditorDecoration = {
  line: number;
  className?: string;
  comment?: string;
};

type Props = {
  language: string;
  value: string;
  onChange: (value: string) => void;
  onCursorMove?: (line: number, column: number) => void;
  decorations?: EditorDecoration[];
  readOnly?: boolean;
};

export default function MonacoWorkspace({
  language,
  value,
  onChange,
  onCursorMove,
  decorations = [],
  readOnly = false,
}: Props) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const handleMount: OnMount = (ed) => {
    editorRef.current = ed;
    ed.onDidChangeCursorPosition((e) => {
      onCursorMove?.(e.position.lineNumber, e.position.column);
    });
  };

  const applyDecorations = useCallback(() => {
    const ed = editorRef.current;
    if (!ed) return;
    const model = ed.getModel();
    if (!model) return;

    const decs: editor.IModelDeltaDecoration[] = decorations.flatMap((d) => {
      const items: editor.IModelDeltaDecoration[] = [
        {
          range: { startLineNumber: d.line, startColumn: 1, endLineNumber: d.line, endColumn: 1 },
          options: {
            isWholeLine: true,
            className: d.className || "ai-line-highlight",
            glyphMarginClassName: d.comment ? "ai-comment-glyph" : undefined,
          },
        },
      ];
      if (d.comment) {
        items.push({
          range: { startLineNumber: d.line, startColumn: 1, endLineNumber: d.line, endColumn: 1 },
          options: { after: { content: ` // ${d.comment}`, inlineClassName: "ai-inline-comment" } },
        });
      }
      return items;
    });
    ed.deltaDecorations([], decs);
  }, [decorations]);

  useEffect(() => {
    applyDecorations();
  }, [applyDecorations]);

  return (
    <div className="monaco-wrap">
      <Editor
        height="100%"
        language={language}
        value={value}
        theme="vs-dark"
        onChange={(v) => onChange(v ?? "")}
        onMount={handleMount}
        options={{
          readOnly,
          minimap: { enabled: true },
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 14,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 4,
          wordWrap: "on",
        }}
      />
      <style>{`
        .monaco-wrap { height: 100%; min-height: 360px; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border); }
        .ai-line-highlight { background: rgba(167, 139, 250, 0.12) !important; }
        .ai-inline-comment { color: var(--ai) !important; font-style: italic; }
      `}</style>
    </div>
  );
}
