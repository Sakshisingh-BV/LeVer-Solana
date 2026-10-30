import { useEffect, useState } from 'react';
import { sampleRuns } from '../data/examples';
import { stagesFor } from '../types/run';
import type { Run, RunInput } from '../types/run';

const STORAGE_KEY = 'lever.demo-runs.v1';
function validRun(value: unknown): value is Run {
  if (!value || typeof value !== 'object') return false;
  const run = value as Partial<Run>;
  return typeof run.id === 'string' && typeof run.name === 'string' && typeof run.requirement === 'string'
    && typeof run.createdAt === 'string' && !Number.isNaN(Date.parse(run.createdAt)) && run.isDemo === true
    && ['solidity', 'solana'].includes(run.target || '')
    && ['no_lean', 'lean', 'full'].includes(run.mode || '')
    && ['running', 'completed', 'cancelled', 'failed'].includes(run.status || '')
    && Number.isInteger(run.stage) && Number(run.stage) >= 0 && Number(run.stage) <= 5
    && Number.isInteger(run.maxIterations) && Number(run.maxIterations) > 0
    && Number.isInteger(run.attackRounds) && Number(run.attackRounds) > 0;
}
function migrateRun(value: unknown): unknown {
  if (!value || typeof value !== 'object') return value;
  const run = value as Record<string, unknown>;
  if (run.mode === 'dynamic_only') return { ...run, mode: 'no_lean' };
  if (run.mode === 'formal_only' || run.mode === 'lean_only') return { ...run, mode: 'lean' };
  return value;
}
function loadRuns(): Run[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return sampleRuns;
    const parsed: unknown = JSON.parse(saved);
    return Array.isArray(parsed) ? parsed.map(migrateRun).filter(validRun).slice(0, 50) : sampleRuns;
  } catch { return sampleRuns; }
}

export function useDemoRuns() {
  const [runs, setRuns] = useState<Run[]>(loadRuns);
  const [storageWarning, setStorageWarning] = useState(false);
  const isRunning = runs.some(run => run.status === 'running');
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(runs)); setStorageWarning(false); }
    catch { setStorageWarning(true); }
  }, [runs]);
  useEffect(() => {
    if (!isRunning) return;
    const timer = window.setInterval(() => setRuns(current => current.map(run => {
      if (run.status !== 'running') return run;
      const stage = run.stage + 1;
      return { ...run, stage, status: stage >= stagesFor(run.mode).length ? 'completed' : 'running' };
    })), 1350);
    return () => window.clearInterval(timer);
  }, [isRunning]);
  function startRun(input: RunInput) {
    const run: Run = { ...input, id: crypto.randomUUID(), createdAt: new Date().toISOString(), status: 'running', stage: 0, isDemo: true };
    setRuns(current => [run, ...current].slice(0, 50));
    return run.id;
  }
  function cancelRun(id: string) { setRuns(current => current.map(run => run.id === id && run.status === 'running' ? { ...run, status: 'cancelled' } : run)); }
  return { runs, startRun, cancelRun, storageWarning };
}
