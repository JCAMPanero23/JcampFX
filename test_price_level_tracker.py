"""
Quick validation test for PriceLevelTracker (Phase 3.1.1)

Tests:
1. Same strategy blocked within cooldown window
2. Different strategy allowed at same price
3. Outside cooldown window allowed
4. Outside pip threshold allowed
"""

from datetime import datetime, timedelta

from src.price_level_tracker import PriceLevelTracker


def test_price_level_cooldown():
    tracker = PriceLevelTracker()
    base_time = datetime(2025, 1, 1, 12, 0, 0)

    # Record a TrendRider loss at USDJPY 145.11
    tracker.add_losing_trade(
        pair="USDJPY",
        price=145.11,
        strategy="TrendRider",
        timestamp=base_time,
        r_result=-1.04,
    )

    # Test 1: Same strategy, same price, within cooldown -> BLOCKED
    is_blocked, reason = tracker.is_blocked(
        pair="USDJPY",
        price=145.11,
        strategy="TrendRider",
        now=base_time + timedelta(hours=1),  # 1 hour later (within 4hr cooldown)
    )
    assert is_blocked, "Test 1 FAILED: Same strategy at same price should be blocked"
    assert "PRICE_LEVEL_COOLDOWN" in reason
    print(f"[PASS] Test 1: {reason}")

    # Test 2: Different strategy, same price -> ALLOWED
    is_blocked, reason = tracker.is_blocked(
        pair="USDJPY",
        price=145.11,
        strategy="BreakoutRider",
        now=base_time + timedelta(hours=1),
    )
    assert not is_blocked, "Test 2 FAILED: Different strategy should be allowed at same price"
    print("[PASS] Test 2: BreakoutRider allowed where TrendRider lost")

    # Test 3: Same strategy, within +/-20 pips -> BLOCKED
    is_blocked, reason = tracker.is_blocked(
        pair="USDJPY",
        price=145.11 + 0.15,  # +15 pips (within +/-20 pip threshold)
        strategy="TrendRider",
        now=base_time + timedelta(hours=2),
    )
    assert is_blocked, "Test 3 FAILED: Entry within +/-20 pips should be blocked"
    print(f"[PASS] Test 3: Entry at 145.26 blocked (15 pips from loss at 145.11)")

    # Test 4: Same strategy, outside +/-20 pips -> ALLOWED
    is_blocked, reason = tracker.is_blocked(
        pair="USDJPY",
        price=145.11 + 0.25,  # +25 pips (outside +/-20 pip threshold)
        strategy="TrendRider",
        now=base_time + timedelta(hours=2),
    )
    assert not is_blocked, "Test 4 FAILED: Entry outside +/-20 pips should be allowed"
    print("[PASS] Test 4: Entry at 145.36 allowed (25 pips from loss)")

    # Test 5: Same strategy, same price, outside cooldown window -> ALLOWED
    is_blocked, reason = tracker.is_blocked(
        pair="USDJPY",
        price=145.11,
        strategy="TrendRider",
        now=base_time + timedelta(hours=5),  # 5 hours later (outside 4hr cooldown)
    )
    assert not is_blocked, "Test 5 FAILED: Entry outside cooldown window should be allowed"
    print("[PASS] Test 5: Entry allowed after 5 hours (cooldown expired)")

    # Test 6: Different pair not affected
    is_blocked, reason = tracker.is_blocked(
        pair="EURUSD",
        price=1.0900,
        strategy="TrendRider",
        now=base_time + timedelta(hours=1),
    )
    assert not is_blocked, "Test 6 FAILED: Different pair should not be affected"
    print("[PASS] Test 6: EURUSD not affected by USDJPY loss")

    # Test 7: Winning trades not tracked (if PRICE_LEVEL_TRACK_LOSSES_ONLY = True)
    tracker.add_losing_trade(
        pair="GBPUSD",
        price=1.2500,
        strategy="TrendRider",
        timestamp=base_time,
        r_result=2.5,  # Win (should not be tracked)
    )
    history = tracker.get_history("GBPUSD")
    assert len(history) == 0, "Test 7 FAILED: Winning trades should not be tracked"
    print("[PASS] Test 7: Winning trades not tracked")

    print("\n*** All tests PASSED! Price Level Cooldown system working correctly. ***")


if __name__ == "__main__":
    test_price_level_cooldown()
