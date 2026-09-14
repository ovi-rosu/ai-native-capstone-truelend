import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { render, screen } from "@testing-library/react";
import Decimal from "decimal.js";
import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { InvalidMoneyAmountError, Money } from "../../src/types/money";
import { MoneyText } from "../../src/ui/components/MoneyText";

describe("Money", () => {
  it("parses a quoted 2dp wire string and round-trips back to the same string", () => {
    const wire = "987654.32";
    expect(Money.fromWire(wire).toWire()).toBe(wire);
  });

  it("quantizes to exactly 2 decimal places using round-half-up", () => {
    expect(Money.fromWire("999.999").toWire()).toBe("1000.00");
    expect(Money.fromWire("-45.005").toWire()).toBe("-45.01");
    expect(Money.fromWire("1234.5").toWire()).toBe("1234.50");
  });

  it("adds and subtracts through Decimal arithmetic", () => {
    const sum = Money.fromWire("10000.335").add(Money.fromWire("250.005"));
    expect(sum.toWire()).toBe("10250.35");

    const diff = Money.fromWire("5000.00").subtract(Money.fromWire("1234.567"));
    expect(diff.toWire()).toBe("3765.43");
  });

  it("multiplies by a Decimal scalar and quantizes the result", () => {
    const result = Money.fromWire("100000.00").multiply(new Decimal("0.105"));
    expect(result.toWire()).toBe("10500.00");
  });

  it("multiplies by a numeric-string scalar and quantizes the result", () => {
    const result = Money.fromWire("1500.335").multiply("3");
    expect(result.toWire()).toBe("4501.02");
  });

  it("compares two Money values by their quantized amount", () => {
    expect(Money.fromWire("100.1").equals(Money.fromWire("100.10"))).toBe(true);
    expect(Money.fromWire("100.10").equals(Money.fromWire("100.11"))).toBe(false);
  });

  it("formats with thousands separators for display", () => {
    expect(Money.fromWire("1234567.5").format()).toBe("1,234,567.50");
    expect(Money.fromWire("-45.005").format()).toBe("-45.01");
  });

  it("rejects a non-numeric wire string with a typed error", () => {
    expect(() => Money.fromWire("not-a-number")).toThrow(InvalidMoneyAmountError);
  });
});

describe("MoneyText", () => {
  it("renders the formatted amount from a wire string", () => {
    render(createElement(MoneyText, { money: "1234.5" }));
    expect(screen.getByText("1,234.50")).toBeTruthy();
  });

  it("renders the formatted amount from a Money instance", () => {
    render(createElement(MoneyText, { money: Money.fromWire("42") }));
    expect(screen.getByText("42.00")).toBeTruthy();
  });
});

/**
 * Patterns that put a JS `number` into a money path.
 *
 * The original list stopped at parseFloat/parseInt/Number()/number-typed
 * declarations, which left the likeliest leaks untouched: `decimal.js`
 * exposes `.toNumber()` and `.toFixed()`, `Math.*` returns floats, and a
 * bare float literal or a unary `+` coerces silently. Every later money
 * story inherits this guard, so it has to catch them before then.
 */
const FLOAT_RISK_PATTERNS: readonly RegExp[] = [
  /\bparseFloat\s*\(/,
  /\bparseInt\s*\(/,
  /\bNumber\s*\(/,
  /:\s*number\b/,
  /\bas\s+number\b/,
  /\.toNumber\s*\(/,
  /\bMath\s*\./,
  /\b\d+\.\d+\b/,
  /(?:^|[=(,[\s])\+\s*[A-Za-z_$(]/m,
];

/**
 * Drop comments and quoted strings before scanning.
 *
 * Money is carried as a decimal *string*, so `"1,234.50"` in a comment or a
 * wire-format example is not a float literal — scanning raw source flagged
 * both and would have forced the real checks to be weakened instead.
 * Template literals are deliberately left in place so code inside `${...}`
 * is still scanned.
 *
 * Note `.toFixed()` is absent from the pattern list on purpose: on a
 * `decimal.js` Decimal it returns a string, and it is the correct way to
 * render 2dp for the wire.
 */
function stripCommentsAndStrings(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/\/\/[^\n]*/g, " ")
    .replace(/'(?:\\[\s\S]|[^'\\])*'/g, '""')
    .replace(/"(?:\\[\s\S]|[^"\\])*"/g, '""');
}

function countFloatRisks(source: string): number {
  const scannable = stripCommentsAndStrings(source);
  return FLOAT_RISK_PATTERNS.filter((pattern) => pattern.test(scannable)).length;
}

describe("static check: zero float-arithmetic operations in src/types/money.ts", () => {
  it("reports no float risk in the shipped money module", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const moneyTsPath = path.resolve(here, "../../src/types/money.ts");
    const source = readFileSync(moneyTsPath, "utf-8");

    expect(countFloatRisks(source)).toBe(0);
  });

  it.each([
    ["toNumber", "const n = amount.toNumber();"],
    ["Math", "const n = Math.round(amount);"],
    ["float literal", "const rate = 0.105;"],
    ["unary plus", "const n = +amount;"],
    ["parseFloat", "const n = parseFloat(raw);"],
    ["Number()", "const n = Number(raw);"],
    ["number type", "let total: number = 0;"],
  ])("flags %s as a float risk", (_label, snippet) => {
    expect(countFloatRisks(snippet)).toBeGreaterThan(0);
  });
});

describe("format() grouping is linear, not quadratic", () => {
  it("groups a very long integer part without quadratic blow-up", () => {
    // The lookahead form /\B(?=(\d{3})+(?!\d))/g is quadratic: measured
    // 41 ms at 10k digits, 1,030 ms at 50k and 4,091 ms at 100k. Reachability
    // is currently limited to tests — MoneyText is the only caller of
    // format() — but a linear implementation removes the question rather than
    // relying on an argument about who calls what.
    const digits = "9".repeat(100_001);
    const money = Money.fromWire(`${digits}.00`);

    const started = Date.now();
    const formatted = money.format();
    const elapsed = Date.now() - started;

    expect(elapsed).toBeLessThan(250);
    expect(formatted.endsWith(".00")).toBe(true);
    expect(formatted.split(",").length).toBe(Math.ceil(digits.length / 3));
  });

  it("still groups ordinary amounts correctly", () => {
    expect(Money.fromWire("1234.50").format()).toBe("1,234.50");
    expect(Money.fromWire("999.99").format()).toBe("999.99");
    expect(Money.fromWire("1000000.00").format()).toBe("1,000,000.00");
    expect(Money.fromWire("-45.01").format()).toBe("-45.01");
    expect(Money.fromWire("-1234567.89").format()).toBe("-1,234,567.89");
  });
});
