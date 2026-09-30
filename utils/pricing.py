"""Canonical discount / tax / total / status math.

Single source of truth reused by the receipt renderer (``utils.invoice``) and
the billing UI (``ui/new_sale.py``). Previously this logic was duplicated
inline in both places, so a discount/rounding change had to be made twice.

All functions are pure and side-effect free (no DB, no UI) so they can be unit
tested directly.
"""
from __future__ import annotations

from typing import Any, Optional


def to_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion tolerant of None/strings/blanks."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace(",", "").strip()
        return float(cleaned) if cleaned else default
    except (ValueError, TypeError):
        return default


def derive_discount(
    subtotal: float,
    discount_amount: Optional[float],
    discount_type: Optional[str],
    discount_value: Optional[Any],
) -> float:
    """Resolve the discount to charge.

    An explicit ``discount_amount`` always wins; otherwise it is derived from
    ``discount_type`` + ``discount_value`` (Percentage of subtotal, or a Fixed
    amount capped at the subtotal). Result is never negative.
    """
    if discount_amount is not None:
        return max(to_float(discount_amount), 0.0)
    if discount_type == "Percentage" and discount_value:
        return to_float(subtotal) * (to_float(discount_value) / 100.0)
    if discount_type == "Fixed" and discount_value:
        return min(to_float(discount_value), to_float(subtotal))
    return 0.0


def derive_status(grand_total: float, amount_paid: Optional[float]) -> str:
    """Infer a payment status from what was paid against the grand total."""
    paid = to_float(amount_paid) if amount_paid is not None else None
    if paid is None or paid <= 0:
        return "Unpaid"
    if paid >= grand_total - 0.005:
        return "Paid"
    return "Partially Paid"


def compute_totals(
    subtotal: Any,
    *,
    discount_amount: Optional[Any] = None,
    discount_type: Optional[str] = None,
    discount_value: Optional[Any] = None,
    tax_percent: Optional[Any] = 0,
    tax_amount: Optional[Any] = None,
    shipping: Optional[Any] = 0,
    amount_paid: Optional[Any] = None,
    status: Optional[str] = None,
) -> dict:
    """Compute the full document total breakdown.

    Returns a dict with: ``subtotal``, ``discount_amount``,
    ``amount_after_discount``, ``tax_percent``, ``tax_amount``, ``shipping``,
    ``grand_total``, ``amount_paid``, ``balance_due`` and ``status``.

    ``discount_amount``/``tax_amount`` when given take precedence over values
    derived from ``discount_type``/``discount_value``/``tax_percent``. A
    caller-supplied ``status`` is preserved (falling back to derivation only
    when it is falsy).
    """
    subtotal = to_float(subtotal)

    resolved_discount = max(
        derive_discount(subtotal, discount_amount, discount_type, discount_value),
        0.0,
    )
    amount_after_discount = subtotal - resolved_discount

    resolved_tax = (
        to_float(tax_amount)
        if tax_amount is not None
        else (amount_after_discount * (to_float(tax_percent) / 100.0) if tax_percent else 0.0)
    )
    resolved_shipping = to_float(shipping)

    grand_total = amount_after_discount + resolved_tax + resolved_shipping

    paid = to_float(amount_paid) if amount_paid is not None else None
    balance_due = grand_total - (paid or 0.0)

    resolved_status = status if status else derive_status(grand_total, paid)

    return {
        "subtotal": subtotal,
        "discount_amount": resolved_discount,
        "amount_after_discount": amount_after_discount,
        "tax_percent": to_float(tax_percent),
        "tax_amount": resolved_tax,
        "shipping": resolved_shipping,
        "grand_total": grand_total,
        "amount_paid": paid,
        "balance_due": balance_due,
        "status": resolved_status,
    }
