import json
from typing import Optional

import customtkinter as ctk
import tkinter.ttk as ttk

from db.local_db import get_session
from db.models import InvoiceItem, Product


class ProductsFrame(ctk.CTkFrame):
    """Product management screen with custom fields and stock editor."""

    def __init__(self, master: ctk.CTk, app=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app

        self.configure(fg_color="transparent")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Outer container to mimic dark content area with inner card
        main = ctk.CTkFrame(self)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main.rowconfigure(1, weight=1)  # table row stretches
        main.columnconfigure(0, weight=1)

        # Shared Treeview style for white tables
        style = ttk.Style()
        style.configure(
            "Products.Treeview",
            background="white",
            foreground="black",
            fieldbackground="white",
            borderwidth=0,
        )
        style.configure(
            "Products.Treeview.Heading",
            font=("TkDefaultFont", 9, "bold"),
        )

        # ---- Header row: title + top buttons (Add / Search) ----
        header = ctk.CTkFrame(main)
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)
        header.columnconfigure(2, weight=0)
        header.columnconfigure(3, weight=0)

        title_label = ctk.CTkLabel(
            header,
            text="Product Management",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=16, pady=10, sticky="w")

        add_top_btn = ctk.CTkButton(
            header,
            text="Add Product",
            command=self._add_product,
        )
        add_top_btn.grid(row=0, column=1, padx=(0, 8), pady=10, sticky="e")

        search_btn = ctk.CTkButton(
            header,
            text="Search",
            command=self.load_products,  # reuse existing logic (no filtering)
            width=90,
        )
        search_btn.grid(row=0, column=2, padx=(0, 8), pady=10, sticky="e")

        search_entry = ctk.CTkEntry(
            header,
            placeholder_text="Search products...",
            width=220,
        )
        search_entry.grid(row=0, column=3, padx=(0, 12), pady=10, sticky="e")

        # ---- Table ----
        table_frame = ctk.CTkFrame(main)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.table = ttk.Treeview(
            table_frame,
            columns=("sku", "name", "category", "sale_price", "cost_price", "stock", "active"),
            show="headings",
            style="Products.Treeview",
        )
        for col, text, width, anchor in [
            ("sku", "SKU", 90, "w"),
            ("name", "Name", 190, "w"),
            ("category", "Category", 120, "w"),
            ("sale_price", "Sale Price", 90, "e"),
            ("cost_price", "Cost Price", 90, "e"),
            ("stock", "Stock", 80, "e"),
            ("active", "Active", 60, "center"),
        ]:
            self.table.heading(col, text=text)
            self.table.column(col, width=width, anchor=anchor)

        self.table.grid(row=0, column=0, sticky="nsew")

        # ---- Footer buttons (bottom dark bar) ----
        btn_frame = ctk.CTkFrame(main)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))
        btn_frame.columnconfigure(0, weight=0)
        btn_frame.columnconfigure(1, weight=0)
        btn_frame.columnconfigure(2, weight=0)
        btn_frame.columnconfigure(3, weight=0)
        btn_frame.columnconfigure(4, weight=1)
        btn_frame.columnconfigure(5, weight=0)

        edit_btn = ctk.CTkButton(
            btn_frame,
            text="Edit Selected",
            command=self._edit_product,
            width=120,
        )
        custom_btn = ctk.CTkButton(
            btn_frame,
            text="Custom Fields",
            command=self._edit_custom_fields,
        )
        toggle_btn = ctk.CTkButton(
            btn_frame,
            text="Disable",
            command=self._toggle_active,
        )
        stock_btn = ctk.CTkButton(
            btn_frame,
            text="Edit Stock",
            command=self._edit_stock,
        )
        refresh_btn = ctk.CTkButton(
            btn_frame,
            text="Refresh",
            command=self.load_products,
        )


        # Admin-only delete button
        self.delete_btn = ctk.CTkButton(
            btn_frame,
            text="Delete Product",
            command=self._delete_product,
            fg_color="#e53e3e",
            hover_color="#c53030",
            text_color="white",
            width=120,
        )

        # Inventory Actions Button (Water Loss / Processing)
        self.inv_actions_btn = ctk.CTkButton(
            btn_frame,
            text="Inv. Actions",
            command=self._inventory_actions,
            fg_color="#e0a800", # Orange/Yellow to stand out
            hover_color="#c69500",
            text_color="black", 
            width=100
        )
        
        # Layout bottom buttons
        edit_btn.grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")
        toggle_btn.grid(row=0, column=1, padx=6, pady=8, sticky="w")
        custom_btn.grid(row=0, column=2, padx=6, pady=8, sticky="w")
        stock_btn.grid(row=0, column=3, padx=6, pady=8, sticky="w")
        self.inv_actions_btn.grid(row=0, column=4, padx=6, pady=8, sticky="w")
        
        # Delete button is column 5 if visible
        # Refresh button pushed to right
        refresh_btn.grid(row=0, column=6, padx=(6, 12), pady=8, sticky="e")

        self.load_products()
        # Update delete button visibility when products are loaded
        self._update_delete_button_visibility()

    # ---------- Helpers ----------

    def _is_admin(self) -> bool:
        """Check if current user is admin."""
        if not self.app:
            return False
        current_user = getattr(self.app, "current_user", None)
        return bool(current_user and getattr(current_user, "is_admin", False))

    def _update_delete_button_visibility(self) -> None:
        """Show/hide delete button based on admin status."""
        if hasattr(self, "delete_btn"):
            if self._is_admin():
                self.delete_btn.grid(row=0, column=5, padx=6, pady=8, sticky="w")
            else:
                self.delete_btn.grid_remove()

    def _get_selected_id(self) -> Optional[int]:
        selection = self.table.selection()
        if not selection:
            return None
        return int(selection[0])

    def load_products(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)

        session = get_session()
        try:
            products = session.query(Product).order_by(Product.name).all()
        finally:
            session.close()

        for p in products:
            unit_type = getattr(p, "unit_type", "piece") or "piece"
            sale_base = getattr(p, "sale_price", None) or getattr(p, "base_unit_price", p.price) or p.price
            cost_base = getattr(p, "cost_price", None) or sale_base

            # Display prices based on unit type
            if unit_type == "g":
                sale_display = f"{sale_base / 1000.0:.2f}/g"
                cost_display = f"{cost_base / 1000.0:.2f}/g"
            elif unit_type == "kg":
                sale_display = f"{sale_base:.2f}/kg"
                cost_display = f"{cost_base:.2f}/kg"
            else:
                sale_display = f"{sale_base:.2f}/piece"
                cost_display = f"{cost_base:.2f}/piece"
            
            # Display stock with unit
            stock_display = f"{p.stock_qty:.2f}" if unit_type in ["kg", "g"] else f"{p.stock_qty:.0f}"
            
            self.table.insert(
                "",
                "end",
                iid=str(p.id),
                values=(
                    p.sku or "",
                    p.name,
                    p.category or "",
                    sale_display,
                    cost_display,
                    stock_display,
                    "Yes" if p.is_active else "No",
                ),
            )

    # ---------- CRUD dialogs ----------

    def _add_product(self) -> None:
        self._open_product_dialog()

    def _edit_product(self) -> None:
        product_id = self._get_selected_id()
        if product_id is None:
            return
        self._open_product_dialog(product_id)

    def _open_product_dialog(self, product_id: Optional[int] = None) -> None:
        session = get_session()
        try:
            product = session.query(Product).get(product_id) if product_id else None
        finally:
            session.close()

        win = ctk.CTkToplevel(self)
        win.title("Product" if product_id is None else "Edit Product")
        win.grab_set()

        row = 0
        # Name
        ctk.CTkLabel(win, text="Name *").grid(row=row, column=0, padx=10, pady=5, sticky="e")
        name_entry = ctk.CTkEntry(win, width=220)
        name_entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1

        # SKU
        ctk.CTkLabel(win, text="SKU").grid(row=row, column=0, padx=10, pady=5, sticky="e")
        sku_entry = ctk.CTkEntry(win, width=220)
        sku_entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1

        # Category
        ctk.CTkLabel(win, text="Category").grid(row=row, column=0, padx=10, pady=5, sticky="e")
        category_entry = ctk.CTkEntry(win, width=220)
        category_entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1

        # Unit Type
        ctk.CTkLabel(win, text="Unit Type *").grid(row=row, column=0, padx=10, pady=5, sticky="e")
        unit_type_combo = ctk.CTkComboBox(
            win, values=["piece", "kg", "g"], width=220, state="readonly"
        )
        unit_type_combo.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1

        # Sale Price
        ctk.CTkLabel(win, text="Sale Price *").grid(row=row, column=0, padx=10, pady=5, sticky="e")
        sale_price_entry = ctk.CTkEntry(win, width=220)
        sale_price_entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        price_info_label = ctk.CTkLabel(
            win, text="(Price per piece/kg/gram)", font=ctk.CTkFont(size=10), text_color="gray"
        )
        price_info_label.grid(row=row, column=2, padx=5, pady=5, sticky="w")
        row += 1

        # Cost Price
        ctk.CTkLabel(win, text="Cost Price").grid(row=row, column=0, padx=10, pady=5, sticky="e")
        cost_price_entry = ctk.CTkEntry(win, width=220)
        cost_price_entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1

        # Legacy Price (for backward compatibility, hidden but still saved)
        price_entry = ctk.CTkEntry(win, width=220)
        price_entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        price_entry.grid_remove()  # Hide but keep for backward compatibility

        # Pre-fill if editing
        if product:
            name_entry.insert(0, product.name)
            sku_entry.insert(0, product.sku or "")
            category_entry.insert(0, product.category or "")
            unit_type = getattr(product, "unit_type", "piece") or "piece"
            sale_price = getattr(product, "sale_price", None) or getattr(product, "base_unit_price", product.price) or product.price
            cost_price = getattr(product, "cost_price", None) or sale_price
            unit_type_combo.set(unit_type)
            sale_price_entry.insert(0, str(sale_price))
            cost_price_entry.insert(0, str(cost_price))
            price_entry.insert(0, str(product.price))  # Keep for backward compatibility

        def update_price_info(*args) -> None:
            """Update price info label based on unit type."""
            unit = unit_type_combo.get()
            if unit == "piece":
                price_info_label.configure(text="(Price per piece)")
            elif unit == "kg":
                price_info_label.configure(text="(Price per kilogram)")
            elif unit == "g":
                price_info_label.configure(text="(Price per gram - will convert to kg internally)")

        unit_type_combo.configure(command=update_price_info)
        update_price_info()  # Initial update

        def save() -> None:
            name = name_entry.get().strip()
            sku = sku_entry.get().strip()
            category = category_entry.get().strip()
            unit_type = unit_type_combo.get()
            
            if not name:
                self._show_error("Product name is required!")
                return

            try:
                sale_price = float(sale_price_entry.get() or "0")
                if sale_price < 0:
                    raise ValueError("Price cannot be negative")
            except ValueError:
                self._show_error("Invalid sale price. Please enter a valid number.")
                return

            try:
                cost_price = float(cost_price_entry.get() or "0")
                if cost_price < 0:
                    raise ValueError("Cost price cannot be negative")
            except ValueError:
                self._show_error("Invalid cost price. Please enter a valid number.")
                return

            # If unit type is "g", convert to kg for internal storage
            # The base_unit_price will be stored as price per kg
            if unit_type == "g":
                # Convert per-gram inputs to per-kg for storage
                sale_price_kg = sale_price * 1000.0
                cost_price_kg = cost_price * 1000.0
            else:
                sale_price_kg = sale_price
                cost_price_kg = cost_price

            session_local = get_session()
            try:
                if product_id:
                    p = session_local.query(Product).get(product_id)
                    if not p:
                        return
                else:
                    p = Product()
                    session_local.add(p)

                p.name = name
                p.sku = sku or None
                p.category = category or None
                p.unit_type = unit_type
                p.base_unit_price = sale_price_kg if unit_type in ["kg", "g"] else sale_price
                p.sale_price = p.base_unit_price
                p.cost_price = cost_price_kg if unit_type in ["kg", "g"] else cost_price
                # Keep price for backward compatibility (use sale price)
                p.price = p.base_unit_price

                session_local.commit()
            except Exception as e:
                session_local.rollback()
                self._show_error(f"Error saving product: {str(e)}")
                return
            finally:
                session_local.close()

            self.load_products()
            win.destroy()

        save_btn = ctk.CTkButton(win, text="Save", command=save, width=100)
        save_btn.grid(row=row, column=0, columnspan=2, padx=10, pady=10)

    # ---------- Custom fields ----------

    def _edit_custom_fields(self) -> None:
        product_id = self._get_selected_id()
        if product_id is None:
            return

        session = get_session()
        try:
            product = session.query(Product).get(product_id)
        finally:
            session.close()

        if product is None:
            return

        win = ctk.CTkToplevel(self)
        win.title("Custom Fields")
        win.grab_set()

        info = ctk.CTkLabel(
            win,
            text="Enter JSON object with custom fields (e.g. {\"brand\": \"X\", \"size\": \"L\"})",
            wraplength=320,
            justify="left",
        )
        info.grid(row=0, column=0, padx=10, pady=(10, 5))

        text = ctk.CTkTextbox(win, width=320, height=160)
        text.grid(row=1, column=0, padx=10, pady=5)
        text.insert("1.0", json.dumps(product.extra_fields or {}, indent=2))

        error_label = ctk.CTkLabel(win, text="", text_color="red")
        error_label.grid(row=2, column=0, padx=10, pady=(5, 0), sticky="w")

        def save_fields() -> None:
            try:
                data = json.loads(text.get("1.0", "end").strip() or "{}")
                if not isinstance(data, dict):
                    raise ValueError("JSON must be an object")
            except Exception as exc:
                error_label.configure(text=str(exc))
                return

            session_local = get_session()
            try:
                p = session_local.query(Product).get(product_id)
                if not p:
                    return
                p.extra_fields = data
                session_local.commit()
            except Exception:
                session_local.rollback()
                raise
            finally:
                session_local.close()

            win.destroy()

        save_btn = ctk.CTkButton(
            win,
            text="Save",
            command=save_fields,
        )
        save_btn.grid(row=3, column=0, padx=10, pady=10)

    # ---------- Inventory Actions (Water Loss / Processing) ----------

    def _inventory_actions(self) -> None:
        product_id = self._get_selected_id()
        if product_id is None:
            self._show_error("Please select a product.")
            return
            
        from ui.inventory_actions import InventoryActionsDialog
        InventoryActionsDialog(self, product_id, self.load_products)

    # ---------- Enable / disable ----------

    def _toggle_active(self) -> None:
        product_id = self._get_selected_id()
        if product_id is None:
            return

        session = get_session()
        try:
            p = session.query(Product).get(product_id)
            if not p:
                return
            p.is_active = not p.is_active
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        self.load_products()

    # ---------- Stock editor ----------

    def _edit_stock(self) -> None:
        product_id = self._get_selected_id()
        if product_id is None:
            return

        session = get_session()
        try:
            product = session.query(Product).get(product_id)
        finally:
            session.close()

        if product is None:
            return

        win = ctk.CTkToplevel(self)
        win.title("Edit Stock")
        win.grab_set()

        label = ctk.CTkLabel(win, text=f"New stock for {product.name}:")
        label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        entry = ctk.CTkEntry(win)
        entry.insert(0, str(product.stock_qty))
        entry.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        error_label = ctk.CTkLabel(win, text="", text_color="red")
        error_label.grid(row=2, column=0, padx=10, pady=(5, 0), sticky="w")

        def save_stock() -> None:
            try:
                qty = float(entry.get() or "0")
            except ValueError:
                error_label.configure(text="Invalid number")
                return

            session_local = get_session()
            try:
                p = session_local.query(Product).get(product_id)
                if not p:
                    return
                p.stock_qty = qty
                session_local.commit()
            except Exception:
                session_local.rollback()
                raise
            finally:
                session_local.close()

            self.load_products()
            win.destroy()

        save_btn = ctk.CTkButton(
            win,
            text="Save",
            command=save_stock,
        )
        save_btn.grid(row=3, column=0, padx=10, pady=10)

    # ---------- Delete product (admin only) ----------

    def _delete_product(self) -> None:
        """Delete selected product (admin only)."""
        if not self._is_admin():
            self._show_error("Only administrators can delete products.")
            return

        product_id = self._get_selected_id()
        if product_id is None:
            self._show_error("Please select a product to delete.")
            return

        session = get_session()
        try:
            product = session.query(Product).get(product_id)
            if not product:
                self._show_error("Product not found.")
                return

            # Check if product is used in any invoices
            invoice_count = session.query(InvoiceItem).filter(
                InvoiceItem.product_id == product_id
            ).count()

            if invoice_count > 0:
                self._show_error(
                    f"Cannot delete product '{product.name}'. "
                    f"It is used in {invoice_count} invoice(s). "
                    f"Disable it instead."
                )
                return

            # Confirmation dialog
            confirm_win = ctk.CTkToplevel(self)
            confirm_win.title("Confirm Delete")
            confirm_win.grab_set()

            msg = ctk.CTkLabel(
                confirm_win,
                text=f"Are you sure you want to delete '{product.name}'?\n\nThis action cannot be undone.",
            )
            msg.pack(padx=20, pady=(20, 10))

            def confirm_delete() -> None:
                session_local = get_session()
                try:
                    p = session_local.query(Product).get(product_id)
                    if p:
                        session_local.delete(p)
                        session_local.commit()
                    session_local.close()
                except Exception:
                    session_local.rollback()
                    session_local.close()
                    self._show_error("Failed to delete product.")
                    return

                self.load_products()
                confirm_win.destroy()

            def cancel() -> None:
                confirm_win.destroy()

            btn_frame = ctk.CTkFrame(confirm_win)
            btn_frame.pack(padx=20, pady=(10, 20))

            cancel_btn = ctk.CTkButton(
                btn_frame,
                text="Cancel",
                command=cancel,
                width=100,
            )
            cancel_btn.pack(side="left", padx=(0, 10))

            delete_btn = ctk.CTkButton(
                btn_frame,
                text="Delete",
                command=confirm_delete,
                fg_color="#e53e3e",
                hover_color="#c53030",
                text_color="white",
                width=100,
            )
            delete_btn.pack(side="left")

        finally:
            session.close()

    def _show_error(self, message: str) -> None:
        """Show error message in a popup."""
        win = ctk.CTkToplevel(self)
        win.title("Error")
        win.grab_set()

        msg = ctk.CTkLabel(win, text=message, text_color="red")
        msg.pack(padx=20, pady=(20, 10))

        ok_btn = ctk.CTkButton(win, text="OK", command=win.destroy, width=100)
        ok_btn.pack(padx=20, pady=(10, 20))

