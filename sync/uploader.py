from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from sqlalchemy.orm import Session

from db import models
from utils.config import load_config


@dataclass
class SupabaseConfig:
    base_url: str
    api_key: str


class CloudUploader:
    """Upload local SQLite data to Supabase via REST upserts."""

    def __init__(
        self,
        session: Session,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ) -> None:
        self.session = session

        app_cfg = load_config()
        url = (supabase_url or app_cfg.api_url or "").removesuffix("/")
        key = supabase_key or app_cfg.supabase_key

        if not url or not key:
            raise ValueError(
                "Supabase URL / API key not configured. "
                "Set them in config.json or pass to CloudUploader."
            )

        self.supabase = SupabaseConfig(base_url=url, api_key=key)

    def upload_all(self) -> None:
        """Upload users, products, invoices, stock transactions, and expenses."""
        print("Starting Supabase sync...")
        self.upload_users()
        self.upload_products()
        self.upload_invoices()
        self.upload_stock_transactions()
        self.upload_expenses()
        print("Supabase sync complete.")

    def upload_products(self) -> None:
        products = list(
            self.session.query(models.Product)
            .filter(models.Product.synced.is_(False))
            .all()
        )
        if not products:
            print("No products to upload.")
            return

        payload: list[dict[str, Any]] = []
        for product in products:
            stock_qty = product.stock_qty
            if product.unit_type == "piece":
                stock_qty = int(stock_qty)

            payload.append(
                {
                    "name": product.name,
                    "sku": product.sku,
                    "category": product.category,
                    "price": product.price,
                    "sale_price": product.sale_price,
                    "cost_price": product.cost_price,
                    "stock_qty": stock_qty,
                    "is_active": product.is_active,
                    "unit_type": product.unit_type or "piece",
                    "base_unit_price": product.base_unit_price or product.price,
                    "extra_fields": product.extra_fields or {},
                    "created_at": product.created_at.isoformat() if product.created_at else None,
                    "last_modified": product.last_modified.isoformat() if product.last_modified else None,
                }
            )

        print(f"Uploading {len(payload)} products...")
        self._post_rows("products", payload, on_conflict="sku")

        for product in products:
            product.synced = True
        self.session.commit()
        print("Products upload finished.")

    def upload_invoices(self) -> None:
        invoices = list(
            self.session.query(models.Invoice)
            .filter(models.Invoice.synced.is_(False))
            .all()
        )
        if not invoices:
            print("No invoices to upload.")
            return

        local_user_ids = {invoice.user_id for invoice in invoices if invoice.user_id is not None}
        local_users = (
            list(
                self.session.query(models.User)
                .filter(models.User.id.in_(list(local_user_ids)))
                .all()
            )
            if local_user_ids
            else []
        )
        id_to_username = {user.id: user.username for user in local_users}
        remote_user_map = self._fetch_remote_user_map()

        invoice_payload: list[dict[str, Any]] = []
        for invoice in invoices:
            remote_user_id = None
            if invoice.user_id is not None:
                username = id_to_username.get(invoice.user_id)
                remote_user_id = remote_user_map.get(username) if username else None

            invoice_payload.append(
                {
                    "number": invoice.number,
                    "user_id": remote_user_id,
                    "customer_uid": invoice.customer_uid,
                    "customer_name": invoice.customer_name,
                    "total_amount": invoice.total_amount,
                    "discount_percent": invoice.discount_percent,
                    "discount_fixed": invoice.discount_fixed,
                    "tax_percent": invoice.tax_percent,
                    "tax_amount": invoice.tax_amount,
                    "net_amount": invoice.net_amount,
                    "payment_method": invoice.payment_method,
                    "payment_account": invoice.payment_account,
                    "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
                    "last_modified": invoice.last_modified.isoformat() if invoice.last_modified else None,
                }
            )

        print(f"Uploading {len(invoice_payload)} invoices...")
        self._post_rows("invoices", invoice_payload, on_conflict="number")

        invoice_ids = [invoice.id for invoice in invoices]
        items = list(
            self.session.query(models.InvoiceItem)
            .filter(models.InvoiceItem.invoice_id.in_(invoice_ids))
            .all()
        )

        if items:
            local_inv_id_to_number = {invoice.id: invoice.number for invoice in invoices}
            remote_invoice_map = self._fetch_remote_invoice_map()

            local_product_ids = {item.product_id for item in items if item.product_id is not None}
            local_products = (
                list(
                    self.session.query(models.Product)
                    .filter(models.Product.id.in_(list(local_product_ids)))
                    .all()
                )
                if local_product_ids
                else []
            )
            id_to_sku = {product.id: product.sku for product in local_products}
            remote_product_map = self._fetch_remote_product_map()

            items_payload: list[dict[str, Any]] = []
            for item in items:
                invoice_number = local_inv_id_to_number.get(item.invoice_id)
                product_sku = id_to_sku.get(item.product_id)

                items_payload.append(
                    {
                        "invoice_id": remote_invoice_map.get(invoice_number) if invoice_number else None,
                        "product_id": remote_product_map.get(product_sku) if product_sku else None,
                        "quantity": item.quantity,
                        "quantity_exact": item.quantity_exact or item.quantity,
                        "unit_type": item.unit_type or "piece",
                        "unit_price": item.unit_price,
                        "total_price": item.total_price or ((item.quantity or 0) * (item.unit_price or 0)),
                        "cost_price": item.cost_price or 0.0,
                        "default_sale_price": item.default_sale_price or 0.0,
                        "actual_sale_price": item.actual_sale_price or item.unit_price,
                        "profit": item.profit or 0.0,
                        "created_at": item.created_at.isoformat() if item.created_at else None,
                        "last_modified": item.last_modified.isoformat() if item.last_modified else None,
                    }
                )

            print(f"Uploading {len(items_payload)} invoice items...")
            self._post_rows("invoice_items", items_payload, on_conflict=None)

        for invoice in invoices:
            invoice.synced = True
        self.session.commit()
        print("Invoices and items upload finished.")

    def upload_stock_transactions(self) -> None:
        transactions = list(
            self.session.query(models.StockTransaction)
            .filter(models.StockTransaction.synced.is_(False))
            .all()
        )
        if not transactions:
            print("No stock transactions to upload.")
            return

        valid_transactions = [transaction for transaction in transactions if transaction.product_id is not None]
        if not valid_transactions:
            for transaction in transactions:
                transaction.synced = True
            self.session.commit()
            return

        payload: list[dict[str, Any]] = []
        for transaction in valid_transactions:
            remaining_stock = transaction.remaining_stock
            if remaining_stock is None or remaining_stock == 0.0:
                remaining_stock = transaction.product.stock_qty or 0.0 if transaction.product else 0.0

            payload.append(
                {
                    "product_id": None,
                    "change_qty": transaction.change_qty,
                    "remaining_stock": remaining_stock,
                    "reason": transaction.reason,
                    "created_at": transaction.created_at.isoformat() if transaction.created_at else None,
                    "last_modified": transaction.last_modified.isoformat() if transaction.last_modified else None,
                }
            )

        local_product_ids = {transaction.product_id for transaction in valid_transactions}
        local_products = list(
            self.session.query(models.Product)
            .filter(models.Product.id.in_(list(local_product_ids)))
            .all()
        )
        id_to_sku = {product.id: product.sku for product in local_products}
        remote_product_map = self._fetch_remote_product_map()

        valid_payload: list[dict[str, Any]] = []
        valid_transaction_indices: list[int] = []
        for index, (row, transaction) in enumerate(zip(payload, valid_transactions)):
            product_sku = id_to_sku.get(transaction.product_id)
            remote_product_id = remote_product_map.get(product_sku) if product_sku else None
            if remote_product_id is not None:
                row["product_id"] = remote_product_id
                valid_payload.append(row)
                valid_transaction_indices.append(index)
            else:
                print(f"Warning: Could not resolve product_id for stock transaction {transaction.id}")

        if not valid_payload:
            print("No stock transactions to upload (could not resolve product_ids).")
            return

        print(f"Uploading {len(valid_payload)} stock transactions...")
        self._post_rows("stock_transactions", valid_payload, on_conflict=None)

        for index in valid_transaction_indices:
            valid_transactions[index].synced = True
        for transaction in transactions:
            if transaction.product_id is None:
                transaction.synced = True
        self.session.commit()
        print("Stock transactions upload finished.")

    def upload_users(self) -> None:
        users = list(self.session.query(models.User).all())
        if not users:
            print("No users to upload.")
            return

        payload = [
            {
                "username": user.username,
                "password_hash": user.password_hash,
                "is_admin": user.is_admin,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_modified": user.last_modified.isoformat() if user.last_modified else None,
            }
            for user in users
        ]

        print(f"Uploading {len(payload)} users...")
        self._post_rows("users", payload, on_conflict="username")
        for user in users:
            user.synced = True
        self.session.commit()
        print("Users upload finished.")

    def upload_expenses(self) -> None:
        expenses = list(
            self.session.query(models.Expense)
            .filter(models.Expense.synced.is_(False))
            .all()
        )
        if not expenses:
            print("No expenses to upload.")
            return

        payload = [
            {
                "id": expense.id,
                "title": expense.title,
                "amount": expense.amount,
                "category": expense.category or "General",
                "notes": expense.notes or "",
                "date": expense.date.isoformat() if expense.date else None,
                "created_at": expense.created_at.isoformat() if expense.created_at else None,
                "last_modified": expense.last_modified.isoformat() if expense.last_modified else None,
            }
            for expense in expenses
        ]

        print(f"Uploading {len(payload)} expenses...")
        self._post_rows("expenses", payload, on_conflict="id")

        for expense in expenses:
            expense.synced = True
        self.session.commit()

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase.api_key,
            "Authorization": f"Bearer {self.supabase.api_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

    def _post_rows(self, table: str, rows: list[dict[str, Any]], on_conflict: str | None) -> None:
        if not rows:
            return

        url = f"{self.supabase.base_url}/rest/v1/{table}"
        if on_conflict:
            url += f"?on_conflict={on_conflict}"

        response = requests.post(url, headers=self._headers(), json=rows)
        if not response.ok:
            raise RuntimeError(
                f"Failed to upload to {table}: {response.status_code} {response.text}"
            )

    def _fetch_remote_user_map(self) -> dict[str, int]:
        return self._fetch_id_map("users", "username")

    def _fetch_remote_product_map(self) -> dict[str, int]:
        return self._fetch_id_map("products", "sku")

    def _fetch_remote_invoice_map(self) -> dict[str, int]:
        return self._fetch_id_map("invoices", "number")

    def _fetch_id_map(self, table: str, key: str) -> dict[str, int]:
        url = f"{self.supabase.base_url}/rest/v1/{table}?select=id,{key}"
        response = requests.get(url, headers=self._headers())
        if not response.ok:
            return {}

        try:
            rows = response.json()
        except ValueError:
            return {}

        mapping: dict[str, int] = {}
        for row in rows:
            value = row.get(key)
            remote_id = row.get("id")
            if isinstance(value, str) and isinstance(remote_id, int):
                mapping[value] = remote_id
        return mapping
