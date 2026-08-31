"""Environment-driven settings, read lazily.

Nothing here touches the environment at import time -- every value is read
inside get_settings(), which itself is only called from within request
handlers or dependency providers. Importing this module (or anything that
imports it) must never fail just because DATABASE_URL, ANTHROPIC_API_KEY, or
AWS credentials are absent, so it stays safe to import in CI and in tests
that override the real dependencies with fakes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    s3_bucket: str | None
    aws_region: str
    anthropic_api_key: str | None
    anthropic_model: str
    razorpay_key_id: str | None
    razorpay_key_secret: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL"),
        s3_bucket=os.environ.get("S3_BUCKET_NAME"),
        aws_region=os.environ.get("AWS_REGION", "ap-south-1"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID"),
        razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET"),
    )
