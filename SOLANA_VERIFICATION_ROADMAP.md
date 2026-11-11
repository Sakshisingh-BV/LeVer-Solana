# Solana Verification Roadmap (PLAN ONLY – nothing here is implemented)

Current state: `SolanaAdapter` has generate / repair / validate. Stubs (`NotImplementedError`): `check_compilation`, `generate_formal_spec`, `verify_spec`, `generate_test_harness`, `run_tests`, `extract_counterexample`. Helpers `kani_utils.py` (`parse_kani_output` partial) and `solana_utils.py` exist. Config in `core/solana_config.py`. Template workspace: `experiments/{exp_name}/{run_id}/simulation_env`.

Target loop (mirrors Solidity): generate → build → formal (Kani) → dynamic (Anchor tests) → counterexample → repair → repeat.

## Prerequisites (install once)
```bash
# Rust + Solana + Anchor (versions from core/solana_config.py)
rustup toolchain install 1.79.0
sh -c "$(curl -sSfL https://release.anza.xyz/v1.18.26/install)"
cargo install --git https://github.com/coral-xyz/anchor avm --force && avm install 0.30.1 && avm use 0.30.1
cargo install --locked kani-verifier && cargo kani setup
node -v && yarn -v            # for Anchor TS tests
# Lean (optional, Phase 6): already used by Solidity – elan/lake on PATH
```
Windows: run the Solana/Anchor/Kani toolchain in **WSL2** (Anchor/Solana tooling is Linux/macOS first). Point `ANCHOR_CLI`, `SOLANA_CLI`, `CARGO_KANI_CLI` env vars at the WSL wrappers.

## Phase 1 – Workspace + `anchor build`
- **What:** materialise generated `Target.rs` into `simulation_env/programs/lever_target/src/lib.rs`; fill `Anchor.toml`/`Cargo.toml`; real program id via `anchor keys sync`.
- **How:** implement `SolanaAdapter.check_compilation` using `solana_utils.validate_anchor_project_structure` + subprocess; feed compiler errors back to `AnchorCoder.repair_anchor_code`.
- **Commands:** `anchor build` (in `simulation_env/`), `cargo check --manifest-path programs/lever_target/Cargo.toml`
- **Expected:** exit 0, `target/deploy/lever_target.so` exists; failure → rustc diagnostics captured.
- **Deliverables:** working compile stage in `workflow_solana_*`; mapper check "Anchor build" = passed/failed; API stage `Compile`.

## Phase 2 – Property selection
- **What:** choose from `properties/solana.json` (SOL-01 signer, SOL-02 owner, PDA, CPI, overflow…) per requirement.
- **How:** reuse `PropertySelector` pattern with the flat schema; store in checkpoint `selected_properties`; start with a static default set (signer, owner, checked arithmetic) so the stage works without LLM.
- **Commands:** `GET /api/properties?target=solana` (already works)
- **Expected:** list of property ids per run, shown on Specification tab.
- **Deliverables:** `select_properties(code, requirement)`; selected ids passed to harness generation.

## Phase 3 – Kani formal verification
- **What:** bounded model checking of pure logic (arithmetic, state transitions, authority checks) extracted from the Anchor program.
- **How:** implement `generate_formal_spec` (`kani_utils.generate_kani_harness_scaffold`, LLM-assisted, template per property) → `#[cfg(kani)] #[kani::proof]` harnesses in `kani_workspace/`; `verify_spec` runs cargo-kani and `parse_kani_output`. Model account state as plain structs (Kani cannot run the Solana runtime); use `kani::any()` + `kani::assume`/`assert!`.
- **Commands:** `cargo kani --harness <name> --output-format terse` (in `kani_workspace/`)
- **Expected:** `VERIFICATION:- SUCCESSFUL` per harness; failure prints a failing check + trace.
- **Deliverables:** harness generator, runner, parsed per-property results → mapper "Kani" check + issues.

## Phase 4 – Dynamic testing (Anchor + local validator)
- **What:** behavioural tests incl. attacker cases (missing signer, wrong owner, replayed init, overflow).
- **How:** implement `generate_test_harness` (TS tests in `tests/`, accounts Alice/Bob/Mallory from `solana_config`) and `run_tests`; parse mocha output into `{success, passed, failed, details}`.
- **Commands:** `anchor test` (spins up `solana-test-validator`), or `solana-test-validator --reset` + `anchor test --skip-local-validator`
- **Expected:** `N passing`; failures list test names + program logs.
- **Deliverables:** test generator, runner, timeout/cleanup of validator, mapper "Anchor tests" check.

## Phase 5 – Counterexample handling + repair loop
- **What:** turn Kani traces / failing tests into repair constraints.
- **How:** finish `extract_kani_counterexample` (variable assignments) and a program-log parser (`Program log:`/`AnchorError`) → `extract_counterexample`; add to `ctx.feedback_constraints`; call `repair_code`; re-run Phases 1-4; stop at `max_iterations`.
- **Commands:** same as Phases 1-4 inside the loop.
- **Expected:** iteration N+1 resolves counterexample from N, or loop ends with reason in `result.json`.
- **Deliverables:** full `workflow_solana` replacing `workflow_solana_generate_only`; `result.json` same shape as Solidity; per-iteration `metrics_iter_N.json`.

## Phase 6 – Lean (optional, only where it adds value)
- **What:** prove abstract invariants Kani can't (unbounded arithmetic, conservation of supply).
- **How:** reuse `FormalVerifier`/`LeanFormalizer` on a hand-abstracted model of the Anchor state machine; keep non-blocking in `full` mode like Solidity.
- **Commands:** `lake build` / `lean Definitions.lean`
- **Deliverables:** Lean stage for `lean`/`full` modes; Kani stays the default formal engine.

## Phase 7 – API / UI wiring + mode semantics
- **What:** map modes: `lean` = Kani (+Lean), `no_lean` = Anchor tests, `full` = both. Update `SolanaResultMapper`, stage regexes in `runners.py`, `capabilities` (`implemented_stages`).
- **Commands:** `python -m api` then run from UI; `python -m core.main_pipeline --target solana --mode full --req-file req.txt`
- **Deliverables:** UI shows real Solana verification checks/issues; remove "pipeline not implemented" notes.

## Order & dependencies
1 → 2 → 3 → 4 → 5 → 7; Phase 6 optional after 5. Each phase is independently shippable: after Phase 1 the UI already shows real build status; after Phase 3 real Kani proofs.

## Risks
- Kani can't execute Solana syscalls/CPI → verify extracted logic only; document unverified surface.
- LLM-generated Anchor code often fails `anchor build` (version drift) → pin anchor-lang 0.30.1 in prompt.
- `anchor test` is slow/flaky on cold start → per-run validator on a free port, hard timeouts.
- Windows tooling → use WSL2.
