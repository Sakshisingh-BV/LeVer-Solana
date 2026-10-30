import type { RunInput } from '../types/run';

// Integration boundary for a future FastAPI service. The current UI uses useDemoRuns.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
// Keep the requested UI names separate from the proposed service's mode names.
const apiModes = { no_lean: 'dynamic_only', lean: 'formal_only', full: 'full' } as const;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!response.ok) throw new Error(`API request failed (${response.status}).`);
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new Error('The backend did not return JSON. Check the API URL.');
  }
  return response.json() as Promise<T>;
}

export interface ApiRun {
  run_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  result?: unknown;
}
export const api = {
  capabilities: () => request<{ targets: { target: string; available: boolean }[] }>('/capabilities'),
  createRun: (input: RunInput) => request<ApiRun>('/runs', {
    method: 'POST',
    body: JSON.stringify({ name: input.name, requirement: input.requirement, target: input.target, mode: apiModes[input.mode], max_iterations: input.maxIterations, attack_rounds: input.attackRounds }),
  }),
  getRun: (id: string) => request<ApiRun>('/runs/' + encodeURIComponent(id)),
  listRuns: () => request<{ items: ApiRun[] }>('/runs'),
};
