"""LeVer HTTP API.

FastAPI service that exposes the Python verification engine to the React
frontend. Run from the ``LeVer/`` directory::

    python -m api            # or: uvicorn api.main:app --port 8000

Layers (see notes.md):
    api.main          -> HTTP routes (thin controllers)
    api.run_service   -> RunService: run lifecycle + event bus (Service Layer)
    api.runners       -> PipelineRunner strategy (subprocess around core.main_pipeline)
    api.result_mapper -> per-target workspace -> GenerationResult mapping (Strategy)
    api.properties    -> PropertyCatalog: per-target property loaders
"""
