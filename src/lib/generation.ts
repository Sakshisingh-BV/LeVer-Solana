import type { ExecutionLog, GenerationResult, RunInput } from '../types/run';

/** UI-domain contract, not a proposed HTTP endpoint. Implement against the real backend. */
export interface GenerationAdapter {
  generate(input: RunInput, context: {
    signal: AbortSignal;
    onProgress: (event: { stage?: string; log?: ExecutionLog }) => void;
  }): Promise<GenerationResult>;
}

export const generationConfigured = Boolean(import.meta.env.VITE_GENERATION_URL?.trim());

/** Optional HTTP bridge. No existing CLI workflow or mode behavior is changed. */
export function createHttpAdapter(endpoint: string): GenerationAdapter {
  return {
    async generate(input, { signal, onProgress }) {
      if (!endpoint.trim()) throw new Error('Backend not connected. Your requirement is saved. Connect the generation service to run this analysis, then retry.');
      let response: Response;
      try {
        response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson, application/json' }, body: JSON.stringify(input), signal });
      } catch (error) {
        if (signal.aborted) throw signal.reason;
        throw new Error('Could not reach the generation service. Check its connection and try again.', { cause: error });
      }
      if (!response.ok) throw new Error(`The generation service returned HTTP ${response.status}. Check the backend and try again.`);
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) return assertResult(await response.json(), input.target);
      if (!contentType.includes('application/x-ndjson') || !response.body) throw new Error('Expected JSON or an NDJSON event stream from the generation service.');
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
        if (event.type === 'result') result = assertResult(event.result, input.target);
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
    },
  };
}
export const generationAdapter = createHttpAdapter(import.meta.env.VITE_GENERATION_URL || '');

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
  for (const key of ['summary', 'specification'] as const) if (result[key] !== undefined && typeof result[key] !== 'string') throw new Error(`Invalid ${key} response.`);
  if (result.report && (typeof result.report.filename !== 'string' || typeof result.report.content !== 'string' || typeof result.report.mimeType !== 'string')) throw new Error('Invalid report response.');
  return result;
}

export async function executeGeneration(input: RunInput, adapter: GenerationAdapter, signal: AbortSignal, onProgress: Parameters<GenerationAdapter['generate']>[1]['onProgress'], timeoutMs = 120_000) {
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
    const result = await Promise.race([adapter.generate(input, { signal: controller.signal, onProgress }), aborted]);
    return assertResult(result, input.target);
  } finally { window.clearTimeout(timeout); signal.removeEventListener('abort', abort); stopListening?.(); }
}
