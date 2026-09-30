import os
from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import scoped_session, sessionmaker

from .models import Base, User
from utils.security import hash_password


def get_database_url() -> str:
    """
    Determine the database URL based on the environment.

    In production (and development), we want to store data in a writable location
    that persists across updates and works in restricted directories like 'Program Files'.

    On Windows, 'ProgramData' is the standard location for application data shared by users.
    """
    # 1. Get ProgramData path (safe for Windows)
    # Default to C:\ProgramData if env var missing for some reason
    program_data = os.getenv("ProgramData", "C:\\ProgramData")

    # 2. Define our app's data directory
    app_data_dir = Path(program_data) / "FishManagement"

    # 3. Create directory if it doesn't exist
    try:
        app_data_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # Fallback to user's local appdata if we can't write to ProgramData (rare permission issue)
        # This is a safety valve.
        print(
            f"Warning: Could not create ProgramData directory: {e}. Falling back to LocalAppData."
        )
        app_data_dir = (
            Path(os.getenv("LOCALAPPDATA", os.path.expanduser("~"))) / "FishManagement"
        )
        app_data_dir.mkdir(parents=True, exist_ok=True)

    # 4. Construct path
    db_path = app_data_dir / "fish.db"

    # Return SQLite URL (absolute path, using forward slashes for SQLAlchemy compatibility)
    return f"sqlite:///{db_path.as_posix()}"


# Initialize engine with the resolving URL
DATABASE_URL = get_database_url()


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite ignores FK constraints unless this pragma is set per-connection.

    Enabling it keeps referential integrity (invoices -> users, items ->
    products, etc.). Callers that must bulk-delete parents (e.g. the cloud
    restorer) clear child rows first so no constraint is violated.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)


def _migrate_invoices_table() -> None:
    """Add new columns to invoices table if they don't exist."""
    with engine.begin() as conn:  # Use begin() for automatic transaction management
        # Check if invoices table exists
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'"
            )
        )
        if not result.fetchone():
            return  # Table doesn't exist yet, create_all will handle it

        # Get existing columns
        result = conn.execute(text("PRAGMA table_info(invoices)"))
        existing_columns = {row[1] for row in result.fetchall()}

        # Add missing columns (using REAL for SQLite compatibility)
        migrations = [
            ("customer_uid", "VARCHAR(100)"),
            ("customer_name", "VARCHAR(200)"),
            ("discount_fixed", "REAL DEFAULT 0.0"),
            ("tax_percent", "REAL DEFAULT 0.0"),
            ("tax_amount", "REAL DEFAULT 0.0"),
            ("net_amount", "REAL DEFAULT 0.0"),
            ("payment_method", "VARCHAR(50) DEFAULT 'Cash'"),
            ("payment_account", "VARCHAR(100)"),
        ]

        for column_name, column_def in migrations:
            if column_name not in existing_columns:
                try:
                    conn.execute(
                        text(
                            f"ALTER TABLE invoices ADD COLUMN {column_name} {column_def}"
                        )
                    )
                    print(f"✓ Added column '{column_name}' to invoices table")
                except Exception as e:
                    print(f"⚠ Could not add column '{column_name}': {e}")
                    # Transaction will rollback automatically on exception


