import { useCallback, useEffect, useRef, useState } from 'react';
import { assertResult, executeGeneration, generationAdapter } from '../lib/generation';
import type { GenerationAdapter } from '../lib/generation';
import type { Run, RunInput } from '../types/run';

const STORAGE_KEY = 'lever.runs.v2';
function loadRuns(): Run[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    if (!Array.isArray(value)) return [];
    return value.filter((run): run is Run => {
      if (!run || run.isDemo || typeof run.id !== 'string' || typeof run.name !== 'string' || typeof run.requirement !== 'string' || !['solidity', 'solana'].includes(run.target) || !['no_lean', 'lean', 'full'].includes(run.mode) || !['running', 'completed', 'failed', 'cancelled'].includes(run.status) || !Number.isFinite(Date.parse(run.createdAt))) return false;
      try { if (run.result) assertResult(run.result, run.target); return true; } catch { return false; }
    }).slice(0, 50).map(run => run.status === 'running' ? { ...run, status: 'failed', error: 'This browser session was interrupted. Check the backend before retrying.' } : run);
  } catch { return []; }
}
export function useRuns(adapter: GenerationAdapter = generationAdapter) {
  const [runs, setRuns] = useState<Run[]>(loadRuns);
  const [storageWarning, setStorageWarning] = useState(false);
  const active = useRef<{ id: string; controller: AbortController } | null>(null);
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(runs)); setStorageWarning(false); }
    catch { setStorageWarning(true); }
  }, [runs]);
  useEffect(() => () => { active.current?.controller.abort(); }, []);
  const startRun = useCallback((input: RunInput) => {
    if (active.current) return active.current.id;
    if (!input.requirement.trim() || !input.name.trim() || !['solidity', 'solana'].includes(input.target) || !['no_lean', 'lean', 'full'].includes(input.mode)) throw new Error('Add requirements and choose a valid ecosystem and mode.');
    const id = crypto.randomUUID(), controller = new AbortController();
    const run: Run = { ...input, id, createdAt: new Date().toISOString(), status: 'running', stage: 0, logs: [] };
    active.current = { id, controller };
    setRuns(current => [run, ...current].slice(0, 50));
    void executeGeneration(input, adapter, controller.signal, event => {
      setRuns(current => current.map(item => item.id === id && item.status === 'running' ? { ...item, currentStage: event.stage ?? item.currentStage, logs: event.log ? [...(item.logs || []), event.log] : item.logs } : item));
    }).then(result => {
      setRuns(current => current.map(item => item.id === id && item.status === 'running' ? { ...item, status: 'completed', result } : item));
    }).catch((error: unknown) => {
      setRuns(current => current.map(item => item.id === id && item.status === 'running' ? { ...item, status: controller.signal.aborted ? 'cancelled' : 'failed', error: error instanceof Error ? error.message : 'Generation failed. Please retry.' } : item));
    }).finally(() => { if (active.current?.id === id) active.current = null; });
    return id;
  }, [adapter]);
  const cancelRun = useCallback((id: string) => {
    if (active.current?.id === id) active.current.controller.abort(new Error('Stopped waiting. The backend may still be running.'));
  }, []);
  return { runs, startRun, cancelRun, storageWarning };
}
