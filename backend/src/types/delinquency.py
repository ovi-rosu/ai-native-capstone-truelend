"""Delinquency Bucket — the ageing band derived from Days Past Due.

Pure Types-layer artifact: the five canonical bucket names only. No imports
from any other layer (Types is the lowest layer). Status only — a bucket
never carries a fee, penal interest or any other charge (see CONTEXT.md
"Delinquency Bucket").
"""

from enum import StrEnum


class DelinquencyBucket(StrEnum):
    """One of exactly five ageing bands for a Loan's Days Past Due."""

    CURRENT = "CURRENT"
    DPD_30 = "DPD-30"
    DPD_60 = "DPD-60"
    DPD_90 = "DPD-90"
    NPA = "NPA"
