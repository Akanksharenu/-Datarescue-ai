from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.db import engine
from app.models import Base


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Repeatable schema setup: create any missing tables on startup. POST /demo/seed resets them.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="DataRescue AI",
    description=(
        "Detects broken retail data batches, stores incident evidence, explains likely causes, "
        "and runs human-approved recovery. All demo data is simulated."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
