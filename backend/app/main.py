from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.collect import router as collect_router
from app.api.health import router as health_router
from app.api.market import router as market_router
from app.api.pool import router as pool_router
from app.core.config import get_settings
from app.scheduler.runner import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


settings = get_settings()
cors_origins = [item.strip() for item in settings.cors_allow_origins.split(",") if item.strip()]

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(collect_router)
app.include_router(pool_router)
app.include_router(market_router)
