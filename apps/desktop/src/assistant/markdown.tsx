/**
 * A tiny, safe markdown renderer for assistant messages: bold, italics, inline code, links and
 * lists. Builds React nodes directly (no `dangerouslySetInnerHTML`), so there is no HTML
 * injection surface regardless of what the model or a person types.
 */
import type { ReactNode } from "react";

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*|\[([^\]]+)\]\(([^)]+)\)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const key = `${keyPrefix}-${i++}`;
    if (match[1] !== undefined) nodes.push(<code key={key}>{match[1]}</code>);
    else if (match[2] !== undefined) nodes.push(<strong key={key}>{match[2]}</strong>);
    else if (match[3] !== undefined) nodes.push(<em key={key}>{match[3]}</em>);
    else if (match[4] !== undefined) {
      nodes.push(
        <a key={key} href={match[5]} target="_blank" rel="noreferrer noopener">
          {match[4]}
        </a>,
      );
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flushList = (key: string) => {
    if (!list.length) return;
    blocks.push(
      <ul key={key}>
        {list.map((item, i) => (
          <li key={i}>{renderInline(item, `${key}-${i}`)}</li>
        ))}
      </ul>,
    );
    list = [];
  };
  lines.forEach((line, i) => {
    const bullet = /^\s*[-*]\s+(.*)/.exec(line);
    if (bullet) {
      list.push(bullet[1]);
      return;
    }
    flushList(`l${i}`);
    if (line.trim()) blocks.push(<p key={i}>{renderInline(line, `p${i}`)}</p>);
  });
  flushList("l-end");
  return <>{blocks}</>;
}
