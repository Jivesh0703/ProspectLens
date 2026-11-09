"""Vercel WSGI entrypoint."""
from server import create_app

app = create_app()
