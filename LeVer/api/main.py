"""FastAPI routes for the LeVer frontend.

Endpoints (all under ``/api``; the Vite dev server proxies ``/api`` -> :8000):
    GET  /health                 liveness + LLM configuration summary
    GET  /capabilities           adapter registry: toolchain, tools on PATH, implemented stages
    GET  /properties?target=     property catalogue (solidity | solana | all)
    POST /runs                   create a run -> 202 {run_id, status, events_url}
    GET  /runs                   list runs
    GET  /runs/{id}              run summary incl. result
    GET  /runs/{id}/events       NDJSON stream: progress | result | error | heartbeat
    POST /runs/{id}/cancel       kill the pipeline subprocess
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.properties import PropertyCatalog
from api.run_service import RunService
from api.schemas import UI_TO_CLI_MODE, RunCreate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_VERSION = "0.1.0"

app = FastAPI(title="LeVer API", version=API_VERSION)

_origins = [o.strip() for o in os.getenv("LEVER_API_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])

service = RunService(PROJECT_ROOT)
catalog = PropertyCatalog(PROJECT_ROOT)


def _llm_summary() -> dict:
    return {
        "model": os.getenv("LLM_MODEL") or "gemma4:e2b (default)",
        "base_url": os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1 (default)",
        "api_key_configured": bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")),
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok", "service": "lever-api", "version": API_VERSION,
        "project_root": str(PROJECT_ROOT), "active_runs": service.active_count, "llm": _llm_summary(),
    }


@app.get("/api/capabilities")
def capabilities() -> dict:
    from core.adapter_factory import _REGISTRY, adapter_factory
    targets = []
    for key in _REGISTRY:
        try:
            targets.append(adapter_factory(key).describe())
        except Exception as exc:  # an adapter that cannot even be constructed is reported, not hidden
            targets.append({"target": key, "available": False, "pipeline_ready": False, "error": str(exc),
                            "tools": {}, "implemented_stages": [], "missing_stages": [], "toolchain": ""})
    modes = [{"id": ui, "cli": cli} for ui, cli in UI_TO_CLI_MODE.items() if ui != "lean_only"]
    return {"targets": targets, "modes": modes, "llm": _llm_summary()}


@app.get("/api/properties")
def properties(target: Optional[str] = Query(default=None)) -> dict:
    if target is None or target == "all":
        items = catalog.all()
        return {"target": "all", "count": len(items), "properties": items}
    try:
        items = catalog.get(target)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"target": target.lower(), "count": len(items), "properties": items}


@app.post("/api/runs", status_code=202)
def create_run(payload: RunCreate) -> dict:
    try:
        record = service.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": record.spec.run_id, "status": record.status,
            "events_url": f"/api/runs/{record.spec.run_id}/events", "run": record.summary()}


@app.get("/api/runs")
def list_runs() -> dict:
    return {"items": [r.summary() for r in service.list()]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    record = service.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'.")
    return record.summary(include_result=True)


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str) -> StreamingResponse:
    if service.get(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'.")
    return StreamingResponse(service.stream(run_id), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    record = service.cancel(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'.")
    return record.summary()
