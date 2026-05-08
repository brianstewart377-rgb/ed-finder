"""Supervisor entry-point shim.

The Emergent preview supervisor runs `uvicorn server:app` from /app/backend,
but this codebase's FastAPI composition root lives in `main.py`. This file
just re-exports `app` from main so the supervisor command works unchanged.
"""
from main import app  # noqa: F401
