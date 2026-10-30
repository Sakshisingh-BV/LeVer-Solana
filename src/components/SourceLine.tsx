import type { ReactNode } from 'react';

const keywords = new Set(['pragma', 'solidity', 'contract', 'public', 'immutable', 'error', 'constructor', 'function', 'external', 'if', 'revert', 'pub', 'fn', 'let', 'mut', 'return', 'use', 'struct', 'impl', 'self']);
const types = new Set(['address', 'uint256', 'Context', 'Increment', 'Result', 'CounterError', 'Unauthorized', 'OwnerCounter']);

/** Lightweight, non-mutating source highlighting. Text artifacts stay plain. */
export function SourceLine({ line, language = 'solidity' }: { line: string; language?: 'solidity' | 'rust' | 'text' }) {
  if (language === 'text') return <>{line || ' '}</>;
  const pattern = /\/\/.*$|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:pragma|solidity|contract|address|public|immutable|uint256|error|constructor|function|external|if|revert|pub|fn|let|mut|return|use|struct|impl|self|Context|Increment|Result|CounterError|Unauthorized|OwnerCounter)\b|\b\d+(?:\.\d+)*\b|\b[A-Za-z_]\w*(?=\s*[!(])/g;
  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const match of line.matchAll(pattern)) {
    const index = match.index;
    if (index > cursor) parts.push(line.slice(cursor, index));
    const token = match[0];
    const kind = token.startsWith('//') ? 'comment'
      : token.startsWith('"') || token.startsWith("'") ? 'string'
      : keywords.has(token) ? 'keyword'
      : types.has(token) ? 'type'
      : /^\d/.test(token) ? 'number' : 'function';
    parts.push(<span className={`syntax-${kind}`} key={index}>{token}</span>);
    cursor = index + token.length;
  }
  if (cursor < line.length) parts.push(line.slice(cursor));
  return <>{parts.length ? parts : ' '}</>;
}
