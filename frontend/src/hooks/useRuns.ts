import { useCallback, useEffect, useRef, useState } from 'react';
import { assertResult, executeGeneration, generationAdapter } from '../lib/generation';
import type { GenerationAdapter, ProgressEvent } from '../lib/generation';
import type { Run, RunInput } from '../types/run';

const STORAGE_KEY = 'lever.runs.v2';
/** Abort reason used on unmount so a React StrictMode remount can re-attach instead of marking runs cancelled. */
const UNMOUNT = Symbol('unmount');

function loadRuns(): Run[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    if (!Array.isArray(value)) return [];
    return value.filter((run): run is Run => {
      if (!run || run.isDemo || typeof run.id !== 'string' || typeof run.name !== 'string' || typeof run.requirement !== 'string' || !['solidity', 'solana'].includes(run.target) || !['no_lean', 'lean', 'full'].includes(run.mode) || !['running', 'completed', 'failed', 'cancelled'].includes(run.status) || !Number.isFinite(Date.parse(run.createdAt))) return false;
      try { if (run.result) assertResult(run.result, run.target); return true; } catch { return false; }
    }).slice(0, 50).map(run => run.status === 'running' && !run.serverRunId ? { ...run, status: 'failed', error: 'This browser session was interrupted before the backend accepted the run. Check the backend before retrying.' } : run);
  } catch { return []; }
}

export function useRuns(adapter: GenerationAdapter = generationAdapter) {
  const [runs, setRuns] = useState<Run[]>(loadRuns);
  const [storageWarning, setStorageWarning] = useState(false);
  const active = useRef(new Map<string, AbortController>());
  const latest = useRef(runs);
  latest.current = runs;
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(runs)); setStorageWarning(false); }
    catch { setStorageWarning(true); }
  }, [runs]);

  const patch = useCallback((id: string, update: (run: Run) => Run) => {
    setRuns(current => current.map(item => item.id === id && item.status === 'running' ? update(item) : item));
  }, []);

  /** Start tracking a run: either a fresh generation or a resume of a backend run. */
  const track = useCallback((id: string, input: RunInput, resumeRunId?: string) => {
    const controller = new AbortController();
    active.current.set(id, controller);
    const onProgress = (event: ProgressEvent) => patch(id, item => ({ ...item, currentStage: event.stage ?? item.currentStage, logs: event.log ? [...(item.logs || []), event.log].slice(-2000) : item.logs }));
    void executeGeneration(input, adapter, controller.signal, onProgress, {
      resumeRunId,
      onRunId: serverRunId => patch(id, item => ({ ...item, serverRunId })),
    }).then(result => {
      patch(id, item => ({ ...item, status: 'completed', result }));
    }).catch((error: unknown) => {
      if (controller.signal.reason === UNMOUNT) return;
      patch(id, item => ({ ...item, status: controller.signal.aborted ? 'cancelled' : 'failed', error: error instanceof Error ? error.message : 'Generation failed. Please retry.' }));
    }).finally(() => { if (active.current.get(id) === controller) active.current.delete(id); });
  }, [adapter, patch]);

  // Re-attach to backend runs that were still executing when the page was last closed.
  useEffect(() => {
    const map = active.current;
    for (const run of latest.current) if (run.status === 'running' && run.serverRunId && !map.has(run.id)) track(run.id, run, run.serverRunId);
    return () => { for (const controller of map.values()) controller.abort(UNMOUNT); map.clear(); };
  }, [track]);

  const startRun = useCallback((input: RunInput) => {
    const running = latest.current.find(run => run.status === 'running' && active.current.has(run.id));
    if (running) return running.id;
    if (!input.requirement.trim() || !input.name.trim() || !['solidity', 'solana'].includes(input.target) || !['no_lean', 'lean', 'full'].includes(input.mode)) throw new Error('Add requirements and choose a valid ecosystem and mode.');
    const id = crypto.randomUUID();
    const run: Run = { ...input, id, createdAt: new Date().toISOString(), status: 'running', stage: 0, logs: [] };
    setRuns(current => [run, ...current].slice(0, 50));
    track(id, input);
    return id;
  }, [track]);

  const cancelRun = useCallback((id: string) => {
    active.current.get(id)?.abort(new Error('Stopped waiting. The backend was asked to cancel this run.'));
    const serverRunId = latest.current.find(run => run.id === id)?.serverRunId;
    if (serverRunId) void adapter.cancel?.(serverRunId);
  }, [adapter]);

  return { runs, startRun, cancelRun, storageWarning };
}
