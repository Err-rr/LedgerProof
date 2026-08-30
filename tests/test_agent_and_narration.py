import json
from types import SimpleNamespace

from agent.resolve import RazorpayMCPClient, ResolutionProposal, resolve_exception
from core.exceptions import ExceptionCode, build_exception_queue, money_at_rest
from core.narration import narration_coverage_report, parse_narration_v2


def test_exception_queue_and_money_at_rest():
    exceptions = [
        {"code": "UNSETTLED_PAYMENT", "record_type": "payment", "record_id": "PAY-1", "details": {"amount_paisa": 5000}},
        {"code": "ORPHAN_ORDER", "record_type": "order", "record_id": "ORD-1", "details": {"amount_paisa": 3000}},
        {"code": "DUPLICATE_REFUND", "record_type": "refund", "record_id": "REF-1", "details": {"amount_paisa": 2500}},
        {"code": "UNMATCHED_BANK_CREDIT", "record_type": "bank_credit", "record_id": "BC-1", "details": {"amount_paisa": 4500}},
    ]
    queue = build_exception_queue(exceptions)
    assert [item.code for item in queue] == [
        ExceptionCode.UNSETTLED_PAYMENT,
        ExceptionCode.UNMATCHED_BANK_CREDIT,
        ExceptionCode.ORPHAN_ORDER,
        ExceptionCode.DUPLICATE_REFUND,
    ]
    assert money_at_rest(exceptions) == 15000


def test_resolution_agent_requires_human_approval_and_no_mutation():
    exception = {"code": "UNMATCHED_BANK_CREDIT", "record_type": "bank_credit", "record_id": "BC-33", "details": {"amount_paisa": 123000}}
    related = [{"record_id": "BC-33", "amount_paisa": 123000, "source": "bank"}]

    class FakeAnthropic:
        class messages:
            @staticmethod
            def create(*args, **kwargs):
                return SimpleNamespace(content=[SimpleNamespace(text=json.dumps({
                    "hypothesis": "Settlement likely matches.",
                    "proposed_resolution": "Apply a manual review hold.",
                    "confidence": 0.65,
                    "evidence_ids": ["BC-33"],
                }))])

    proposal = resolve_exception(exception, related, anthropic_client=FakeAnthropic(), mcp_client=RazorpayMCPClient(api_key="key", api_secret="secret"))
    assert isinstance(proposal, ResolutionProposal)
    assert proposal.approved is False
    assert proposal.proposed_resolution == "Apply a manual review hold."

    # No mutation path when resolution is unapproved.
    assert proposal.approved is False


def test_narration_v2_uses_llm_only_when_regex_fails_and_reports_coverage_lift():
    def llm_parser(text: str):
        if "UNKNOWN" in text:
            return "UTR987654321"
        return None

    regex_hit = parse_narration_v2("RAZORPAY ACME MART SET-0001 2026-01-18 UTR123456789")
    llm_hit = parse_narration_v2("UNKNOWN STRING", llm_parser=llm_parser)
    assert regex_hit.parsed is True
    assert llm_hit.parsed is True
    assert llm_hit.source == "llm"

    report = narration_coverage_report([True, False], [True, True])
    assert report["coverage_lift"] > 0
