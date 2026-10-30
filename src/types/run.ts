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
export const modeLabels: Record<VerificationMode, string> = {
  no_lean: 'no_lean', lean: 'lean', full: 'full',
};
export const targetLabels: Record<Target, string> = { solidity: 'Solidity', solana: 'Solana' };
export function stagesFor(mode: VerificationMode) {
  return ['Generate', 'Compile', ...(mode !== 'no_lean' ? ['Formal checks'] : []), ...(mode !== 'lean' ? ['Dynamic tests'] : []), 'Report'];
}
