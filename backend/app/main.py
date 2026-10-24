"""ASGI entry point; invalid settings fail before the server accepts requests."""

from app.application import create_app

app = create_app()
