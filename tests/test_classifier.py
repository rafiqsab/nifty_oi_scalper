"""
tests/test_classifier.py
Unit tests for the four OI scenario classifications.
Run with:  python -m pytest tests/ -v
"""
import pytest
from core.oi_velocity_tracker import OIVelocityTracker


@pytest.fixture
def tracker():
    return OIVelocityTracker(oi_threshold=100_000, tick_window=2)


def test_long_buildup(tracker):
    scenario, direction = tracker._classify(oi_change=500_000, price_change=30.0)
    assert scenario  == "LONG_BUILDUP"
    assert direction == "BUY"


def test_short_buildup(tracker):
    scenario, direction = tracker._classify(oi_change=500_000, price_change=-20.0)
    assert scenario  == "SHORT_BUILDUP"
    assert direction == "SELL"


def test_long_unwind(tracker):
    scenario, direction = tracker._classify(oi_change=-400_000, price_change=-25.0)
    assert scenario  == "LONG_UNWIND"
    assert direction == "SELL"


def test_short_cover(tracker):
    scenario, direction = tracker._classify(oi_change=-600_000, price_change=40.0)
    assert scenario  == "SHORT_COVER"
    assert direction == "BUY"


def test_confidence_scales_with_oi():
    c_small = OIVelocityTracker._confidence(300_000, 10.0)
    c_large = OIVelocityTracker._confidence(1_500_000, 10.0)
    assert c_large > c_small


def test_below_threshold_returns_none(tracker):
    """OI change below threshold should produce no event."""
    from datetime import datetime
    from core.models import OISnapshot

    snap1 = OISnapshot(datetime.now(), 24500, "CE", 1_000_000, 120.0)
    snap2 = OISnapshot(datetime.now(), 24500, "CE", 1_050_000, 122.0)   # only 50k change

    tracker.update_option(snap1)
    event = tracker.update_option(snap2)
    assert event is None
