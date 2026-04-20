"""FastAPI application entry-point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from auth import COOKIE_NAME
from config import ENABLE_AUTH_DEBUG, IS_POSIT_CONNECT, get_allowed_users
from database import close_db, init_db, migrate_legacy_tasks
from routers import auth, custom_tasks, dashboard, me, studies, tracker, user

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
    logger.info("ALLOWED_USERS      = %s", get_allowed_users() or "(no restriction)")

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
# Auth middleware — redirect unauthenticated users to /login
# ---------------------------------------------------------------------------
_PUBLIC_PREFIXES = ("/login", "/api/auth/", "/static/")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        username = request.cookies.get(COOKIE_NAME, "").strip().lower()
        allowed = get_allowed_users()

        if allowed and (not username or username not in allowed):
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return RedirectResponse(url="/login", status_code=302)
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "未登录"}, status_code=401)

        return await call_next(request)


app.add_middleware(AuthMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
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


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the main dashboard page."""
    return templates.TemplateResponse(request, "index.html")
