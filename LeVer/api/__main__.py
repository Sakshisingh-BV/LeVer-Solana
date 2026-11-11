"""``python -m api`` — start the LeVer HTTP API with uvicorn."""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=os.getenv("LEVER_API_HOST", "127.0.0.1"),
        port=int(os.getenv("LEVER_API_PORT", "8000")),
        log_level=os.getenv("LEVER_API_LOG_LEVEL", "info"),
    )
