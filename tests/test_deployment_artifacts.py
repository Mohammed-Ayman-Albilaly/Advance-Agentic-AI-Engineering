from pathlib import Path

import yaml


def test_dockerfile_has_reproducible_fastapi_service_and_nonroot_user():
    text = Path("Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in text
    assert "pip install -r requirements.txt" in text
    assert "USER uniflow" in text
    assert "HEALTHCHECK" in text
    assert "uvicorn" in text
    assert "app.api.main:app" in text


def test_compose_persists_application_and_checkpoint_data():
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "uniflow-api:" in text
    assert "DATABASE_PATH: /app/data/uniflow.sqlite" in text
    assert "CHECKPOINT_DATABASE_PATH: /app/data/checkpoints.sqlite" in text
    assert "uniflow-data:/app/data" in text
    assert "OPENAI_API_KEY: ${OPENAI_API_KEY:-}" in text


def test_dockerignore_excludes_secrets_and_runtime_data():
    text = Path(".dockerignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert "data/*.sqlite" in text
    assert "logs" in text


def test_compose_file_parses_as_yaml():
    data = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    assert "services" in data
    assert "uniflow-api" in data["services"]
