/** Форматирование речи AI для читаемого отображения. */

export function formatMessageParagraphs(text: string): string[] {
  const raw = (text || "").trim();
  if (!raw) return [];
  const byBreak = raw.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  if (byBreak.length > 1) return byBreak;
  const sentences = raw.split(/(?<=[.!?…])\s+(?=[А-ЯA-Z«])/u).map((s) => s.trim()).filter(Boolean);
  if (sentences.length <= 2) return [raw];
  const chunks: string[] = [];
  let buf = "";
  for (const s of sentences) {
    if (buf.length + s.length > 220 && buf) {
      chunks.push(buf.trim());
      buf = s;
    } else {
      buf = buf ? `${buf} ${s}` : s;
    }
  }
  if (buf) chunks.push(buf.trim());
  return chunks.length ? chunks : [raw];
}

export function isEmphasisLine(line: string): boolean {
  const t = line.trim();
  if (t.length < 8 || t.length > 120) return false;
  if (/^(важно|внимание|итог|задача|вопрос|следующ)/i.test(t)) return true;
  if (t.endsWith("?") && t.split(/\s+/).length <= 18) return true;
  return false;
}

export function MessageBody({ text, large = false }: { text: string; large?: boolean }) {
  const paragraphs = formatMessageParagraphs(text);
  return (
    <div className={large ? "message-body message-body--large" : "message-body"}>
      {paragraphs.map((p, i) => (
        <p key={i} className={isEmphasisLine(p) ? "message-emphasis" : undefined}>
          {p}
        </p>
      ))}
    </div>
  );
}