def _migrate_products_table() -> None:
    """Add new columns to products table if they don't exist."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
            )
        )
        if not result.fetchone():
            return

        result = conn.execute(text("PRAGMA table_info(products)"))
        existing_columns = {row[1] for row in result.fetchall()}

        migrations = [
            ("unit_type", "VARCHAR(20) DEFAULT 'piece'"),
            ("base_unit_price", "REAL DEFAULT 0.0"),
            ("sale_price", "REAL DEFAULT 0.0"),
            ("cost_price", "REAL DEFAULT 0.0"),
        ]

        for column_name, column_def in migrations:
            if column_name not in existing_columns:
                try:
                    conn.execute(
                        text(
                            f"ALTER TABLE products ADD COLUMN {column_name} {column_def}"
                        )
                    )
                    print(f"✓ Added column '{column_name}' to products table")
                    # For existing products, set base_unit_price = price and unit_type = 'piece'
                    if column_name == "base_unit_price":
                        conn.execute(
                            text(
                                "UPDATE products SET base_unit_price = price WHERE base_unit_price = 0.0"
                            )
                        )
                    elif column_name == "sale_price":
                        conn.execute(
                            text(
                                "UPDATE products SET sale_price = base_unit_price WHERE sale_price = 0.0"
                            )
                        )
                    elif column_name == "cost_price":
                        conn.execute(
                            text(
                                "UPDATE products SET cost_price = base_unit_price WHERE cost_price = 0.0"
                            )
                        )
                except Exception as e:
                    print(f"⚠ Could not add column '{column_name}': {e}")


def _migrate_invoice_items_table() -> None:
    """Add new columns to invoice_items table if they don't exist."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='invoice_items'"
            )
        )
        if not result.fetchone():
            return

        result = conn.execute(text("PRAGMA table_info(invoice_items)"))
        existing_columns = {row[1] for row in result.fetchall()}

        migrations = [
            ("quantity_exact", "REAL DEFAULT 1.0"),
            ("unit_type", "VARCHAR(20) DEFAULT 'piece'"),
            ("total_price", "REAL DEFAULT 0.0"),
            ("cost_price", "REAL DEFAULT 0.0"),
            ("default_sale_price", "REAL DEFAULT 0.0"),
            ("actual_sale_price", "REAL DEFAULT 0.0"),
            ("profit", "REAL DEFAULT 0.0"),
        ]

        for column_name, column_def in migrations:
            if column_name not in existing_columns:
                try:
                    conn.execute(
                        text(
                            f"ALTER TABLE invoice_items ADD COLUMN {column_name} {column_def}"
                        )
                    )
                    print(f"✓ Added column '{column_name}' to invoice_items table")
                    # For existing items, set quantity_exact = quantity, total_price = quantity * unit_price
                    if column_name == "quantity_exact":
                        conn.execute(
                            text(
                                "UPDATE invoice_items SET quantity_exact = quantity WHERE quantity_exact = 1.0"
                            )
                        )
                    elif column_name == "total_price":
                        conn.execute(
                            text(
                                "UPDATE invoice_items SET total_price = quantity * unit_price WHERE total_price = 0.0"
                            )
                        )
                    elif column_name == "cost_price":
                        # Set cost_price from product's cost_price at time of sale (approximation)
                        conn.execute(text("""
                                UPDATE invoice_items 
                                SET cost_price = (
                                    SELECT COALESCE(p.cost_price, 0.0)
                                    FROM products p
                                    WHERE p.id = invoice_items.product_id
                                )
                                WHERE cost_price = 0.0
                            """))
                    elif column_name == "default_sale_price":
                        # Set default_sale_price from product's sale_price
                        conn.execute(text("""
                                UPDATE invoice_items 
                                SET default_sale_price = (
                                    SELECT COALESCE(p.sale_price, p.base_unit_price, p.price, 0.0)
                                    FROM products p
                                    WHERE p.id = invoice_items.product_id
                                )
                                WHERE default_sale_price = 0.0
                            """))
                    elif column_name == "actual_sale_price":
                        # Set actual_sale_price = unit_price (for existing records)
                        conn.execute(
                            text(
                                "UPDATE invoice_items SET actual_sale_price = unit_price WHERE actual_sale_price = 0.0"
                            )
                        )
                    elif column_name == "profit":
                        # Calculate profit: actual_sale_price - cost_price
                        conn.execute(
                            text(
                                "UPDATE invoice_items SET profit = actual_sale_price - cost_price WHERE profit = 0.0"
                            )
                        )
                except Exception as e:
                    print(f"⚠ Could not add column '{column_name}': {e}")


def _migrate_stock_transactions_table() -> None:
    """Add new columns to stock_transactions table if they don't exist."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_transactions'"
            )
        )
        if not result.fetchone():
            return

        result = conn.execute(text("PRAGMA table_info(stock_transactions)"))
        existing_columns = {row[1] for row in result.fetchall()}

        migrations = [
            ("remaining_stock", "REAL DEFAULT 0.0"),
        ]

        for column_name, column_def in migrations:
            if column_name not in existing_columns:
                try:
                    conn.execute(
                        text(
                            f"ALTER TABLE stock_transactions ADD COLUMN {column_name} {column_def}"
                        )
                    )
                    print(f"✓ Added column '{column_name}' to stock_transactions table")
                    # For existing transactions, set remaining_stock to product's current stock
                    # This is an approximation - new transactions will have accurate values
                    if column_name == "remaining_stock":
                        conn.execute(text("""
                                UPDATE stock_transactions 
                                SET remaining_stock = (
                                    SELECT COALESCE(p.stock_qty, 0)
                                    FROM products p
                                    WHERE p.id = stock_transactions.product_id
                                )
                                WHERE remaining_stock = 0.0
                            """))
                except Exception as e:
                    print(f"⚠ Could not add column '{column_name}': {e}")


def init_db() -> None:
    """Create all tables defined on the ORM Base and seed default admin."""
    Base.metadata.create_all(bind=engine)

    # Run migrations for existing tables
    _migrate_invoices_table()
    _migrate_products_table()
    _migrate_invoice_items_table()
    _migrate_stock_transactions_table()

    # Seed default admin user (admin / admin) if none exist
    session = SessionLocal()
    try:
        has_user = session.query(User).first() is not None
        if not has_user:
            admin = User(
                username="admin", password_hash=hash_password("admin"), is_admin=True
            )
            session.add(admin)
            session.commit()
        existing_user = session.query(User).filter(User.username == "user").first()
        if existing_user is None:
            standard_user = User(
                username="user", password_hash=hash_password("user"), is_admin=False
            )
            session.add(standard_user)
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session():
    """Return a new SQLAlchemy session."""
    return SessionLocal()


def get_by_id(session, model, object_id):
    """Compatibility wrapper for SQLAlchemy 1.x and 2.x entity fetches."""
    if session is None or model is None or object_id is None:
        return None
    try:
        return session.get(model, object_id)
    except Exception:
        try:
            return session.query(model).filter(model.id == object_id).first()
        except Exception:
            return None
