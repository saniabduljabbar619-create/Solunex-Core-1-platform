from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context

# Import Base where models register
from config import Base

# Import models so metadata includes them
import app.models.license_model
import app.models.logs_model
import app.models.license_model   # If you have this
import app.models.user_model      # If you have this
# Alembic config
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Important: Provide metadata for autogenerate
target_metadata = Base.metadata

# Read DB URL from env or alembic.ini
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

def run_migrations_offline():
    """Run migrations without DB engine."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations with DB engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()