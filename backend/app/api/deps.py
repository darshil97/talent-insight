"""Shared request dependencies for catalog-backed routes."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

JobId = Annotated[str, Path(pattern=r"^demo_[a-z0-9_]+$", max_length=64)]


def catalog_session(request: Request) -> Iterator[Session]:
    """Each request uses a bounded, read-only transaction; never seed on demand."""
    engine = request.app.state.database_engine
    if engine is None:
        raise HTTPException(503)
    try:
        with Session(engine, autoflush=False) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            yield session
    except SQLAlchemyError:
        raise HTTPException(503) from None


CatalogSession = Annotated[Session, Depends(catalog_session)]
