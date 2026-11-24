import os
from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context
from webhook_relay import models  # noqa: F401  (registers the tables on Base.metadata)
from webhook_relay.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    # Tests hand over an open connection; otherwise connect with DATABASE_URL.
    connection = config.attributes.get("connection")
    if connection is None:
        engine = create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        return
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
