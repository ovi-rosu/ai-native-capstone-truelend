/**
 * MoneyText — presentational component rendering a formatted money amount.
 * Pure display: no business logic, no arithmetic, no fetching.
 */
import type { ReactElement } from "react";

import { Money } from "../../types/money";

export interface MoneyTextProps {
  readonly money: Money | string;
}

export function MoneyText({ money }: MoneyTextProps): ReactElement {
  const value = typeof money === "string" ? Money.fromWire(money) : money;
  return <span>{value.format()}</span>;
}
