from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from platform_common.observability import configure_logging, install_request_observability

from app.api.routes import router
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import UserAddress, UserProfile  # noqa: F401
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.service_name, version="0.1.0", lifespan=lifespan)
    install_request_observability(app, settings.service_name, settings.environment)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
