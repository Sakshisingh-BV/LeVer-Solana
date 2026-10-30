import { useId, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, Check, ChevronDown, Code2, FileText, Sparkles, Upload } from 'lucide-react';
import { examples } from '../data/examples';
import { executionModes } from '../data/modes';
import { TargetIcon } from '../components/ui';
import { generationConfigured } from '../lib/generation';
import '../components/mode-motion.css';
import type { RunInput, Target, VerificationMode } from '../types/run';

export default function NewRunPage({ onRun, notify, embedded = false }: { onRun: (input: RunInput) => void; notify: (message: string) => void; embedded?: boolean }) {
  const location = useLocation();
  const draft = (location.state as { draft?: RunInput } | null)?.draft;
  const [requirement, setRequirement] = useState(draft?.requirement || '');
  const [target, setTarget] = useState<Target>(draft?.target || 'solidity');
  const [mode, setMode] = useState<VerificationMode>(draft?.mode || 'full');
  const [detail, setDetail] = useState<VerificationMode | null>(null);
  const modeDetailsId = useId();
  const [error, setError] = useState('');
  const upload = useRef<HTMLInputElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  async function importFile(file?: File) {
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name) || file.size > 80_000) { notify('Choose a .txt or .md file smaller than 80 KB.'); return; }
    try { const text = await file.text(); if (text.length > 20_000) { notify('Keep requirements under 20,000 characters.'); return; } setRequirement(text); setError(''); notify('Requirement imported.'); } catch { notify('Could not read this file. Try another text file.'); }
  }
  return <div className={`contract-builder ${embedded ? 'embedded-builder' : ''}`}>
    <div className="section-heading"><span className="section-kicker"><span/>THE BUILDER</span><h2>Your next contract starts here.</h2><p>Choose your approach. Pick your ecosystem. Tell LeVer what you have in mind.</p></div>
    <form noValidate onSubmit={event => {
      event.preventDefault();
      if (!['solidity', 'solana'].includes(target) || !executionModes.some(option => option.id === mode)) { setError('Choose an ecosystem and execution mode.'); return; }
      if (!requirement.trim()) { setError('Describe what your smart contract should do before continuing.'); editor.current?.focus(); return; }
      onRun({ name: draft?.name || requirement.trim().split(/[.!?\n]/)[0].slice(0, 70) || 'Untitled contract', requirement: requirement.trim(), target, mode, maxIterations: draft?.maxIterations || 3, attackRounds: draft?.attackRounds || 3 });
    }}>
      <section className="builder-step" id="modes"><div className="builder-step-title"><span>01</span><h3>Choose Your Execution Mode</h3><span className="step-aside">YOUR WORKFLOW, YOUR CHOICE</span></div><div className="execution-modes" role="group" aria-label="Execution mode">{executionModes.map(option => <div key={option.id} className={`execution-card ${mode === option.id ? 'selected' : ''}`}><button type="button" className="mode-select" aria-pressed={mode === option.id} onClick={() => setMode(option.id)}><div className="execution-card-top"><option.icon size={22}/><span className="mode-check" aria-hidden="true"><Check size={11}/></span></div><h4>{option.name}{option.id === 'full' && <span>COMPLETE PIPELINE</span>}</h4><p>{option.description}</p></button><button type="button" className="mode-learn" aria-expanded={detail === option.id} aria-controls={`${modeDetailsId}-${option.id}`} onClick={() => setDetail(detail === option.id ? null : option.id)}>Learn more<ChevronDown size={12}/></button><div id={`${modeDetailsId}-${option.id}`} className={`mode-detail-reveal ${detail === option.id ? 'is-open' : ''}`} aria-hidden={detail !== option.id} inert={detail !== option.id}><div><p className="mode-detail">{option.detail}</p></div></div></div>)}</div></section>
      <section className="builder-step"><div className="builder-step-title"><span>02</span><h3>Choose Your Blockchain Ecosystem</h3><span className="step-aside">ONE UNIFIED PLATFORM</span></div><div className="ecosystem-cards" role="group" aria-label="Blockchain ecosystem">{(['solidity', 'solana'] as const).map(value => <button type="button" key={value} className={`ecosystem-card ${target === value ? 'selected' : ''}`} aria-pressed={target === value} onClick={() => setTarget(value)}><span className={`ecosystem-logo ${value}`}><TargetIcon target={value}/></span><span><strong>{value === 'solidity' ? 'Ethereum' : 'Solana'}</strong><small>{value === 'solidity' ? 'Solidity · EVM Smart Contracts' : 'Rust · Solana Programs'}</small></span><span className="ecosystem-selection">{target === value ? <><Check size={12}/><span>Selected</span></> : <span className="empty-radio"/>}</span></button>)}</div></section>
      <section className="builder-step requirement-step"><div className="builder-step-title"><span>03</span><h3><label htmlFor="requirement">What Would You Like to Build?</label></h3><button type="button" className="import-brief" onClick={() => upload.current?.click()}><Upload size={13}/>Import brief</button><input ref={upload} className="visually-hidden" tabIndex={-1} type="file" accept=".txt,.md,text/plain,text/markdown" aria-label="Import requirement file" onChange={event => { void importFile(event.target.files?.[0]); event.target.value = ''; }}/></div>
        <div className={`prompt-panel ${error ? 'has-error' : ''}`}><div className="prompt-topline"><span><FileText size={14}/>YOUR REQUIREMENTS</span><span>Plain English. Powerful possibilities.</span></div><textarea ref={editor} id="requirement" maxLength={20_000} value={requirement} onChange={event => { setRequirement(event.target.value); setError(''); }} aria-invalid={!!error} aria-describedby={error ? 'requirement-error' : 'prompt-help'} placeholder={'Describe your smart contract requirements in plain English...\n\nFor example: Create a token vault where users can deposit tokens, but only the owner can withdraw them.'}/><div className="prompt-bottomline"><span id="prompt-help">Be specific about actions, permissions, and rules.</span><span>{requirement.length.toLocaleString()} / 20,000</span></div></div>
        <div className="builder-examples"><span>TRY AN IDEA</span>{examples.slice(0, 3).map(example => <button type="button" key={example.id} onClick={() => { setRequirement(example.requirement); setError(''); editor.current?.focus(); }}><Code2 size={12}/>{example.name}<ArrowUpRight size={11}/></button>)}</div>
        {error && <p id="requirement-error" className="form-error" role="alert">{error}</p>}
        <div className="generate-row"><div className="selected-summary"><span><TargetIcon target={target}/>{target === 'solidity' ? 'Ethereum' : 'Solana'}</span><span>+</span><span>{executionModes.find(item => item.id === mode)?.name} mode</span></div><button className="button primary generate-button" type="submit"><Sparkles size={16}/>Generate Smart Contract<ArrowRight size={16}/></button></div>
        <div className="builder-service-note"><span><span className={generationConfigured ? 'service-dot' : 'service-dot offline'}/>{generationConfigured ? 'Generation endpoint configured' : 'Connect your backend to generate contracts'}</span><Link to={`/preview/${target}`}>Explore sample output<ArrowUpRight size={12}/></Link></div>
      </section>
    </form>
  </div>;
}
