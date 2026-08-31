from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.deps import get_llm_client, get_repository, get_storage
from api.main import app
from tests.api_fakes import FakeLLMClient, FakeRepository, FakeStorage


@pytest.fixture
def fake_repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def client(fake_repo: FakeRepository, fake_storage: FakeStorage, fake_llm: FakeLLMClient) -> TestClient:
    app.dependency_overrides[get_repository] = lambda: fake_repo
    app.dependency_overrides[get_storage] = lambda: fake_storage
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
