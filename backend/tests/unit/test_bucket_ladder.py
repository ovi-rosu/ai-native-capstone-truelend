"""Tests for the canonical Delinquency Bucket ladder (E11-S1).

Exercises only the public interface: the DelinquencyBucket enum and the
classify_by_days_past_due / classify functions.
"""

from datetime import date

import pytest
from src.config.delinquency import classify, classify_by_days_past_due
from src.types.delinquency import DelinquencyBucket


def _expected_bucket_for(days_past_due: int) -> DelinquencyBucket:
    """Independent oracle mirroring D-B's literal ranges (not the production table)."""
    if days_past_due >= 180:
        return DelinquencyBucket.NPA
    if days_past_due >= 90:
        return DelinquencyBucket.DPD_90
    if days_past_due >= 60:
        return DelinquencyBucket.DPD_60
    if days_past_due >= 30:
        return DelinquencyBucket.DPD_30
    return DelinquencyBucket.CURRENT


# AC1: a 35-day-past-due oldest unpaid installment classifies as DPD-30.
def test_35_days_past_due_is_dpd_30() -> None:
    assert classify_by_days_past_due(35) == DelinquencyBucket.DPD_30


def test_installment_due_35_days_before_as_of_date_is_dpd_30() -> None:
    oldest_unpaid_due_date = date(2026, 8, 9)
    as_of_date = date(2026, 9, 13)  # 35 days after the due date
    assert classify(oldest_unpaid_due_date, as_of_date) == DelinquencyBucket.DPD_30


# AC2: every value 0..400 lands in exactly one of the five buckets, no gap/overlap.
def test_full_sweep_has_no_gap_or_overlap() -> None:
    seen_buckets: set[DelinquencyBucket] = set()
    for days_past_due in range(0, 401):
        bucket = classify_by_days_past_due(days_past_due)
        assert bucket == _expected_bucket_for(days_past_due)
        seen_buckets.add(bucket)
    assert seen_buckets == set(DelinquencyBucket)


@pytest.mark.parametrize(
    ("days_past_due", "expected"),
    [
        (0, DelinquencyBucket.CURRENT),
        (29, DelinquencyBucket.CURRENT),
        (30, DelinquencyBucket.DPD_30),
        (59, DelinquencyBucket.DPD_30),
        (60, DelinquencyBucket.DPD_60),
        (89, DelinquencyBucket.DPD_60),
        (90, DelinquencyBucket.DPD_90),
        (179, DelinquencyBucket.DPD_90),
        (180, DelinquencyBucket.NPA),
    ],
)
def test_bucket_boundaries_have_no_gap_or_overlap(
    days_past_due: int, expected: DelinquencyBucket
) -> None:
    assert classify_by_days_past_due(days_past_due) == expected


def test_exactly_five_buckets_exist() -> None:
    assert len(DelinquencyBucket) == 5
    assert {b.value for b in DelinquencyBucket} == {
        "CURRENT",
        "DPD-30",
        "DPD-60",
        "DPD-90",
        "NPA",
    }


# AC3: a loan with no installment past its due date classifies as CURRENT.
def test_no_installment_overdue_is_current_when_due_date_is_as_of_date() -> None:
    as_of_date = date(2026, 9, 13)
    assert classify(as_of_date, as_of_date) == DelinquencyBucket.CURRENT


def test_no_installment_overdue_is_current_when_due_date_is_in_the_future() -> None:
    oldest_unpaid_due_date = date(2026, 10, 1)
    as_of_date = date(2026, 9, 13)
    assert classify(oldest_unpaid_due_date, as_of_date) == DelinquencyBucket.CURRENT


def test_zero_days_past_due_is_current() -> None:
    assert classify_by_days_past_due(0) == DelinquencyBucket.CURRENT


# AC4: a classification result carries a bucket only, no fee/interest/charge.
def test_result_carries_bucket_only_no_fee_or_charge_attribute() -> None:
    result = classify_by_days_past_due(35)
    for forbidden_attribute in ("fee", "late_fee", "penal_interest", "charge", "penalty"):
        assert not hasattr(result, forbidden_attribute)
    assert isinstance(result, DelinquencyBucket)
    assert result.value in {"CURRENT", "DPD-30", "DPD-60", "DPD-90", "NPA"}


def test_negative_days_past_due_is_rejected() -> None:
    with pytest.raises(ValueError, match="days_past_due"):
        classify_by_days_past_due(-1)
