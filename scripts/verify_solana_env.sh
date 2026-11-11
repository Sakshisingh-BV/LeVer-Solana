#!/usr/bin/env bash
# Verifies the Codespaces Solana toolchain independently of LeVer's own code.
#
#   bash scripts/verify_solana_env.sh          # versions + `anchor build`
#   bash scripts/verify_solana_env.sh --test   # also runs `anchor test`
#
# A throw-away Anchor project is created in a temp directory and deleted
# afterwards. No file in this repository is read or modified.
set -uo pipefail

EXPECT_RUST="1.79.0"
EXPECT_SOLANA="1.18.26"
EXPECT_ANCHOR="0.30.1"
RUN_TEST=0
[ "${1:-}" = "--test" ] && RUN_TEST=1

PASS=0; FAIL=0
ok()   { printf '  [PASS] %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }

check_version() {  # name, actual-output, expected
  if printf '%s' "$2" | grep -q "$3"; then ok "$1 = $3"; else bad "$1: expected $3, got: ${2:-<not found>}"; fi
}

echo "== 1. Toolchain versions =="
check_version "rustc"   "$(rustc --version 2>&1)"        "$EXPECT_RUST"
check_version "solana"  "$(solana --version 2>&1)"       "$EXPECT_SOLANA"
check_version "anchor"  "$(anchor --version 2>&1)"       "$EXPECT_ANCHOR"
node_v="$(node --version 2>&1)";   printf '%s' "$node_v" | grep -q '^v20\.' && ok "node = $node_v" || bad "node: expected v20.x, got $node_v"
py_v="$(python3 --version 2>&1)";  printf '%s' "$py_v"  | grep -q ' 3\.11\.' && ok "python3 = $py_v" || bad "python3: expected 3.11.x, got $py_v"
command -v cargo-kani >/dev/null 2>&1 && bad "Kani is installed (not expected in this phase)" || ok "Kani not installed (expected)"

echo "== 2. anchor build (temp project) =="
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
(
  cd "$WORK" && anchor init verify_prog --no-git >/dev/null 2>&1 \
  || { echo "anchor init failed"; exit 1; }
  cd verify_prog && anchor build
) && BUILD_OK=1 || BUILD_OK=0

SO="$(ls "$WORK"/verify_prog/target/deploy/*.so 2>/dev/null | head -n1)"
if [ "$BUILD_OK" = 1 ] && [ -n "$SO" ]; then ok "anchor build produced $(basename "$SO")"; else bad "anchor build failed or no .so produced"; fi

if [ "$RUN_TEST" = 1 ]; then
  echo "== 3. anchor test (local validator) =="
  if (cd "$WORK/verify_prog" && timeout 600 anchor test); then ok "anchor test passed"; else bad "anchor test failed/timed out"; fi
fi

echo
echo "Result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
