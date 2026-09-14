"""Identity value objects: the authenticated actor and the audit entry.

Both are frozen: a session's identity must not be reassigned after it is
issued, and an `AuditEntry` is insert-only by decision **D-E** — a mutable
audit record is not an audit record.

`occurred_at` must be timezone-aware. A naive timestamp cannot be ordered
across deployments, and `E1-S2-AC4` reads a timestamp off this entry as
evidence of when a privileged action happened.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator
from src.types.enums import Role


class User(BaseModel):
    """An authenticated actor, carrying exactly one role (`E1-S1-AC1`)."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: str
    role: Role


class AuditEntry(BaseModel):
    """One insert-only record of a privileged action.

    `comment` and `reason_code` are optional because only an Override carries
    them (`E7-S1-AC3`); every other action records the actor, the entity and
    the time.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    actor_user_id: str
    action: str
    entity_type: str
    entity_id: str
    occurred_at: datetime
    comment: str | None = None
    reason_code: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def _must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value
