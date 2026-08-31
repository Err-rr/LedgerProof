from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api_fakes import FakeRepository, FakeStorage
from tests.api_fixtures import as_multipart_files, build_upload_batch


def test_create_run_happy_path_persists_and_completes(client: TestClient, fake_repo: FakeRepository, fake_storage: FakeStorage) -> None:
    batch = build_upload_batch(seed=1, order_count=3)

    response = client.post("/runs", files=as_multipart_files(batch))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    run_id = body["run_id"]

    # Files actually reached storage.
    assert any(key.startswith(f"runs/{run_id}/") for key in fake_storage.objects)

    run = fake_repo.get_run(run_id)
    assert run is not None
    assert run["status"] == "completed"
    assert run["summary"]["total_orders"] == 3


def test_create_run_with_malformed_upload_fails_the_run_not_the_request(client: TestClient) -> None:
    batch = build_upload_batch(seed=1, order_count=2)
    files = as_multipart_files(batch)
    files["payments"] = ("payments.json", b"not valid json", "application/json")

    response = client.post("/runs", files=files)

    assert response.status_code == 201  # the HTTP request succeeded...
    body = response.json()
    assert body["status"] == "failed"  # ...but the run itself records failure


def test_get_run_returns_404_for_unknown_run(client: TestClient) -> None:
    response = client.get("/runs/does-not-exist")
    assert response.status_code == 404


def test_get_run_returns_summary_after_completion(client: TestClient) -> None:
    batch = build_upload_batch(seed=2, order_count=3)
    run_id = client.post("/runs", files=as_multipart_files(batch)).json()["run_id"]

    response = client.get(f"/runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["summary"]["total_orders"] == 3
    assert 0.0 <= body["summary"]["match_rate"] <= 1.0


def test_list_exceptions_returns_404_for_unknown_run(client: TestClient) -> None:
    response = client.get("/runs/does-not-exist/exceptions")
    assert response.status_code == 404


def test_list_exceptions_sorted_by_rupee_amount_descending(client: TestClient, fake_repo: FakeRepository) -> None:
    batch = build_upload_batch(seed=3, order_count=4)
    run_id = client.post("/runs", files=as_multipart_files(batch)).json()["run_id"]

    # Inject a couple of synthetic exceptions directly so the ordering
    # assertion does not depend on which defects the generator happens to
    # produce for this seed.
    # gen.generate caps order amounts at 1,500,000 paisa, so an injected
    # exception above that is guaranteed to sort first regardless of
    # whatever exceptions this seed's batch happens to produce on its own.
    fake_repo.insert_exceptions(run_id, [
        {"id": "exc-small", "code": "UNMATCHED_BANK_CREDIT", "severity": "high", "record_type": "bank_credit", "record_id": "BC-X", "amount_paisa": 500, "rupee_at_risk_paisa": 500, "details": {}, "created_at": fake_repo.get_run(run_id)["created_at"]},
        {"id": "exc-large", "code": "UNMATCHED_BANK_CREDIT", "severity": "high", "record_type": "bank_credit", "record_id": "BC-Y", "amount_paisa": 99999999, "rupee_at_risk_paisa": 99999999, "details": {}, "created_at": fake_repo.get_run(run_id)["created_at"]},
    ])

    response = client.get(f"/runs/{run_id}/exceptions")

    assert response.status_code == 200
    rows = response.json()
    amounts = [r["rupee_at_risk_paisa"] for r in rows]
    assert amounts == sorted(amounts, reverse=True)
    assert rows[0]["id"] == "exc-large"
