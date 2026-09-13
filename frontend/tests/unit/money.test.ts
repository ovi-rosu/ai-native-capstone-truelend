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

describe("static check: zero float-arithmetic operations in src/types/money.ts", () => {
  it("contains no parseFloat/parseInt/Number()/number-typed arithmetic", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const moneyTsPath = path.resolve(here, "../../src/types/money.ts");
    const source = readFileSync(moneyTsPath, "utf-8");

    const forbiddenPatterns = [
      /\bparseFloat\s*\(/,
      /\bparseInt\s*\(/,
      /\bNumber\s*\(/,
      /:\s*number\b/,
      /\bas\s+number\b/,
    ];

    for (const pattern of forbiddenPatterns) {
      expect(pattern.test(source)).toBe(false);
    }
  });
});
