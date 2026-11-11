"""Pydantic models shared by the HTTP layer.

The request model accepts the frontend's ``RunInput`` shape verbatim
(camelCase) as well as snake_case aliases. UI mode identifiers are mapped to
the CLI identifiers used by ``core.main_pipeline`` (``lean`` -> ``lean_only``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

Target = Literal["solidity", "solana"]

# UI identifier -> CLI identifier. ``lean_only`` is accepted for CLI parity.
UI_TO_CLI_MODE: Dict[str, str] = {
    "lean": "lean_only",
    "lean_only": "lean_only",
    "no_lean": "no_lean",
    "full": "full",
}


class RunCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(default="Untitled build", max_length=120)
    requirement: str = Field(max_length=20_000)
    target: Target = "solidity"
    mode: str = "full"
    max_iterations: int = Field(
        default=3, ge=1, le=10,
        validation_alias=AliasChoices("maxIterations", "max_iterations"),
    )
    attack_rounds: int = Field(
        default=3, ge=1, le=10,
        validation_alias=AliasChoices("attackRounds", "attack_rounds"),
    )

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, value: str) -> str:
        key = (value or "").strip().lower()
        if key not in UI_TO_CLI_MODE:
            raise ValueError(f"Unsupported mode '{value}'. Use one of: lean, no_lean, full.")
        return "lean" if key == "lean_only" else key

    @field_validator("name", "requirement")
    @classmethod
    def _strip(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("requirement")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Requirement must not be empty.")
        return value

    @property
    def cli_mode(self) -> str:
        return UI_TO_CLI_MODE[self.mode]


class RunHandle(BaseModel):
    run_id: str
    status: str
    events_url: str


# ── GenerationResult (mirrors frontend/src/types/run.ts) ─────────────

class SourceFile(BaseModel):
    path: str
    language: Literal["solidity", "rust", "text"]
    content: str


class ExecutionLog(BaseModel):
    message: str
    level: Literal["info", "warning", "error"] = "info"
    timestamp: Optional[str] = None


class VerificationCheck(BaseModel):
    name: str
    status: Literal["passed", "failed", "unknown", "skipped"]
    detail: Optional[str] = None


class Verification(BaseModel):
    status: Literal["passed", "failed", "unknown", "skipped"]
    detail: Optional[str] = None
    checks: List[VerificationCheck] = Field(default_factory=list)


class Issue(BaseModel):
    id: str
    title: str
    description: str
    severity: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    endLine: Optional[int] = None
    suggestion: Optional[str] = None


class Report(BaseModel):
    filename: str
    content: str
    mimeType: str


class GenerationResult(BaseModel):
    files: List[SourceFile]
    specification: Optional[str] = None
    verification: Optional[Verification] = None
    issues: Optional[List[Issue]] = None
    logs: Optional[List[ExecutionLog]] = None
    summary: Optional[str] = None
    report: Optional[Report] = None


class RunSummary(BaseModel):
    run_id: str
    name: str
    target: str
    mode: str
    cli_mode: str
    status: str
    created_at: str
    finished_at: Optional[str] = None
    current_stage: Optional[str] = None
    error: Optional[str] = None
    workspace: str
    exit_code: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
