"""Config-layer Days Past Due boundaries and the one canonical classifier.

Per D-B (specs/design/architecture.md) the Delinquency Bucket floors are
Config-layer constants: CURRENT 0-29, DPD-30 30-59, DPD-60 60-89,
DPD-90 90-179, NPA 180+ Days Past Due. The classifier lives here rather than
in the Types layer because it is the single Config-layer mapping function
named in the architecture risk table (mitigating the "DPD boundaries
re-derived by the End-Of-Day Run / repayment recalculation / Portfolio
Summary" duplication risk, E16-S1-AC1) — Types is the lowest layer and may
not import Config, so co-locating the boundary table with its lookup here
keeps every consumer importing one source of truth instead of two.

Pure and stateless: no Repository or Service dependency, no I/O.
"""

from datetime import date

from src.types.delinquency import DelinquencyBucket

# Ordered ascending by floor. The last entry whose floor the input meets or
# exceeds is the bucket — see classify_by_days_past_due.
DPD_BUCKET_FLOORS: tuple[tuple[DelinquencyBucket, int], ...] = (
    (DelinquencyBucket.CURRENT, 0),
    (DelinquencyBucket.DPD_30, 30),
    (DelinquencyBucket.DPD_60, 60),
    (DelinquencyBucket.DPD_90, 90),
    (DelinquencyBucket.NPA, 180),
)


def classify_by_days_past_due(days_past_due: int) -> DelinquencyBucket:
    """Classify an integer Days Past Due value into its Delinquency Bucket.

    Raises ValueError if days_past_due is negative — Days Past Due is
    defined as zero or a positive whole-day count, never negative.
    """
    if days_past_due < 0:
        raise ValueError(f"days_past_due must be zero or positive, got {days_past_due}")
    bucket = DPD_BUCKET_FLOORS[0][0]
    for candidate_bucket, floor_days in DPD_BUCKET_FLOORS:
        if days_past_due < floor_days:
            break
        bucket = candidate_bucket
    return bucket


def classify(oldest_unpaid_due_date: date, as_of_date: date) -> DelinquencyBucket:
    """Classify a Loan as of a date from its oldest unpaid Installment due date.

    Days Past Due is the whole days between as_of_date and
    oldest_unpaid_due_date, zero when the Installment is not yet overdue.
    """
    days_past_due = max(0, (as_of_date - oldest_unpaid_due_date).days)
    return classify_by_days_past_due(days_past_due)
