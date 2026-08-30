from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


UTR_RE = re.compile(r"(?:UTR|REF|TXN|NARR|TRACE)[A-Z0-9-]{6,}", re.IGNORECASE)


@dataclass
class NarrationParseResult:
    parsed: bool
    utm: str | None = None
    details: dict[str, Any] | None = None
    source: str = "regex"


def parse_narration_v2(narration: str, *, llm_parser: Any | None = None) -> NarrationParseResult:
    if narration is None or not str(narration).strip():
        return NarrationParseResult(parsed=False, source="regex")

    text = str(narration).strip()
    match = UTR_RE.search(text)
    if match:
        return NarrationParseResult(parsed=True, utm=match.group(0).upper(), details={"raw": text}, source="regex")

    if llm_parser is not None:
        llm_result = llm_parser(text)
        if llm_result:
            return NarrationParseResult(parsed=True, utm=str(llm_result).upper(), details={"raw": text}, source="llm")

    return NarrationParseResult(parsed=False, source="regex")


def narration_coverage_report(regex_only: list[bool], llm_augmented: list[bool]) -> dict[str, Any]:
    regex_baseline = sum(regex_only) / len(regex_only) if regex_only else 0.0
    combined = sum(llm_augmented) / len(llm_augmented) if llm_augmented else 0.0
    return {
        "regex_baseline_coverage": regex_baseline,
        "regex_plus_llm_coverage": combined,
        "coverage_lift": combined - regex_baseline,
    }
