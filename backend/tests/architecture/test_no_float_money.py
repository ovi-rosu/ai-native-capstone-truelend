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


_GUARD_EXEMPTION = "money-guard: decimal-division"


def _exempt_lines(source: str) -> frozenset[int]:
    """Line numbers carrying the reviewable `# money-guard:` exemption.

    Decimal/Decimal division is legitimate — E9-S3's EMI needs it. Without a
    per-line escape hatch the only way to divide would be to disable the guard
    wholesale, so the exemption is annotated line by line and shows up in a diff.
    """
    return frozenset(
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if _GUARD_EXEMPTION in line
    )


def _count_float_usages(source: str) -> int:
    """Count constructs that can put a float into a money code path.

    Counting only `float(...)` calls and float literals let the most likely
    leak through untouched: `principal / months` over two ints yields a float
    in Python 3, which is exactly the shape an EMI calculation takes. Division
    and the `math` module (whose functions all return floats) are therefore
    counted too. Every later money story inherits this guard.
    """
    tree = ast.parse(source)
    exempt = _exempt_lines(source)
    math_aliases = {"math"}
    count = 0

    for node in ast.walk(tree):
        # `import math` / `from math import ceil` both hand back floats.
        if isinstance(node, ast.Import):
            if any(alias.name == "math" for alias in node.names):
                count += 1
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "math":
            count += 1
            continue

        is_float_call = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "float"
        )
        is_math_attr = (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in math_aliases
        )
        is_float_literal = isinstance(node, ast.Constant) and isinstance(node.value, float)
        is_division = isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Div, ast.FloorDiv)
        )
        # The marker names one category, so it exempts one category. It used
        # to `continue` before any check ran, muting the whole line: a real
        # `float(...)` call or float literal sharing a line with a justified
        # Decimal division went unreported.
        if is_division and getattr(node, "lineno", None) in exempt:
            continue
        if is_float_call or is_math_attr or is_float_literal or is_division:
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


@pytest.mark.parametrize(
    "raw",
    [
        Decimal("NaN"),
        "NaN",
        "nan",
        "-NaN",
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        "Infinity",
        "-Infinity",
    ],
)
def test_construction_rejects_non_finite(raw: Decimal | str) -> None:
    """A non-finite amount is not money.

    `Decimal` accepts NaN and Infinity, and a NaN that reaches a `Money`
    poisons every downstream decision: an ordering comparison against an
    underwriting threshold raises `InvalidOperation` (not an `AppError`, so
    it surfaces as an unhandled 500), equality returns False so dedupe
    breaks, and the serializer emits `"NaN"` on the wire, which the
    frontend's `decimal.js` parser then throws on. The frontend module
    already rejects non-finite values; the backend must match it.
    """
    with pytest.raises(InvalidMoneyAmountError):
        Money(raw)


@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param("value = principal / months\n", id="true-division"),
        pytest.param("value = total // count\n", id="floor-division"),
        pytest.param("import math\nvalue = math.floor(x)\n", id="math-module"),
        pytest.param("value = float(amount)\n", id="float-call"),
        pytest.param("value = 0.1 + x\n", id="float-literal"),
        pytest.param("value = base ** 0.5\n", id="float-exponent"),
        pytest.param("from math import ceil\nvalue = ceil(x)\n", id="math-import-from"),
    ],
)
def test_float_guard_detects_realistic_leaks(snippet: str) -> None:
    """The guard must catch the ways float actually enters money code.

    Counting only `float(...)` calls and float literals let the most likely
    leak through: `principal / months` on two ints yields a float in Python
    3, which is exactly the EMI shape E9-S3 will write. Every later money
    story inherits this guard, so it has to bite before then.
    """
    assert _count_float_usages(snippet) > 0


def test_float_guard_allows_explicitly_marked_decimal_division() -> None:
    """Decimal division is legitimate and needs a reviewable escape hatch.

    Without one, E9-S3's EMI implementation cannot divide at all and the
    guard would be bypassed wholesale instead of annotated line by line.
    """
    marked = "value = principal / months  # money-guard: decimal-division\n"
    assert _count_float_usages(marked) == 0


def test_float_guard_still_reports_zero_for_the_real_money_modules() -> None:
    """The hardened guard must not fire on the shipped modules."""
    for path in (_MONEY_TYPE_PATH, _SERIALIZERS_PATH):
        source = path.read_text(encoding="utf-8")
        assert _count_float_usages(source) == 0, f"found float usage in {path}"


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


@pytest.mark.parametrize(
    "marked",
    [
        pytest.param(
            "value = float(principal) / months  # money-guard: decimal-division",
            id="float-call-on-marked-line",
        ),
        pytest.param(
            "value = principal / months + 0.5  # money-guard: decimal-division",
            id="float-literal-on-marked-line",
        ),
        pytest.param(
            "import math  # money-guard: decimal-division",
            id="math-import-on-marked-line",
        ),
    ],
)
def test_division_exemption_does_not_silence_other_float_categories(marked: str) -> None:
    """CR-003: the exemption was a whole-line mute, not a division exemption.

    `# money-guard: decimal-division` skipped the line for *every* category,
    so a genuine `float(...)` call or float literal sharing the line with a
    justified Decimal division went unreported. The marker names one category
    and must exempt only that one -- this sits in the D-G/D-J oracle every
    later money story inherits.
    """
    assert _count_float_usages(marked) > 0
