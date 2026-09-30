from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import requests
from sqlalchemy.orm import Session

from db import models
from utils.config import load_config


class CloudRestorer:
    """Download and restore data from Supabase to local SQLite database."""

    def __init__(
        self,
        session: Session,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ) -> None:
        self.session: Session = session

        app_cfg = load_config()
        url = supabase_url or app_cfg.api_url
        key = supabase_key or app_cfg.supabase_key

        if not url or not key:
            raise ValueError(
                "Supabase URL / API key not configured. "
                "Set them in config.json or pass to CloudRestorer."
            )

        url = url.removesuffix("/")

        self.base_url: str = url
        self.api_key: str = key

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _get_rows(self, table: str, select: str | None = None) -> list[dict[str, object]]:
        """Fetch all rows from a Supabase table."""
        url = f"{self.base_url}/rest/v1/{table}"
        if select:
            url += f"?select={select}"
        
        resp = requests.get(url, headers=self._headers())
        if not resp.ok:
            raise RuntimeError(
                f"Failed to fetch {table}: {resp.status_code} {resp.text}"
            )
        return resp.json()

    def restore_all(self) -> None:
        """Restore all data from Supabase to local database."""
        print("Starting backup restore from Supabase...")
        
        # Restore in order: users, products, invoices, invoice_items, stock_transactions, settings
        self.restore_users()
        self.restore_products()
        self.restore_invoices()
        self.restore_invoice_items()
        self.restore_stock_transactions()
        self.restore_expenses()
        self.restore_settings()
        
        print("Backup restore complete.")

    def restore_users(self) -> None:
        """Restore users from Supabase."""
        print("Restoring users...")
        rows = self._get_rows("users")
        
        # Clear existing users
        self.session.query(models.User).delete()
        
        # Create user mapping for invoice restoration
        username_to_id = {}
        
        for row in rows:
            user = models.User(
                username=row.get("username"),
                password_hash=row.get("password_hash"),
                is_admin=row.get("is_admin", False),
                synced=True,
            )
            if row.get("created_at"):
                try:
                    user.created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            if row.get("last_modified"):
                try:
                    user.last_modified = datetime.fromisoformat(row["last_modified"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            self.session.add(user)
            username_to_id[user.username] = user
        
        self.session.commit()
        print(f"Restored {len(rows)} users.")

    def restore_products(self) -> None:
        """Restore products from Supabase."""
        print("Restoring products...")
        rows = self._get_rows("products")
        
        # Clear existing products
        self.session.query(models.Product).delete()
        
        # Create SKU to product mapping for invoice_items and stock_transactions
        sku_to_product = {}
        
        for row in rows:
            product = models.Product(
                name=row.get("name"),
                sku=row.get("sku"),
                category=row.get("category"),
                price=row.get("price", 0.0),
                stock_qty=row.get("stock_qty", 0.0),
                is_active=row.get("is_active", True),
                unit_type=row.get("unit_type", "piece") or "piece",
                base_unit_price=row.get("base_unit_price", row.get("price", 0.0)) or row.get("price", 0.0),
                extra_fields=row.get("extra_fields", {}),
                synced=True,
            )
            if row.get("created_at"):
                try:
                    product.created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            if row.get("last_modified"):
                try:
                    product.last_modified = datetime.fromisoformat(row["last_modified"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            self.session.add(product)
            sku_to_product[product.sku] = product
        
        self.session.commit()
        print(f"Restored {len(rows)} products.")
        return sku_to_product

    def restore_invoices(self) -> None:
        """Restore invoices from Supabase."""
        print("Restoring invoices...")
        rows = self._get_rows("invoices")
        
        # Clear existing invoices
        self.session.query(models.InvoiceItem).delete()  # Delete items first due to FK
        self.session.query(models.Invoice).delete()
        
        # Get user mapping
        username_to_user = {u.username: u for u in self.session.query(models.User).all()}
        
        # Get remote user IDs from Supabase
        remote_users = self._get_rows("users", "id,username")
        remote_user_map = {row["id"]: row["username"] for row in remote_users if "id" in row and "username" in row}
        
        invoice_number_to_invoice = {}
        
        for row in rows:
            # Map remote user_id to local user
            user_id = row.get("user_id")
            local_user = None
            if user_id and user_id in remote_user_map:
                username = remote_user_map[user_id]
                local_user = username_to_user.get(username)
            
            invoice = models.Invoice(
                number=row.get("number"),
                user_id=local_user.id if local_user else None,
                customer_uid=row.get("customer_uid"),
                customer_name=row.get("customer_name"),
                total_amount=row.get("total_amount", 0.0),
                discount_percent=row.get("discount_percent", 0.0),
                discount_fixed=row.get("discount_fixed", 0.0),
                tax_percent=row.get("tax_percent", 0.0),
                tax_amount=row.get("tax_amount", 0.0),
                net_amount=row.get("net_amount", row.get("total_amount", 0.0)),
                synced=True,
            )
            if row.get("created_at"):
                try:
                    invoice.created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            if row.get("last_modified"):
                try:
                    invoice.last_modified = datetime.fromisoformat(row["last_modified"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            self.session.add(invoice)
            invoice_number_to_invoice[invoice.number] = invoice
        
        self.session.commit()
        print(f"Restored {len(rows)} invoices.")
        return invoice_number_to_invoice

    def restore_invoice_items(self) -> None:
        """Restore invoice items from Supabase."""
        print("Restoring invoice items...")
        rows = self._get_rows("invoice_items")
        
        # Get mappings
        invoice_number_to_invoice = {inv.number: inv for inv in self.session.query(models.Invoice).all()}
        sku_to_product = {p.sku: p for p in self.session.query(models.Product).all()}
        
        # Get remote mappings from Supabase
        remote_invoices = self._get_rows("invoices", "id,number")
        remote_invoice_map = {row["id"]: row["number"] for row in remote_invoices if "id" in row and "number" in row}
        
        remote_products = self._get_rows("products", "id,sku")
        remote_product_map = {row["id"]: row["sku"] for row in remote_products if "id" in row and "sku" in row}
        
        for row in rows:
            # Map remote invoice_id to local invoice
            remote_inv_id = row.get("invoice_id")
            local_invoice = None
            if remote_inv_id and remote_inv_id in remote_invoice_map:
                invoice_number = remote_invoice_map[remote_inv_id]
                local_invoice = invoice_number_to_invoice.get(invoice_number)
            
            # Map remote product_id to local product
            remote_prod_id = row.get("product_id")
            local_product = None
            if remote_prod_id and remote_prod_id in remote_product_map:
                sku = remote_product_map[remote_prod_id]
                local_product = sku_to_product.get(sku)
            
            if not local_invoice or not local_product:
                continue  # Skip if mappings not found
            
            item = models.InvoiceItem(
                invoice_id=local_invoice.id,
                product_id=local_product.id,
                quantity=row.get("quantity", 1),
                quantity_exact=row.get("quantity_exact", row.get("quantity", 1.0)),
                unit_type=row.get("unit_type", "piece") or "piece",
                unit_price=row.get("unit_price", 0.0),
                total_price=row.get("total_price", 0.0),
                cost_price=row.get("cost_price", 0.0) or 0.0,
                default_sale_price=row.get("default_sale_price", 0.0) or 0.0,
                actual_sale_price=row.get("actual_sale_price", row.get("unit_price", 0.0)) or row.get("unit_price", 0.0),
                profit=row.get("profit", 0.0) or 0.0,
                synced=True,
            )
            if row.get("created_at"):
                try:
                    item.created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            if row.get("last_modified"):
                try:
                    item.last_modified = datetime.fromisoformat(row["last_modified"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            self.session.add(item)
        
        self.session.commit()
        print(f"Restored {len(rows)} invoice items.")

    def restore_stock_transactions(self) -> None:
        """Restore stock transactions from Supabase."""
        print("Restoring stock transactions...")
        rows = self._get_rows("stock_transactions")
        
        # Clear existing transactions
        self.session.query(models.StockTransaction).delete()
        
        # Get product mapping
        sku_to_product = {p.sku: p for p in self.session.query(models.Product).all()}
        
        # Get remote product mapping from Supabase
        remote_products = self._get_rows("products", "id,sku")
        remote_product_map = {row["id"]: row["sku"] for row in remote_products if "id" in row and "sku" in row}
        
        for row in rows:
            # Map remote product_id to local product
            remote_prod_id = row.get("product_id")
            local_product = None
            if remote_prod_id and remote_prod_id in remote_product_map:
                sku = remote_product_map[remote_prod_id]
                local_product = sku_to_product.get(sku)
            
            if not local_product:
                continue  # Skip if product not found
            
            tx = models.StockTransaction(
                product_id=local_product.id,
                change_qty=row.get("change_qty", 0.0),
                remaining_stock=row.get("remaining_stock", local_product.stock_qty or 0.0),
                reason=row.get("reason", ""),
                synced=True,
            )
            if row.get("created_at"):
                try:
                    tx.created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            if row.get("last_modified"):
                try:
                    tx.last_modified = datetime.fromisoformat(row["last_modified"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            self.session.add(tx)
        
        self.session.commit()
        print(f"Restored {len(rows)} stock transactions.")

    def restore_settings(self) -> None:
        """Restore settings from Supabase (if settings table exists)."""
        try:
            print("Restoring settings...")
            rows = self._get_rows("settings")
            
            # Note: Settings table might not exist in local DB, so we'll skip if it doesn't
            # This is optional functionality
            if rows:
                print(f"Found {len(rows)} settings to restore (settings table may not exist locally).")
        except Exception as e:
            print(f"Settings restore skipped: {e}")

    def restore_expenses(self) -> None:
        """Restore expenses from Supabase."""
        print("Restoring expenses...")
        try:
            rows = self._get_rows("expenses")
            
            # Clear existing expenses
            self.session.query(models.Expense).delete()
            
            for row in rows:
                expense = models.Expense(
                    title=row.get("title"),
                    amount=row.get("amount", 0.0),
                    category=row.get("category", "General"),
                    notes=row.get("notes", ""),
                    synced=True,
                )
                if row.get("date"):
                    try:
                        expense.date = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
                    except Exception:
                        pass
                if row.get("created_at"):
                    try:
                        expense.created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                    except Exception:
                        pass
                if row.get("last_modified"):
                    try:
                        expense.last_modified = datetime.fromisoformat(row["last_modified"].replace("Z", "+00:00"))
                    except Exception:
                        pass
                
                self.session.add(expense)
            
            self.session.commit()
            print(f"Restored {len(rows)} expenses.")
        except Exception as e:
            print(f"Warning: Could not restore expenses: {e}")