export type Target = 'solidity' | 'solana';
export type VerificationMode = 'no_lean' | 'lean' | 'full';
export type RunStatus = 'running' | 'completed' | 'cancelled' | 'failed';
export interface RunInput {
  name: string;
  requirement: string;
  target: Target;
  mode: VerificationMode;
  maxIterations: number;
  attackRounds: number;
}
export interface Run extends RunInput {
  id: string;
  createdAt: string;
  status: RunStatus;
  stage: number;
  isDemo?: true;
  result?: GenerationResult;
  error?: string;
  currentStage?: string;
  logs?: ExecutionLog[];
  /** Backend run id; lets the UI re-attach to a long-running pipeline after a reload. */
  serverRunId?: string;
}
export interface SourceFile { path: string; language: 'solidity' | 'rust' | 'text'; content: string; before?: string }
export interface ExecutionLog { message: string; level: 'info' | 'warning' | 'error'; timestamp?: string }
export interface VerificationCheck { name: string; status: 'passed' | 'failed' | 'unknown' | 'skipped'; detail?: string }
export interface Issue { id: string; title: string; severity?: string; description: string; file?: string; line?: number; endLine?: number; suggestion?: string }
export interface GenerationResult {
  files: SourceFile[];
  specification?: string;
  verification?: { status: 'passed' | 'failed' | 'unknown' | 'skipped'; detail?: string; checks: VerificationCheck[] };
  issues?: Issue[];
  logs?: ExecutionLog[];
  summary?: string;
  report?: { filename: string; content: string; mimeType: string };
}
/** `POST /api/runs` reply: the run was accepted and its events are streamed separately. */
export interface RunHandle { run_id: string; status: string; events_url?: string }
/** One entry of the backend property catalogue (`GET /api/properties`). */
export interface PropertyEntry {
  id: string; name: string; category: string; description: string; target: string;
  severity?: string | null; level?: string; invariant_template?: string; remediation?: string | null;
  example_attack?: string | null; references?: string[];
}
/** One adapter from `GET /api/capabilities`. */
export interface TargetCapability {
  target: string; toolchain: string; available: boolean; pipeline_ready: boolean;
  tools: Record<string, boolean>; optional_tools?: Record<string, boolean>;
  implemented_stages: string[]; missing_stages: string[]; error?: string;
}
export interface BackendStatus { state: 'checking' | 'online' | 'offline'; targets: TargetCapability[]; model?: string; error?: string; checkedAt?: string }
export const modeLabels: Record<VerificationMode, string> = {
  no_lean: 'no_lean', lean: 'lean', full: 'full',
};
export const targetLabels: Record<Target, string> = { solidity: 'Solidity', solana: 'Solana' };
export function stagesFor(mode: VerificationMode) {
  return ['Generate', 'Compile', ...(mode !== 'no_lean' ? ['Formal checks'] : []), ...(mode !== 'lean' ? ['Dynamic tests'] : []), 'Report'];
}
