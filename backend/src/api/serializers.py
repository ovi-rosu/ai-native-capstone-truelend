"""Wire serialization for `Money`.

This is the ONE module that converts a `Money` value to and from its wire
representation: a quoted 2-decimal-place JSON string (design decision D-G).
No JSON number ever carries a money amount. Other Pydantic models that need
a money field import `MoneyField` from here rather than re-implementing
this conversion — see the D-G coupling-risk note in specs/design/architecture.md.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from src.types.money import InvalidMoneyAmountError, Money

# The wire form D-G mandates: a quoted decimal string with exactly two decimal
# places. Expressed in the schema so a generated client cannot send `12.3` or a
# JSON number and still look contract-conformant -- which is the float-on-the-
# wire outcome D-G exists to prevent.
_WIRE_PATTERN = r"^-?\d+\.\d{2}$"

# The same rule, compiled, so the validator enforces exactly what the schema
# advertises rather than the two drifting apart.
_WIRE_FORM = re.compile(_WIRE_PATTERN)


def _validate_money(value: Money | str | Decimal) -> Money:
    """Build a `Money` from the wire value: a `Money`, a decimal string, or a `Decimal`.

    A **string** is held to the exact wire form, because a string is what a
    client sends. `"12.345"` used to be accepted and stored as `12.35` — a
    caller's amount altered without a word — while the published JSON schema
    advertised `^-?\\d+\\.\\d{2}$` and so promised that shape was invalid. A
    client reading the contract sends two places; anything else is a contract
    violation and deserves a 422 rather than silent rounding.

    A `Decimal` or an existing `Money` comes from inside the process, not the
    wire, so it still goes through `Money`'s own quantization — rounding the
    result of a calculation is exactly what that type is for.
    """
    if isinstance(value, Money):
        return value
    if isinstance(value, Decimal):
        return Money(value)
    if isinstance(value, str):
        if not _WIRE_FORM.fullmatch(value):
            raise InvalidMoneyAmountError(
                f"money must be a decimal string with exactly two decimal places; got {value!r}"
            )
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

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _schema: core_schema.CoreSchema, _handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Describe the wire form for OpenAPI.

        Without this, a plain validator function leaves Pydantic nothing to
        infer from. The symptoms were quiet rather than loud:
        `model_json_schema()` raised `PydanticInvalidForJsonSchema`; a response
        model degraded to a bare `{"type": "string"}` inferred from the
        serializer's `return_schema`; and a **request-body** model was omitted
        from `components.schemas` entirely, so `/openapi.json` still returned
        200 while documenting no body at all. That last one matters twice over,
        because `E1-S2-AC3` enumerates the guarded routes *from* that document.
        """
        return {
            "type": "string",
            "pattern": _WIRE_PATTERN,
            "examples": ["1234.50", "-45.01"],
            "description": (
                "Monetary amount as a quoted decimal string with exactly two "
                "decimal places, never a JSON number (decision D-G)."
            ),
        }


MoneyField = Annotated[Money, _MoneyPydanticAnnotation]
"""Pydantic field type for `Money`: use this on any response model that
carries a money amount so it renders as a quoted 2dp JSON string."""
