"""
Amazon-style profit, margin, and ROI calculator (CLI + library helpers).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TextIO


# --- Pure / testable core -------------------------------------------------


def effective_unit_cost(product_cost: float, shipping_per_unit: float) -> float:
    return product_cost + shipping_per_unit


def compute_fee_amount(
    selling_price: float,
    fees_absolute: float | None,
    fee_percent: float | None,
) -> float:
    if fees_absolute is not None and fee_percent is not None:
        raise ValueError("Provide only one of fees_absolute or fee_percent.")
    if fee_percent is not None:
        return selling_price * (fee_percent / 100.0)
    if fees_absolute is not None:
        return fees_absolute
    raise ValueError("Provide fees_absolute or fee_percent.")


def unit_profit(selling_price: float, landed_cost: float, fee_amount: float) -> float:
    return selling_price - landed_cost - fee_amount


def margin_pct(profit_val: float, selling_price: float) -> float | None:
    if selling_price == 0:
        return None
    return (profit_val / selling_price) * 100.0


def roi_pct(profit_val: float, landed_cost: float) -> float | None:
    if landed_cost == 0:
        return None
    return (profit_val / landed_cost) * 100.0


def break_even_units(fixed_cost: float, profit_per_unit: float) -> int | None:
    if fixed_cost <= 0:
        return None
    if profit_per_unit <= 0:
        return None
    return math.ceil(fixed_cost / profit_per_unit)


def format_money(amount: float, currency: str) -> str:
    code = currency.strip().upper() or "USD"
    if code == "USD":
        return f"${amount:.2f}"
    return f"{amount:.2f} {code}"


# --- Validation -----------------------------------------------------------


def validate_product_cost(value: float, name: str = "Product cost") -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative.")


def validate_shipping(value: float) -> None:
    if value < 0:
        raise ValueError("Shipping per unit cannot be negative.")


def validate_price(value: float) -> None:
    if value <= 0:
        raise ValueError("Selling price must be greater than zero.")


def validate_landed_cost(landed: float) -> None:
    if landed <= 0:
        raise ValueError("Landed cost (product + shipping) must be greater than zero.")


def validate_fees_absolute(value: float) -> None:
    if value < 0:
        raise ValueError("Fees cannot be negative.")


def validate_fee_percent(value: float) -> None:
    if value < 0:
        raise ValueError("Fee percent cannot be negative.")
    if value > 100:
        # Allowed but unusual; caller may warn
        pass


def validate_fixed_cost(value: float) -> None:
    if value < 0:
        raise ValueError("Fixed one-time cost cannot be negative.")


# --- Orchestration --------------------------------------------------------


@dataclass(frozen=True)
class CalculationResult:
    currency: str
    product_cost: float
    shipping_per_unit: float
    landed_cost: float
    selling_price: float
    fee_mode: str
    fee_input_value: float
    fee_amount: float
    fixed_one_time_cost: float
    profit: float
    margin: float | None
    roi: float | None
    break_even: int | None


def run_calculation(
    *,
    currency: str,
    product_cost: float,
    shipping_per_unit: float,
    selling_price: float,
    fees_absolute: float | None,
    fee_percent: float | None,
    fixed_one_time_cost: float,
) -> CalculationResult:
    validate_product_cost(product_cost)
    validate_shipping(shipping_per_unit)
    validate_price(selling_price)
    validate_fixed_cost(fixed_one_time_cost)

    landed = effective_unit_cost(product_cost, shipping_per_unit)
    validate_landed_cost(landed)

    if fees_absolute is not None:
        validate_fees_absolute(fees_absolute)
        fee_mode = "absolute"
        fee_input = fees_absolute
        fee_amount = fees_absolute
    else:
        assert fee_percent is not None
        validate_fee_percent(fee_percent)
        fee_mode = "percent"
        fee_input = fee_percent
        fee_amount = compute_fee_amount(selling_price, None, fee_percent)

    prof = unit_profit(selling_price, landed, fee_amount)
    margin = margin_pct(prof, selling_price)
    roi = roi_pct(prof, landed)
    be = break_even_units(fixed_one_time_cost, prof)

    return CalculationResult(
        currency=currency.strip().upper() or "USD",
        product_cost=product_cost,
        shipping_per_unit=shipping_per_unit,
        landed_cost=landed,
        selling_price=selling_price,
        fee_mode=fee_mode,
        fee_input_value=fee_input,
        fee_amount=fee_amount,
        fixed_one_time_cost=fixed_one_time_cost,
        profit=prof,
        margin=margin,
        roi=roi,
        break_even=be,
    )


def print_report(res: CalculationResult, stream: TextIO = sys.stdout) -> None:
    w = stream.write
    w("\n--- Results ---\n")
    w(f"Summary: you keep {format_money(res.profit, res.currency)} per unit after landed cost and fees.\n")
    w(f"Landed cost (product + shipping): {format_money(res.landed_cost, res.currency)}\n")
    if res.fee_mode == "percent":
        w(f"Fees ({res.fee_input_value:.2f}% of price): {format_money(res.fee_amount, res.currency)}\n")
    else:
        w(f"Fees (absolute): {format_money(res.fee_amount, res.currency)}\n")
    w(f"Profit: {format_money(res.profit, res.currency)}\n")
    if res.margin is None:
        w("Margin: N/A\n")
    else:
        w(f"Margin: {res.margin:.2f}% of selling price\n")
    if res.roi is None:
        w("ROI: N/A\n")
    else:
        w(f"ROI: {res.roi:.2f}% on landed cost\n")
    if res.break_even is not None:
        w(f"Break-even units (fixed cost): {res.break_even}\n")
    elif res.fixed_one_time_cost and res.fixed_one_time_cost > 0:
        w("Break-even units: N/A (profit per unit is zero or negative)\n")

    if res.fee_amount > res.selling_price:
        w("\nWarning: fees exceed selling price (unusual).\n")
    if res.profit < 0:
        w("\nWarning: negative profit (loss) on this scenario.\n")
    if res.fee_mode == "percent" and res.fee_input_value > 100:
        w("\nWarning: fee percent is over 100%.\n")


def append_csv(path: str, res: CalculationResult) -> None:
    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "currency": res.currency,
        "product_cost": f"{res.product_cost:.4f}",
        "shipping_per_unit": f"{res.shipping_per_unit:.4f}",
        "landed_cost": f"{res.landed_cost:.4f}",
        "selling_price": f"{res.selling_price:.4f}",
        "fee_mode": res.fee_mode,
        "fee_input": f"{res.fee_input_value:.4f}",
        "fee_amount": f"{res.fee_amount:.4f}",
        "fixed_one_time_cost": f"{res.fixed_one_time_cost:.4f}",
        "profit": f"{res.profit:.4f}",
        "margin_pct": "" if res.margin is None else f"{res.margin:.4f}",
        "roi_pct": "" if res.roi is None else f"{res.roi:.4f}",
        "break_even_units": "" if res.break_even is None else str(res.break_even),
    }
    fieldnames = list(row.keys())
    write_header = not (os.path.isfile(path) and os.path.getsize(path) > 0)

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# --- Interactive I/O ------------------------------------------------------


def read_line(prompt: str, default: str = "") -> str:
    try:
        s = input(prompt)
    except EOFError:
        print("\nNo more input (EOF). Exiting.", file=sys.stderr)
        raise SystemExit(0) from None
    s = s.strip()
    return s if s else default


def read_float(prompt: str) -> float:
    while True:
        raw = read_line(prompt)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a valid number.")


def read_non_negative_float(prompt: str) -> float:
    while True:
        v = read_float(prompt)
        if v < 0:
            print("Value cannot be negative.")
            continue
        return v


def read_positive_float(prompt: str) -> float:
    while True:
        v = read_float(prompt)
        if v <= 0:
            print("Value must be greater than zero.")
            continue
        return v


def interactive_collect() -> dict[str, Any]:
    print("Interactive mode (rounding: money and percents shown to 2 decimals).")
    cur = read_line("Currency code [USD]: ", "USD")

    product_cost = read_non_negative_float("Product cost per unit (>= 0): ")
    shipping = read_non_negative_float("Inbound/shipping per unit (0 if none): ")
    landed = effective_unit_cost(product_cost, shipping)
    try:
        validate_landed_cost(landed)
    except ValueError as e:
        print(e)
        raise SystemExit(1) from None

    price = read_positive_float("Selling price per unit: ")

    mode = ""
    while mode not in ("1", "2"):
        mode = read_line("Fees as [1] dollar amount  or  [2] percent of price? Enter 1 or 2: ", "")

    fees_abs: float | None = None
    fee_pct: float | None = None
    if mode == "1":
        fees_abs = read_non_negative_float("Total fees per unit (dollars): ")
    else:
        fee_pct = read_non_negative_float("Total fees as % of selling price (e.g. 15 for 15%): ")

    fixed = read_non_negative_float("One-time fixed cost to cover (0 if none): ")

    return {
        "currency": cur,
        "product_cost": product_cost,
        "shipping_per_unit": shipping,
        "selling_price": price,
        "fees_absolute": fees_abs,
        "fee_percent": fee_pct,
        "fixed_one_time_cost": fixed,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Per-unit profit, margin, ROI; optional break-even and CSV export.",
    )
    p.add_argument("--interactive", action="store_true", help="Force interactive prompts.")
    p.add_argument("--currency", default="USD", help="ISO currency label for display/export (default USD).")
    p.add_argument("--cost", type=float, default=None, help="Product cost per unit (>= 0).")
    p.add_argument("--shipping-per-unit", type=float, default=0.0, help="Shipping/landed add-on per unit (>= 0).")
    p.add_argument("--price", type=float, default=None, help="Selling price per unit (> 0).")
    fee = p.add_mutually_exclusive_group()
    fee.add_argument("--fees", type=float, default=None, help="Total marketplace fees per unit (absolute).")
    fee.add_argument("--fee-percent", type=float, default=None, help="Total fees as %% of selling price.")
    p.add_argument("--fixed-cost", type=float, default=0.0, help="One-time fixed cost for break-even units.")
    p.add_argument(
        "--append-csv",
        metavar="PATH",
        default=None,
        help="Append a result row to PATH (creates file with header if missing).",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    ns = parser.parse_args(argv)

    has_full = (
        ns.cost is not None
        and ns.price is not None
        and (ns.fees is not None or ns.fee_percent is not None)
    )
    has_some = (
        ns.cost is not None
        or ns.price is not None
        or ns.fees is not None
        or ns.fee_percent is not None
    )

    try:
        if ns.interactive:
            data = interactive_collect()
            res = run_calculation(
                currency=data["currency"],
                product_cost=data["product_cost"],
                shipping_per_unit=data["shipping_per_unit"],
                selling_price=data["selling_price"],
                fees_absolute=data["fees_absolute"],
                fee_percent=data["fee_percent"],
                fixed_one_time_cost=data["fixed_one_time_cost"],
            )
        elif has_full:
            res = run_calculation(
                currency=ns.currency,
                product_cost=ns.cost,
                shipping_per_unit=ns.shipping_per_unit,
                selling_price=ns.price,
                fees_absolute=ns.fees,
                fee_percent=ns.fee_percent,
                fixed_one_time_cost=ns.fixed_cost,
            )
        elif has_some:
            print(
                "Incomplete batch args: provide --cost, --price, and (--fees or --fee-percent), "
                "or omit them for interactive mode. Use --interactive to force prompts.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        else:
            data = interactive_collect()
            res = run_calculation(
                currency=data["currency"],
                product_cost=data["product_cost"],
                shipping_per_unit=data["shipping_per_unit"],
                selling_price=data["selling_price"],
                fees_absolute=data["fees_absolute"],
                fee_percent=data["fee_percent"],
                fixed_one_time_cost=data["fixed_one_time_cost"],
            )

        print_report(res)
        if ns.append_csv:
            append_csv(ns.append_csv, res)
            print(f"\nAppended row to {ns.append_csv}")
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130) from None
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
