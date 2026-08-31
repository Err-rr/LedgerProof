"""The Q&A LLM surface: natural-language questions over an already-reconciled
ledger (CLAUDE.md's third permitted LLM use). This module never decides a
match, never classifies a variance, and never writes anything -- it only
reads a bundle the deterministic passes already produced and describes it.
"""

from __future__ import annotations

import json
from typing import Any, Protocol


class AnthropicLike(Protocol):
    """Structural type for whatever `.messages.create(...)` client is passed in."""

    messages: Any


class _NullAnthropicClient:
    """Used when no ANTHROPIC_API_KEY is configured. Never calls out to a
    network, and is exactly what tests get by default -- consistent with the
    rest of the codebase's lazy-client convention (see agent/resolve.py)."""

    class messages:
        @staticmethod
        def create(*_args: Any, **_kwargs: Any) -> Any:
            class _Resp:
                content = [type("Block", (), {"text": "No ANTHROPIC_API_KEY is configured, so this ledger cannot be queried in natural language right now."})()]

            return _Resp()


def get_anthropic_client(api_key: str | None) -> AnthropicLike:
    if not api_key:
        return _NullAnthropicClient()
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def _summarize_bundle_for_prompt(bundle: dict[str, Any]) -> str:
    run = bundle.get("run") or {}
    exceptions = bundle.get("exceptions") or []
    journal_lines = bundle.get("journal_lines") or []
    payload = {
        "run_status": run.get("status"),
        "run_summary": run.get("summary"),
        "exceptions": exceptions,
        "journal_lines": journal_lines,
    }
    return json.dumps(payload, default=str)


SYSTEM_PROMPT = (
    "You are answering questions about a reconciliation ledger that has already been "
    "matched by a deterministic engine. You are not permitted to decide, change, or "
    "imply any change to a match or an exception's status -- you only describe what "
    "the provided data already says. All monetary amounts in the data are integer "
    "paisa; convert to rupees (divide by 100) when stating amounts in your answer. "
    "If the data does not contain enough information to answer, say so plainly "
    "instead of guessing."
)


def ask_ledger_question(question: str, bundle: dict[str, Any], *, client: AnthropicLike, model: str) -> str:
    context = _summarize_bundle_for_prompt(bundle)
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Ledger data:\n{context}\n\nQuestion: {question}"}],
    )
    content = getattr(response, "content", None)
    if not content:
        return "No answer could be generated."
    first = content[0]
    text = getattr(first, "text", None)
    if text is None and isinstance(first, dict):
        text = first.get("text")
    return text or "No answer could be generated."
