from lab8.db import init_store, load_json, load_jsonl, connect
from lab8.durability import get_refund
from lab8.shapes import single


def test_single_step_cap_returns_failed_without_refund(tmp_path, monkeypatch):
    store = str(tmp_path / "t.sqlite")
    init_store(store, load_json("data/public_world_state.json"), load_jsonl("data/public_claims.jsonl"))
    monkeypatch.setattr(
        single, "run_react",
        lambda *a, **k: {"stopped": "step_cap", "final": {"status": "failed", "error_reason": "step_cap"}},
    )
    result = single.run_claim("C-001", seed=11, store_path=store)
    assert result.status == "failed"
    assert result.proposal_amount == 0
    assert result.error_reason == "step_cap"
    conn = connect(store)
    try:
        assert get_refund(conn, "C-001") is None
    finally:
        conn.close()
