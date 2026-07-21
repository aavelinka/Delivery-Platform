from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from platform_common.observability import configure_logging, install_request_observability
from platform_common.outbox import OutboxPublisher

from app.api.routes import router
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import CourierLocation, OutboxEvent, TrackedOrder  # noqa: F401
from app.db.session import SessionLocal, engine
from app.kafka.consumer import NoopOrderEventsConsumer, OrderEventsConsumer
from app.kafka.producer import KafkaPublisher, NoopKafkaPublisher
from app.metrics import register_domain_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    publisher = KafkaPublisher(settings) if settings.kafka_enabled else NoopKafkaPublisher()
    consumer = (
        OrderEventsConsumer(settings, publisher if settings.kafka_enabled else None)
        if settings.kafka_enabled
        else NoopOrderEventsConsumer()
    )
    outbox_publisher = (
        OutboxPublisher(
            session_factory=SessionLocal,
            event_model=OutboxEvent,
            publisher=publisher,
        )
        if settings.kafka_enabled
        else None
    )
    app.state.kafka_publisher = publisher
    app.state.order_events_consumer = consumer
    app.state.outbox_publisher = outbox_publisher
    await publisher.start()
    await consumer.start()
    if outbox_publisher is not None:
        await outbox_publisher.start()
    try:
        yield
    finally:
        if outbox_publisher is not None:
            await outbox_publisher.stop()
        await consumer.stop()
        await publisher.stop()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.service_name, version="0.1.0", lifespan=lifespan)
    install_request_observability(app, settings.service_name, settings.environment)
    register_domain_metrics(app)

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
