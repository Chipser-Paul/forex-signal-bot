from backtests.broker_safety_replay import run_broker_replay


def test_broker_replay_covers_required_safe_transitions(tmp_path):
    replay = run_broker_replay(tmp_path)
    assert replay["successful_order"]["status"] == "CONFIRMED"
    assert replay["spread_rejection"]["reason"] == "SPREAD_ABSOLUTE_LIMIT"
    assert replay["stale_tick_rejection"]["reason"] == "TICK_STALE"
    assert replay["margin_rejection"]["reason"] == "NEW_ORDER_MARGIN_LIMIT"
    assert replay["invalid_stop_lower_volume"]["executed_volume"] == 0.05
    assert replay["partial_fill"]["status"] == "PARTIALLY_FILLED"
    assert replay["requote_safe_retry"]["status"] == "CONFIRMED"
    assert replay["timeout_reconciliation"]["reconciled"] == "MATCHED"
    assert replay["duplicate_action"]["reason"] == "DUPLICATE_ACTION"
    assert replay["manual_position_isolation"]["reason"] == "OWNERSHIP_UNPROVEN"
    assert replay["startup_recovery"]["state"] == "RECOVERED"
    assert replay["owned_only_liquidation"] == {"results": 1, "send_count": 1}
