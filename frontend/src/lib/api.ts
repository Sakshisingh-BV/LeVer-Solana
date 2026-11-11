import type { PropertyEntry, RunHandle, RunInput, TargetCapability } from '../types/run';

/**
 * Transport layer for the LeVer FastAPI backend. `generation.ts` is the
 * central API layer the UI talks to; this module only knows URLs and JSON.
 * `/api` is proxied to http://127.0.0.1:8000 by vite.config.ts in development.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) { super(message); this.name = 'ApiError'; this.status = status; }
}

/** Extract FastAPI's `{detail}` (string or validation list) from an error response. */
export async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.clone().json();
    const detail = body?.detail ?? body?.message;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map(item => (typeof item?.msg === 'string' ? item.msg : JSON.stringify(item))).join('; ');
  } catch { /* not JSON */ }
  return `The backend returned HTTP ${response.status}.`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(API_BASE + path, { ...init, headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers } });
  } catch (error) {
    if (init.signal?.aborted) throw init.signal.reason;
    throw new ApiError('Could not reach the LeVer backend. Start the API (python -m api in LeVer/) and try again.');
  }
  if (!response.ok) throw new ApiError(await readErrorDetail(response), response.status);
  if (!response.headers.get('content-type')?.includes('application/json')) throw new ApiError('The backend did not return JSON. Check the API URL.', response.status);
  return response.json() as Promise<T>;
}

export interface HealthResponse { status: string; service: string; version: string; active_runs: number; llm: { model: string; base_url: string; api_key_configured: boolean } }
export interface CapabilitiesResponse { targets: TargetCapability[]; modes: { id: string; cli: string }[]; llm: HealthResponse['llm'] }
export interface PropertiesResponse { target: string; count: number; properties: PropertyEntry[] }
export interface ApiRunSummary {
  run_id: string; name: string; target: string; mode: string; cli_mode: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string; finished_at?: string | null; current_stage?: string | null; error?: string | null; result?: unknown;
}

export const api = {
  health: (signal?: AbortSignal) => request<HealthResponse>('/health', { signal }),
  capabilities: (signal?: AbortSignal) => request<CapabilitiesResponse>('/capabilities', { signal }),
  properties: (target?: string, signal?: AbortSignal) => request<PropertiesResponse>(`/properties${target && target !== 'all' ? `?target=${encodeURIComponent(target)}` : ''}`, { signal }),
  /** The backend accepts the UI `RunInput` as-is and maps `lean` -> CLI `lean_only`. */
  createRun: (input: RunInput, signal?: AbortSignal) => request<RunHandle & { run: ApiRunSummary }>('/runs', { method: 'POST', body: JSON.stringify(input), signal }),
  getRun: (id: string, signal?: AbortSignal) => request<ApiRunSummary>('/runs/' + encodeURIComponent(id), { signal }),
  listRuns: (signal?: AbortSignal) => request<{ items: ApiRunSummary[] }>('/runs', { signal }),
  cancelRun: (id: string) => request<ApiRunSummary>('/runs/' + encodeURIComponent(id) + '/cancel', { method: 'POST' }),
  eventsUrl: (id: string) => `${API_BASE}/runs/${encodeURIComponent(id)}/events`,
};
