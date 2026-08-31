"""Upload storage: an S3-backed Storage protocol implementation.

The boto3 client is constructed lazily inside S3Storage.__init__, never at
import time, so importing this module never requires AWS credentials --
tests substitute a Storage implementation entirely instead of hitting S3.
"""

from __future__ import annotations

from typing import Protocol


class Storage(Protocol):
    def put(self, key: str, content: bytes, *, content_type: str = "application/octet-stream") -> str:
        """Store bytes under `key`, returning a locator (e.g. an s3:// URI)."""
        ...

    def get(self, key: str) -> bytes:
        """Retrieve the bytes stored under `key`."""
        ...


class S3Storage:
    def __init__(self, bucket: str, *, region: str | None = None) -> None:
        import boto3  # imported lazily so boto3 need not be configured at module import time

        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region)

    def put(self, key: str, content: bytes, *, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content, ContentType=content_type)
        return f"s3://{self._bucket}/{key}"

    def get(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()
