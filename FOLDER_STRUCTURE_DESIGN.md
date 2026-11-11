# 📂 LeVer Platform — System Folder Structure

> **Overview:** Unified, language-agnostic architecture for LeVer. Integrates the **React/Vite Frontend** with the **Python Core Engine** supporting both **Ethereum (Solidity)** and **Solana (Rust/Anchor)** via the Target Adapter Pattern.

---

## 1. Top-Level Platform Layout (Monorepo)

```text
LeVer-Platform/
├── frontend/                   # 🖥️ Interactive Web Studio (React + Vite + TypeScript)
├── backend/ (LeVer/)           # ⚙️ Core Verification & Repair Engine (Python)
├── docs/                       # 📚 System Architecture & Research Documentation
├── .gitignore                  # Root git exclusion rules
└── README.md                   # Platform summary & quick start
```

---

## 2. Frontend Directory Structure (`frontend/`)

```text
frontend/
├── public/                     # Static assets & icons (favicon.svg)
├── src/
│   ├── components/             # Reusable UI components
│   │   ├── AppShell.tsx        # Responsive navigation & layout header
│   │   ├── CodeViewer.tsx      # Multi-file syntax-highlighted source viewer
│   │   ├── FlowWave.tsx        # Interactive canvas background animation
│   │   ├── Starfield.tsx       # Ambient particle visualizer
│   │   ├── SourceLine.tsx      # Code line renderer with issue markers
│   │   ├── AnimatedDisclosure.tsx # Collapsible accordions
│   │   └── ui.tsx              # Status pills, stage trackers & modal dialogs
│   │
│   ├── pages/                  # Route views
│   │   ├── LandingPage.tsx     # Hero overview, feature highlights & quick demo
│   │   ├── NewRunPage.tsx      # Requirement builder & target selection (Solidity/Solana)
│   │   ├── RunHistoryPage.tsx  # Persisted analysis records & run filters
│   │   ├── RunDetailPage.tsx   # Generated code, specification, verification evidence & logs
│   │   └── WorkspacePages.tsx  # Documentation, guides & platform settings
│   │
│   ├── data/                   # Static presets & mock previews
│   │   ├── examples.ts         # Preloaded starter requirements
│   │   ├── modes.ts            # Verification modes (full, lean, no_lean)
│   │   └── preview.ts          # Offline sample run data (EVM / SVM)
│   │
│   ├── hooks/                  # Custom React hooks
│   │   ├── useRuns.ts          # State management & persistence for runs
│   │   ├── useDemoRuns.ts      # Offline client-side simulation runner
│   │   └── usePreference.ts    # User settings (theme, motion preferences)
│   │
│   ├── lib/                    # API communication & validation
│   │   ├── api.ts              # FastAPI backend client (endpoints & models)
│   │   └── generation.ts       # Streaming generation adapter & result validator
│   │
│   ├── types/
│   │   └── run.ts              # TypeScript domain types (Target, Run, Mode, Issue, Log)
│   │
│   ├── App.tsx                 # Client routing & toast notifications
│   ├── main.tsx                # React DOM entry point
│   ├── site.css                # Global theme variables & responsive styles
│   └── styles.css              # Component-level styles
│
├── tests/                      # Playwright E2E UI automation tests
│   └── platform.spec.ts        # Input validation, mode selection & responsive checks
│
├── index.html                  # HTML template
├── package.json                # Frontend dependencies (React 19, Lucide, Vite)
├── tsconfig.json               # TypeScript compiler options
└── vite.config.ts              # Dev server & reverse-proxy configuration
```

---

## 3. Backend Engine Directory Structure (`backend/` / `LeVer/`)

### Architecture After Adapter Pattern Applied

