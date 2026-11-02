from logging.config import fileConfig

from alembic import context

from netforge.db import get_engine
from netforge.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
