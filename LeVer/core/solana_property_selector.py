"""Choose the Kani properties for a generated Solana (Anchor) program.

The five baseline properties apply to almost every program and are always kept.
Further Kani-eligible properties are added when the generated code shows the
feature they protect (a PDA, an ``init``, lamport movement, ...). Selection reads
the code, not the requirement: the code is what Kani checks, and a requirement
often leaves out features such as PDAs.

Overrides (for experiments):
  LEVER_SOLANA_KANI_PROPERTIES="SOL-01,SOL-03"  use exactly these (eligible ones only)
  LEVER_SOLANA_PROPERTY_SELECTION=0             baseline only
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Pattern, Tuple

from core.kani_templates import KANI_ELIGIBLE, normalize_property_id

BASELINE: Tuple[str, ...] = ("SOL-01", "SOL-02", "SOL-04", "SOL-07", "SOL-08")

# property id -> (why it was added, pattern that shows the feature in Anchor code)
SIGNALS: Dict[str, Tuple[str, Pattern[str]]] = {
    "SOL-03": ("PDA derivation (seeds / bump)",
               re.compile(r"\bseeds\s*=|\bfind_program_address\b|\bcreate_program_address\b|\bctx\.bumps\b")),
    "SOL-09": ("state / status enum",
               re.compile(r"\benum\s+\w*(?:State|Status|Phase|Stage)\b")),
    "SOL-11": ("manual account deserialization or unchecked accounts",
               re.compile(r"\btry_from_slice\b|\btry_deserialize(?:_unchecked)?\b|\bAccountLoader\b|\bUncheckedAccount\b")),
    "SOL-12": ("account initialization (init / init_if_needed)",
               re.compile(r"\binit_if_needed\b|#\s*\[\s*account\s*\((?:(?!\)\s*\]).)*?\binit\b|\bis_initialized\b", re.S)),
    "SOL-13": ("account closing",
               re.compile(r"\bclose\s*=|\bclose_account\b")),
    "SOL-16": ("remaining_accounts",
               re.compile(r"\bremaining_accounts\b")),
    "SOL-17": ("lamport movement / rent",
               re.compile(r"\btry_borrow_mut_lamports\b|\bsystem_program::transfer\b|\bRent::get\b|\bminimum_balance\b")),
    "SOL-18": ("account realloc",
               re.compile(r"\brealloc\b")),
}


def _mask(code: str) -> str:
    """Blank out comments and string literals so they cannot trigger a signal."""
    try:
        from core.pipeline.kani_utils import _mask_rust
        return _mask_rust(code)
    except Exception:  # pragma: no cover - fallback if the helper moves
        code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
        code = re.sub(r"//[^\n]*", " ", code)
        return re.sub(r'"(?:\\.|[^"\\])*"', '""', code)


def select_solana_kani_properties(code: str) -> Tuple[List[str], Dict[str, str]]:
    """Return (property ids in id order, {added id: reason})."""
    pinned = os.getenv("LEVER_SOLANA_KANI_PROPERTIES", "").strip()
    if pinned:
        ids = []
        for raw in pinned.split(","):
            pid = normalize_property_id(raw.strip())
            if pid in KANI_ELIGIBLE and pid not in ids:
                ids.append(pid)
        return sorted(ids), {pid: "pinned by LEVER_SOLANA_KANI_PROPERTIES" for pid in ids if pid not in BASELINE}

    selected = [pid for pid in BASELINE if pid in KANI_ELIGIBLE]
    reasons: Dict[str, str] = {}
    if os.getenv("LEVER_SOLANA_PROPERTY_SELECTION", "1").strip() not in ("0", "false", "off"):
        masked = _mask(code or "")
        for pid, (why, pattern) in SIGNALS.items():
            if pid in KANI_ELIGIBLE and pid not in selected and pattern.search(masked):
                selected.append(pid)
                reasons[pid] = why
    return sorted(selected), reasons