```text
backend/ (LeVer/)
├── core/
│   │   # ─── Language-Agnostic Common Core ───
│   ├── adapter_factory.py      # Target factory: adapter_factory(target_name)
│   ├── main_pipeline.py        # CLI Entry Point: accepts --target solana|solidity
│   ├── logger.py               # Central execution logger
│   ├── structured_logging.py   # Machine-readable JSON event stream
│   ├── regression_runner.py    # Multi-case test benchmark harness
│   │
│   │   # ─── Target Adapter Layer (Plug-in Interface) ───
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py             # TargetAdapter abstract base class (Universal Interface)
│   │   ├── solidity_adapter.py # SolidityAdapter (Wraps Foundry, Anvil & Lean 4)
│   │   └── solana_adapter.py   # SolanaAdapter (Wraps Anchor, Solana CLI & Kani)
│   │
│   │   # ─── Common Workflow Engine ───
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── workflows.py        # Target-neutral workflow orchestrator
│   │   ├── iteration.py        # Generic generate-verify-repair loop
│   │   ├── context.py          # Unified PipelineContext (target, generated_code, state)
│   │   ├── checkpoint.py       # Iteration checkpoint persistence
│   │   ├── metrics.py          # Test & proof metrics collector
│   │   ├── cleanup.py          # Temporary workspace garbage collector
│   │   ├── solidity_utils.py   # EVM syntax and pragma checkers
│   │   ├── solana_utils.py     # Anchor & Rust parsing helpers
│   │   ├── lean_utils.py       # Lean 4 formal prover bridges
│   │   └── kani_utils.py       # Kani model-checker output parsers
│   │
│   │   # ─── Core Agents & Tools ───
│   ├── agents.py               # LLM Agent definitions (Coder, Prover, Auditor, Analyst)
│   ├── config.py               # Local testnet & deployment configuration
│   ├── simulator.py            # Dynamic test execution runner (Forge / Anchor test)
│   └── formal_verifier.py      # Formal verification runner (Lean 4 / Kani)
│
├── properties/                 # 🛡️ Semantic Property Knowledge Base (IR Layer)
│   ├── schema.json             # Target-neutral JSON Schema for safety properties
│   ├── solidity.json           # EVM properties (Reentrancy, Access Control, Overflow)
│   └── solana.json             # SVM properties (Missing Signer, Owner Check, Math Overflow)
│
├── examples/                   # Reference requirement specification files (.txt)
├── experiments/                # Generated workspaces per run (<exp_name>/<run_id>/)
│   └── <run_id>/
│       ├── Target.sol / lib.rs # Generated on-chain program
│       ├── execution.log       # Step-by-step logs
│       ├── checkpoint.json     # Checkpoint state
│       └── result.json         # Final outcome & evaluation metrics
│
├── libs_cache/                 # Cached toolchain libraries (forge-std, openzeppelin)
├── env.ps1 / env.sh            # Environment variables (LLM endpoint, API keys)
└── requirements.txt            # Python dependencies
```

---

## 4. Adapter Interface Methods: Solidity vs. Solana

The core pipeline calls uniform methods on `TargetAdapter`. Each adapter maps them to its respective toolchain:

| Adapter Method | Solidity Implementation | Solana Implementation |
|---|---|---|
| `generate_code(spec)` | LLM Prompt ➔ Solidity Contract (`.sol`) | LLM Prompt ➔ Anchor Program (`lib.rs`) |
| `is_valid_source(code)` | Checks `pragma solidity` & basic AST | Checks `use anchor_lang::prelude::*` |
| `check_compilation(code)` | `forge build` via Foundry | `anchor build` via Solana toolchain |
| `generate_formal_spec(code)` | Synthesizes Lean 4 model (`Model.lean`) | Synthesizes Kani proof harnesses (`#[kani::proof]`) |
| `verify_spec(model)` | Executes `lake build` / Lean 4 prover | Executes `cargo kani` bounded model checker |
| `generate_test_harness(spec)` | Forge test scripts (`Target.t.sol`) | TypeScript tests (`tests/*.ts`) |
| `run_tests(harness)` | `forge test` against Anvil RPC | `anchor test` against local-validator |
| `repair_code(feedback)` | Patches Solidity code using error trace | Patches Anchor Rust code using counterexample |

---

