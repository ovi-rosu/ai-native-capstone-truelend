/**
 * Money — the frontend money module (design decisions D-G / D-J).
 *
 * Wraps `decimal.js` over the quoted 2dp wire string produced by the
 * backend's Pydantic serializer. An amount is held as a `Decimal` and is
 * NEVER converted to a JS `number` for arithmetic — there is no integer
 * minor-units representation and no scale/unscale helper (D-J forbids
 * both). Matches the CONTEXT.md invariant: "Money is fixed-point decimal
 * at 2 decimal places end to end, never floating-point."
 *
 * Rounding: every quantization step uses `Decimal.ROUND_HALF_UP`, matching
 * the backend's `Money` type (see backend/src/types/money.py) so the same
 * amount rounds identically on both sides of the wire.
 */
import Decimal from "decimal.js";

export class InvalidMoneyAmountError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidMoneyAmountError";
  }
}

function toQuantizedDecimal(value: string | Decimal): Decimal {
  let parsed: Decimal;
  try {
    parsed = value instanceof Decimal ? value : new Decimal(value);
  } catch {
    throw new InvalidMoneyAmountError(`invalid money amount: ${String(value)}`);
  }
  if (!parsed.isFinite()) {
    throw new InvalidMoneyAmountError(`invalid money amount: ${String(value)}`);
  }
  return parsed.toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
}

/** A monetary amount held as a `Decimal`, quantized to exactly 2 places. */
export class Money {
  private readonly amount: Decimal;

  private constructor(amount: Decimal) {
    this.amount = amount;
  }

  /** Parse the quoted 2dp wire string (or a `Decimal`) into a `Money`. */
  static fromWire(value: string | Decimal): Money {
    return new Money(toQuantizedDecimal(value));
  }

  /** Render the quoted 2dp wire string this `Money` would serialize to. */
  toWire(): string {
    return this.amount.toFixed(2);
  }

  add(other: Money): Money {
    return new Money(toQuantizedDecimal(this.amount.plus(other.amount)));
  }

  subtract(other: Money): Money {
    return new Money(toQuantizedDecimal(this.amount.minus(other.amount)));
  }

  /** Multiply by a scalar. `scalar` is a `Decimal` or numeric string — never a JS number. */
  multiply(scalar: Decimal | string): Money {
    const factor = scalar instanceof Decimal ? scalar : new Decimal(scalar);
    return new Money(toQuantizedDecimal(this.amount.times(factor)));
  }

  equals(other: Money): boolean {
    return this.amount.equals(other.amount);
  }

  /**
   * Format for display with thousands separators, e.g. "1,234.50".
   * Never used for arithmetic.
   *
   * Grouped by walking the digits rather than with the idiomatic
   * `/\B(?=(\d{3})+(?!\d))/g`. That lookahead re-scans the remaining digits at
   * every position, which is quadratic: measured 41 ms at 10k digits, 1,030 ms
   * at 50k and 4,091 ms at 100k, on the UI thread. Only `MoneyText` calls this
   * today, so a hostile amount is not reachable from a served response, but the
   * linear form costs nothing and removes the argument.
   */
  format(): string {
    const [integerPart, fractionPart] = this.toWire().split(".");
    const isNegative = integerPart.startsWith("-");
    const digits = isNegative ? integerPart.slice(1) : integerPart;

    // Walked forward and deliberately without `Math.max` for the slice bound:
    // the money module's own float guard flags any `Math.*`, conservatively and
    // correctly, and index arithmetic has no need of it.
    let grouped = "";
    for (let index = 0; index < digits.length; index += 1) {
      if (index > 0 && (digits.length - index) % 3 === 0) {
        grouped += ",";
      }
      grouped += digits[index];
    }

    return `${isNegative ? "-" : ""}${grouped}.${fractionPart}`;
  }
}
