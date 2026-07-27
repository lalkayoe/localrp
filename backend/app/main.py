from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.characters import router as characters_router
from app.api.routes.memory import router as memory_router
from app.api.routes.misc import router as misc_router
from app.api.routes.backup import router as backup_router
from app.core.config import settings
from app.db.session import init_db
from app.services.auth.deps import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(characters_router)
app.include_router(memory_router)
app.include_router(misc_router)
app.include_router(backup_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
