"""FastAPI application entry-point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import close_db, init_db, migrate_legacy_tasks
from routers import custom_tasks, dashboard, file_compare, me, settings, studies, todos, tracker, user

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
    from config import DATABASE_PATH, PROJECTS_BASE_PATH

    logger.info("PROJECTS_BASE_PATH = %s (exists=%s)", PROJECTS_BASE_PATH, PROJECTS_BASE_PATH.exists())
    logger.info("DATABASE_PATH      = %s", DATABASE_PATH)

    await init_db()

    migrated = await migrate_legacy_tasks(_LEGACY_JSON)
    if migrated:
        logger.info("Migrated %d legacy custom tasks into SQLite", migrated)

    yield

    await close_db()


app = FastAPI(
    title="PEAK — Project Efficiency & Automation Kernel",
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
app.include_router(todos.router)
app.include_router(me.router)
app.include_router(file_compare.router)
app.include_router(settings.router)

# ---------------------------------------------------------------------------
# Static files & templates
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=_BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def welcome_page(request: Request) -> HTMLResponse:
    """Landing / welcome page."""
    return templates.TemplateResponse(request, "welcome.html")


@app.get("/tracker", response_class=HTMLResponse)
async def tracker_page(request: Request) -> HTMLResponse:
    """Tracker dashboard (brick log visualization)."""
    return templates.TemplateResponse(request, "tracker.html")


@app.get("/file-compare", response_class=HTMLResponse)
async def file_compare_page(request: Request) -> HTMLResponse:
    """File preview & compare module (placeholder)."""
    return templates.TemplateResponse(request, "file_compare.html")
