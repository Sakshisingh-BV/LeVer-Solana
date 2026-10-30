import { useEffect, useRef } from 'react';
import { Check, X } from 'lucide-react';
import { stagesFor } from '../types/run';
import type { ReactNode } from 'react';
import type { Run, RunStatus, Target, VerificationMode } from '../types/run';

export function TargetIcon({ target }: { target: Target }) {
  return target === 'solidity' ? <svg width="19" height="23" viewBox="0 0 24 38" fill="none" aria-hidden="true"><path d="M12 0 0 20l12 7 12-7L12 0Z" fill="currentColor" opacity=".8"/><path d="M12 0v27l12-7L12 0Z" fill="currentColor" opacity=".55"/><path d="m0 23 12 15 12-15-12 7-12-7Z" fill="currentColor"/><path d="M12 14 0 20l12 7 12-7-12-6Z" fill="currentColor" opacity=".35"/></svg> : <span className="solana-mark" aria-hidden="true"><i /><i /><i /></span>;
}
export function StatusPill({ status }: { status: RunStatus }) {
  return <span className={`status-pill ${status}`}><span className="status-dot" />{{ running: 'In progress', completed: 'Completed', cancelled: 'Stopped', failed: 'Failed' }[status]}</span>;
}
export function StageTrack({ mode, run }: { mode: VerificationMode; run?: Run }) {
  return <ol className={`stage-track ${run ? 'with-run' : ''}`} aria-label={run ? 'Simulated run progress' : 'Pipeline stages'}>
    {stagesFor(mode).map((stage, index) => {
      const done = run && (run.status === 'completed' || run.stage > index);
      const active = run?.status === 'running' && run.stage === index;
      return <li key={stage} className={`${done ? 'done' : ''} ${active ? 'active' : ''}`} aria-current={active ? 'step' : undefined}>
        <span className="stage-node">{done ? <Check size={12} aria-hidden="true" /> : String(index + 1).padStart(2, '0')}</span><span>{stage}</span>
      </li>;
    })}
  </ol>;
}
export function Dialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className="dialog" aria-label={title} onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="dialog-header"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={19} /></button></div>
    {children}
  </dialog>;
}
export function downloadText(content: string, filename: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
