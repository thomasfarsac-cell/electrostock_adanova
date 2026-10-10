from contextlib import asynccontextmanager
import mimetypes

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as fastapi_http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import ensure_active_admin_recovery, ensure_initial_admin_user, is_request_authenticated
from app.config import APP_NAME, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR = DATA_DIR / 'images'
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
mimetypes.add_type('image/webp', '.webp')
from app.db import Base, SessionLocal, engine
from app import routes
from app.seed import seed_if_needed
from app.services.images import ensure_dirs
from app.services.schema import MIGRATION_MANAGED_TABLES, ensure_optional_columns, run_migrations
from app.services.setup_state import is_setup_completed


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_dirs()
    Base.metadata.create_all(
        bind=engine,
        tables=[table for table in Base.metadata.sorted_tables if table.name not in MIGRATION_MANAGED_TABLES],
    )
    ensure_optional_columns(engine)
    run_migrations(engine)
    db = SessionLocal()
    try:
        ensure_initial_admin_user(db)
        if is_setup_completed(db):
            ensure_active_admin_recovery(db)
            seed_if_needed(db)
    finally:
        db.close()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 403:
        return HTMLResponse(
            (
                '<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
                f'<title>Acces refuse - {APP_NAME}</title>'
                '<link rel="stylesheet" href="/static/style.css"></head><body>'
                '<main class="container narrow"><section class="card login-card">'
                '<h1>Acces refuse</h1>'
                f'<p class="muted">{exc.detail or "Vous n avez pas les droits suffisants pour cette action."}</p>'
                '<a class="btn btn-secondary" href="/">Retour au dashboard</a>'
                '</section></main></body></html>'
            ),
            status_code=403,
        )
    return await fastapi_http_exception_handler(request, exc)


@app.middleware('http')
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    public_prefixes = ('/static/', '/data/', '/login', '/setup', '/healthz')
    if path == '/healthz' or any(path.startswith(prefix) for prefix in public_prefixes):
        if path.startswith('/login'):
            db = SessionLocal()
            try:
                if not is_setup_completed(db):
                    return RedirectResponse(url='/setup', status_code=303)
            finally:
                db.close()
        return await call_next(request)
    db = SessionLocal()
    try:
        if not is_setup_completed(db):
            return RedirectResponse(url='/setup', status_code=303)
    finally:
        db.close()
    if not is_request_authenticated(request):
        return RedirectResponse(url=f'/login?next={path}', status_code=303)
    return await call_next(request)


app.mount('/static', StaticFiles(directory='static'), name='static')
app.mount('/data/images', StaticFiles(directory=str(MEDIA_DIR)), name='media')
app.include_router(routes.router)
