import type { ExecutionLog, GenerationResult, RunInput } from '../types/run';

/** UI-domain contract, not a proposed HTTP endpoint. Implement against the real backend. */
export interface GenerationAdapter {
  generate(input: RunInput, context: {
    signal: AbortSignal;
    onProgress: (event: { stage?: string; log?: ExecutionLog }) => void;
  }): Promise<GenerationResult>;
}

// Keep local development honest: no invented source, proofs, progress, or API routes.
export const generationAdapter: GenerationAdapter = {
  async generate() {
    throw new Error('Backend not connected. Your requirement is saved. Connect the generation service to run this analysis, then retry.');
  },
};

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
