"""FastAPI application entry-point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import ENABLE_AUTH_DEBUG, IS_POSIT_CONNECT
from database import close_db, init_db, migrate_legacy_tasks
from routers import custom_tasks, dashboard, me, studies, tracker, user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
_LEGACY_JSON = _BASE_DIR / "custom_tasks.json"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup / shutdown: DB init, legacy migration, cleanup."""
    await init_db()

    migrated = await migrate_legacy_tasks(_LEGACY_JSON)
    if migrated:
        logger.info("Migrated %d legacy custom tasks into SQLite", migrated)

    logger.info(
        "Auth mode: %s | ALLOW_ANONYMOUS=%s | ENABLE_AUTH_DEBUG=%s",
        "posit-connect" if IS_POSIT_CONNECT else "dev",
        os.environ.get("ALLOW_ANONYMOUS", "0"),
        os.environ.get("ENABLE_AUTH_DEBUG", "0"),
    )

    yield

    await close_db()


app = FastAPI(
    title="Tracker 追踪日志可视化平台",
    version="0.2.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(user.router)
app.include_router(studies.router)
app.include_router(tracker.router)
app.include_router(dashboard.router)
app.include_router(custom_tasks.router)
app.include_router(me.router)

if ENABLE_AUTH_DEBUG:
    from routers import debug as debug_router
    app.include_router(debug_router.router)
    logger.warning("Auth debug endpoint enabled at /api/debug/auth — disable in production")

# ---------------------------------------------------------------------------
# Static files & templates
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=_BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the main dashboard page."""
    return templates.TemplateResponse(request, "index.html")
