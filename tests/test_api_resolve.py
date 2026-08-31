from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tests.api_fakes import FakeRepository


def _seed_exception(fake_repo: FakeRepository, run_id: str = "run-1", exception_id: str = "exc-1") -> None:
    fake_repo.runs.setdefault(run_id, {"run_id": run_id, "status": "completed", "summary": None, "error": None, "created_at": datetime.now(timezone.utc), "completed_at": None})
    fake_repo.insert_exceptions(run_id, [{
        "id": exception_id, "code": "UNMATCHED_BANK_CREDIT", "severity": "high",
        "record_type": "bank_credit", "record_id": "BC-1", "amount_paisa": 12345,
        "rupee_at_risk_paisa": 12345, "details": {}, "created_at": datetime.now(timezone.utc),
    }])


def test_resolve_requires_explicit_approval(client: TestClient, fake_repo: FakeRepository) -> None:
    _seed_exception(fake_repo)

    response = client.post("/exceptions/exc-1/resolve", json={
        "approved": False, "resolved_by": "shivam", "resolution_notes": "looks fine",
    })

    assert response.status_code == 422
    assert fake_repo.get_exception("exc-1")["status"] == "open"


def test_resolve_requires_approved_field_present(client: TestClient, fake_repo: FakeRepository) -> None:
    _seed_exception(fake_repo)

    response = client.post("/exceptions/exc-1/resolve", json={
        "resolved_by": "shivam", "resolution_notes": "looks fine",
    })

    assert response.status_code == 422  # pydantic: approved is a required field


def test_resolve_happy_path_records_resolver_and_notes(client: TestClient, fake_repo: FakeRepository) -> None:
    _seed_exception(fake_repo)

    response = client.post("/exceptions/exc-1/resolve", json={
        "approved": True, "resolved_by": "shivam", "resolution_notes": "confirmed with merchant",
        "proposal": {"hypothesis": "duplicate settlement", "confidence": 0.4},
    })

    assert response.status_code == 200
    body = response.json()["exception"]
    assert body["status"] == "resolved"
    assert body["resolution"]["resolved_by"] == "shivam"
    assert body["resolution"]["approved"] is True
    assert body["resolution"]["proposal"]["hypothesis"] == "duplicate settlement"


def test_resolve_unknown_exception_returns_404(client: TestClient) -> None:
    response = client.post("/exceptions/does-not-exist/resolve", json={
        "approved": True, "resolved_by": "shivam", "resolution_notes": "n/a",
    })
    assert response.status_code == 404


def test_resolve_already_resolved_returns_409(client: TestClient, fake_repo: FakeRepository) -> None:
    _seed_exception(fake_repo)
    body = {"approved": True, "resolved_by": "shivam", "resolution_notes": "first pass"}
    first = client.post("/exceptions/exc-1/resolve", json=body)
    assert first.status_code == 200

    second = client.post("/exceptions/exc-1/resolve", json=body)
    assert second.status_code == 409


def test_propose_with_no_related_records_returns_no_hypothesis(client: TestClient, fake_repo: FakeRepository) -> None:
    """No related match_records reach agent.resolve_exception -> it always
    declines to guess (see agent/resolve.py), never fabricating a hypothesis."""
    _seed_exception(fake_repo)

    response = client.post("/exceptions/exc-1/propose")

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 0.0
    assert "No hypothesis" in body["hypothesis"]
    assert "human review" in body["proposed_resolution"]


def test_propose_never_writes_to_the_exception(client: TestClient, fake_repo: FakeRepository) -> None:
    _seed_exception(fake_repo)

    client.post("/exceptions/exc-1/propose")

    assert fake_repo.get_exception("exc-1")["status"] == "open"
    assert fake_repo.get_exception("exc-1")["resolution"] is None


def test_propose_unknown_exception_returns_404(client: TestClient) -> None:
    response = client.post("/exceptions/does-not-exist/propose")
    assert response.status_code == 404
