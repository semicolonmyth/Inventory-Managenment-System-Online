"""Integration tests for the SQLite data layer.

Uses the isolated in-memory DB from conftest (NEVER the production file).
Covers schema creation, unique constraints, relations, transaction
rollback, and foreign-key enforcement (the test engine enables
PRAGMA foreign_keys just like db.local_db does for production).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db.models import (
    Invoice,
    InvoiceItem,
    Product,
    Setting,
    StockTransaction,
    User,
)


def _product(sku="S1", name="Rice", **kw):
    return Product(sku=sku, name=name, **kw)


@pytest.mark.integration
class TestSchema:
    def test_all_tables_created(self, engine):
        from sqlalchemy import inspect

        tables = set(inspect(engine).get_table_names())
        assert {"users", "products", "invoices", "invoice_items",
                "stock_transactions", "settings", "expenses"} <= tables


@pytest.mark.integration
class TestUniqueConstraints:
    def test_duplicate_username_rejected(self, db_session):
        db_session.add(User(username="bob", password_hash="x"))
        db_session.commit()
        db_session.add(User(username="bob", password_hash="y"))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_duplicate_sku_rejected(self, db_session):
        db_session.add(_product(sku="DUP"))
        db_session.commit()
        db_session.add(_product(sku="DUP", name="Other"))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_product_name_required(self, db_session):
        db_session.add(Product(sku="NONAME"))  # name is NOT NULL
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_duplicate_setting_key_rejected(self, db_session):
        db_session.add(Setting(key="k", value="1"))
        db_session.commit()
        db_session.add(Setting(key="k", value="2"))
        with pytest.raises(IntegrityError):
            db_session.commit()


@pytest.mark.integration
class TestRelations:
    def test_invoice_items_relation(self, db_session):
        user = User(username="seller", password_hash="x")
        prod = _product(sku="R1", name="Rice")
        db_session.add_all([user, prod])
        db_session.commit()

        inv = Invoice(number="INV-1", user_id=user.id,
                      customer_name="Ali", total_amount=100)
        inv.items.append(InvoiceItem(product_id=prod.id, quantity=2,
                                     unit_price=50, total_price=100))
        db_session.add(inv)
        db_session.commit()

        loaded = db_session.query(Invoice).filter_by(number="INV-1").one()
        assert len(loaded.items) == 1
        assert loaded.items[0].product.name == "Rice"

    def test_stock_transaction_relation(self, db_session):
        prod = _product(sku="S2", name="Wheat", stock_qty=10)
        db_session.add(prod)
        db_session.commit()
        prod.stock_transactions.append(
            StockTransaction(product_id=prod.id, change_qty=-3,
                             remaining_stock=7, reason="Sale")
        )
        db_session.commit()
        assert db_session.query(Product).filter_by(sku="S2").one().stock_transactions


@pytest.mark.integration
class TestTransactions:
    def test_rollback_leaves_no_partial_data(self, db_session):
        db_session.add(_product(sku="T1", name="A"))
        db_session.commit()
        db_session.add(_product(sku="T2", name="B"))
        db_session.rollback()
        assert db_session.query(Product).filter_by(sku="T2").first() is None
        assert db_session.query(Product).filter_by(sku="T1").first() is not None


@pytest.mark.integration
class TestForeignKeyEnforcement:
    def test_orphan_invoice_rejected(self, db_session):
        """With FK enforcement on, an Invoice cannot point at a missing user."""
        db_session.add(Invoice(number="ORPHAN", user_id=9999))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_valid_parent_first_invoice_ok(self, db_session):
        """The same insert succeeds when the referenced user exists."""
        user = User(username="real", password_hash="x")
        db_session.add(user)
        db_session.commit()
        db_session.add(Invoice(number="OK", user_id=user.id, total_amount=10))
        db_session.commit()
        assert db_session.query(Invoice).filter_by(number="OK").one()

    def test_delete_parent_with_children_blocked(self, db_session):
        """A raw DELETE of a user who has invoices is blocked by FK.

        (Note: ORM ``session.delete(user)`` silently nulls ``invoices.user_id``
        instead of raising -- which is precisely the corruption the employee-
        delete UI guard prevents, hence the count check before deleting.)
        """
        user = User(username="busy", password_hash="x")
        db_session.add(user)
        db_session.commit()
        db_session.add(Invoice(number="INVX", user_id=user.id, total_amount=5))
        db_session.commit()

        with pytest.raises(IntegrityError):
            # Bulk delete issues DELETE FROM users -> FK violation.
            db_session.query(User).filter(User.id == user.id).delete()
            db_session.commit()

    def test_children_first_wipe_is_fk_safe(self, db_session):
        """Mirrors CloudRestorer._clear_local_data ordering."""
        user = User(username="wipe", password_hash="x")
        prod = _product(sku="W1", name="Wheat")
        db_session.add_all([user, prod])
        db_session.commit()
        inv = Invoice(number="WI", user_id=user.id, total_amount=1)
        inv.items.append(
            InvoiceItem(product_id=prod.id, quantity=1, unit_price=1, total_price=1)
        )
        db_session.add(inv)
        db_session.commit()

        # Delete children before parents: no violation.
        db_session.query(InvoiceItem).delete()
        db_session.query(Invoice).delete()
        db_session.query(Product).delete()
        db_session.query(User).delete()
        db_session.commit()
        assert db_session.query(Invoice).count() == 0
