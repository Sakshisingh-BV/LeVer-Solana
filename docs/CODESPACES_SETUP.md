# Solana development in GitHub Codespaces

All Solana tooling runs **inside a cloud container**. Nothing (Rust, Solana CLI, Anchor, Docker, WSL2) is installed on your PC, and your local `PATH` is never touched. You only need a browser and a GitHub account.

## Pinned toolchain

| Tool | Version | Source |
|---|---|---|
| Rust | **1.79.0** | `rustup`, minimal profile (`.devcontainer/Dockerfile`) |
| Solana CLI | **1.18.26** | Anza release installer |
| Anchor | **0.30.1** | `avm` pinned to tag `v0.30.1` |
| Node.js | 20 | Dev Container Feature |
| Python | 3.11 | Dev Container Feature |
| Kani | *not installed* | planned for the later formal-verification phase |

Environment variables set in the container (read by `LeVer/core/solana_config.py`):
`ANCHOR_CLI=anchor`, `SOLANA_CLI=solana`, `SOLANA_TEST_VALIDATOR_URL=http://127.0.0.1:8899`, `SOLANA_CLUSTER=localnet`.

## 1. Launch the Codespace (browser only)

1. Open <https://github.com/Sakshisingh-BV/LeVer-Solana> (branch `main`).
2. Click **Code → Codespaces → ⋯ → New with options…**
3. Branch: `main`. Machine type: **2-core** (default for this repo; saves free quota).
4. Click **Create codespace**.

The first build compiles `avm`/Anchor from source and typically takes **15–25 minutes on 2 cores**. Later starts reuse the cached image and take about a minute. Prebuilds are intentionally **not** enabled.

If a build is too slow or runs out of memory, delete the Codespace and re-create it with the 4-core machine.

## 2. Verify the toolchain and `anchor build`

In the Codespace terminal:

```bash
bash scripts/verify_solana_env.sh          # versions + anchor build
bash scripts/verify_solana_env.sh --test   # additionally runs `anchor test` (slower)
```

The script checks the pinned versions, confirms Kani is absent, then creates a throw-away Anchor project in a temp directory, runs `anchor build`, and checks that a `.so` is produced. It does not read or modify any file in this repository. The first `anchor build` also downloads Solana platform-tools (several hundred MB), so it is slow once.

Expected last line: `Result: N passed, 0 failed`.

## 3. Run LeVer

```bash
source .venv/bin/activate
cd LeVer && python -m api            # backend on :8000 (auto-forwarded)
# second terminal:
cd frontend && npm run dev           # Vite on :5173 (auto-forwarded)
```

Open the forwarded port 5173 from the **Ports** tab.

## 4. Secrets and quota

- Do **not** put LLM API keys in `.env` files that get committed. Use **GitHub → Settings → Codespaces → Secrets** and expose them to this repository; they appear as environment variables inside the Codespace.
- Free plans include a monthly core-hour allowance (2-core machine = 2 core-hours per hour of use). Stop the Codespace when finished (**Codespaces → ⋯ → Stop**); it also auto-stops after the idle timeout.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `anchor: command not found` | `avm use 0.30.1`, then reopen the terminal |
| Build killed / out of memory | Re-create the Codespace with 4 cores |
| `anchor build` complains about lockfile version | Delete `Cargo.lock` in the project and rebuild (Rust 1.79 writes lockfile v3) |
| `anchor test` hangs | Port 8899 busy: `pkill solana-test-validator`, retry |
| Env vars missing | Open a new terminal; `containerEnv` applies to new shells |

## Scope of this phase

Environment only. Kani, Anchor-test generation and the verification workflow are implemented later on a dedicated branch; see `docs/SOLANA_SECURITY_PROPERTIES.md` and `docs/SOLANA_VERIFICATION_ARCHITECTURE.md` for the design.
