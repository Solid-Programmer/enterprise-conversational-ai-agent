"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.core.config import settings
from app.observability.tracing import setup_tracing, shutdown_tracing


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_tracing()
    try:
        yield
    finally:
        shutdown_tracing()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.include_router(chat_router)
