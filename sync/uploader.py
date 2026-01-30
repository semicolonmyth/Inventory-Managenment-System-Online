from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional

import requests
from sqlalchemy.orm import Session

from db import models
from utils.config import load_config


@dataclass
class SupabaseConfig:
    base_url: str
    api_key: str


class CloudUploader:
    """Upload local SQLite data to Supabase via REST upserts.

    Uses the `synced` flag and `last_modified` timestamp from each model.
    Desktop is the source of truth, so all local changes are upserted.
    """

    def __init__(
        self,
        session: Session,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ) -> None:
        self.session = session

        app_cfg = load_config()
        url = supabase_url or app_cfg.api_url
        key = supabase_key or app_cfg.supabase_key

        if not url or not key:
            raise ValueError(
                "Supabase URL / API key not configured. "
                "Set them in config.json or pass to CloudUploader."
            )

        if url.endswith("/"):
            url = url[:-1]

        self.supabase = SupabaseConfig(base_url=url, api_key=key)

    # ---------- Public API ----------

    def upload_all(self) -> None:
        """Upload products, invoices (and items), and stock transactions."""
        print("Starting Supabase sync...")
        self.upload_users()
        self.upload_products()
        self.upload_invoices()
        self.upload_stock_transactions()
        self.upload_expenses()
        print("Supabase sync complete.")

    def upload_products(self) -> None:
        products: List[models.Product] = (
            self.session.query(models.Product)
            .filter(models.Product.synced.is_(False))
            .all()
        )
        if not products:
            print("No products to upload.")
            return

        payload = [
            {
                "name": p.name,
                "sku": p.sku,
                "category": p.category,
                "price": p.price,
                "stock_qty": int(p.stock_qty) if p.stock_qty is not None and getattr(p, "unit_type", "piece") == "piece" else p.stock_qty,
                "is_active": p.is_active,
                "unit_type": getattr(p, "unit_type", "piece") or "piece",
                "base_unit_price": getattr(p, "base_unit_price", p.price) or p.price,
                "extra_fields": p.extra_fields,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "last_modified": p.last_modified.isoformat()
                if p.last_modified
                else None,
            }
            for p in products
        ]

        print(f"Uploading {len(payload)} products...")
        self._post_rows("products", payload, on_conflict="sku")

        for p in products:
            p.synced = True
        self.session.commit()
        print("Products upload finished.")

    def upload_invoices(self) -> None:
        invoices: List[models.Invoice] = (
            self.session.query(models.Invoice)
            .filter(models.Invoice.synced.is_(False))
            .all()
        )
        if not invoices:
            print("No invoices to upload.")
            return

        local_user_ids = {inv.user_id for inv in invoices if inv.user_id is not None}
        local_users: List[models.User] = []
        if local_user_ids:
            local_users = (
                self.session.query(models.User)
                .filter(models.User.id.in_(list(local_user_ids)))
                .all()
            )
        id_to_username = {u.id: u.username for u in local_users}
        remote_user_map = self._fetch_remote_user_map()

        invoice_payload = [
            {
                "number": inv.number,
                "user_id": remote_user_map.get(id_to_username.get(inv.user_id, ""))
                if inv.user_id is not None
                else None,
                "customer_uid": getattr(inv, "customer_uid", None),
                "customer_name": getattr(inv, "customer_name", None),
                "total_amount": inv.total_amount,
                "discount_percent": inv.discount_percent,
                "discount_fixed": getattr(inv, "discount_fixed", 0.0),
                "tax_percent": getattr(inv, "tax_percent", 0.0),
                "tax_amount": getattr(inv, "tax_amount", 0.0),
                "net_amount": getattr(inv, "net_amount", inv.total_amount),
                "payment_method": getattr(inv, "payment_method", "Cash"),
                "payment_account": getattr(inv, "payment_account", None),
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "last_modified": inv.last_modified.isoformat()
                if inv.last_modified
                else None,
            }
            for inv in invoices
        ]

        print(f"Uploading {len(invoice_payload)} invoices...")
        self._post_rows("invoices", invoice_payload, on_conflict="number")

        # Upload invoice items belonging to these invoices
        invoice_ids = [inv.id for inv in invoices]
        items: List[models.InvoiceItem] = (
            self.session.query(models.InvoiceItem)
            .filter(models.InvoiceItem.invoice_id.in_(invoice_ids))
            .all()
        )

        if items:
            local_inv_id_to_number = {inv.id: inv.number for inv in invoices}
            remote_invoice_map = self._fetch_remote_invoice_map()
            # product mapping
            local_product_ids = {item.product_id for item in items if item.product_id is not None}
            local_products = []
            if local_product_ids:
                local_products = (
                    self.session.query(models.Product)
                    .filter(models.Product.id.in_(list(local_product_ids)))
                    .all()
                )
            id_to_sku = {p.id: p.sku for p in local_products}
            remote_product_map = self._fetch_remote_product_map()
            items_payload = [
                {
                    "invoice_id": remote_invoice_map.get(local_inv_id_to_number.get(item.invoice_id, "")),
                    "product_id": remote_product_map.get(id_to_sku.get(item.product_id, "")),
                    "quantity": item.quantity,
                    "quantity_exact": getattr(item, "quantity_exact", item.quantity) or item.quantity,
                    "unit_type": getattr(item, "unit_type", "piece") or "piece",
                    "unit_price": item.unit_price,
                    "total_price": getattr(item, "total_price", (item.quantity or 0) * (item.unit_price or 0)) or ((item.quantity or 0) * (item.unit_price or 0)),
                    "cost_price": getattr(item, "cost_price", 0.0) or 0.0,
                    "default_sale_price": getattr(item, "default_sale_price", 0.0) or 0.0,
                    "actual_sale_price": getattr(item, "actual_sale_price", item.unit_price) or item.unit_price,
                    "profit": getattr(item, "profit", 0.0) or 0.0,
                    "created_at": item.created_at.isoformat()
                    if item.created_at
                    else None,
                    "last_modified": item.last_modified.isoformat()
                    if item.last_modified
                    else None,
                }
                for item in items
            ]
            print(f"Uploading {len(items_payload)} invoice items...")
            self._post_rows("invoice_items", items_payload, on_conflict=None)

        for inv in invoices:
            inv.synced = True
        self.session.commit()
        print("Invoices and items upload finished.")

    def upload_stock_transactions(self) -> None:
        txs: List[models.StockTransaction] = (
            self.session.query(models.StockTransaction)
            .filter(models.StockTransaction.synced.is_(False))
            .all()
        )
        if not txs:
            print("No stock transactions to upload.")
            return

        # Filter out transactions with null product_id (invalid data)
        valid_txs = [tx for tx in txs if tx.product_id is not None]
        if not valid_txs:
            print("No valid stock transactions to upload (all have null product_id).")
            # Mark invalid transactions as synced to avoid retrying
            for tx in txs:
                tx.synced = True
            self.session.commit()
            return

        if len(valid_txs) < len(txs):
            skipped = len(txs) - len(valid_txs)
            print(f"Warning: Skipping {skipped} stock transaction(s) with null product_id.")

        payload = []
        for tx in valid_txs:
            # Get remaining_stock from transaction, or calculate from product if not set
            remaining_stock = getattr(tx, "remaining_stock", None)
            if remaining_stock is None or remaining_stock == 0.0:
                # Fallback: use product's current stock if remaining_stock not set
                if tx.product:
                    remaining_stock = tx.product.stock_qty or 0.0
                else:
                    remaining_stock = 0.0
            
            payload.append({
                "product_id": None,  # Will be filled below
                "change_qty": tx.change_qty,
                "remaining_stock": remaining_stock,
                "reason": tx.reason,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "last_modified": tx.last_modified.isoformat()
                if tx.last_modified
                else None,
            })

        # fill product_id via remote map
        local_product_ids = {tx.product_id for tx in valid_txs}
        local_products = (
            self.session.query(models.Product)
            .filter(models.Product.id.in_(list(local_product_ids)))
            .all()
        )
        id_to_sku = {p.id: p.sku for p in local_products}
        remote_product_map = self._fetch_remote_product_map()
        
        # Filter out rows where product_id couldn't be resolved
        valid_payload = []
        valid_tx_indices = []
        for idx, (row, tx) in enumerate(zip(payload, valid_txs)):
            remote_product_id = remote_product_map.get(id_to_sku.get(tx.product_id, ""))
            if remote_product_id is not None:
                row["product_id"] = remote_product_id
                valid_payload.append(row)
                valid_tx_indices.append(idx)
            else:
                print(f"Warning: Could not resolve product_id for stock transaction {tx.id}")

        if not valid_payload:
            print("No stock transactions to upload (could not resolve product_ids).")
            return

        print(f"Uploading {len(valid_payload)} stock transactions...")
        self._post_rows("stock_transactions", valid_payload, on_conflict=None)

        # Mark only successfully uploaded transactions as synced
        for idx in valid_tx_indices:
            valid_txs[idx].synced = True
        # Also mark invalid transactions (null product_id) as synced to avoid retrying
        for tx in txs:
            if tx.product_id is None:
                tx.synced = True
        self.session.commit()
        print("Stock transactions upload finished.")

    def upload_users(self) -> None:
        users: List[models.User] = self.session.query(models.User).all()
        if not users:
            print("No users to upload.")
            return

        payload = [
            {
                "username": u.username,
                "password_hash": u.password_hash,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_modified": u.last_modified.isoformat() if u.last_modified else None,
            }
            for u in users
        ]

        print(f"Uploading {len(payload)} users...")
        self._post_rows("users", payload, on_conflict="username")
        for u in users:
            u.synced = True
        self.session.commit()
        print("Users upload finished.")

    # ---------- Internal helpers ----------

    def _headers(self) -> dict:
        return {
            "apikey": self.supabase.api_key,
            "Authorization": f"Bearer {self.supabase.api_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

    def _post_rows(self, table: str, rows: List[dict], on_conflict: Optional[str]) -> None:
        if not rows:
            return

        if on_conflict:
            url = f"{self.supabase.base_url}/rest/v1/{table}?on_conflict={on_conflict}"
        else:
            url = f"{self.supabase.base_url}/rest/v1/{table}"
        resp = requests.post(url, headers=self._headers(), json=rows)

        if not resp.ok:
            raise RuntimeError(
                f"Failed to upload to {table}: {resp.status_code} {resp.text}"
            )

    def _fetch_remote_user_map(self) -> dict[str, int]:
        url = f"{self.supabase.base_url}/rest/v1/users?select=id,username"
        resp = requests.get(url, headers={k: v for k, v in self._headers().items() if k != "Content-Type"})
        if not resp.ok:
            return {}
        try:
            data = resp.json()
        except Exception:
            return {}
        mapping: dict[str, int] = {}
        for row in data:
            uname = row.get("username")
            rid = row.get("id")
            if isinstance(uname, str) and isinstance(rid, int):
                mapping[uname] = rid
        return mapping

    def _fetch_remote_product_map(self) -> dict[str, int]:
        url = f"{self.supabase.base_url}/rest/v1/products?select=id,sku"
        resp = requests.get(url, headers={k: v for k, v in self._headers().items() if k != "Content-Type"})
        if not resp.ok:
            return {}
        try:
            data = resp.json()
        except Exception:
            return {}
        mapping: dict[str, int] = {}
        for row in data:
            sku = row.get("sku")
            rid = row.get("id")
            if isinstance(sku, str) and isinstance(rid, int):
                mapping[sku] = rid
        return mapping

    def _fetch_remote_invoice_map(self) -> dict[str, int]:
        url = f"{self.supabase.base_url}/rest/v1/invoices?select=id,number"
        resp = requests.get(url, headers={k: v for k, v in self._headers().items() if k != "Content-Type"})
        if not resp.ok:
            return {}
        try:
            data = resp.json()
        except Exception:
            return {}
        mapping: dict[str, int] = {}
        for row in data:
            num = row.get("number")
            rid = row.get("id")
            if isinstance(num, str) and isinstance(rid, int):
                mapping[num] = rid
        return mapping

    def upload_expenses(self) -> None:
        """Upload expenses to cloud."""
        expenses = (
            self.session.query(models.Expense)
            .filter(models.Expense.synced.is_(False))
            .all()
        )
        if not expenses:
            print("No expenses to upload.")
            return

        payload = [
            {
                "title": e.title,
                "amount": e.amount,
                "category": e.category or "General",
                "notes": e.notes or "",
                "date": e.date.isoformat() if e.date else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "last_modified": e.last_modified.isoformat() if e.last_modified else None,
            }
            for e in expenses
        ]

        print(f"Uploading {len(payload)} expenses...")
        self._post_rows("expenses", payload, on_conflict=None)

        # Mark as synced
        for e in expenses:
            e.synced = True
        self.session.commit()
