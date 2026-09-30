"""Integration tests for atomic stock adjustments (db.stock).

These guard the oversell fix: the decrement is a single conditional UPDATE,
so it either fully applies or applies nothing (never negative stock), and it
records a matching StockTransaction row.
"""

import pytest
from sqlalchemy import select

from db.models import Product, StockTransaction
from db.stock import (
    InsufficientStockError,
    apply_decrement,
    increment_stock,
    reserve_lines,
    try_decrement_stock,
)


def _product(session, sku, stock):
    p = Product(
        name=f"P-{sku}",
        sku=sku,
        price=1.0,
        sale_price=1.0,
        cost_price=0.5,
        stock_qty=stock,
        unit_type="piece",
        base_unit_price=1.0,
    )
    session.add(p)
    session.commit()
    return p


@pytest.mark.integration
class TestTryDecrementStock:
    def test_successful_decrement(self, db_session):
        p = _product(db_session, "A1", 10)
        new_stock = try_decrement_stock(db_session, p.id, 4)
        assert new_stock == pytest.approx(6.0)
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p.id)
        ) == pytest.approx(6.0)

    def test_insufficient_stock_is_rejected_atomically(self, db_session):
        p = _product(db_session, "A2", 3)
        result = try_decrement_stock(db_session, p.id, 5)
        assert result is None
        # Nothing changed: no partial deduction, no transaction row.
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p.id)
        ) == pytest.approx(3.0)
        assert db_session.query(StockTransaction).count() == 0

    def test_exact_stock_depletes_to_zero(self, db_session):
        p = _product(db_session, "A3", 5)
        assert try_decrement_stock(db_session, p.id, 5) == pytest.approx(0.0)

    def test_zero_or_negative_qty_is_noop(self, db_session):
        p = _product(db_session, "A4", 5)
        assert try_decrement_stock(db_session, p.id, 0) is None
        assert try_decrement_stock(db_session, p.id, -2) is None

    def test_missing_product_returns_none(self, db_session):
        assert try_decrement_stock(db_session, 999999, 1) is None

    def test_records_stock_transaction(self, db_session):
        p = _product(db_session, "A5", 8)
        try_decrement_stock(db_session, p.id, 3, reason="Billing - Sale")
        tx = db_session.query(StockTransaction).one()
        assert tx.product_id == p.id
        assert tx.change_qty == pytest.approx(-3.0)
        assert tx.remaining_stock == pytest.approx(5.0)
        assert tx.reason == "Billing - Sale"

    def test_marks_product_unsynced(self, db_session):
        p = _product(db_session, "A6", 5)
        p.synced = True
        db_session.commit()
        try_decrement_stock(db_session, p.id, 1)
        assert db_session.scalar(
            select(Product.synced).where(Product.id == p.id)
        ) is False

    def test_sequential_decrements_until_exhausted(self, db_session):
        # Two "sales" draining a pool of 5: 3 then 2 succeed, next fails.
        p = _product(db_session, "A7", 5)
        assert try_decrement_stock(db_session, p.id, 3) == pytest.approx(2.0)
        assert try_decrement_stock(db_session, p.id, 2) == pytest.approx(0.0)
        assert try_decrement_stock(db_session, p.id, 1) is None


@pytest.mark.integration
class TestIncrementStock:
    def test_increment_adds_back(self, db_session):
        p = _product(db_session, "B1", 2)
        new_stock = increment_stock(db_session, p.id, 3)
        assert new_stock == pytest.approx(5.0)

    def test_missing_product_returns_none(self, db_session):
        assert increment_stock(db_session, 999999, 1) is None

    def test_decrement_then_increment_round_trips(self, db_session):
        p = _product(db_session, "B2", 10)
        try_decrement_stock(db_session, p.id, 4)
        increment_stock(db_session, p.id, 4)
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p.id)
        ) == pytest.approx(10.0)


@pytest.mark.integration
class TestApplyDecrement:
    def test_does_not_commit(self, db_session):
        p = _product(db_session, "C1", 10)
        new_stock = apply_decrement(db_session, p.id, 3)
        assert new_stock == pytest.approx(7.0)
        # Still inside the transaction: a rollback must fully undo it.
        db_session.rollback()
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p.id)
        ) == pytest.approx(10.0)


@pytest.mark.integration
class TestReserveLines:
    def test_all_lines_succeed_together(self, db_session):
        p1 = _product(db_session, "D1", 10)
        p2 = _product(db_session, "D2", 4)
        reserve_lines(db_session, [(p1.id, 3), (p2.id, 4)])
        db_session.commit()
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p1.id)
        ) == pytest.approx(7.0)
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p2.id)
        ) == pytest.approx(0.0)

    def test_any_shortage_raises_and_nothing_persists(self, db_session):
        # This is the reserve-until-commit guarantee: a failing line aborts the
        # whole sale so a committed invoice can never be backed by missing stock.
        p1 = _product(db_session, "D3", 10)
        p2 = _product(db_session, "D4", 1)
        with pytest.raises(InsufficientStockError):
            reserve_lines(db_session, [(p1.id, 3), (p2.id, 5)])
        db_session.rollback()
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p1.id)
        ) == pytest.approx(10.0)
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p2.id)
        ) == pytest.approx(1.0)

    def test_same_product_multi_line_accumulates(self, db_session):
        p = _product(db_session, "D5", 5)
        reserve_lines(db_session, [(p.id, 2), (p.id, 2)])
        db_session.commit()
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p.id)
        ) == pytest.approx(1.0)

    def test_zero_lines_skipped(self, db_session):
        p = _product(db_session, "D6", 5)
        reserve_lines(db_session, [(p.id, 0), (p.id, -1)])
        db_session.commit()
        assert db_session.scalar(
            select(Product.stock_qty).where(Product.id == p.id)
        ) == pytest.approx(5.0)
        assert db_session.query(StockTransaction).count() == 0

    def test_records_one_transaction_per_line(self, db_session):
        p1 = _product(db_session, "D7", 10)
        p2 = _product(db_session, "D8", 10)
        reserve_lines(db_session, [(p1.id, 1), (p2.id, 2)])
        db_session.commit()
        assert db_session.query(StockTransaction).count() == 2
