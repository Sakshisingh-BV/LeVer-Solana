import { examples, sampleSource } from './examples';
import type { Run, Target } from '../types/run';

/** Explicit opt-in fixtures. Never inserted into analysis history or submission results. */
export function previewRun(target: Target): Run {
  return {
    id: 'preview-' + target, name: target === 'solidity' ? 'Owner counter' : 'Anchor counter',
    requirement: examples[0].requirement, target, mode: 'full', maxIterations: 3, attackRounds: 3,
    status: 'cancelled', stage: 0, isDemo: true, createdAt: '2026-10-30T00:00:00Z',
    result: {
      files: [{ path: target === 'solidity' ? 'contracts/OwnerCounter.sol' : 'programs/counter/src/lib.rs', language: target === 'solidity' ? 'solidity' : 'rust', content: sampleSource[target] }, { path: 'README.md', language: 'text', content: 'LeVer workspace preview\n\nThese files are illustrative examples, not generated output.\nUse the studio to describe your own requirements.\nLive execution becomes available when the backend is connected.' }],
      summary: 'This is an interface preview. No generation, compilation, or verification has run.',
    },
  };
}
