"""E1-S1 Types layer: the shared enums and the identity value objects.

Operations steps 1-2. These are the vocabulary every later story imports, so
the tests pin the names and members `specs/design/CONTEXT.md` fixes rather
than just checking the code runs.
"""

from __future__ import annotations

import pytest
from src.types.enums import (
    ApplicationStatus,
    DecisionOutcome,
    DocumentVerificationStatus,
    Role,
)
from src.types.identity import AuditEntry, User


def test_role_members_match_the_context_vocabulary() -> None:
    """Three roles, exactly as CONTEXT.md and the api-contracts auth column name."""
    assert {role.value for role in Role} == {"CUSTOMER", "UNDERWRITER", "ADMIN"}


def test_application_status_includes_manual_review() -> None:
    """Seven states, not six.

    Decision D-L added MANUAL_REVIEW to the Application Status term after the
    design review (U-6), so a six-member enum is the pre-amendment shape.
    """
    values = {status.value for status in ApplicationStatus}
    assert "MANUAL_REVIEW" in values
    assert len(values) == 7, f"expected the seven D-L states, got {sorted(values)}"


def test_decision_outcome_matches_the_frozen_contract() -> None:
    """The three outcomes every decision endpoint returns."""
    assert {outcome.value for outcome in DecisionOutcome} == {
        "AUTO_APPROVE",
        "AUTO_REJECT",
        "MANUAL_REVIEW",
    }


def test_document_verification_status_has_no_intermediate_state() -> None:
    """PENDING, VERIFIED, REJECTED — E6-S1 transitions straight between them."""
    assert {status.value for status in DocumentVerificationStatus} == {
        "PENDING",
        "VERIFIED",
        "REJECTED",
    }


def test_user_carries_exactly_one_role() -> None:
    """E1-S1-AC1: a session names exactly one role, so the type holds one."""
    user = User(id="u-1", username="alice", role=Role.UNDERWRITER)

    assert user.role is Role.UNDERWRITER
    assert isinstance(user.role, Role), "the role must be typed, not a bare string"


def test_user_rejects_an_unknown_role() -> None:
    """A role outside the enum is not a role."""
    with pytest.raises(ValueError):
        User(id="u-1", username="alice", role="SUPERUSER")  # type: ignore[arg-type]


def test_user_is_immutable() -> None:
    """A session's identity must not be reassigned after it is issued."""
    from pydantic import ValidationError

    user = User(id="u-1", username="alice", role=Role.CUSTOMER)

    with pytest.raises(ValidationError):
        user.role = Role.ADMIN


def test_audit_entry_records_actor_and_timestamp() -> None:
    """E1-S2-AC4 reads the acting user id and a timestamp off this entry."""
    from datetime import UTC, datetime

    occurred = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
    entry = AuditEntry(
        id="a-1",
        actor_user_id="u-1",
        action="POLICY_VERSION_PUBLISHED",
        entity_type="policy_version",
        entity_id="pv-1",
        occurred_at=occurred,
    )

    assert entry.actor_user_id == "u-1"
    assert entry.occurred_at is occurred
    assert entry.comment is None
    assert entry.reason_code is None


def test_audit_entry_timestamp_must_be_timezone_aware() -> None:
    """A naive timestamp cannot be ordered across deployments."""
    from datetime import datetime

    with pytest.raises(ValueError):
        AuditEntry(
            id="a-1",
            actor_user_id="u-1",
            action="X",
            entity_type="y",
            entity_id="z",
            occurred_at=datetime(2026, 3, 31, 12, 0),
        )
