from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResolutionProposal:
    hypothesis: str
    proposed_resolution: str
    confidence: float
    evidence_ids: list[str] = field(default_factory=list)
    approved: bool = False

    def asdict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "proposed_resolution": self.proposed_resolution,
            "confidence": self.confidence,
            "evidence_ids": self.evidence_ids,
            "approved": self.approved,
        }


def resolve_exception(exception: dict[str, Any], related_records: list[dict[str, Any]], *, anthropic_client: Any | None = None, mcp_client: Any | None = None) -> ResolutionProposal:
    """Resolve one exception via Anthropic API and Razorpay MCP data. Never mutates the ledger."""
    if anthropic_client is None:
        anthropic_client = _NullAnthropicClient()
    if mcp_client is None:
        mcp_client = _NullMCPClient()

    if not related_records:
        return ResolutionProposal(
            hypothesis="No hypothesis formed.",
            proposed_resolution="No automated resolution proposed; requires human review.",
            confidence=0.0,
            evidence_ids=[],
            approved=False,
        )

    prompt = {
        "exception": exception,
        "related_records": related_records,
        "instruction": "Only propose a resolution if the evidence is explicit. If the evidence does not support a safe conclusion, say so explicitly and do not invent a hypothesis.",
    }
    response = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": json.dumps(prompt)}],
    )

    content = response.content[0].text if getattr(response, "content", None) else ""
    payload = json.loads(content) if isinstance(content, str) and content.strip().startswith("{") else {}
    hypothesis = payload.get("hypothesis")
    proposed_resolution = payload.get("proposed_resolution")
    confidence = float(payload.get("confidence", 0.0))
    evidence_ids = payload.get("evidence_ids", [])

    if not hypothesis or not proposed_resolution:
        return ResolutionProposal(
            hypothesis="No hypothesis formed.",
            proposed_resolution="No automated resolution proposed; requires human review.",
            confidence=0.0,
            evidence_ids=evidence_ids,
            approved=False,
        )

    return ResolutionProposal(
        hypothesis=hypothesis,
        proposed_resolution=proposed_resolution,
        confidence=confidence,
        evidence_ids=evidence_ids,
        approved=False,
    )


class _NullAnthropicClient:
    class messages:
        @staticmethod
        def create(*args: Any, **kwargs: Any) -> Any:
            class _Resp:
                content = [{"text": json.dumps({
                    "hypothesis": "No hypothesis formed.",
                    "proposed_resolution": "No automated resolution proposed; requires human review.",
                    "confidence": 0.0,
                    "evidence_ids": [],
                })}]
            return _Resp()


class _NullMCPClient:
    def fetch(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class RazorpayMCPClient:
    def __init__(self, endpoint: str = "mcp.razorpay.com/sse", *, api_key: str | None = None, api_secret: str | None = None):
        self.endpoint = endpoint
        self.api_key = api_key
        self.api_secret = api_secret

    def fetch_related_records(self, exception: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.api_key or not self.api_secret:
            return []
        return [{
            "record_type": exception.get("record_type"),
            "record_id": exception.get("record_id"),
            "source": "razorpay_mcp",
            "endpoint": self.endpoint,
        }]
