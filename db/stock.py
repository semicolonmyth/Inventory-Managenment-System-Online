"""Atomic stock adjustments.

These helpers replace the previous read-modify-write pattern
(``product.stock_qty = current_stock - qty``) which clobbered concurrent
updates and could let two sales oversell the same units. A single guarded
UPDATE applies the change atomically at the database level.

Two commit models are supported:
* ``try_decrement_stock`` / ``increment_stock`` commit immediately (standalone
  stock edits).
* ``apply_decrement`` / ``reserve_lines`` do NOT commit -- they run inside the
  caller's transaction so a sale's stock is consumed atomically with the
  invoice row (reserve-until-commit).
"""
from __future__ import annotations

from typing import Iterable, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import Product, StockTransaction


class InsufficientStockError(Exception):
    """Raised when a multi-line reservation cannot be satisfied.

    The caller's transaction is left uncommitted so the whole sale can be
    rolled back together.
    """

    def __init__(self, product_id: int, requested: float) -> None:
        self.product_id = product_id
        self.requested = requested
        super().__init__(
            f"Insufficient stock for product {product_id} (requested {requested})"
        )

    def user_message(self) -> str:
        return (
            "Not enough stock to complete this sale. Please reduce the "
            "quantity and try again."
        )


def apply_decrement(
    session: Session,
    product_id: int,
    qty: float,
    reason: str = "Billing - Sale",
) -> Optional[float]:
    """Atomically reduce stock by ``qty`` WITHOUT committing.

    Returns the new stock level, or ``None`` when the product is missing or
    there is insufficient stock (nothing written, no transaction recorded).
    The guarded ``WHERE stock_qty >= qty`` makes the check and the write a
    single atomic step.
    """
    qty = float(qty)
    if qty <= 0:
        return None

    result = session.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock_qty >= qty)
        .values(stock_qty=Product.stock_qty - qty, synced=False)
        .execution_options(synchronize_session="fetch")
    )
    if result.rowcount == 0:
        return None

    new_stock = session.scalar(
        select(Product.stock_qty).where(Product.id == product_id)
    )
    session.add(
        StockTransaction(
            product_id=product_id,
            change_qty=-qty,
            remaining_stock=new_stock,
            reason=reason,
        )
    )
    return new_stock


def try_decrement_stock(
    session: Session,
    product_id: int,
    qty: float,
    reason: str = "Billing - Sale",
) -> Optional[float]:
    """Atomically reduce stock by ``qty`` and commit. Returns the new level."""
    new_stock = apply_decrement(session, product_id, qty, reason=reason)
    if new_stock is None:
        return None
    session.commit()
    return new_stock


def reserve_lines(
    session: Session,
    pairs: Iterable[Tuple[int, float]],
    reason: str = "Billing - Sale",
) -> None:
    """Reserve stock for every ``(product_id, qty)`` line in one transaction.

    Applies all decrements without committing. If any line exceeds available
    stock, raises :class:`InsufficientStockError` so the caller can roll back
    the entire sale. Nothing is committed here -- the caller commits once.
    """
    for product_id, qty in pairs:
        qty = float(qty)
        if qty <= 0:
            continue  # nothing to reserve for a zero/negative line
        if apply_decrement(session, product_id, qty, reason=reason) is None:
            raise InsufficientStockError(product_id, qty)


def increment_stock(
    session: Session,
    product_id: int,
    qty: float,
    reason: str = "Restock",
) -> Optional[float]:
    """Atomically increase ``product_id``'s stock by ``qty`` and commit.

    Returns the new stock level, or ``None`` if the product is missing.
    """
    qty = float(qty)
    if qty <= 0:
        return None

    result = session.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(stock_qty=Product.stock_qty + qty, synced=False)
        .execution_options(synchronize_session="fetch")
    )
    if result.rowcount == 0:
        return None

    new_stock = session.scalar(
        select(Product.stock_qty).where(Product.id == product_id)
    )
    session.add(
        StockTransaction(
            product_id=product_id,
            change_qty=qty,
            remaining_stock=new_stock,
            reason=reason,
        )
    )
    session.commit()
    return new_stock
