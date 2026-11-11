import { useLayoutEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, CircleAlert, Code2, Download, FileText, ListChecks, RotateCcw, ShieldCheck, Square, Terminal } from 'lucide-react';
import { StatusPill, TargetIcon, downloadText } from '../components/ui';
import { AnimatedDisclosure } from '../components/AnimatedDisclosure';
import { CodeViewer } from '../components/CodeViewer';
import { targetLabels } from '../types/run';
import type { Run, RunInput } from '../types/run';

const tabs = [{ id: 'source', label: 'Generated Code', icon: Code2 }, { id: 'specification', label: 'Specification', icon: FileText }, { id: 'verification', label: 'Verification', icon: ShieldCheck }, { id: 'issues', label: 'Issues & Fixes', icon: CircleAlert }, { id: 'logs', label: 'Execution Logs', icon: Terminal }, { id: 'summary', label: 'Summary', icon: ListChecks }];
export default function RunDetailPage({ runs, preview, onCancel, onRetry, notify }: { runs: Run[]; preview?: Run; onCancel: (id: string) => void; onRetry: (input: RunInput) => void; notify: (message: string) => void }) {
  const { id } = useParams();
  const run = preview || runs.find(item => item.id === id);
  const [tab, setTab] = useState('source');
  const [codeLocation, setCodeLocation] = useState<{ file: string; line: number; endLine?: number }>();
  const tablist = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });
  useLayoutEffect(() => {
    const update = () => { const button = tablist.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]'); if (button) setIndicator({ left: button.offsetLeft, width: button.offsetWidth }); };
    update(); const observer = new ResizeObserver(update); if (tablist.current) observer.observe(tablist.current);
    return () => observer.disconnect();
  }, [tab, run?.id]);
  if (!run) return <div className="empty-state"><FileText size={30} /><h1>Analysis not found.</h1><p>This run is not saved in this browser.</p><Link className="button primary" to="/runs">Back to history<ArrowRight size={16} /></Link></div>;
  const result = run.result;
  const logs = [...(run.logs || []), ...(result?.logs || [])];
  const running = run.status === 'running' && !preview;
  const verification = result?.verification;
  return <>
    <Link className="text-link back-link" to={preview ? '/' : '/runs'}><ArrowLeft size={14} />{preview ? 'Back to studio' : 'Analysis history'}</Link>
    <div className="page-heading detail-heading"><div><div className="eyebrow"><span className="eyebrow-line" />{preview ? 'WORKSPACE PREVIEW' : 'CODE WORKSPACE'}</div><h1>{run.name}<span className="serif-dot">.</span></h1><div className="detail-meta"><span><TargetIcon target={run.target} />{targetLabels[run.target]}</span><span className="meta-divider" /><code className="mode-code">{run.mode}</code><span className="quiet-badge">{result?.files.length || 0} source files</span></div></div><div className="detail-actions"><Link className="button secondary" to="/build" state={{ draft: run }}><RotateCcw size={14} />Edit requirement</Link>{result?.report && <button className="button primary" onClick={() => { downloadText(result.report!.content, result.report!.filename, result.report!.mimeType); notify('Report downloaded.'); }}><Download size={15} />Download report</button>}</div></div>
    {preview ? <div className="preview-notice"><CircleAlert size={16} /><span>Sample workspace · Illustrative source for exploring the interface. No code was generated or verified.</span><Link to={run.target === 'solidity' ? '/preview/solana' : '/preview/solidity'}>{run.target === 'solidity' ? 'Preview Solana' : 'Preview Solidity'}<ArrowRight size={14} /></Link></div> : <section className={`progress-panel ${run.status}`} aria-label="Execution status" aria-live="polite"><div className="progress-topline"><div><StatusPill status={run.status} /><span className="progress-stage">{running ? run.currentStage || 'Waiting for the generation service…' : run.status === 'completed' ? 'The backend returned this run’s output.' : run.status === 'cancelled' ? 'Stopped waiting for this request.' : 'This analysis could not run.'}</span></div>{running && <button className="text-button" onClick={() => onCancel(run.id)}><Square size={12} />Stop waiting</button>}</div>
      {running && <div className="indeterminate" role="progressbar" aria-label="Generation in progress"><span /></div>}
      {run.error && <div className="run-error" role="alert"><CircleAlert size={18} /><div><p>{run.error}</p><button className="text-button" onClick={() => onRetry(run)}><RotateCcw size={13} />Retry analysis</button></div></div>}
      {run.status === 'completed' && <div className="completion-note"><Check size={16} />{result?.files.length ? 'Source received' : 'No source files returned'}<span>Verification: {verification?.status || 'not provided'}</span></div>}
      <AnimatedDisclosure title="Submitted requirement"><p className="preserve-text">{run.requirement}</p></AnimatedDisclosure>
    </section>}
    <section className="results-panel"><div className="result-tab-scroll"><div ref={tablist} className="workspace-tabs" role="tablist" aria-label="Analysis results"><span className="tab-indicator" style={{ left: indicator.left, width: indicator.width }} />{tabs.map(item => <button role="tab" id={`tab-${item.id}`} aria-selected={tab === item.id} aria-controls="result-content" tabIndex={tab === item.id ? 0 : -1} key={item.id} onClick={() => setTab(item.id)} onKeyDown={event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault(); const index = tabs.findIndex(value => value.id === tab); const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        setTab(tabs[next].id); document.getElementById(`tab-${tabs[next].id}`)?.focus();
      }}><item.icon size={14} />{item.label}</button>)}</div></div>
      <div id="result-content" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0} className="result-pane" key={tab}>
        {tab === 'source' && <CodeViewer files={result?.files || []} location={codeLocation} notify={notify} />}
        {tab === 'specification' && (result?.specification ? <div className="overview-content preserve-text">{result.specification}</div> : <Empty title="No specification returned" description="The generated specification will appear here when available." />)}
        {tab === 'verification' && (verification ? <div className="overview-content"><div className="verification-heading"><ShieldCheck size={24} /><h2>Verification: {verification.status}</h2></div>{verification.detail && <p className="result-policy-note">{verification.detail}</p>}<div className="check-table">{verification.checks.map((check, i) => <div className="check-row" key={i}><div><strong>{check.name}</strong><small>{check.detail}</small></div><span className={`check-status ${check.status}`}>{check.status}</span></div>)}</div></div> : <Empty title="Verification not provided" description="Code generation and verification are separate outcomes. No verification evidence has been returned." />)}
        {tab === 'issues' && (result?.issues?.length ? <div className="overview-content issue-list">{result.issues.map(issue => <article className="issue-card" key={issue.id}><div><h3>{issue.title}</h3>{issue.severity && <span className="quiet-badge">{issue.severity}</span>}</div><p>{issue.description}</p>{issue.suggestion && <AnimatedDisclosure title="Suggested fix"><p className="preserve-text">{issue.suggestion}</p></AnimatedDisclosure>}{issue.file && issue.line && result.files.some(file => file.path === issue.file) && <button className="text-button" onClick={() => { setCodeLocation({ file: issue.file!, line: issue.line!, endLine: issue.endLine }); setTab('source'); }}>{issue.file}:{issue.line}<ArrowRight size={13} /></button>}</article>)}</div> : <Empty title="No issues supplied" description="No issue data was returned. This does not establish that the code is issue-free." />)}
        {tab === 'logs' && <div className="overview-content"><AnimatedDisclosure title={`Execution logs · ${logs.length} entries`} initialOpen>{logs.length ? <div className="execution-logs">{logs.map((log, i) => <div className={`execution-log ${log.level}`} key={i}>{log.timestamp && <time>{log.timestamp}</time>}<span>{log.level}</span><code>{log.message}</code></div>)}</div> : <p className="muted">No execution logs have been returned.</p>}</AnimatedDisclosure></div>}
        {tab === 'summary' && <div className="overview-content"><h2>Run summary</h2><dl className="summary-list"><div><dt>Ecosystem</dt><dd>{targetLabels[run.target]}</dd></div><div><dt>Execution mode</dt><dd>{run.mode}</dd></div><div><dt>Request status</dt><dd>{preview ? 'Sample preview' : run.status}</dd></div><div><dt>Source files</dt><dd>{result?.files.length || 0}</dd></div><div><dt>Verification</dt><dd>{verification?.status || 'Not provided'}</dd></div></dl>{result?.summary ? <p className="preserve-text">{result.summary}</p> : <p className="muted">No backend summary has been returned.</p>}<Link className="button secondary" to="/build">New generation<ArrowRight size={14} /></Link></div>}
      </div>
    </section>
  </>;
}
function Empty({ title, description }: { title: string; description: string }) { return <div className="empty-state"><FileText size={28} /><h2>{title}</h2><p>{description}</p></div>; }
