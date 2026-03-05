"""
API Server Launcher
===================
Starts the IB Trading Assistant FastAPI server.

Usage:
    python run_api.py

Endpoints:
    http://localhost:8000/        — health check
    http://localhost:8000/docs   — interactive API docs (Swagger UI)
    http://localhost:8000/redoc  — ReDoc API docs
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,   # reload=True is incompatible with ib_async background tasks
        log_level="info",
    )
