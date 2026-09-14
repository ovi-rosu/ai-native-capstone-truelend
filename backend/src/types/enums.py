"""Shared enumerations: the project's closed vocabularies.

Declared once here because `specs/design/component-map.md` makes this the
registry every later story appends to, and because these names appear in the
frozen `specs/design/api-contracts.md` — a string literal duplicated across
stories is how two of them drift apart.

`StrEnum` so a member serialises as its own value through Pydantic and
SQLAlchemy without a custom encoder, while an unknown member still fails.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Who is acting. A session names exactly one (`E1-S1-AC1`)."""

    CUSTOMER = "CUSTOMER"
    UNDERWRITER = "UNDERWRITER"
    ADMIN = "ADMIN"


class ApplicationStatus(StrEnum):
    """The Application lifecycle.

    Seven states, not six: decision **D-L** added `MANUAL_REVIEW` after the
    design review (U-6), so the CONTEXT.md term covers a case the original
    six-state enum could not express.
    """

    SUBMITTED = "SUBMITTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISBURSED = "DISBURSED"
    CLOSED = "CLOSED"
    WITHDRAWN = "WITHDRAWN"


class DecisionOutcome(StrEnum):
    """What underwriting decided. Every decision carries one of these."""

    AUTO_APPROVE = "AUTO_APPROVE"
    AUTO_REJECT = "AUTO_REJECT"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DocumentVerificationStatus(StrEnum):
    """Where a checklist document stands.

    No intermediate state: E6-S1 transitions straight from `PENDING` to
    `VERIFIED` or `REJECTED`, and a rejection must carry a reason.
    """

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
