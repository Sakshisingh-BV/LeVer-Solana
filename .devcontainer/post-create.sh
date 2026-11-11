#!/usr/bin/env bash
# Runs once after the Codespace/container is created.
# Everything here stays inside the container. Failures in optional steps
# are reported but do not abort the whole setup.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

step() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

# 1) Python virtualenv + backend dependencies (Python 3.11 from the Feature)
step "Python backend dependencies"
if [ ! -d "$ROOT/.venv" ]; then
  python3.11 -m venv "$ROOT/.venv" 2>/dev/null || python3 -m venv "$ROOT/.venv" || warn "venv creation failed"
fi
if [ -f "$ROOT/LeVer/requirements.txt" ] && [ -x "$ROOT/.venv/bin/pip" ]; then
  "$ROOT/.venv/bin/pip" install --upgrade pip >/dev/null 2>&1
  "$ROOT/.venv/bin/pip" install -r "$ROOT/LeVer/requirements.txt" || warn "pip install failed"
else
  warn "LeVer/requirements.txt not found – skipping"
fi

# 2) Frontend dependencies (Node 20 from the Feature)
step "Frontend dependencies"
if [ -f "$ROOT/frontend/package-lock.json" ]; then
  (cd "$ROOT/frontend" && npm ci) || warn "npm ci failed"
elif [ -f "$ROOT/frontend/package.json" ]; then
  (cd "$ROOT/frontend" && npm install) || warn "npm install failed"
fi

# 3) yarn is required by Anchor's generated TypeScript tests
step "yarn (for Anchor tests)"
command -v yarn >/dev/null 2>&1 || npm install -g yarn || warn "yarn install failed"

# 4) Container-only Solana keypair + localnet config (never a real wallet)
step "Solana local keypair / config"
KEYPAIR="$HOME/.config/solana/id.json"
if [ ! -f "$KEYPAIR" ]; then
  solana-keygen new --no-bip39-passphrase --silent --outfile "$KEYPAIR" || warn "keygen failed"
fi
solana config set --url localhost >/dev/null || warn "solana config failed"

step "Done. Run:  bash scripts/verify_solana_env.sh"
