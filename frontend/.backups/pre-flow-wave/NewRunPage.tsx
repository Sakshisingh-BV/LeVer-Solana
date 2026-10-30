import { useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, Check, Code2, FileText, Layers3, ShieldCheck, Sparkles, Swords, Upload } from 'lucide-react';
import { examples } from '../data/examples';
import { TargetIcon } from '../components/ui';
import { AnimatedDisclosure } from '../components/AnimatedDisclosure';
import type { RunInput, Target, VerificationMode } from '../types/run';

const modes = [
  { id: 'no_lean' as const, detail: 'Dynamic tests & security analysis', icon: Swords },
  { id: 'lean' as const, detail: 'Formal verification path', icon: ShieldCheck },
  { id: 'full' as const, detail: 'Formal checks + dynamic testing', icon: Layers3 },
];
const staking = { id: 'staking', name: 'Token staking', requirement: 'Create a staking smart contract where users can stake tokens, earn rewards, and withdraw their staked tokens. Only the admin can update reward parameters.' };
const startingPoints = [staking, ...examples.slice(1)];
export default function NewRunPage({ onRun, notify }: { onRun: (input: RunInput) => void; notify: (message: string) => void }) {
  const location = useLocation();
  const draft = (location.state as { draft?: RunInput } | null)?.draft;
  const [name, setName] = useState(draft?.name || '');
  const [requirement, setRequirement] = useState(draft?.requirement || '');
  const [target, setTarget] = useState<Target>(draft?.target || 'solidity');
  const [mode, setMode] = useState<VerificationMode>(draft?.mode || 'full');
  const [maxIterations, setMaxIterations] = useState(draft?.maxIterations || 3);
  const [attackRounds, setAttackRounds] = useState(draft?.attackRounds || 3);
  const [selectedExample, setSelectedExample] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const upload = useRef<HTMLInputElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const submitLock = useRef(false);
  async function importFile(file?: File) {
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name) || file.size > 80_000) { notify('Choose a .txt or .md file smaller than 80 KB.'); return; }
    try { const text = await file.text(); if (text.length > 20_000) { notify('Keep requirements under 20,000 characters.'); return; } setRequirement(text); setSelectedExample(null); setError(''); notify('Requirement imported.'); } catch { notify('Could not read this file. Try another text file.'); }
  }
  return <>
    <div className="page-heading studio-heading"><div><div className="eyebrow"><span className="eyebrow-pill"><Sparkles size={12} />YOUR IDEAS. VERIFIED POSSIBILITIES.</span></div><h1>From plain English.<br /><em>To on-chain.</em></h1><p>Describe your vision. Generate your contract. Verify what matters.</p></div><Link className="text-link heading-link" to={`/preview/${target}`}>Explore a sample workspace<ArrowUpRight size={16} /></Link></div>
    <form className="studio-layout" noValidate onSubmit={event => {
      event.preventDefault();
      if (submitLock.current) return;
      if (!requirement.trim()) { setError('Describe what your smart contract should do before continuing.'); editor.current?.focus(); return; }
      if (!['solidity', 'solana'].includes(target) || !modes.some(option => option.id === mode)) { setError('Choose an ecosystem and execution mode.'); return; }
      if (!Number.isInteger(maxIterations) || maxIterations < 1 || maxIterations > 10 || (mode !== 'lean' && (!Number.isInteger(attackRounds) || attackRounds < 1 || attackRounds > 10))) { setError('Run limits must be whole numbers between 1 and 10.'); return; }
      submitLock.current = true; setSubmitting(true);
      onRun({ name: name.trim() || 'Untitled contract', requirement: requirement.trim(), target, mode, maxIterations, attackRounds: mode === 'lean' ? 3 : attackRounds });
      submitLock.current = false; setSubmitting(false);
    }}>
      <div className="brief-column"><section className="brief-panel">
        <div className="panel-title"><div><span className="section-index"><FileText size={16} /></span><h2>Describe Your Smart Contract</h2></div><span className="subtle-label">01 / REQUIREMENTS</span></div>
        <div className="brief-fields"><div className="name-field"><label className="field-label" htmlFor="contract-name">Contract name <span className="optional-label">Optional</span></label><input id="contract-name" className="name-input" value={name} maxLength={80} onChange={event => setName(event.target.value)} placeholder="Give your idea a name" /></div>
          <div className="requirement-label"><label className="field-label" htmlFor="requirement">Your requirements</label><button type="button" className="text-button" onClick={() => upload.current?.click()}><Upload size={13} />Import brief</button><input ref={upload} className="visually-hidden" tabIndex={-1} type="file" accept=".txt,.md,text/plain,text/markdown" aria-label="Import requirement file" onChange={event => { void importFile(event.target.files?.[0]); event.target.value = ''; }} /></div>
          <div className={`editor-surface ${error ? 'has-error' : ''}`}><textarea ref={editor} id="requirement" className="requirement-editor" value={requirement} maxLength={20_000} onChange={event => { setRequirement(event.target.value); setSelectedExample(null); setError(''); }} aria-invalid={!!error} aria-describedby={error ? 'requirement-error' : 'requirement-help'} spellCheck={false} placeholder="Describe what your smart contract should do in plain English..." /><div className="editor-footer"><span><span className="editor-status-dot" />Natural language, powerful outcomes</span><span>{requirement.length.toLocaleString()} / 20,000</span></div></div>
          <p id="requirement-help" className="editor-help">Define permissions, actions, and the rules your contract should always follow.</p>
        </div>
        <div className="example-section"><span className="field-label">NEED A STARTING POINT?</span><div className="example-options">{startingPoints.map(example => <button type="button" className={selectedExample === example.id ? 'selected' : ''} aria-pressed={selectedExample === example.id} key={example.id} onClick={() => { setName(example.name); setRequirement(example.requirement); setSelectedExample(example.id); setError(''); }}>{selectedExample === example.id ? <Check size={13} /> : <Code2 size={13} />}{example.name}<ArrowUpRight size={12} /></button>)}</div></div>
      </section>
      <section className="workflow-preview"><div className="workflow-heading"><span className="tiny-label">ONE CONNECTED WORKFLOW</span><span>From intent to evidence</span></div><div className="workflow-steps"><span><FileText size={15} />Describe</span><ArrowRight size={12} /><span><Code2 size={15} />Generate</span><ArrowRight size={12} /><span><ShieldCheck size={15} />Verify</span><ArrowRight size={12} /><span><Layers3 size={15} />Inspect</span></div></section>
      <div className="brief-note"><ShieldCheck size={17} /><p>Clarity is your first security layer.<br /><strong>Specific requirements make the output easier to assess.</strong></p><Link to="/docs">Writing a good brief<ArrowUpRight size={13} /></Link></div></div>
      <section className="config-panel"><div className="panel-title"><div><span className="section-index"><Layers3 size={16} /></span><h2>Configure your build</h2></div><span className="subtle-label">02</span></div>
        <div className="config-body"><span className="field-label">Choose your ecosystem</span><div className="target-options" role="group" aria-label="Contract ecosystem">{(['solidity', 'solana'] as const).map(value => <button type="button" key={value} className={`target-option ${target === value ? 'selected' : ''}`} aria-pressed={target === value} onClick={() => setTarget(value)}><div><TargetIcon target={value} /><span className="selection-dot">{target === value && <Check size={10} />}</span></div><strong>{value === 'solidity' ? 'Solidity (EVM)' : 'Solana'}</strong><small>{value === 'solidity' ? 'Ethereum-compatible' : 'Solana programs'}</small><span className="extension-badge">{value === 'solidity' ? '.sol' : '.rs'}</span></button>)}</div>
          <fieldset className="mode-options"><legend className="field-label">Execution mode</legend>{modes.map(option => <label className={`mode-option ${mode === option.id ? 'selected' : ''}`} key={option.id}><input type="radio" name="mode" value={option.id} checked={mode === option.id} onChange={() => setMode(option.id)} /><option.icon size={17} /><span><strong className="mode-code">{option.id}{option.id === 'full' && <span className="mode-tag">ALL CHECKS</span>}</strong><small>{option.detail}</small></span><span className="radio-mark" /></label>)}</fieldset>
          <AnimatedDisclosure title="Advanced options"><div className="limit-fields"><label>Max iterations<input aria-label="Max iterations" type="number" min="1" max="10" step="1" value={Number.isNaN(maxIterations) ? '' : maxIterations} onChange={event => setMaxIterations(event.target.valueAsNumber)} /></label><label>Attack rounds<input aria-label="Attack rounds" type="number" min="1" max="10" step="1" value={Number.isNaN(attackRounds) ? '' : attackRounds} disabled={mode === 'lean'} onChange={event => setAttackRounds(event.target.valueAsNumber)} /></label></div><p className="muted">Checks depend on the connected pipeline. <Link to="/docs">Read mode details.</Link></p></AnimatedDisclosure>
          {error && <p id="requirement-error" className="form-error" role="alert">{error}</p>}
          <button className="button primary run-button" type="submit" disabled={submitting}><Sparkles size={16} />{submitting ? 'Preparing request…' : 'Generate & Verify'}<ArrowRight size={17} /></button><p className="run-caption"><span />Backend connection pending</p>
        </div>
      </section>
    </form>
  </>;
}
