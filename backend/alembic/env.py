"""Owned-schema migrations; offline SQL preview does not need credentials."""

from sqlalchemy.exc import SQLAlchemyError

from alembic import context
from app.config import load_settings
from app.database import SCHEMA, VERSION_TABLE, create_database_engine, migration_url
from app.models import Base


def include_name(name, type_, parent_names):
    return type_ != "schema" or name == SCHEMA


def configure(connection=None):
    context.configure(
        connection=connection,
        dialect_name="postgresql" if connection is None else None,
        target_metadata=Base.metadata,
        version_table=VERSION_TABLE,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        literal_binds=connection is None,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    configure()
else:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        configure(supplied)
    else:
        engine = create_database_engine(migration_url(load_settings()), direct=True)
        try:
            with engine.connect() as connection:
                configure(connection)
        except SQLAlchemyError:
            raise RuntimeError("Migration failed. Check the database target and access.") from None
        finally:
            engine.dispose()
