# ──────────────────────────────────────────────────────────────────────
# core/kani_templates.py
# Which Solana properties (properties/solana.json) get Kani harnesses,
# and the per-property data used to name and prompt those harnesses.
#
# Split (SOLANA_VERIFICATION_ROADMAP.md Phase 3; solana.json default_selection
# rule "Run Kani only for properties whose formal rating is yes or partial"):
#   KANI_ELIGIBLE      → a `sol_XX_<slug>` harness may be generated.
#   UNVERIFIED_SURFACE → never given a harness; static + Anchor tests only,
#                        reported as unverified surface.
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional

#: Default loop-unwinding bound for generated harnesses (`#[kani::unwind(N)]`).
#: Loops that need more iterations show up as `unwind` FAILUREs, never as passes.
DEFAULT_UNWIND = 8

KANI_ELIGIBLE = (
    "SOL-01", "SOL-02", "SOL-03", "SOL-04", "SOL-07", "SOL-08", "SOL-09",
    "SOL-11", "SOL-12", "SOL-13", "SOL-16", "SOL-17", "SOL-18",
)

UNVERIFIED_SURFACE = ("SOL-05", "SOL-06", "SOL-10", "SOL-14", "SOL-15")

# Harness-name slugs. A harness for property SOL-XX is named
# `sol_XX_<slug>`; harness_property_id() in kani_utils reverses this.
_SLUGS: Dict[str, str] = {
    "SOL-01": "signer_check",
    "SOL-02": "owner_check",
    "SOL-03": "pda_bump",
    "SOL-04": "duplicate_accounts",
    "SOL-07": "arithmetic_overflow",
    "SOL-08": "authority_match",
    "SOL-09": "state_transition",
    "SOL-11": "discriminator_check",
    "SOL-12": "reinitialization",
    "SOL-13": "close_safety",
    "SOL-16": "remaining_accounts",
    "SOL-17": "lamport_conservation",
    "SOL-18": "realloc_bounds",
}

PROPERTIES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "properties", "solana.json"
)

_ID_RE = re.compile(r"^\s*sol[-_ ]?(\d{1,2})(?!\d)", re.IGNORECASE)


@dataclass(frozen=True)
class KaniTemplate:
    property_id: str      # "SOL-07"
    name: str             # catalogue name, e.g. "Arithmetic Overflow"
    slug: str             # "arithmetic_overflow"
    harness_prefix: str   # "sol_07_"
    harness_name: str     # "sol_07_arithmetic_overflow"
    prompt_snippet: str   # what the harness must model and assert
    snippet_source: str   # "formal_invariant" or "invariant_template" (fallback)


def harness_prefix(property_id: str) -> str:
    """``"SOL-07"`` → ``"sol_07_"``."""
    return property_id.lower().replace("-", "_") + "_"


def normalize_property_id(value: str) -> Optional[str]:
    """Map ``"SOL-07"``, ``"sol_07"``, ``"SOL_07_overflow"``, ``"sol-7"`` → ``"SOL-07"``.

    Returns None when *value* does not name a property in the Solana catalogue.
    """
    if not isinstance(value, str):
        return None
    m = _ID_RE.match(value)
    if not m:
        return None
    pid = f"SOL-{int(m.group(1)):02d}"
    return pid if pid in _catalogue() else None


@lru_cache(maxsize=1)
def _catalogue() -> Dict[str, dict]:
    with open(PROPERTIES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {p["id"]: p for p in data.get("properties", [])}


@lru_cache(maxsize=1)
def kani_templates() -> Dict[str, KaniTemplate]:
    """Templates for every KANI_ELIGIBLE property, built from properties/solana.json.

    SOL-01..09 have no ``annotations.formal_invariant`` in the catalogue yet, so their
    snippet falls back to ``invariant_template`` (recorded in ``snippet_source``).
    The ``verification.formal.note`` (what Kani can and cannot model), when present,
    is appended as the scope.
    """
    catalogue = _catalogue()
    templates: Dict[str, KaniTemplate] = {}
    for pid in KANI_ELIGIBLE:
        prop = catalogue.get(pid)
        if prop is None:
            raise KeyError(f"{pid} is KANI_ELIGIBLE but missing from {PROPERTIES_PATH}")
        annotations = prop.get("annotations") or {}
        formal = annotations.get("formal_invariant")
        invariant = formal or prop.get("invariant_template", "")
        source = "formal_invariant" if formal else "invariant_template"
        snippet = f"Invariant: {invariant}"
        scope = ((annotations.get("verification") or {}).get("formal") or {}).get("note")
        if scope:
            snippet += f"\nKani scope: {scope}"
        prefix = harness_prefix(pid)
        templates[pid] = KaniTemplate(
            property_id=pid,
            name=prop.get("name", pid),
            slug=_SLUGS[pid],
            harness_prefix=prefix,
            harness_name=prefix + _SLUGS[pid],
            prompt_snippet=snippet,
            snippet_source=source,
        )
    return templates


def get_kani_template(property_id: str) -> Optional[KaniTemplate]:
    """Template for a Kani-eligible property, or None (unknown id or unverified surface)."""
    pid = normalize_property_id(property_id)
    return kani_templates().get(pid) if pid else None
