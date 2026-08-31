"""FastAPI dependency providers.

Every provider here constructs its real client lazily, inside the function
body -- never at import time -- so importing api.main never requires
DATABASE_URL, S3_BUCKET_NAME, or ANTHROPIC_API_KEY to be set. Tests override
these with fakes via app.dependency_overrides instead of setting real
credentials, the same pattern already used by agent/resolve.py's null
clients.
"""

from __future__ import annotations

from typing import Iterator

import psycopg

from api.config import get_settings
from api.llm import AnthropicLike, get_anthropic_client
from api.repository import PostgresRepository, Repository
from api.storage import S3Storage, Storage


def get_repository() -> Iterator[Repository]:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    conn = psycopg.connect(settings.database_url)
    try:
        yield PostgresRepository(conn)
    finally:
        conn.close()


def get_storage() -> Storage:
    settings = get_settings()
    if not settings.s3_bucket:
        raise RuntimeError("S3_BUCKET_NAME is not configured")
    return S3Storage(settings.s3_bucket, region=settings.aws_region)


def get_llm_client() -> AnthropicLike:
    settings = get_settings()
    return get_anthropic_client(settings.anthropic_api_key)
