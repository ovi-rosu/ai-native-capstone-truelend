"""Wire serialization for `Money`.

This is the ONE module that converts a `Money` value to and from its wire
representation: a quoted 2-decimal-place JSON string (design decision D-G).
No JSON number ever carries a money amount. Other Pydantic models that need
a money field import `MoneyField` from here rather than re-implementing
this conversion — see the D-G coupling-risk note in specs/design/architecture.md.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from src.types.money import InvalidMoneyAmountError, Money


def _validate_money(value: Money | str | Decimal) -> Money:
    """Build a `Money` from the wire value: a `Money`, a decimal string, or a `Decimal`."""
    if isinstance(value, Money):
        return value
    if isinstance(value, (str, Decimal)):
        return Money(value)
    raise InvalidMoneyAmountError(f"cannot build Money from {type(value).__name__}")


def _serialize_money(value: Money) -> str:
    """Render a `Money` as its quoted 2dp wire string, e.g. `"1234.50"`."""
    return str(value.amount)


class _MoneyPydanticAnnotation:
    """Wires `Money` into Pydantic v2 validation/serialization.

    Validates from a quoted 2dp string (or a `Decimal`); serializes back to
    a quoted 2dp string — never a JSON number.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            _validate_money,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _serialize_money,
                return_schema=core_schema.str_schema(),
            ),
        )


MoneyField = Annotated[Money, _MoneyPydanticAnnotation]
"""Pydantic field type for `Money`: use this on any response model that
carries a money amount so it renders as a quoted 2dp JSON string."""
