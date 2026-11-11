#!/usr/bin/env bash
# Verifies the Codespaces Solana toolchain independently of LeVer's own code.
#
#   bash scripts/verify_solana_env.sh          # versions + `anchor build`
#   bash scripts/verify_solana_env.sh --test   # also runs `anchor test`
#
# A throw-away Anchor project is created in a temp directory and deleted
# afterwards. No file in this repository is read or modified.
# The temp project's Cargo.lock is generated and the crates listed in PINS are
# pinned to versions that Rust 1.79 can parse (reasons are documented at PINS).
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

# --- Cargo.lock helpers (read the lockfile only; no crate download/parse) -----
# Cargo 1.79 ignores `rust-version`, so a fresh lockfile can select crates that
# need a newer Rust (edition 2024 / Rust 1.85), which Cargo 1.79 cannot parse.
# Known cases for solana-program 1.18.26 (each pin: "<crate> <version>"):
#   blake3 1.8.2         solana-program -> blake3 ^1.5.0 (features digest + traits-preview).
#                        blake3 >= 1.8.4 -> digest ^0.11 -> crypto-common 0.2.x (Rust 1.85).
#                        1.8.2 deps (digest ^0.10, constant_time_eq 0.3) are all old.
#   zeroize_derive 1.4.2 solana-program zeroize ^1.3 + curve25519-dalek 3.2.1 (zeroize >=1,<1.4)
#                        force zeroize 1.3.0, whose zeroize_derive req is a bare ^1, so Cargo
#                        picks zeroize_derive 1.5.0 (Rust 1.85). 1.4.2 is edition 2021 (MSRV 1.56).
PINS=(
  "blake3 1.8.2"
  "zeroize_derive 1.4.2"
)

lock_why() {  # lock_why <crate> : lockfile packages that depend on <crate>
  awk -v want="$1" '
    /^\[\[package\]\]/ { name=""; ver=""; indeps=0; next }
    /^name = /         { n=$3; gsub(/"/,"",n); name=n; next }
    /^version = /      { v=$3; gsub(/"/,"",v); ver=v; next }
    /^dependencies = \[/ { indeps=1; next }
    indeps && /^\]/    { indeps=0; next }
    indeps             { d=$1; gsub(/[",]/,"",d); if (d==want) { l=$0; gsub(/^ +/,"",l); print "    " name " " ver "  ->  " l } }
  ' Cargo.lock
}
lock_versions() {  # lock_versions <crate> : versions of <crate> present in the lockfile
  awk -v want="$1" '
    /^name = /    { n=$3; gsub(/"/,"",n); hit=(n==want); next }
    /^version = / { if (hit) { v=$3; gsub(/"/,"",v); print v; hit=0 } }
  ' Cargo.lock
}
lock_has_bad_crypto_common() { lock_versions crypto-common | grep -q '^0\.2'; }

echo "== 2. Prepare temp project and pin Rust-1.79-incompatible crates =="
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PREP_OK=0
if (cd "$WORK" && anchor init verify_prog --no-git >"$WORK/init.log" 2>&1); then
  cd "$WORK/verify_prog" || exit 1
  if cargo generate-lockfile >"$WORK/lock.log" 2>&1; then
    echo "  lockfile generated. Chain evidence BEFORE pinning:"
    for pin in "${PINS[@]}"; do
      read -r crate ver <<<"$pin"
      echo "  - $crate in lock: $(lock_versions "$crate" | tr '\n' ' ')(pin -> $ver); depended on by:"
      lock_why "$crate"
    done
    if lock_has_bad_crypto_common; then
      echo "  - crypto-common $(lock_versions crypto-common | tr '\n' ' ')(0.2.x needs Rust 1.85); depended on by:"
      lock_why crypto-common
    fi
    pin_failed=0
    for pin in "${PINS[@]}"; do
      read -r crate ver <<<"$pin"
      if [ -z "$(lock_versions "$crate")" ]; then echo "  skip $crate (not in lockfile)"; continue; fi
      if ! cargo update -p "$crate" --precise "$ver" >"$WORK/pin-$crate.log" 2>&1; then
        bad "cargo update -p $crate --precise $ver failed:"; sed 's/^/    /' "$WORK/pin-$crate.log"; pin_failed=1; continue
      fi
      if lock_versions "$crate" | grep -qx "$ver"; then ok "$crate pinned to $ver"
      else bad "$crate is not at $ver after pinning (lock has: $(lock_versions "$crate" | tr '\n' ' '))"; pin_failed=1; fi
    done
    if lock_has_bad_crypto_common; then
      bad "crypto-common 0.2.x is STILL in Cargo.lock after pinning. Remaining dependents:"; lock_why crypto-common; pin_failed=1
    fi
    [ "$pin_failed" = 0 ] && PREP_OK=1
  else
    bad "cargo generate-lockfile failed:"; sed 's/^/    /' "$WORK/lock.log"
  fi
else
  bad "anchor init failed:"; tail -n 20 "$WORK/init.log" | sed 's/^/    /'
fi

echo "== 2b. anchor build (temp project) =="
BUILD_OK=0
if [ "$PREP_OK" = 1 ]; then
  anchor build && BUILD_OK=1
  if [ "$BUILD_OK" = 0 ]; then
    echo "  build failed. Report the first 'error:' above; if it names another crate that needs a newer Rust/edition2024,"
    echo "  that crate must be pinned the same way (cargo update -p <crate> --precise <older-version>)."
  fi
else
  echo "  skipped (project preparation failed)"
fi

SO="$(ls "$WORK"/verify_prog/target/deploy/*.so 2>/dev/null | head -n1)"
if [ "$BUILD_OK" = 1 ] && [ -n "$SO" ]; then ok "anchor build produced $(basename "$SO")"; else bad "anchor build failed or no .so produced"; fi

if [ "$RUN_TEST" = 1 ]; then
  echo "== 3. anchor test (local validator) =="
  if (cd "$WORK/verify_prog" && timeout 600 anchor test); then ok "anchor test passed"; else bad "anchor test failed/timed out"; fi
fi

echo
echo "Result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
