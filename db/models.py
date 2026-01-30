from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class TimestampMixin:
    """Common timestamp and sync fields for all tables."""

    created_at = Column(DateTime, default=datetime.utcnow)
    last_modified = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    synced = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="True when successfully uploaded to cloud.",
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)

    invoices = relationship("Invoice", back_populates="user")


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(100), unique=True, index=True)
    category = Column(String(100))
    price = Column(Float, nullable=False, default=0.0)  # legacy field (kept for compatibility)
    sale_price = Column(Float, nullable=False, default=0.0)
    cost_price = Column(Float, nullable=False, default=0.0)
    stock_qty = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, default=True, nullable=False)
    unit_type = Column(String(20), default="piece", nullable=False, doc="Unit type: 'piece', 'kg', or 'g'")
    base_unit_price = Column(Float, nullable=False, default=0.0, doc="Price per unit (per piece, per kg, or per gram)")
    extra_fields = Column(
        JSON,
        default=dict,
        doc="Arbitrary product fields (JSON) that can be added/removed.",
    )

    invoice_items = relationship("InvoiceItem", back_populates="product")
    stock_transactions = relationship(
        "StockTransaction", back_populates="product"
    )


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(50), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    customer_uid = Column(String(100), index=True)
    customer_name = Column(String(200))
    total_amount = Column(Float, default=0.0)
    discount_percent = Column(Float, default=0.0)
    discount_fixed = Column(Float, default=0.0)
    tax_percent = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    net_amount = Column(Float, default=0.0)
    payment_method = Column(String(50), default="Cash")
    payment_account = Column(String(100), nullable=True)

    user = relationship("User", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice")


class InvoiceItem(TimestampMixin, Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Float, default=1.0)
    quantity_exact = Column(Float, default=1.0, doc="Exact quantity (can be decimal for weight-based items)")
    unit_type = Column(String(20), default="piece", nullable=False, doc="Unit type: 'piece', 'kg', or 'g'")
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0, doc="Total price for this line item")
    cost_price = Column(Float, default=0.0, doc="Product cost price per unit at time of sale")
    default_sale_price = Column(Float, default=0.0, doc="Default sale price per unit at time of sale")
    actual_sale_price = Column(Float, default=0.0, doc="Actual sale price per unit (can be overridden for bargaining)")
    profit = Column(Float, default=0.0, doc="Profit per unit: actual_sale_price - cost_price (can be negative for loss)")

    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", back_populates="invoice_items")


class StockTransaction(TimestampMixin, Base):
    __tablename__ = "stock_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    change_qty = Column(Float, default=0.0)
    remaining_stock = Column(Float, default=0.0, doc="Stock quantity remaining after this transaction")
    reason = Column(String(200))

    product = relationship("Product", back_populates="stock_transactions")


class Setting(TimestampMixin, Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(String(500), nullable=False)


class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False, default=0.0)
    category = Column(String(100), default="General")
    notes = Column(String(500), nullable=True)
    date = Column(DateTime, default=datetime.utcnow)


