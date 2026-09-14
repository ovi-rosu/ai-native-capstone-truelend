"""Typed error base.

`AppError` is the one typed-error base the API boundary maps to a JSON
response (see `src/api/errors.py`). Kept minimal per this story: no
business-specific subclasses are added here until a story needs one.
"""

from __future__ import annotations

from collections.abc import Mapping


class AppError(Exception):
    """Base class for application errors mapped to an HTTP JSON response.

    Carries the three fields the frozen error envelope requires
    (`specs/design/api-contracts.md`): the error *name*, a human-readable
    `detail`, and a `context` mapping. `context` is where a subclass puts the
    machine-readable specifics a caller has to act on -- E4-S4-AC2 needs
    `threshold_kind` and `configured_value` there.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        context: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.context: dict[str, object] = dict(context or {})

    @property
    def error(self) -> str:
        """The error name the envelope reports -- the concrete class name."""
        return type(self).__name__
