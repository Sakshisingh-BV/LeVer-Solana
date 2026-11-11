# LeVer – Integration Notes

## How frontend ↔ backend are connected
- New FastAPI service in `LeVer/api/` (`python -m api`, port 8000).
- Vite proxies `/api` → `http://127.0.0.1:8000` (`frontend/vite.config.ts`, already present).
- `frontend/src/lib/generation.ts` = central API layer; `lib/api.ts` = HTTP transport only.
- Backend runs `python -m core.main_pipeline --target solidity|solana` as a subprocess, parses stdout into stages.

## Endpoints & data flow
- `GET  /api/health` – liveness, LLM config summary
- `GET  /api/capabilities` – adapters, tools on PATH, implemented/missing stages
- `GET  /api/properties?target=` – property catalogue (solidity: `property.json`, solana: `properties/solana.json`)
- `POST /api/runs` – body = UI `RunInput`; `lean` → CLI `lean_only`; returns `202 {run_id, events_url}`
- `GET  /api/runs/{id}/events` – NDJSON: `progress` | `result` | `error` | `heartbeat`
- `GET  /api/runs`, `GET /api/runs/{id}`, `POST /api/runs/{id}/cancel`
- Flow: UI → `POST /runs` → follow `events` → `assertResult()` → Run detail page (code, spec, verification, issues, logs).
- Errors (LLM down, pipeline failure, bad input) arrive as `error` events / HTTP detail and show in the run page.
- Unfinished runs re-attach after page reload (`serverRunId`).

## Files changed / added
**Backend (new)** – `LeVer/api/`
- `main.py` – routes, CORS
- `schemas.py` – request model, mode mapping, result models
- `run_service.py` – run lifecycle, event bus, `run.json` persistence, cancel
- `runners.py` – subprocess runner + stdout→stage parser
- `result_mapper.py` – workspace files → `GenerationResult` (per target)
- `properties.py` – property loaders per target
- `__init__.py`, `__main__.py` – package + uvicorn launcher

**Backend (edited)**
- `core/adapters/base.py` – added target metadata + `describe()`
- `core/adapters/solidity_adapter.py` – now delegates to existing agents/simulator/verifier
- `core/adapters/solana_adapter.py` – generate/repair/validate wired; rest still `NotImplementedError`
- `core/solana_agents.py` – `AnchorCoder` implemented (on `BaseAgent`)
- `core/main_pipeline.py` – `--target` flag via `adapter_factory`; Solidity path unchanged
- `core/pipeline/workflows.py` – added `workflow_solana_generate_only`
- `requirements.txt` – fastapi, uvicorn
- `property.json` – restored to `LeVer/` (CLI needs it; recovered from Recycle Bin)

**Frontend (edited/new)**
- `lib/api.ts` – real endpoints, error parsing
- `lib/generation.ts` – run handle → NDJSON follow, resume, cancel, status, properties
- `hooks/useRuns.ts` – resume/cancel, multi-run tracking
- `hooks/useBackendStatus.ts` (new) – live backend status
- `pages/NewRunPage.tsx`, `WorkspacePages.tsx` – live backend status text
- `pages/PropertiesPage.tsx` – live catalogue (falls back to examples)
- `App.tsx`, `components/AppShell.tsx` – `/properties` route + nav link
- `types/run.ts` – handle/capability/property types
- `tests/platform.spec.ts` – updated + new run-handle test; `.env.example`, `README.md`

## Design patterns
- **Adapter** – `TargetAdapter` → `SolidityAdapter` / `SolanaAdapter`; frontend `GenerationAdapter`
- **Factory** – `adapter_factory(target)`
- **Strategy** – `PipelineRunner`, per-target `ResultMapper`, per-target property loaders
- **Service layer** – `RunService` (routes stay thin)
- **Observer / pub-sub** – run event bus feeding NDJSON streams

## Implemented
- Full API + frontend wiring for both targets
- Solidity: existing pipeline reached via `--target solidity` (all modes)
- Solana: Anchor generation (`AnchorCoder`) + structural validation → `Target.rs`; result marked "verification skipped"
- Tests passed: mocked API suite (create/stream/cancel/reload/errors), real subprocess reaches generation for both targets, `tsc` clean

## Not done / pending
- **Not verified:** a full real-LLM run (local Ollama OOM, remote endpoint `Connection error`); Playwright suite not re-run
- **Solana:** `anchor build`, Kani harness + `cargo kani`, Lean (optional), Anchor tests + local validator, counterexample parsing/repair loop, Solana attack/fuzz stage
- Solana modes `lean`/`no_lean`/`full` behave identically for now (generation only)
- Roadmap: see `SOLANA_VERIFICATION_ROADMAP.md`
