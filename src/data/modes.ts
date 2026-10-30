import { Layers3, ShieldCheck, Zap } from 'lucide-react';
import type { VerificationMode } from '../types/run';

// Centralized copy can follow the configured backend without changing identifiers.
export const executionModes: { id: VerificationMode; name: string; description: string; detail: string; icon: typeof Zap }[] = [
  { id: 'lean', name: 'Lean', description: 'A focused, lightweight verification path.', detail: 'Selects the Lean-based formal verification path. The existing CLI names this mode lean_only. Available checks depend on your configured ecosystem.', icon: Zap },
  { id: 'no_lean', name: 'No Lean', description: 'Generation without the Lean verification path.', detail: 'Runs the existing no_lean workflow. In the Solidity pipeline, dynamic checks inform iteration while Slither and the LLM audit are reported separately.', icon: ShieldCheck },
  { id: 'full', name: 'Full', description: 'The complete configured LeVer pipeline.', detail: 'Runs the full workflow supported by your backend. In the Solidity implementation, formal and dynamic checks are included; individual verification outcomes are reported separately.', icon: Layers3 },
];
