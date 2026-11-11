import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, FileCode2, Plus, Search } from 'lucide-react';
import { StatusPill, TargetIcon } from '../components/ui';
import { modeLabels, targetLabels } from '../types/run';
import type { Run } from '../types/run';

export default function RunHistoryPage({ runs, contractsOnly = false }: { runs: Run[]; contractsOnly?: boolean }) {
  const [search, setSearch] = useState('');
  const [target, setTarget] = useState('all');
  const query = search.trim().toLowerCase();
  const available = contractsOnly ? runs.filter(run => run.result?.files.length) : runs;
  const filtered = available.filter(run => (target === 'all' || run.target === target) && `${run.name} ${run.requirement} ${run.target} ${run.mode}`.toLowerCase().includes(query));
  return <>
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" />{contractsOnly ? 'GENERATED CODE' : 'ANALYSIS HISTORY'}</div><h1>{contractsOnly ? <>Your ideas, <em>in code.</em></> : <>A record of <em>every run.</em></>}</h1><p>{contractsOnly ? 'Source files returned by your generation pipeline.' : `${runs.length} ${runs.length === 1 ? 'analysis' : 'analyses'} in this browser’s workspace.`}</p></div><Link className="button primary" to="/build"><Plus size={16} />New build</Link></div>
    <div className="history-toolbar"><div className="filter-tabs" role="group" aria-label="Filter by ecosystem">{['all', 'solidity', 'solana'].map(value => <button key={value} className={target === value ? 'active' : ''} aria-pressed={target === value} onClick={() => setTarget(value)}>{value === 'all' ? 'All analyses' : value === 'solidity' ? 'Solidity' : 'Solana'}</button>)}</div><label className="search-field"><Search size={16} /><input placeholder="Find an analysis…" aria-label="Search analyses by name, ecosystem, or mode" value={search} onChange={event => setSearch(event.target.value)} /></label></div>
    <div className="history-list">
      <div className="history-columns"><span>PROJECT / CODE</span><span>ECOSYSTEM / MODE</span><span>STATUS</span><span /></div>
      {filtered.map(run => <Link className="history-item" key={run.id} to={'/runs/' + run.id}><div className="history-name"><span className="experiment-icon"><FileCode2 size={19} /></span><div><strong>{run.name}</strong><small>{run.id.startsWith('sample-') ? 'Sample analysis' : new Date(run.createdAt).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}<span>· Demo</span></small></div></div><div className="history-target"><div><TargetIcon target={run.target} /><span>{targetLabels[run.target]}</span></div><small><code className="mode-code">{modeLabels[run.mode]}</code></small></div><StatusPill status={run.status} /><ArrowUpRight className="row-arrow" size={17} /></Link>)}
      {!filtered.length && <div className="empty-state"><Search size={28} /><h2>{runs.length ? 'No matching analyses.' : 'Your first build starts here.'}</h2><p>{runs.length ? 'Try another name, ecosystem, or mode.' : 'Describe what you want to build to start.'}</p>{runs.length ? <button className="button secondary" onClick={() => { setSearch(''); setTarget('all'); }}>Clear filters</button> : <Link className="button primary" to="/build">New build<ArrowRight size={16} /></Link>}</div>}
    </div>
    <p className="data-caption">Stored in this browser · Latest 50 analyses. Sample previews are kept separate from your history.</p>
  </>;
}
