from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .api.routes import router
from .config import settings
from .db import Base, engine


class Redact(logging.Filter):
    """Never log credentials or message bodies."""
    def filter(self, record):
        msg = str(record.getMessage())
        for needle in (settings.anthropic_api_key, settings.jwt_secret):
            if needle and needle in msg:
                record.msg, record.args = msg.replace(needle, "[redacted]"), ()
        return True


logging.getLogger().addFilter(Redact())
logging.getLogger("uvicorn.access").addFilter(Redact())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.run_worker_in_api:
        jobs.start_workers()
    yield
    jobs.stop_workers()


app = FastAPI(title="AI Architect Studio", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"], allow_credentials=False)
app.include_router(router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logging.getLogger("studio").error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse(status_code=500, content=dict(error=dict(code="internal", message="Something went wrong on the server. Your project is unchanged.", next_actions=["Retry"])))


dist = Path(settings.frontend_dir)
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (dist / path).resolve()
        if path and dist.resolve() in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(dist / "index.html")
