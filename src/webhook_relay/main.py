from fastapi import FastAPI
from sqlalchemy import text

from webhook_relay.config import Settings, get_settings
from webhook_relay.db import make_engine, make_session_factory
from webhook_relay.delivery import Deliverer
from webhook_relay.routers import events, hooks, sources


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    app = FastAPI(title="Webhook Relay", version="0.1.0")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.deliverer = Deliverer(session_factory, settings)

    app.include_router(sources.router)
    app.include_router(hooks.router)
    app.include_router(events.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app
