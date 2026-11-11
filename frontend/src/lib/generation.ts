import { API_BASE, api, readErrorDetail } from './api';
import type { BackendStatus, ExecutionLog, GenerationResult, PropertyEntry, RunHandle, RunInput, Target } from '../types/run';

/**
 * Central API layer for the UI. Pages and hooks import from here only.
 *
 * Flow (Adapter pattern over the HTTP contract):
 *   POST {endpoint}            -> RunHandle {run_id, events_url}      (FastAPI backend)
 *   GET  {events_url}          -> NDJSON progress | result | error | heartbeat
 * A bridge that answers the POST directly with NDJSON or a GenerationResult JSON is
 * still accepted, so the original single-request contract keeps working.
 */
export interface ProgressEvent { stage?: string; log?: ExecutionLog }
export interface GenerationContext {
  signal: AbortSignal;
  onProgress: (event: ProgressEvent) => void;
  /** Called once the backend has accepted the run, so the UI can re-attach later. */
  onRunId?: (runId: string) => void;
}
export interface GenerationAdapter {
  generate(input: RunInput, context: GenerationContext): Promise<GenerationResult>;
  /** Re-attach to a run the backend is still executing (after a page reload). */
  resume?(runId: string, target: Target, context: GenerationContext): Promise<GenerationResult>;
  /** Ask the backend to stop the pipeline. Best effort. */
  cancel?(runId: string): Promise<void>;
}

export const generationEndpoint = import.meta.env.VITE_GENERATION_URL?.trim() || `${API_BASE}/runs`;
/** Static configuration flag. Live reachability comes from `useBackendStatus`. */
export const generationConfigured = Boolean(generationEndpoint);
export const DEFAULT_GENERATION_TIMEOUT_MS = Number(import.meta.env.VITE_GENERATION_TIMEOUT_MS) || 3_600_000;

function isRunHandle(value: unknown): value is RunHandle {
  return !!value && typeof value === 'object' && typeof (value as RunHandle).run_id === 'string' && !Array.isArray((value as { files?: unknown }).files);
}

