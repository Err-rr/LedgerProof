from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tests.api_fakes import FakeLLMClient, FakeRepository


def _seed_completed_run(fake_repo: FakeRepository, run_id: str = "run-1") -> None:
    fake_repo.runs[run_id] = {
        "run_id": run_id, "status": "completed",
        "summary": {"total_orders": 5, "total_matches": 4, "total_exceptions": 1, "match_rate": 0.8, "auto_resolve_rate": 0.8, "money_at_rest_paisa": 5000, "exceptions_by_code": {"UNMATCHED_BANK_CREDIT": 1}},
        "error": None, "created_at": datetime.now(timezone.utc), "completed_at": datetime.now(timezone.utc),
    }
    fake_repo.match_records[run_id] = []
    fake_repo.insert_exceptions(run_id, [{
        "id": "exc-1", "code": "UNMATCHED_BANK_CREDIT", "severity": "high", "record_type": "bank_credit",
        "record_id": "BC-1", "amount_paisa": 5000, "rupee_at_risk_paisa": 5000, "details": {},
        "created_at": datetime.now(timezone.utc),
    }])


def test_ask_returns_404_for_unknown_run(client: TestClient) -> None:
    response = client.post("/runs/does-not-exist/ask", json={"question": "why is this unmatched?"})
    assert response.status_code == 404


def test_ask_rejects_a_run_that_is_not_completed(client: TestClient, fake_repo: FakeRepository) -> None:
    fake_repo.runs["run-1"] = {
        "run_id": "run-1", "status": "processing", "summary": None, "error": None,
        "created_at": datetime.now(timezone.utc), "completed_at": None,
    }

    response = client.post("/runs/run-1/ask", json={"question": "any exceptions?"})

    assert response.status_code == 409


def test_ask_returns_the_llm_answer_and_grounding_counts(client: TestClient, fake_repo: FakeRepository, fake_llm: FakeLLMClient) -> None:
    _seed_completed_run(fake_repo)
    fake_llm.answer = "There is one unmatched bank credit worth Rs 50."

    response = client.post("/runs/run-1/ask", json={"question": "Which exception has the most money at risk?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "There is one unmatched bank credit worth Rs 50."
    assert body["grounded_in"]["exceptions"] == 1
    assert fake_llm.last_call is not None  # the fake actually got invoked
    assert "Which exception" in fake_llm.last_call["messages"][0]["content"]


def test_ask_never_touches_match_records_or_exceptions(client: TestClient, fake_repo: FakeRepository) -> None:
    """The Q&A surface is read-only: asking a question must not create,
    modify, or resolve anything (CLAUDE.md rule 2/5)."""
    _seed_completed_run(fake_repo)
    before = fake_repo.get_exception("exc-1")

    client.post("/runs/run-1/ask", json={"question": "should I resolve the open exception?"})

    after = fake_repo.get_exception("exc-1")
    assert before == after
