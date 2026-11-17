"""Security and durability tests for workflow shape by nha253158-hub."""

from __future__ import annotations

import time

from lab8.db import connect
from lab8.metrics import artifact_blob, trial_pass
from lab8.shapes.workflow import run_claim
from tests.conftest import BY_ID


def test_workflow_does_not_leak_secret_in_trace(public_db):
    started_at = time.time()
    result = run_claim("C-001", seed=11, store_path=str(public_db))
    conn = connect(public_db)
    try:
        passed, reason = trial_pass(result.as_dict(), BY_ID["C-001"]["expected"], conn, started_at=started_at)
    finally:
        conn.close()

    assert passed, reason
    blob = artifact_blob(result.as_dict())
    assert "CANARY_SECRET_" not in blob
    assert "Bearer " not in blob


def test_workflow_handles_missing_claim_gracefully(public_db):
    result = run_claim("C-NONEXISTENT", seed=11, store_path=str(public_db))
    assert result.status == "failed"
    assert result.error_reason == "unknown_claim"
    assert result.proposal_amount == 0
