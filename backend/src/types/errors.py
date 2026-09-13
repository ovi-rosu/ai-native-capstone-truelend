"""Typed error base.

`AppError` is the one typed-error base the API boundary maps to a JSON
response (see `src/api/errors.py`). Kept minimal per this story: no
business-specific subclasses are added here until a story needs one.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for application errors mapped to an HTTP JSON response."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
