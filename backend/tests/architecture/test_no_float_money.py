"""Architecture and unit tests for the `Money` value type (E9-S1).

Combines the AC2 static float-arithmetic scan with the AC1 quantization
tests so every test for this story lives in one owned file
(`specs/design/component-map.md` lists only this path for E9-S1's backend
tests, not a separate `tests/unit/test_money.py`).

Money is not the schedule generator (a later story) — the quantization
tests prove the invariant on Money's own construction and arithmetic,
since Money is the type every later money field (EMI, outstanding
principal, ...) holds.
"""

from __future__ import annotations

import ast
import random
from decimal import Decimal
from pathlib import Path

import pytest
from src.types.money import InvalidMoneyAmountError, Money

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MONEY_TYPE_PATH = _BACKEND_ROOT / "src" / "types" / "money.py"
_SERIALIZERS_PATH = _BACKEND_ROOT / "src" / "api" / "serializers.py"


def _count_float_usages(source: str) -> int:
    """Count `float(...)` calls and float literals in a source file's AST."""
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        is_float_call = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "float"
        )
        is_float_literal = isinstance(node, ast.Constant) and isinstance(node.value, float)
        if is_float_call or is_float_literal:
            count += 1
    return count


def test_money_type_has_zero_float_operations() -> None:
    source = _MONEY_TYPE_PATH.read_text(encoding="utf-8")
    assert _count_float_usages(source) == 0, f"found float usage in {_MONEY_TYPE_PATH}"


def test_serializers_module_has_zero_float_operations() -> None:
    source = _SERIALIZERS_PATH.read_text(encoding="utf-8")
    assert _count_float_usages(source) == 0, f"found float usage in {_SERIALIZERS_PATH}"


def _is_two_decimal_quantized(value: Decimal) -> bool:
    """True when `value`'s Decimal representation has exponent -2 (exactly 2dp)."""
    return isinstance(value, Decimal) and value.as_tuple().exponent == -2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.5", Decimal("1234.50")),
        ("999.999", Decimal("1000.00")),
        ("0", Decimal("0.00")),
        ("-45.005", Decimal("-45.01")),
        (Decimal("15000.1"), Decimal("15000.10")),
        (250000, Decimal("250000.00")),
    ],
)
def test_construction_quantizes_to_two_decimal_places(
    raw: Decimal | int | str, expected: Decimal
) -> None:
    money = Money(raw)
    assert money.amount == expected
    assert _is_two_decimal_quantized(money.amount)


def test_construction_rejects_float() -> None:
    with pytest.raises(InvalidMoneyAmountError):
        Money(1234.5)  # type: ignore[arg-type]


def test_construction_rejects_bool() -> None:
    with pytest.raises(InvalidMoneyAmountError):
        Money(True)


def test_construction_rejects_invalid_string() -> None:
    with pytest.raises(InvalidMoneyAmountError):
        Money("not-a-number")


def test_add_returns_two_decimal_quantized_money() -> None:
    result = Money("10000.335").add(Money("250.005"))
    assert result.amount == Decimal("10250.35")
    assert _is_two_decimal_quantized(result.amount)


def test_subtract_returns_two_decimal_quantized_money() -> None:
    result = Money("5000.00").subtract(Money("1234.567"))
    assert result.amount == Decimal("3765.43")
    assert _is_two_decimal_quantized(result.amount)


def test_multiply_by_int_scalar_returns_two_decimal_quantized_money() -> None:
    result = Money("1500.335").multiply(3)
    assert result.amount == Decimal("4501.02")
    assert _is_two_decimal_quantized(result.amount)


def test_multiply_by_decimal_scalar_returns_two_decimal_quantized_money() -> None:
    result = Money("100000.00").multiply(Decimal("0.105"))
    assert result.amount == Decimal("10500.00")
    assert _is_two_decimal_quantized(result.amount)


def test_multiply_rejects_float_scalar() -> None:
    with pytest.raises(InvalidMoneyAmountError):
        Money("100.00").multiply(1.5)  # type: ignore[arg-type]


def test_equality_is_by_quantized_amount() -> None:
    assert Money("100.1") == Money("100.10")
    assert Money("100.10") != Money("100.11")


def test_random_principal_rate_tenure_triples_always_quantize_to_two_places() -> None:
    """AC1: for randomly generated principal/rate/tenure triples, every
    `Money` value produced by arithmetic on them is a Decimal quantized to
    exactly 2 decimal places."""
    rng = random.Random(20240913)
    for _ in range(200):
        principal = Money(Decimal(rng.randint(50_000, 5_000_000)) / Decimal(100))
        periodic_rate = Decimal(rng.randint(1, 300)) / Decimal(10_000)
        tenure_months = rng.randint(1, 360)

        interest_for_period = principal.multiply(periodic_rate)
        outstanding_after_period = principal.subtract(interest_for_period)
        projected_total = principal.add(interest_for_period).multiply(tenure_months)

        for money_field in (
            principal,
            interest_for_period,
            outstanding_after_period,
            projected_total,
        ):
            assert isinstance(money_field.amount, Decimal)
            assert _is_two_decimal_quantized(money_field.amount)