export function createHttpAdapter(endpoint: string): GenerationAdapter {
  const base = endpoint.trim().replace(/\/$/, '');
  const eventsUrl = (handle: RunHandle) => handle.events_url || `${base}/${encodeURIComponent(handle.run_id)}/events`;
  return {
    async generate(input, context) {
      if (!base) throw new Error('Backend not connected. Your requirement is saved. Connect the generation service to run this analysis, then retry.');
      const response = await send(base, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson, application/json' }, body: JSON.stringify(input), signal: context.signal });
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/x-ndjson')) return consumeStream(response, input.target, context.onProgress);
      if (!contentType.includes('application/json')) throw new Error('Expected JSON or an NDJSON event stream from the generation service.');
      const body: unknown = await response.json();
      if (isRunHandle(body)) {
        context.onRunId?.(body.run_id);
        return followEvents(eventsUrl(body), input.target, context);
      }
      return assertResult(body as GenerationResult, input.target);
    },
    resume(runId, target, context) {
      return followEvents(`${base}/${encodeURIComponent(runId)}/events`, target, context);
    },
    async cancel(runId) {
      await fetch(`${base}/${encodeURIComponent(runId)}/cancel`, { method: 'POST' }).catch(() => undefined);
    },
  };
}
export const generationAdapter = createHttpAdapter(generationEndpoint);

async function send(url: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try { response = await fetch(url, init); } catch (error) {
    if (init.signal?.aborted) throw init.signal.reason;
    throw new Error('Could not reach the generation service. Check its connection and try again.', { cause: error });
  }
  if (!response.ok) throw new Error(`The generation service returned HTTP ${response.status}. ${await readErrorDetail(response)}`);
  return response;
}

async function followEvents(url: string, target: Target, context: GenerationContext): Promise<GenerationResult> {
  const response = await send(url, { headers: { Accept: 'application/x-ndjson' }, signal: context.signal });
  if (!(response.headers.get('content-type') || '').includes('application/x-ndjson')) throw new Error('Expected an NDJSON event stream from the generation service.');
  return consumeStream(response, target, context.onProgress);
}

async function consumeStream(response: Response, target: Target, onProgress: GenerationContext['onProgress']): Promise<GenerationResult> {
  if (!response.body) throw new Error('Expected JSON or an NDJSON event stream from the generation service.');
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '', result: GenerationResult | undefined;
  function consume(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === 'error') throw new Error(typeof event.message === 'string' ? event.message : 'The generation service reported an error.');
    if (event.type === 'progress') {
      if (event.stage !== undefined && typeof event.stage !== 'string') throw new Error('Invalid pipeline stage response.');
      if (event.log && (typeof event.log.message !== 'string' || !['info', 'warning', 'error'].includes(event.log.level))) throw new Error('Invalid pipeline log response.');
      onProgress({ stage: event.stage, log: event.log });
    }
    if (event.type === 'result') result = assertResult(event.result, target);
    // Other event types (e.g. heartbeat) keep the connection alive and are ignored.
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let newline: number;
      while ((newline = buffer.indexOf('\n')) !== -1) { consume(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1); }
      if (buffer.length > 10_000_000) throw new Error('The generation response exceeded the maximum event size.');
      if (done) { consume(buffer); break; }
    }
    if (!result) throw new Error('The generation stream ended without a result.');
    return result;
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

export function assertResult(result: GenerationResult, target: RunInput['target']): GenerationResult {
  if (!result || !Array.isArray(result.files)) throw new Error('The backend returned an invalid result: expected a source file list.');
  for (const file of result.files) {
    if (!file || typeof file.path !== 'string' || typeof file.content !== 'string' || !['solidity', 'rust', 'text'].includes(file.language)) {
      throw new Error('The backend returned an invalid source file.');
    }
    if ((target === 'solana' && (file.language === 'solidity' || /\.sol$/i.test(file.path))) || (target === 'solidity' && (file.language === 'rust' || /\.rs$/i.test(file.path)))) {
      throw new Error('The returned source does not match the selected ecosystem. Check the backend adapter.');
    }
  }
  if (new Set(result.files.map(file => file.path)).size !== result.files.length) throw new Error('The backend returned duplicate file paths.');
  if (result.verification && (!['passed', 'failed', 'unknown', 'skipped'].includes(result.verification.status) || !Array.isArray(result.verification.checks) || result.verification.checks.some(check => !check || typeof check.name !== 'string' || !['passed', 'failed', 'unknown', 'skipped'].includes(check.status)))) throw new Error('Invalid verification response.');
  if (result.issues && (!Array.isArray(result.issues) || result.issues.some(issue => !issue || typeof issue.id !== 'string' || typeof issue.title !== 'string' || typeof issue.description !== 'string'))) throw new Error('Invalid issues response.');
  if (result.logs && (!Array.isArray(result.logs) || result.logs.some(log => !log || typeof log.message !== 'string' || !['info', 'warning', 'error'].includes(log.level)))) throw new Error('Invalid execution log response.');
  for (const key of ['summary', 'specification'] as const) if (result[key] !== undefined && result[key] !== null && typeof result[key] !== 'string') throw new Error(`Invalid ${key} response.`);
  if (result.report && (typeof result.report.filename !== 'string' || typeof result.report.content !== 'string' || typeof result.report.mimeType !== 'string')) throw new Error('Invalid report response.');
  return result;
}

export interface ExecutionOptions { timeoutMs?: number; onRunId?: (runId: string) => void; resumeRunId?: string }

/** Runs (or resumes) a generation with a hard timeout and abort propagation. */
export async function executeGeneration(input: RunInput, adapter: GenerationAdapter, signal: AbortSignal, onProgress: GenerationContext['onProgress'], options: ExecutionOptions | number = {}) {
  const { timeoutMs = DEFAULT_GENERATION_TIMEOUT_MS, onRunId, resumeRunId } = typeof options === 'number' ? { timeoutMs: options } : options;
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  const timeout = window.setTimeout(() => controller.abort(new Error('The request timed out. The backend may still be running. Check it before retrying.')), timeoutMs);
  let stopListening: (() => void) | undefined;
  try {
    controller.signal.throwIfAborted();
    // Race even adapters that fail to honour cancellation, so the UI never waits forever.
    const aborted = new Promise<never>((_, reject) => {
      const rejectAbort = () => reject(controller.signal.reason);
      controller.signal.addEventListener('abort', rejectAbort, { once: true });
      stopListening = () => controller.signal.removeEventListener('abort', rejectAbort);
    });
    const context: GenerationContext = { signal: controller.signal, onProgress, onRunId };
    const work = resumeRunId && adapter.resume ? adapter.resume(resumeRunId, input.target, context) : adapter.generate(input, context);
    const result = await Promise.race([work, aborted]);
    return assertResult(result, input.target);
  } finally { window.clearTimeout(timeout); signal.removeEventListener('abort', abort); stopListening?.(); }
}

/** Live backend status: health + adapter capabilities. Throws when unreachable. */
export async function fetchBackendStatus(signal?: AbortSignal): Promise<BackendStatus> {
  const [health, capabilities] = await Promise.all([api.health(signal), api.capabilities(signal)]);
  return { state: 'online', targets: capabilities.targets, model: health.llm?.model, checkedAt: new Date().toISOString() };
}

/** Property catalogue for one target, or every target when omitted. */
export async function fetchProperties(target?: Target | 'all', signal?: AbortSignal): Promise<PropertyEntry[]> {
  const response = await api.properties(target, signal);
  return response.properties;
}
