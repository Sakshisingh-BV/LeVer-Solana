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

# --- Lockfile strategy ---------------------------------------------------------
# Problem: Cargo 1.79 ignores `rust-version`, so a fresh Cargo.lock can select
# crates that need a newer Rust (edition 2024 / Rust >= 1.85), which Cargo 1.79
# cannot even parse (seen: crypto-common 0.2, zeroize_derive 1.5, indexmap 2.14, ...).
#
# Fix: generate the lockfile with a TEMPORARY newer Cargo that has an MSRV-aware
# resolver (CARGO_RESOLVER_INCOMPATIBLE_RUST_VERSIONS=fallback, Cargo >= 1.84) and a
# compatibility target of Rust $MSRV_TARGET (rust-version in the temp project's manifest).
# That toolchain is used ONLY for `generate-lockfile` / `update`; the default
# toolchain (rustc/cargo $EXPECT_RUST) is never changed and does all the building.
# It is installed inside the container only (rustup, --profile minimal).
LOCK_TOOLCHAIN="1.85.0"
MSRV_TARGET="1.75"

# Safety net for crates the MSRV-aware resolver cannot fix (no/incorrect rust-version
# metadata). Each pin: "<crate> <version>":
#   blake3 1.8.2         solana-program -> blake3 ^1.5.0 (features digest + traits-preview).
#                        blake3 >= 1.8.4 -> digest ^0.11 -> crypto-common 0.2.x (Rust 1.85).
#                        blake3 declares no rust-version, so the resolver cannot avoid it.
#   zeroize_derive 1.4.2 solana-program zeroize ^1.3 + curve25519-dalek 3.2.1 (zeroize >=1,<1.4)
#                        force zeroize 1.3.0 whose zeroize_derive req is a bare ^1 -> 1.5.0 (Rust 1.85).
PINS=(
  "blake3 1.8.2"
  "zeroize_derive 1.4.2"
)

lockcargo() { CARGO_RESOLVER_INCOMPATIBLE_RUST_VERSIONS=fallback cargo "+$LOCK_TOOLCHAIN" "$@"; }

# Cargo.lock helpers (read the lockfile only; no crate download/parse)
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

echo "== 2. Prepare temp project and an MSRV-$MSRV_TARGET lockfile =="
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

prepare_project() {  # returns non-zero (after reporting) if anything fails
  # 2.1 temporary lockfile toolchain (container only)
  if ! rustup toolchain list 2>/dev/null | grep -q "^$LOCK_TOOLCHAIN"; then
    echo "  installing temporary lockfile-only toolchain $LOCK_TOOLCHAIN (container only, not used to build)"
    if ! rustup toolchain install "$LOCK_TOOLCHAIN" --profile minimal --no-self-update >"$WORK/rustup.log" 2>&1; then
      bad "rustup toolchain install $LOCK_TOOLCHAIN failed:"; tail -n 15 "$WORK/rustup.log" | sed 's/^/    /'; return 1
    fi
  fi
  ok "lockfile toolchain available: $(cargo "+$LOCK_TOOLCHAIN" --version 2>&1)"
  active="$(rustup show active-toolchain 2>/dev/null | head -n1)"
  case "$active" in
    "$EXPECT_RUST"*) ok "build toolchain unchanged: $active" ;;
    *) bad "default (build) toolchain is not $EXPECT_RUST: ${active:-<unknown>}"; return 1 ;;
  esac

  # 2.2 temp project + compatibility target
  if ! (cd "$WORK" && anchor init verify_prog --no-git >"$WORK/init.log" 2>&1); then
    bad "anchor init failed:"; tail -n 20 "$WORK/init.log" | sed 's/^/    /'; return 1
  fi
  cd "$WORK/verify_prog" || return 1
  for m in programs/*/Cargo.toml; do sed -i "/^\[package\]/a rust-version = \"$MSRV_TARGET\"" "$m"; done
  if ! grep -q "rust-version = \"$MSRV_TARGET\"" programs/*/Cargo.toml; then bad "could not set rust-version $MSRV_TARGET in temp project"; return 1; fi
  ok "compatibility target rust-version = $MSRV_TARGET set in temp project manifest"

  # 2.3 MSRV-aware lockfile (new Cargo, lockfile generation only)
  if ! lockcargo generate-lockfile >"$WORK/lock.log" 2>&1; then
    bad "cargo +$LOCK_TOOLCHAIN generate-lockfile failed:"; sed 's/^/    /' "$WORK/lock.log"; return 1
  fi
  lockver="$(sed -n 's/^version = \([0-9][0-9]*\)$/\1/p' Cargo.lock | head -n1)"
  if [ "${lockver:-0}" -ge 4 ]; then
    bad "Cargo.lock format v$lockver is too new for Cargo $EXPECT_RUST / Solana platform-tools (need v3)"; return 1
  fi
  ok "MSRV-aware Cargo.lock generated (format v${lockver:-?})"

  # 2.4 safety-net pins, with chain evidence
  echo "  Lock contents before pins:"
  for pin in "${PINS[@]}"; do
    read -r crate ver <<<"$pin"
    echo "  - $crate: $(lock_versions "$crate" | tr '\n' ' ')(pin -> $ver); depended on by:"
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
    if lock_versions "$crate" | grep -qx "$ver"; then ok "$crate already at $ver"; continue; fi
    if ! lockcargo update -p "$crate" --precise "$ver" >"$WORK/pin-$crate.log" 2>&1; then
      bad "cargo update -p $crate --precise $ver failed:"; sed 's/^/    /' "$WORK/pin-$crate.log"; pin_failed=1; continue
    fi
    if lock_versions "$crate" | grep -qx "$ver"; then ok "$crate pinned to $ver"
    else bad "$crate is not at $ver after pinning (lock has: $(lock_versions "$crate" | tr '\n' ' '))"; pin_failed=1; fi
  done
  if lock_has_bad_crypto_common; then
    bad "crypto-common 0.2.x is STILL in Cargo.lock after pinning. Remaining dependents:"; lock_why crypto-common; pin_failed=1
  fi
  lockver="$(sed -n 's/^version = \([0-9][0-9]*\)$/\1/p' Cargo.lock | head -n1)"
  if [ "${lockver:-0}" -ge 4 ]; then bad "Cargo.lock became format v$lockver after pinning"; pin_failed=1; fi
  [ "$pin_failed" = 0 ]
}

PREP_OK=0
prepare_project && PREP_OK=1

echo "== 2b. anchor build (temp project) =="
BUILD_OK=0
if [ "$PREP_OK" = 1 ]; then
  cd "$WORK/verify_prog" || exit 1
  echo "  building with default toolchain: $(rustc --version) / $(cargo --version)"
  anchor build && BUILD_OK=1
  if [ "$BUILD_OK" = 0 ]; then
    echo "  build failed. Report the first 'error:' above. If it names a crate that needs a newer Rust/edition2024,"
    echo "  add it to PINS (cargo update -p <crate> --precise <older-version>) and re-run."
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
