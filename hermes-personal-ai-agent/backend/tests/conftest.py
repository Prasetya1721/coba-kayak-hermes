"""Pytest fixtures and shared configuration."""

from __future__ import annotations

import os

import pytest

# Ensure deterministic test settings before importing the app.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("VAULT_REQUIRED", "false")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-long-enough-1234567890")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("OPENAI_API_KEY", "")


@pytest.fixture
def app_client():
    """FastAPI test client without a live database (routes requiring DB are skipped)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client
