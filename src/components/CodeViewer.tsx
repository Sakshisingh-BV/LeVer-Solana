import { useEffect, useMemo, useRef, useState } from 'react';
import { Columns2, Copy, Download, FileCode2, FolderOpen, Maximize2, Minimize2, Search } from 'lucide-react';
import { SourceLine } from './SourceLine';
import { downloadText } from './ui';
import type { SourceFile } from '../types/run';

export function CodeViewer({ files, location, notify }: { files: SourceFile[]; location?: { file: string; line: number; endLine?: number }; notify: (message: string) => void }) {
  const [path, setPath] = useState(files[0]?.path || '');
  const [expanded, setExpanded] = useState(false);
  const [diff, setDiff] = useState(false);
  const [query, setQuery] = useState('');
  const [match, setMatch] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const file = files.find(item => item.path === path) || files[0];
  const lines = useMemo(() => file?.content.split('\n') || [], [file]);
  const matches = useMemo(() => query ? lines.flatMap((line, i) => line.toLowerCase().includes(query.toLowerCase()) ? [i + 1] : []) : [], [lines, query]);
  const jumpLine = query ? matches[match % Math.max(1, matches.length)] : location && file && location.file === file.path ? location.line : undefined;
  useEffect(() => { if (location) { setPath(location.file); setQuery(''); setDiff(false); } }, [location]);
  useEffect(() => { if (jumpLine) root.current?.querySelector(`[data-line="${jumpLine}"]`)?.scrollIntoView({ block: 'center', behavior: 'instant' }); }, [jumpLine, file]);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', escape);
    return () => { document.body.style.overflow = previous; window.removeEventListener('keydown', escape); };
  }, [expanded]);
  if (!file) return <div className="empty-state"><FileCode2 size={30} /><h2>No source files yet</h2><p>Source files will appear when the backend returns them.</p></div>;
  const before = file.before?.split('\n');
  function sourceRow(line: string, i: number, old = false) {
    const highlighted = !old && (query ? matches.includes(i + 1) : location?.file === file.path && i + 1 >= location.line && i + 1 <= (location.endLine || location.line));
    return <div className={`code-line ${highlighted ? 'highlighted' : ''} ${diff && before && before[i] !== lines[i] ? old ? 'removed-line' : 'added-line' : ''}`} key={i} data-line={old ? undefined : i + 1}><span className="line-number" aria-hidden="true">{i + 1}</span><code><SourceLine line={line} language={file.language} /></code></div>;
  }
  return <div ref={root} className={`code-workspace ${expanded ? 'is-expanded' : ''}`}>
    <aside className="file-explorer"><span className="tiny-label"><FolderOpen size={13} />FILES</span>{files.map(item => <button key={item.path} className={item.path === file.path ? 'active' : ''} onClick={() => { setPath(item.path); setDiff(false); setQuery(''); }} title={item.path}><FileCode2 size={14} /><span>{item.path}</span></button>)}</aside>
    <div className="source-panel"><div className="file-tabs" role="group" aria-label="Source files">{files.map(item => <button key={item.path} aria-pressed={item.path === file.path} className={item.path === file.path ? 'active' : ''} onClick={() => { setPath(item.path); setDiff(false); setQuery(''); }}><FileCode2 size={13} />{item.path.split('/').pop()}</button>)}</div>
      <div className="source-toolbar"><span><span className="language-label">{file.language}</span><small>{lines.length.toLocaleString()} lines</small></span><div>
        {before && <button className="text-button" aria-pressed={diff} onClick={() => setDiff(!diff)}><Columns2 size={14} />{diff ? 'Source' : 'Compare'}</button>}
        <button className="icon-button" aria-label="Copy source" title="Copy source" onClick={async () => { try { await navigator.clipboard.writeText(file.content); notify('Source copied to clipboard.'); } catch { notify('Clipboard unavailable. Download the source instead.'); } }}><Copy size={15} /></button>
        <button className="icon-button" aria-label="Download source" title="Download source" onClick={() => { downloadText(file.content, file.path.split('/').pop() || 'source.txt'); notify('Source downloaded.'); }}><Download size={15} /></button>
        <button className="icon-button" aria-label={expanded ? 'Exit expanded editor' : 'Expand editor'} title="Expand editor" onClick={() => setExpanded(!expanded)}>{expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button>
      </div></div>
      <div className="code-search"><Search size={14} /><input aria-label="Search in code" placeholder="Find in file…" value={query} onChange={event => { setQuery(event.target.value); setMatch(0); }} onKeyDown={event => { if (event.key === 'Enter') setMatch(value => value + 1); }} /><span>{query ? `${matches.length ? match % matches.length + 1 : 0} / ${matches.length}` : ''}</span>{query && <button className="text-button" disabled={!matches.length} onClick={() => setMatch(value => value + 1)}>Next</button>}</div>
      {diff && before ? <div className="diff-grid"><div><h3>Before</h3><div className="code-view" tabIndex={0} aria-label="Original source">{before.map((line, i) => sourceRow(line, i, true))}</div></div><div><h3>After</h3><div className="code-view" tabIndex={0} aria-label="Updated source">{lines.map((line, i) => sourceRow(line, i))}</div></div></div> : <div className="code-view" tabIndex={0} aria-label={`${file.path} source code`}>{lines.map((line, i) => sourceRow(line, i))}</div>}
      <div className="source-statusbar"><span>Read-only · Original source</span><span>{file.path}<span className="meta-divider" />UTF-8</span></div>
    </div>
  </div>;
}
