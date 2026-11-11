"""Property catalogue served to the frontend.

Each target has a loader (Strategy): Solidity uses the levelled legacy
``property.json`` that ``PropertySelector`` consumes (falling back to
``properties/solidity.json`` once it is populated); Solana uses the flat,
schema-conformant ``properties/solana.json``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


PropertyList = List[Dict[str, Any]]


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _flatten_legacy(data: Dict[str, Any]) -> PropertyList:
    """Flatten ``Level -> categories -> properties`` into schema-like entries."""
    out: PropertyList = []
    if not isinstance(data, dict):
        return out
    for level_name, level in data.items():
        if not isinstance(level, dict):
            continue
        for cat_name, cat in (level.get("categories") or {}).items():
            for prop in (cat or {}).get("properties", []) or []:
                out.append({
                    "id": prop.get("id", ""),
                    "name": prop.get("name", ""),
                    "category": cat_name,
                    "level": level_name,
                    "severity": prop.get("severity"),
                    "invariant_template": prop.get("invariant_template", ""),
                    "description": prop.get("description", ""),
                    "example_attack": prop.get("example_attack"),
                    "remediation": prop.get("remediation"),
                    "references": prop.get("references", []),
                    "target": "solidity",
                })
    return out


def _flat_catalog(target: str) -> Callable[[Path], PropertyList]:
    def load(root: Path) -> PropertyList:
        data = _read_json(root / "properties" / f"{target}.json") or {}
        props = data.get("properties") if isinstance(data, dict) else None
        return [dict(p, target=target) for p in (props or []) if isinstance(p, dict)]
    return load


def _solidity_loader(root: Path) -> PropertyList:
    flat = _flat_catalog("solidity")(root)
    if flat:
        return flat
    return _flatten_legacy(_read_json(root / "property.json") or {})


class PropertyCatalog:
    """Per-target property loaders with mtime-based caching."""

    def __init__(self, project_root: Path):
        self.root = Path(project_root)
        self._loaders: Dict[str, Callable[[Path], PropertyList]] = {
            "solidity": _solidity_loader,
            "solana": _flat_catalog("solana"),
        }
        self._cache: Dict[str, tuple] = {}

    @property
    def targets(self) -> List[str]:
        return sorted(self._loaders)

    def _sources(self, target: str) -> List[Path]:
        if target == "solidity":
            return [self.root / "properties" / "solidity.json", self.root / "property.json"]
        return [self.root / "properties" / f"{target}.json"]

    def _stamp(self, target: str) -> tuple:
        stamps = []
        for path in self._sources(target):
            try:
                stamps.append(os.path.getmtime(path))
            except OSError:
                stamps.append(None)
        return tuple(stamps)

    def get(self, target: str) -> PropertyList:
        key = (target or "").strip().lower()
        if key not in self._loaders:
            raise KeyError(f"Unknown target '{target}'. Supported: {', '.join(self.targets)}")
        stamp = self._stamp(key)
        cached = self._cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
        props = self._loaders[key](self.root)
        self._cache[key] = (stamp, props)
        return props

    def all(self) -> PropertyList:
        merged: PropertyList = []
        for target in self.targets:
            merged.extend(self.get(target))
        return merged
