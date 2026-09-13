"""Money value type.

Per the CONTEXT.md invariant: "Money is fixed-point decimal at 2 decimal
places end to end, never floating-point." `Money` is a pure value type that
holds one monetary amount as a `decimal.Decimal`, quantized to exactly two
places on construction and after every arithmetic operation. It carries no
interest/EMI business logic and no currency-conversion path — see
specs/design/architecture.md decision D-G.

Rounding convention: every quantization step in this module uses
`ROUND_HALF_UP` (round-half-away-from-zero on ties). This is the one
rounding mode used consistently everywhere `Money` quantizes a value.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

_TWO_PLACES: Final[Decimal] = Decimal("0.01")


class InvalidMoneyAmountError(ValueError):
    """Raised when a `Money` value cannot be built from the given input.

    Covers: float inputs (money never touches float), bool inputs, and
    strings/Decimals that are not valid decimal numbers.
    """


def _reject_float_or_bool(value: object) -> None:
    if isinstance(value, bool):
        raise InvalidMoneyAmountError(
            f"Money does not accept bool; got {value!r}"
        )
    if isinstance(value, float):
        raise InvalidMoneyAmountError(
            f"Money does not accept float; got {value!r}. Use Decimal, int, or str."
        )


class Money:
    """A monetary amount held as a `Decimal` quantized to exactly 2 places.

    Construct from a `Decimal`, `int`, or numeric `str` — never from a
    `float`. Every arithmetic method returns a new `Money`, also quantized
    to exactly 2 places. `Money` never converts its amount to a Python
    `float` internally.
    """

    __slots__ = ("_amount",)

    def __init__(self, amount: Decimal | int | str) -> None:
        _reject_float_or_bool(amount)
        try:
            decimal_amount = amount if isinstance(amount, Decimal) else Decimal(amount)
        except InvalidOperation as exc:
            raise InvalidMoneyAmountError(f"invalid money amount: {amount!r}") from exc
        self._amount = self._quantize(decimal_amount)

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        try:
            return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise InvalidMoneyAmountError(f"cannot quantize amount: {value}") from exc

    @property
    def amount(self) -> Decimal:
        """The underlying amount, always quantized to exactly 2 places."""
        return self._amount

    def add(self, other: Money) -> Money:
        """Return a new `Money` holding `self + other`, quantized to 2dp."""
        return Money(self._amount + other._amount)

    def subtract(self, other: Money) -> Money:
        """Return a new `Money` holding `self - other`, quantized to 2dp."""
        return Money(self._amount - other._amount)

    def multiply(self, scalar: Decimal | int) -> Money:
        """Return a new `Money` holding `self * scalar`, quantized to 2dp.

        `scalar` must be a `Decimal` or `int` — never a `float`. Python's
        default decimal context (28 significant digits) applies to the
        intermediate product before it is quantized down to 2dp.
        """
        _reject_float_or_bool(scalar)
        if not isinstance(scalar, (Decimal, int)):
            raise InvalidMoneyAmountError(f"invalid scalar: {scalar!r}")
        return Money(self._amount * scalar)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._amount == other._amount

    def __hash__(self) -> int:
        return hash(self._amount)

    def __repr__(self) -> str:
        return f"Money({self._amount!s})"

    def __str__(self) -> str:
        return str(self._amount)
