from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, engine, ensure_schema
from .routers import evaluations, rubrics

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="AI Innovation Lab Grading API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(rubrics.router)
app.include_router(evaluations.router)
