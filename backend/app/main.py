# -*- coding: utf-8 -*-
"""Harbi Ganyan API."""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, auth, content
from .config import settings
from .db import Base, engine

APP_DIR = Path(__file__).resolve().parent
cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Development convenience; production should run Alembic migrations.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Harbi Ganyan API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/saglik")
def saglik():
    return {"durum": "ok"}


app.include_router(content.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.mount("/admin-static", StaticFiles(directory=APP_DIR / "static"), name="admin-static")


@app.get("/admin", include_in_schema=False)
def admin_panel():
    return FileResponse(APP_DIR / "static" / "admin.html")
