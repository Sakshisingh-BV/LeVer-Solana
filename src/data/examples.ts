import type { Run } from '../types/run';

export const examples = [
  { id: 'counter', name: 'Owner counter', category: 'A simple starting point', requirement: 'Create a counter with an owner.\n\nOnly the owner can increment the counter. Reject unauthorized updates and prevent integer overflow. Anyone should be able to read the current value.' },
  { id: 'vault', name: 'Token vault', category: 'Deposits & withdrawals', requirement: 'Create a vault where users can deposit and withdraw tokens.\n\nTrack each user’s balance independently. A user must never withdraw more than they deposited. Update balances before transferring tokens, and reject unauthorized withdrawals.' },
  { id: 'escrow', name: 'Simple escrow', category: 'Conditional transfers', requirement: 'Create an escrow between a buyer and a seller.\n\nThe buyer deposits funds. Release funds to the seller only after buyer approval. Allow a refund after the deadline if approval has not been given. Prevent double withdrawals.' },
];

export const sampleRuns: Run[] = [
  { id: 'sample-owner-counter', name: 'Owner counter', requirement: examples[0].requirement, target: 'solidity', mode: 'full', maxIterations: 3, attackRounds: 3, createdAt: '2026-10-29T06:00:00.000Z', status: 'completed', stage: 5, isDemo: true },
  { id: 'sample-solana-counter', name: 'Anchor counter', requirement: examples[0].requirement, target: 'solana', mode: 'lean', maxIterations: 3, attackRounds: 3, createdAt: '2026-10-29T05:00:00.000Z', status: 'completed', stage: 4, isDemo: true },
];

export const sampleSource = {
  solidity: '// Illustrative counter source — not generated from your input\n// SPDX-License-Identifier: MIT\npragma solidity ^0.8.24;\n\ncontract OwnerCounter {\n    address public immutable owner;\n    uint256 public count;\n\n    error Unauthorized();\n\n    constructor() {\n        owner = msg.sender;\n    }\n\n    function increment() external {\n        if (msg.sender != owner) revert Unauthorized();\n        count += 1;\n    }\n}',
  solana: '// Illustrative Anchor handler — not generated from your input\n// Account and context definitions are omitted from this excerpt.\n\npub fn increment(ctx: Context<Increment>) -> Result<()> {\n    let counter = &mut ctx.accounts.counter;\n\n    require_keys_eq!(\n        counter.owner,\n        ctx.accounts.owner.key(),\n        CounterError::Unauthorized\n    );\n\n    counter.value = counter.value\n        .checked_add(1)\n        .ok_or(CounterError::Overflow)?;\n\n    Ok(())\n}',
};

export const propertyExamples = [
  { id: 'access', name: 'Access control', category: 'Authorization', target: 'both', description: 'State-changing operations are restricted to authorized callers.', detail: 'For Solidity, check the caller against the owner or role. For Solana, validate the signer and the authority of the account.' },
  { id: 'balance', name: 'Balance conservation', category: 'Accounting', target: 'both', description: 'Transfers preserve the accounting rules of the contract.', detail: 'Track deposits, withdrawals and total balances. A user must not withdraw funds belonging to another account.' },
  { id: 'overflow', name: 'Integer safety', category: 'Arithmetic', target: 'both', description: 'Arithmetic cannot silently overflow or underflow.', detail: 'Express explicit range assumptions and verify boundary values. Rust checked arithmetic and Solidity compiler checks have different semantics.' },
  { id: 'reentrancy', name: 'Reentrancy protection', category: 'External calls', target: 'solidity', description: 'External calls cannot re-enter a sensitive state transition.', detail: 'Check state changes around external calls and model adversarial callbacks. A passed example is not a guarantee for other paths.' },
  { id: 'ownership', name: 'Account ownership', category: 'Accounts', target: 'solana', description: 'Program instructions validate the ownership of every account.', detail: 'Verify expected account owners, signers and PDA derivations before changing state.' },
  { id: 'double-spend', name: 'Single-use transfers', category: 'State transitions', target: 'both', description: 'A completed transfer cannot be claimed a second time.', detail: 'After a claim, the corresponding state must prevent repeating the same transfer, including through reordered operations.' },
];
