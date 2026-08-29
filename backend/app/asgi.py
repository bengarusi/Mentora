"""Production ASGI entrypoint: one service that serves both the API and the SPA.

``app.main:app`` stays the pure API with its routers at the root — that is what
the test suite and the Vite dev proxy talk to, and neither needs a built
frontend. This module wraps it for deployment:

* the API is mounted under ``/api``, which is exactly the axios ``baseURL`` the
  frontend already uses, so no frontend code changes between dev and prod;
* the built React app is served at ``/``.

One origin means no CORS in production. Mounting the API under a prefix is also
what keeps the two route spaces apart: the SPA owns ``/progress`` and ``/files``
while the API owns ``/progress`` and ``/materials``, so serving both at the root
would collide.

Kept out of ``main.py`` deliberately — importing this module requires a built
frontend, and the tests must not.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.main import app as api_app

log = logging.getLogger("app.asgi")

# asgi.py -> app -> backend -> repo root -> frontend/dist
_REPO_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _dist_dir() -> Path:
    """Where the built SPA lives. FRONTEND_DIST_DIR wins so the Docker image can
    place it outside the source tree; the repo path is the local fallback."""
    configured = settings.FRONTEND_DIST_DIR
    return Path(configured).resolve() if configured else _REPO_DIST.resolve()


app = FastAPI(title="Mentora")

# Registered first so /api/* is matched by the mount and never by the SPA
# catch-all below — Starlette resolves routes in registration order.
app.mount("/api", api_app)

_dist = _dist_dir()
_index = _dist / "index.html"

if _index.is_file():
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        """Serve a real build artifact if the path names one, otherwise hand back
        index.html so React Router can resolve the client-side route."""
        if full_path:
            candidate = (_dist / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(_dist):
                return FileResponse(candidate)
        return FileResponse(_index)

else:
    # Serving the API alone is a valid way to run, so this is a warning rather
    # than a hard failure — but in a deployed image it means the build stage
    # did not produce a frontend, which is worth shouting about.
    log.warning(
        "frontend build not found at %s — serving the API only, / will 404", _dist
    )
