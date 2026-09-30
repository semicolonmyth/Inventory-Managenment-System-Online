import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import requests
import webbrowser

import customtkinter as ctk
import tkinter.ttk as ttk

from db.local_db import get_session
from db.models import Invoice, InvoiceItem, Product, StockTransaction, Setting
from utils.config import load_config
from utils.invoice import generate_invoice_pdf
from utils.theme_utils import get_theme_color, get_theme_button_color
from utils.units import (
    grams_to_kg,
    format_quantity,
    normalize_to_kg,
    calculate_price,
)


class NewSaleFrame(ctk.CTkFrame):
    """Modern billing screen with enhanced features."""

    def __init__(self, master: ctk.CTk, app=None, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self.app = app
        self.lines: List[dict] = []
        self.discount_percent: float = 0.0
        self.discount_fixed: float = 0.0
        self.tax_percent: float = 0.0
        self.customer: dict = {}
        self.current_invoice_number: Optional[str] = None
        self.bill_generated: bool = False  # Track if bill was successfully generated
        self._is_updating: bool = False  # Flag to prevent recursive updates

        self.configure(fg_color="transparent")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Main layout: Left (Products) + Right (Cart & Totals)
        layout = ctk.CTkFrame(self, fg_color="transparent")
        layout.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        layout.columnconfigure(0, weight=1)
        layout.columnconfigure(1, weight=1)
        layout.rowconfigure(0, weight=1)

        # ========== LEFT PANEL: Product Search & Selection ==========
        left = ctk.CTkFrame(layout)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
        left.columnconfigure(1, weight=1)
        left.rowconfigure(2, weight=1)

        # Customer section
        customer_frame = ctk.CTkFrame(left)
        customer_frame.grid(
            row=0, column=0, columnspan=5, sticky="ew", padx=8, pady=(8, 4)
        )
        customer_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            customer_frame, text="Customer Name", font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=0, padx=(8, 5), pady=6, sticky="w")

        # Customer name entry with autocomplete
        customer_entry_frame = ctk.CTkFrame(customer_frame, fg_color="transparent")
        customer_entry_frame.grid(row=0, column=1, padx=(0, 8), pady=6, sticky="ew")
        customer_entry_frame.columnconfigure(0, weight=1)

        self.customer_name_entry = ctk.CTkEntry(
            customer_entry_frame, placeholder_text="Type customer name...", width=200
        )
        self.customer_name_entry.grid(row=0, column=0, sticky="ew")
        self.customer_name_entry.bind("<KeyRelease>", self._on_customer_name_change)
        self.customer_name_entry.bind("<FocusOut>", self._on_customer_entry_focus_out)
        self.customer_name_entry.bind("<FocusIn>", self._on_customer_entry_focus_in)

        # Autocomplete dropdown frame (initially hidden)
        self.customer_dropdown = None
        self.customer_suggestions = []
        self.selected_customer_index = -1

        add_customer_btn = ctk.CTkButton(
            customer_frame,
            text="Add Customer",
            command=self._open_customer_dialog,
            width=120,
        )
        add_customer_btn.grid(row=0, column=2, padx=(0, 8), pady=6)

        # Product search section
        search_frame = ctk.CTkFrame(left)
        search_frame.grid(row=1, column=0, columnspan=5, sticky="ew", padx=8, pady=4)
        search_frame.columnconfigure(1, weight=1)

        # Row 0: Product Search (Full width)
        ctk.CTkLabel(search_frame, text="Search Product").grid(
            row=0, column=0, padx=(8, 5), pady=6, sticky="w"
        )
        self.search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="Type product name or SKU..."
        )
        self.search_entry.grid(
            row=0, column=1, columnspan=3, padx=(0, 8), pady=6, sticky="ew"
        )
        self.search_entry.bind("<KeyRelease>", self._on_search_change)
        self.search_entry.bind("<Return>", lambda e: self.add_current_line())

        # Row 1: Quantity and Total Price side-by-side
        # Quantity
        self.qty_label = ctk.CTkLabel(search_frame, text="Qty")
        self.qty_label.grid(row=1, column=0, padx=(8, 5), pady=6, sticky="w")
        self.qty_entry = ctk.CTkEntry(search_frame, width=100, placeholder_text="0.000")
        self.qty_entry.grid(row=1, column=1, padx=(0, 5), pady=6, sticky="w")
        self.qty_entry.bind("<KeyRelease>", self._on_qty_change)
        self.qty_entry.bind("<Return>", lambda e: self.add_current_line())
        
        self.selected_product_unit_type = "piece"
        self.selected_product_sale_price = 0.0
        self.selected_product_cost_price = 0.0

        # Total Price
        self.total_price_label = ctk.CTkLabel(search_frame, text="Total Price")
        self.total_price_label.grid(row=1, column=2, padx=(5, 5), pady=6, sticky="w")
        self.total_price_entry = ctk.CTkEntry(search_frame, width=100, placeholder_text="0.00")
        self.total_price_entry.grid(row=1, column=3, padx=(0, 8), pady=6, sticky="w")
        self.total_price_entry.bind("<KeyRelease>", self._on_total_price_change)
        self.total_price_entry.bind("<Return>", lambda e: self.add_current_line())

        # Row 2: Custom Price and Profit Display
        # Custom Price
        self.custom_price_label = ctk.CTkLabel(search_frame, text="Custom Price")
        self.custom_price_label.grid(row=2, column=0, padx=(8, 5), pady=6, sticky="w")
        self.custom_price_entry = ctk.CTkEntry(search_frame, width=100, placeholder_text="0.00")
        self.custom_price_entry.grid(row=2, column=1, padx=(0, 5), pady=6, sticky="w")
        self.custom_price_entry.bind("<KeyRelease>", self._on_custom_price_change)

        # Profit Display
        self.profit_label = ctk.CTkLabel(search_frame, text="Profit/Unit")
        self.profit_label.grid(row=2, column=2, padx=(5, 5), pady=6, sticky="w")
        self.profit_display = ctk.CTkLabel(
            search_frame, text="0.00", text_color="green"
        )
        self.profit_display.grid(row=2, column=3, padx=(0, 8), pady=6, sticky="w")

        # Row 3: Add to Cart Button (Full Width of inputs)
        add_btn = ctk.CTkButton(
            search_frame, text="Add to Cart", command=self.add_current_line, width=120
        )
        add_btn.grid(row=3, column=1, columnspan=3, padx=(0, 8), pady=(10, 6), sticky="e")

        # Product results table
        style = ttk.Style()
        style.configure(
            "NewSale.Treeview",
            background="white",
            foreground="black",
            fieldbackground="white",
            borderwidth=0,
        )
        style.configure("NewSale.Treeview.Heading", font=("TkDefaultFont", 9, "bold"))
        # Get theme primary color for selection
        primary_color = get_theme_color("primary")
        style.map(
            "NewSale.Treeview",
            background=[("selected", primary_color)],
            foreground=[("selected", "white")],
        )

        self.search_results = ttk.Treeview(
            left,
            columns=("name", "price", "stock", "status"),
            show="headings",
            height=12,
            style="NewSale.Treeview",
        )
        self.search_results.heading("name", text="Product Name")
        self.search_results.heading("price", text="Price")
        self.search_results.heading("stock", text="Stock")
        self.search_results.heading("status", text="Status")
        self.search_results.column("name", width=200)
        self.search_results.column("price", width=80, anchor="e")
        self.search_results.column("stock", width=70, anchor="e")
        self.search_results.column("status", width=80, anchor="center")
        self.search_results.grid(
            row=2, column=0, columnspan=5, sticky="nsew", padx=8, pady=(4, 8)
        )
        self.search_results.bind("<<TreeviewSelect>>", self._on_product_selected)
        self.search_results.bind("<Double-1>", lambda e: self.add_current_line())

        # ========== RIGHT PANEL: Cart & Totals ==========
        right = ctk.CTkFrame(layout)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        # Cart title
        cart_title = ctk.CTkLabel(
            right, text="Shopping Cart", font=ctk.CTkFont(size=16, weight="bold")
        )
        cart_title.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="w")

        # Cart table with scrollbar
        cart_table_frame = ctk.CTkFrame(right)
        cart_table_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        cart_table_frame.rowconfigure(0, weight=1)
        cart_table_frame.columnconfigure(0, weight=1)

        self.lines_table = ttk.Treeview(
            cart_table_frame,
            columns=("name", "qty", "price", "total", "profit", "delete"),
            show="headings",
            style="NewSale.Treeview",
        )
        self.lines_table.heading("name", text="Item")
        self.lines_table.heading("qty", text="Qty")
        self.lines_table.heading("price", text="Price/Unit")
        self.lines_table.heading("total", text="Total")
        self.lines_table.heading("profit", text="Profit/Loss")
        self.lines_table.heading("delete", text="Delete")
        self.lines_table.column("name", width=150)
        self.lines_table.column("qty", width=60, anchor="e")
        self.lines_table.column("price", width=80, anchor="e")
        self.lines_table.column("total", width=80, anchor="e")
        self.lines_table.column("profit", width=90, anchor="e")
        self.lines_table.column("delete", width=60, anchor="center")
        self.lines_table.grid(row=0, column=0, sticky="nsew")
        self.lines_table.bind("<Double-1>", self._edit_cart_item)
        self.lines_table.bind("<Button-1>", self._on_cart_click)

        # Configure profit column colors for loss display
        self.lines_table.tag_configure("profit_loss", foreground="red")
        self.lines_table.tag_configure("profit_gain", foreground="green")

        scrollbar = ttk.Scrollbar(
            cart_table_frame, orient="vertical", command=self.lines_table.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.lines_table.configure(yscrollcommand=scrollbar.set)

        # Totals section
        totals_frame = ctk.CTkFrame(right)
        totals_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        totals_frame.columnconfigure(1, weight=1)

        # Subtotal
        ctk.CTkLabel(totals_frame, text="Subtotal:").grid(
            row=0, column=0, padx=8, pady=4, sticky="w"
        )
        self.subtotal_label = ctk.CTkLabel(totals_frame, text="0.00", anchor="e")
        self.subtotal_label.grid(row=0, column=1, padx=8, pady=4, sticky="e")

        # Discount section
        discount_frame = ctk.CTkFrame(totals_frame, fg_color="transparent")
        discount_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        discount_frame.columnconfigure(1, weight=1)
        discount_frame.columnconfigure(3, weight=1)

        ctk.CTkLabel(discount_frame, text="Discount:").grid(
            row=0, column=0, padx=(0, 5), sticky="w"
        )
        self.discount_type_combo = ctk.CTkComboBox(
            discount_frame,
            values=["Percentage", "Fixed"],
            width=100,
            command=self._on_discount_type_change,
        )
        self.discount_type_combo.set("Percentage")
        self.discount_type_combo.grid(row=0, column=1, padx=(0, 5), sticky="w")

        self.discount_entry = ctk.CTkEntry(discount_frame, width=100)
        self.discount_entry.insert(0, "0")
        self.discount_entry.grid(row=0, column=2, padx=(0, 5), sticky="w")
        self.discount_entry.bind("<KeyRelease>", lambda e: self._refresh_totals())

        self.discount_label = ctk.CTkLabel(discount_frame, text="0.00", anchor="e")
        self.discount_label.grid(row=0, column=3, padx=(0, 0), sticky="e")

        # Tax section
        tax_frame = ctk.CTkFrame(totals_frame, fg_color="transparent")
        tax_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        tax_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(tax_frame, text="Tax (GST/VAT %):").grid(
            row=0, column=0, padx=(0, 5), sticky="w"
        )
        self.tax_entry = ctk.CTkEntry(tax_frame, width=100)
        self.tax_entry.insert(0, "0")
        self.tax_entry.grid(row=0, column=1, padx=(0, 5), sticky="w")
        self.tax_entry.bind("<KeyRelease>", lambda e: self._refresh_totals())

        self.tax_label = ctk.CTkLabel(tax_frame, text="0.00", anchor="e")
        self.tax_label.grid(row=0, column=2, padx=(0, 0), sticky="e")

        # Net Total
        total_sep = ctk.CTkFrame(totals_frame, height=2, fg_color="gray50")
        total_sep.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=4)

        ctk.CTkLabel(
            totals_frame, text="Net Total:", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=4, column=0, padx=8, pady=8, sticky="w")
        self.total_label = ctk.CTkLabel(
            totals_frame,
            text="0.00",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="e",
        )
        self.total_label.grid(row=4, column=1, padx=8, pady=8, sticky="e")

        # Action buttons
        buttons_frame = ctk.CTkFrame(right)
        buttons_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)

        clear_btn = ctk.CTkButton(
            buttons_frame,
            text="Clear Cart",
            command=self._clear_cart,
            width=120,
            fg_color="gray50",
        )
        clear_btn.grid(row=0, column=0, padx=4, pady=4)

        primary_color = get_theme_color("primary")
        generate_btn = ctk.CTkButton(
            buttons_frame,
            text="Generate Bill",
            command=self._generate_bill,
            width=120,
            fg_color=primary_color,
        )
        generate_btn.grid(row=0, column=1, padx=4, pady=4)

        # Keyboard shortcuts - bind to the frame
        # Note: These work when the frame or its children have focus
        self.bind("<Control-b>", lambda e: self._generate_bill())
        self.bind("<Control-c>", lambda e: self._clear_cart())
        self.bind("<Control-a>", lambda e: self._open_customer_dialog())
        self.bind("<Control-p>", lambda e: self._print_bill())

        # Bind to key input widgets for better accessibility
        def bind_shortcuts(widget):
            widget.bind("<Control-b>", lambda e: self._generate_bill())
            widget.bind("<Control-c>", lambda e: self._clear_cart())
            widget.bind("<Control-a>", lambda e: self._open_customer_dialog())
            widget.bind("<Control-p>", lambda e: self._print_bill())

        for widget in [
            self.search_entry,
            self.customer_name_entry,
            self.qty_entry,
            self.discount_entry,
            self.tax_entry,
        ]:
            bind_shortcuts(widget)

        # Initialize
        self._on_search_change()
        self._refresh_totals()

    # ========== Customer Management ==========

    def _on_customer_name_change(self, event=None) -> None:
        """Update customer dict when name changes and show autocomplete suggestions."""
        name = self.customer_name_entry.get().strip()

        # Update customer dict
        if name and not self.customer.get("uid"):
            # Auto-generate UID if not set
            self.customer["uid"] = self._generate_customer_uid()
            self.customer["name"] = name

        # Show autocomplete suggestions
        if len(name) >= 1:  # Show suggestions after 1 character
            self._show_customer_suggestions(name)
        else:
            self._hide_customer_dropdown()

    def _on_customer_entry_focus_in(self, event=None) -> None:
        """Show suggestions when entry gets focus."""
        name = self.customer_name_entry.get().strip()
        if len(name) >= 1:
            self._show_customer_suggestions(name)

    def _on_customer_entry_focus_out(self, event=None) -> None:
        """Hide dropdown when entry loses focus (with small delay to allow clicks)."""
        self.after(200, self._hide_customer_dropdown)

    def _show_customer_suggestions(self, search_term: str) -> None:
        """Query database for matching customer names and show dropdown."""
        session = get_session()
        try:
            # Query distinct customer names from invoices
            # Use group_by for SQLite compatibility
            customers = (
                session.query(Invoice.customer_name, Invoice.customer_uid)
                .filter(Invoice.customer_name.isnot(None))
                .filter(Invoice.customer_name.ilike(f"%{search_term}%"))
                .group_by(Invoice.customer_name)
                .order_by(Invoice.customer_name)
                .limit(10)
                .all()
            )

            # Get unique customer names with their UIDs
            customer_dict = {}
            for cust in customers:
                name = cust.customer_name
                uid = cust.customer_uid
                if name and name not in customer_dict:
                    customer_dict[name] = uid or ""

            self.customer_suggestions = list(customer_dict.items())
        except Exception:
            self.customer_suggestions = []
        finally:
            session.close()

        # Show dropdown if we have suggestions
        if self.customer_suggestions:
            self._create_customer_dropdown()
        else:
            self._hide_customer_dropdown()

    def _create_customer_dropdown(self) -> None:
        """Create or update the customer autocomplete dropdown."""
        # Destroy existing dropdown if any
        if self.customer_dropdown:
            self.customer_dropdown.destroy()

        # Get entry position and dimensions
        entry = self.customer_name_entry
        self.update_idletasks()  # Update all pending geometry changes
        entry.update_idletasks()

        # Get absolute position of entry relative to screen
        entry_x = entry.winfo_rootx()
        entry_y = entry.winfo_rooty()
        entry_width = entry.winfo_width()
        entry_height = entry.winfo_height()

        # Ensure we have valid dimensions
        if entry_width < 1:
            entry_width = 300  # Default width
        if entry_height < 1:
            entry_height = 30  # Default height

        # Calculate height based on number of suggestions (max 5 visible)
        num_suggestions = len(self.customer_suggestions)
        item_height = 35
        max_height = min(
            num_suggestions * item_height, 5 * item_height
        )  # Max 5 items visible

        # Create a Toplevel window for dropdown (won't affect main layout)
        self.customer_dropdown = ctk.CTkToplevel(self)
        self.customer_dropdown.overrideredirect(True)  # Remove window decorations
        self.customer_dropdown.attributes("-topmost", True)  # Keep on top

        # Position dropdown directly below entry, aligned to left edge
        dropdown_x = entry_x
        dropdown_y = entry_y + entry_height + 2

        # Set window size and position - ensure width matches entry exactly
        self.customer_dropdown.geometry(
            f"{entry_width}x{max_height}+{dropdown_x}+{dropdown_y}"
        )

        # Create main frame inside toplevel - no padding to ensure perfect alignment
        dropdown_frame = ctk.CTkFrame(
            self.customer_dropdown,
            corner_radius=6,
            border_width=1,
            border_color="gray50",
            fg_color=self.customer_dropdown.cget("fg_color"),
        )
        dropdown_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Create scrollable frame for suggestions if needed
        if num_suggestions > 5:
            container = ctk.CTkScrollableFrame(
                dropdown_frame, fg_color="transparent", height=max_height - 4
            )
            container.pack(fill="both", expand=True, padx=2, pady=2)
        else:
            container = dropdown_frame

        for idx, (name, uid) in enumerate(self.customer_suggestions):
            suggestion_frame = ctk.CTkFrame(
                container, fg_color="transparent", height=32
            )
            suggestion_frame.pack(fill="x", padx=2, pady=1)

            # Make it clickable
            suggestion_frame.bind(
                "<Button-1>", lambda e, n=name, u=uid: self._select_customer(n, u)
            )

            label = ctk.CTkLabel(
                suggestion_frame, text=name, anchor="w", font=ctk.CTkFont(size=12)
            )
            label.pack(fill="x", padx=8, pady=4)
            label.bind(
                "<Button-1>", lambda e, n=name, u=uid: self._select_customer(n, u)
            )

            # Hover effect
            def on_enter(frame=suggestion_frame):
                frame.configure(fg_color="gray30")

            def on_leave(frame=suggestion_frame):
                frame.configure(fg_color="transparent")

            suggestion_frame.bind("<Enter>", lambda e: on_enter())
            suggestion_frame.bind("<Leave>", lambda e: on_leave())
            label.bind("<Enter>", lambda e: on_enter())
            label.bind("<Leave>", lambda e: on_leave())

    def _select_customer(self, name: str, uid: str) -> None:
        """Select a customer from suggestions."""
        self.customer_name_entry.delete(0, "end")
        self.customer_name_entry.insert(0, name)

        # Update customer dict - use existing UID if available, otherwise generate new
        if not uid:
            uid = self._generate_customer_uid()

        self.customer = {
            "name": name,
            "uid": uid,
            "phone": "",
            "email": "",
            "address": "",
        }

        # Try to load customer details from most recent invoice
        session = get_session()
        try:
            recent_invoice = (
                session.query(Invoice)
                .filter(Invoice.customer_name == name)
                .order_by(Invoice.created_at.desc())
                .first()
            )
            if recent_invoice and recent_invoice.customer_uid:
                # Use the UID from the invoice
                self.customer["uid"] = recent_invoice.customer_uid
        finally:
            session.close()

        self._hide_customer_dropdown()
        self._show_toast(f"Customer '{name}' selected")

    def _hide_customer_dropdown(self) -> None:
        """Hide the customer autocomplete dropdown."""
        if self.customer_dropdown:
            self.customer_dropdown.destroy()
            self.customer_dropdown = None

    def _generate_customer_uid(self) -> str:
        """Generate unique customer UID."""
        return f"CUST-{uuid.uuid4().hex[:8].upper()}"

    def _open_customer_dialog(self) -> None:
        """Open customer creation dialog."""
        win = ctk.CTkToplevel(self)
        win.title("Add Customer")
        win.grab_set()
        win.geometry("400x250")

        labels = ["Name *", "Phone", "Email", "Address"]
        entries = []
        for i, label in enumerate(labels):
            lbl = ctk.CTkLabel(
                win,
                text=label,
                font=ctk.CTkFont(weight="bold" if "*" in label else "normal"),
            )
            lbl.grid(row=i, column=0, padx=20, pady=10, sticky="e")
            entry = ctk.CTkEntry(win, width=250)
            entry.grid(row=i, column=1, padx=20, pady=10, sticky="w")
            entries.append(entry)

        # Pre-fill if customer name already entered
        if self.customer_name_entry.get().strip():
            entries[0].insert(0, self.customer_name_entry.get().strip())

        def save() -> None:
            name = entries[0].get().strip()
            if not name:
                self._show_error_popup("Customer name is required!")
                return

            self.customer = {
                "name": name,
                "phone": entries[1].get().strip(),
                "email": entries[2].get().strip(),
                "address": entries[3].get().strip(),
                "uid": self._generate_customer_uid(),
            }
            self.customer_name_entry.delete(0, "end")
            self.customer_name_entry.insert(0, name)
            self._show_toast(f"Customer '{name}' added successfully!")
            win.destroy()

        btn_frame = ctk.CTkFrame(win)
        btn_frame.grid(row=len(labels), column=0, columnspan=2, pady=20)

        save_btn = ctk.CTkButton(
            btn_frame, text="Save Customer", command=save, width=120
        )
        save_btn.pack(side="left", padx=10)

        cancel_btn = ctk.CTkButton(
            btn_frame, text="Cancel", command=win.destroy, width=120, fg_color="gray50"
        )
        cancel_btn.pack(side="left", padx=10)

    # ========== Product Search ==========

    def _on_search_change(self, event=None) -> None:
        """Update product search results."""
        text = self.search_entry.get().strip()
        session = get_session()
        try:
            q = session.query(Product).filter(Product.is_active == True)
            if text:
                like = f"%{text}%"
                q = q.filter(Product.name.ilike(like) | Product.sku.ilike(like))
            products = q.order_by(Product.name).limit(20).all()
        finally:
            session.close()

        # Clear existing results
        for row in self.search_results.get_children():
            self.search_results.delete(row)

        # Add products with stock status
        for p in products:
            stock = p.stock_qty or 0
            unit_type = getattr(p, "unit_type", "piece") or "piece"
            base_price = (
                getattr(p, "sale_price", None)
                or getattr(p, "base_unit_price", p.price)
                or p.price
            )

            # Format price display
            if unit_type == "g":
                price_display = f"{base_price / 1000.0:.2f}/g"
            elif unit_type == "kg":
                price_display = f"{base_price:.2f}/kg"
            else:
                price_display = f"{base_price:.2f}/piece"

            # Format stock display
            if unit_type in ["kg", "g"]:
                stock_display = f"{stock:.2f}"
            else:
                stock_display = f"{stock:.0f}"

            status = ""
            tags = []
            # For weight-based products, use different threshold
            threshold = 0.1 if unit_type in ["kg", "g"] else 5
            if stock < threshold:
                status = "⚠ Low Stock"
                tags = ("low_stock",)
            elif stock == 0:
                status = "❌ Out of Stock"
                tags = ("out_of_stock",)
            else:
                status = "✓ In Stock"
                tags = ("in_stock",)

            item_id = self.search_results.insert(
                "",
                "end",
                iid=str(p.id),
                values=(p.name, price_display, stock_display, status),
                tags=tags,
            )

            # Color code low stock items
            if stock < threshold:
                self.search_results.set(item_id, "status", f"⚠ Low ({stock_display})")

    def _on_product_selected(self, event=None) -> None:
        """Update labels and store product info when product is selected."""
        selection = self.search_results.selection()
        if not selection:
            return

        product_id = int(selection[0])
        session = get_session()
        try:
            product = session.query(Product).get(product_id)
            if product:
                unit_type = getattr(product, "unit_type", "piece") or "piece"
                self.selected_product_unit_type = unit_type

                # Get sale price (unit_sale_price) and cost price
                sale_price = (
                    getattr(product, "sale_price", None)
                    or getattr(product, "base_unit_price", product.price)
                    or product.price
                )
                cost_price = getattr(product, "cost_price", 0.0) or 0.0

                self.selected_product_sale_price = sale_price
                self.selected_product_cost_price = cost_price

                # Update quantity label based on unit type
                if unit_type == "piece":
                    self.qty_label.configure(text="Qty (pieces)")
                elif unit_type == "kg":
                    self.qty_label.configure(text="Qty (kg)")
                elif unit_type == "g":
                    self.qty_label.configure(text="Qty (grams)")

                # Reset quantity display (keep editable)
                self.qty_entry.delete(0, "end")

                # Reset total price entry
                self.total_price_entry.delete(0, "end")

                # Reset custom price to default sale price
                self.custom_price_entry.delete(0, "end")
                self.custom_price_entry.insert(0, f"{sale_price:.2f}")

                # Reset profit display
                self.profit_display.configure(text="0.00", text_color="green")
        finally:
            session.close()

        self.total_price_entry.focus_set()
        self.total_price_entry.select_range(0, "end")

    def _on_total_price_change(self, event=None) -> None:
        """Auto-calculate quantity from total price (FEATURE 1)."""
        if self._is_updating:
            return
            
        if (
            not self.selected_product_sale_price
            or self.selected_product_sale_price <= 0
        ):
            return

        try:
            total_price = float(self.total_price_entry.get() or "0")
        except ValueError:
            total_price = 0.0

        self._is_updating = True
        try:
            if total_price <= 0:
                self.qty_entry.delete(0, "end")
                self._update_profit_display()
                return

            # Calculate quantity: quantity = total_price / unit_sale_price
            # Use custom price if available, else standard sale price
            try:
                custom_price = float(self.custom_price_entry.get() or "0")
            except ValueError:
                custom_price = 0.0
                
            unit_sale_price = custom_price if custom_price > 0 else self.selected_product_sale_price
            unit_type = self.selected_product_unit_type

            # For grams, unit_sale_price is per kg, so we need to adjust
            if unit_type == "g":
                # If sale_price is per kg, convert to per gram
                price_per_gram = unit_sale_price / 1000.0
                quantity = total_price / price_per_gram if price_per_gram > 0 else 0
            else:
                quantity = total_price / unit_sale_price if unit_sale_price > 0 else 0

            # Update quantity display
            self.qty_entry.delete(0, "end")
            if unit_type == "piece":
                self.qty_entry.insert(0, f"{quantity:.2f}")
            else:
                self.qty_entry.insert(0, f"{quantity:.3f}")

            # Update profit display
            self._update_profit_display()
        finally:
            self._is_updating = False

    def _on_qty_change(self, event=None) -> None:
        """Auto-calculate total price from quantity (bidirectional calculation)."""
        if self._is_updating:
            return
            
        if (
            not self.selected_product_sale_price
            or self.selected_product_sale_price <= 0
        ):
            return

        try:
            quantity = float(self.qty_entry.get() or "0")
        except ValueError:
            quantity = 0.0

        self._is_updating = True
        try:
            if quantity <= 0:
                self.total_price_entry.delete(0, "end")
                self._update_profit_display()
                return

            # Calculate total price: total_price = quantity * unit_sale_price
            # Use custom price if available
            try:
                 custom_price = float(self.custom_price_entry.get() or "0")
            except ValueError:
                custom_price = 0.0
                
            unit_sale_price = custom_price if custom_price > 0 else self.selected_product_sale_price
            unit_type = self.selected_product_unit_type

            # For grams, unit_sale_price is per kg, so we need to adjust
            if unit_type == "g":
                # If sale_price is per kg and quantity is in grams
                price_per_gram = unit_sale_price / 1000.0
                total_price = quantity * price_per_gram
            else:
                total_price = quantity * unit_sale_price

            # Update total price display
            self.total_price_entry.delete(0, "end")
            self.total_price_entry.insert(0, f"{total_price:.2f}")

            # Update profit display
            self._update_profit_display()
        finally:
            self._is_updating = False

    def _on_custom_price_change(self, event=None) -> None:
        """Update profit display when custom price changes."""
        self._update_profit_display()

    def _calculate_profit(self) -> tuple[float, float]:
        """Calculate profit per unit and total profit.

        Returns:
            (profit_per_unit, total_profit)
        """
        try:
            custom_price = float(self.custom_price_entry.get() or "0")
        except ValueError:
            custom_price = self.selected_product_sale_price

        try:
            quantity = float(self.qty_entry.get() or "0")
        except ValueError:
            quantity = 0.0

        cost_price = self.selected_product_cost_price or 0.0

        # Profit per unit = custom_price - cost_price
        profit_per_unit = custom_price - cost_price

        # Total profit = profit_per_unit * quantity
        total_profit = profit_per_unit * quantity

        return profit_per_unit, total_profit

    def _update_profit_display(self) -> None:
        """Update the profit display label with color coding."""
        profit_per_unit, total_profit = self._calculate_profit()

        # Determine color based on profit
        if total_profit < 0:
            color = "red"  # Loss
        elif total_profit == 0:
            color = "orange"  # Break even
        else:
            color = "green"  # Profit

        # Display profit per unit and total profit
        display_text = f"{profit_per_unit:.2f} (Total: {total_profit:.2f})"
        self.profit_display.configure(text=display_text, text_color=color)

    # ========== Cart Management ==========

    def add_current_line(self) -> None:
        """Add selected product to cart using total price (FEATURE 1 & 2)."""
        selected = self.search_results.selection()
        if not selected:
            self._show_error_popup("Please select a product from the list.")
            return

        product_id = int(selected[0])

        session = get_session()
        try:
            product = session.query(Product).get(product_id)
        finally:
            session.close()

        if product is None:
            return

        # Get product unit type and prices
        unit_type = getattr(product, "unit_type", "piece") or "piece"
        default_sale_price = (
            getattr(product, "sale_price", None)
            or getattr(product, "base_unit_price", product.price)
            or product.price
        )
        cost_price = getattr(product, "cost_price", 0.0) or 0.0

        # Get quantity and total price - try qty first, then total price
        try:
            qty_input = float(self.qty_entry.get() or "0")
        except ValueError:
            qty_input = 0.0

        try:
            total_price_input = float(self.total_price_entry.get() or "0")
        except ValueError:
            total_price_input = 0.0

        # Get custom price for bargaining (or use default if not set)
        try:
            custom_price = float(self.custom_price_entry.get() or "0")
        except ValueError:
            custom_price = default_sale_price

        if custom_price <= 0:
            custom_price = default_sale_price

        # Determine which input to use and calculate the other
        if qty_input > 0 and total_price_input > 0:
            # Both provided - use qty as primary, ignore total price input
            quantity = qty_input
            total_price = quantity * custom_price
        elif qty_input > 0:
            # Only qty provided
            quantity = qty_input
            total_price = quantity * custom_price
        elif total_price_input > 0:
            # Only total price provided
            total_price = total_price_input
            quantity = total_price / custom_price if custom_price > 0 else 0
        else:
            self._show_error_popup("Please enter either Qty or Total Price.")
            return

        if quantity <= 0 or total_price <= 0:
            self._show_error_popup("Qty and Total Price must be greater than 0.")
            return

        # Calculate quantity in base unit for stock checking
        if unit_type == "g":
            qty_for_stock = grams_to_kg(quantity)
        elif unit_type == "kg":
            qty_for_stock = quantity
        else:  # piece
            qty_for_stock = quantity

        # Stock validation
        current_stock = product.stock_qty or 0
        if current_stock < qty_for_stock:
            stock_display = format_quantity(current_stock, unit_type)
            self._show_error_popup(
                f"Insufficient stock! Available: {stock_display}, Requested: {format_quantity(quantity, unit_type)}"
            )
            return

        # Low stock alert
        threshold = 0.1 if unit_type in ["kg", "g"] else 5
        if current_stock < threshold:
            stock_display = format_quantity(current_stock, unit_type)
            self._show_toast(f"⚠ Low Stock Alert: Only {stock_display} remaining!")

        # Calculate profit per unit and total profit
        profit_per_unit = custom_price - cost_price
        total_profit = profit_per_unit * quantity

        # Show warning if loss
        if total_profit < 0:
            loss_amount = abs(total_profit)
            confirm = self._show_yes_no_popup(
                "Loss Warning",
                f"You will make a loss of {loss_amount:.2f} on this transaction.\nDo you want to continue?",
            )
            if not confirm:
                return

        # Actual sale price per unit (using custom price for bargaining)
        actual_sale_price_per_unit = custom_price

        # Profit calculation: actual_sale_price_per_unit and cost_price should be in same unit (per kg for weight, per piece for pieces)
        profit_per_unit = actual_sale_price_per_unit - cost_price

        # Display prices (convert to per gram for display if needed)
        unit_price_display = (
            actual_sale_price_per_unit / 1000.0
            if unit_type == "g"
            else actual_sale_price_per_unit
        )

        # Check if product already in cart (merge with same product and unit type)
        existing_idx = None
        for idx, line in enumerate(self.lines):
            if line["product_id"] == product_id and line.get("unit_type") == unit_type:
                existing_idx = idx
                break

        if existing_idx is not None:
            # Update existing line - add quantities and prices
            old_qty = self.lines[existing_idx]["qty"]
            new_qty = old_qty + quantity
            new_total = self.lines[existing_idx]["total"] + total_price

            # Recalculate actual sale price per unit for merged line
            if unit_type == "g":
                new_actual_sale_price_per_gram = (
                    new_total / new_qty
                    if new_qty > 0
                    else (actual_sale_price_per_unit / 1000.0)
                )
                new_actual_sale_price = (
                    new_actual_sale_price_per_gram * 1000.0
                )  # Convert to per kg
            else:
                new_actual_sale_price = (
                    new_total / new_qty if new_qty > 0 else actual_sale_price_per_unit
                )
            new_profit_per_unit = new_actual_sale_price - cost_price

            new_qty_for_stock = (
                normalize_to_kg(new_qty, unit_type)
                if unit_type in ["kg", "g"]
                else new_qty
            )
            if current_stock < new_qty_for_stock:
                stock_display = format_quantity(current_stock, unit_type)
                self._show_error_popup(
                    f"Cannot add more. Available stock: {stock_display}"
                )
                return

            self.lines[existing_idx]["qty"] = new_qty
            self.lines[existing_idx]["total"] = new_total
            self.lines[existing_idx]["actual_sale_price"] = new_actual_sale_price
            self.lines[existing_idx]["profit"] = new_profit_per_unit

            # Update table
            item_id = list(self.lines_table.get_children())[existing_idx]
            qty_display = format_quantity(new_qty, unit_type)
            # Display profit per unit (convert to per gram for grams)
            profit_display_value = (
                new_profit_per_unit / 1000.0
                if unit_type == "g"
                else new_profit_per_unit
            )
            profit_display = f"{profit_display_value:.2f}"

            self.lines_table.item(
                item_id,
                values=(
                    self.lines[existing_idx]["name"],
                    qty_display,
                    f"{new_actual_sale_price / 1000.0 if unit_type == 'g' else new_actual_sale_price:.2f}",
                    f"{new_total:.2f}",
                    profit_display,
                    "❌",
                ),
                tags=("profit_loss",) if new_profit_per_unit < 0 else (),
            )
        else:
            # Add new line with profit tracking
            line = {
                "product_id": product.id,
                "name": product.name,
                "qty": quantity,
                "unit_type": unit_type,
                "unit_price": unit_price_display,
                "base_unit_price": default_sale_price,
                "cost_price": cost_price,
                "default_sale_price": default_sale_price,
                "actual_sale_price": actual_sale_price_per_unit,
                "profit": profit_per_unit,
                "total": total_price,
            }
            self.lines.append(line)

            qty_display = format_quantity(quantity, unit_type)
            # Display profit per unit (convert to per gram for grams)
            profit_display_value = (
                profit_per_unit / 1000.0 if unit_type == "g" else profit_per_unit
            )
            profit_display = f"{profit_display_value:.2f}"

            self.lines_table.insert(
                "",
                "end",
                values=(
                    line["name"],
                    qty_display,
                    f"{unit_price_display:.2f}",
                    f"{total_price:.2f}",
                    profit_display,
                    "❌",
                ),
                tags=("profit_loss",) if profit_per_unit < 0 else (),
            )

        # Deduct stock immediately (optimistic update)
        new_stock = current_stock - qty_for_stock
        session2 = get_session()
        try:
            p2 = session2.query(Product).get(product_id)
            if p2:
                p2.stock_qty = new_stock
                p2.synced = False  # Ensure cloud uploader picks up the change
                tx = StockTransaction(
                    product_id=p2.id,
                    change_qty=-qty_for_stock,
                    remaining_stock=new_stock,
                    reason="Billing - Sale",
                )
                session2.add(tx)
                session2.commit()

                # Update Supabase
                try:
                    self._update_supabase_product_stock(p2.sku, new_stock)
                except Exception:
                    pass  # Silent fail for cloud sync
        except Exception:
            session2.rollback()
            raise
        finally:
            session2.close()

        self._refresh_totals()
        self._on_search_change()  # Refresh product list

        # Reset inputs
        self.total_price_entry.delete(0, "end")
        self.qty_entry.configure(state="normal")
        self.qty_entry.delete(0, "end")
        # Keep it normal so user can type for next product
        self.qty_entry.configure(state="normal")
        self.search_entry.focus_set()

    def _edit_cart_item(self, event=None) -> None:
        """Edit cart item: quantity, total price, and sale price override (FEATURE 1 & 2)."""
        selection = self.lines_table.selection()
        if not selection:
            return

        item_id = selection[0]
        children = list(self.lines_table.get_children())
        idx = children.index(item_id)
        line = self.lines[idx]

        # Get unit type and prices
        unit_type = line.get("unit_type", "piece") or "piece"
        cost_price = line.get("cost_price", 0.0) or 0.0
        default_sale_price = line.get(
            "default_sale_price", line.get("base_unit_price", 0)
        ) or line.get("base_unit_price", 0)
        current_actual_sale_price = (
            line.get("actual_sale_price", default_sale_price) or default_sale_price
        )
        current_total = line.get("total", 0.0) or 0.0
        current_qty = line.get("qty", 0.0) or 0.0

        # Dialog to edit total price and sale price
        win = ctk.CTkToplevel(self)
        win.title("Edit Item - Bargaining")
        win.grab_set()
        win.geometry("400x320")

        ctk.CTkLabel(
            win,
            text=f"Product: {line['name']}",
            font=ctk.CTkFont(weight="bold", size=14),
        ).pack(pady=10)

        # Quantity Input (Editable)
        qty_frame = ctk.CTkFrame(win, fg_color="transparent")
        qty_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(
            qty_frame, text="Quantity:", font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=5)
        qty_entry = ctk.CTkEntry(qty_frame, width=150)
        if unit_type == "piece":
             qty_entry.insert(0, f"{current_qty:.2f}")
        else:
             qty_entry.insert(0, f"{current_qty:.3f}")
        qty_entry.pack(side="left", padx=5)

        # Total Price input
        total_price_frame = ctk.CTkFrame(win, fg_color="transparent")
        total_price_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(
            total_price_frame, text="Total Price:", font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=5)
        total_price_entry = ctk.CTkEntry(total_price_frame, width=150)
        total_price_entry.insert(0, f"{current_total:.2f}")
        total_price_entry.pack(side="left", padx=5)

        # Sale Price Override (FEATURE 2)
        sale_price_frame = ctk.CTkFrame(win, fg_color="transparent")
        sale_price_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(
            sale_price_frame, text="Sale Price/Unit:", font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=5)
        sale_price_entry = ctk.CTkEntry(sale_price_frame, width=150)
        sale_price_entry.insert(
            0,
            f"{current_actual_sale_price / 1000.0 if unit_type == 'g' else current_actual_sale_price:.2f}",
        )
        sale_price_entry.pack(side="left", padx=5)

        # Show default sale price for reference
        default_label = ctk.CTkLabel(
            win,
            text=f"Default: {default_sale_price / 1000.0 if unit_type == 'g' else default_sale_price:.2f} | Cost: {cost_price / 1000.0 if unit_type == 'g' else cost_price:.2f}",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        )
        default_label.pack(pady=5)

        # Profit/Loss display
        profit_frame = ctk.CTkFrame(win, fg_color="transparent")
        profit_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(
            profit_frame, text="Profit/Loss per unit:", font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=5)
        profit_label = ctk.CTkLabel(
            profit_frame, text="0.00", font=ctk.CTkFont(size=12, weight="bold")
        )
        profit_label.pack(side="left", padx=5)
        
        # State tracking to prevent recursion
        self._edit_updating = False

        def update_from_qty(event=None) -> None:
            if self._edit_updating: return
            self._edit_updating = True
            try:
                try:
                    qty = float(qty_entry.get() or "0")
                    sale_price = float(sale_price_entry.get() or "0")
                except ValueError:
                    return

                # Recalc Total Price = Qty * Sale Price
                if unit_type == "g":
                    # sale_price is per gram here
                    total = qty * sale_price
                else:
                    total = qty * sale_price
                
                total_price_entry.delete(0, "end")
                total_price_entry.insert(0, f"{total:.2f}")
                
                update_profit_display()
            finally:
                self._edit_updating = False

        def update_from_total(event=None) -> None:
            if self._edit_updating: return
            self._edit_updating = True
            try:
                try:
                    total = float(total_price_entry.get() or "0")
                    sale_price = float(sale_price_entry.get() or "0")
                except ValueError:
                    return

                if sale_price <= 0: return

                # Recalc Qty = Total / Sale Price
                if unit_type == "g":
                    qty = total / sale_price if sale_price > 0 else 0
                else:
                    qty = total / sale_price if sale_price > 0 else 0
                
                qty_entry.delete(0, "end")
                if unit_type == "piece":
                    qty_entry.insert(0, f"{qty:.2f}")
                else:
                    qty_entry.insert(0, f"{qty:.3f}")

                update_profit_display()
            finally:
                self._edit_updating = False

        def update_from_price(event=None) -> None:
             # Changing price preserves quantity, updates total
            if self._edit_updating: return
            self._edit_updating = True
            try:
                try:
                     qty = float(qty_entry.get() or "0")
                     sale_price = float(sale_price_entry.get() or "0")
                except ValueError:
                    return
                
                # Recalc Total = Qty * Sale Price
                if unit_type == "g":
                    total = qty * sale_price
                else:
                    total = qty * sale_price
                
                total_price_entry.delete(0, "end")
                total_price_entry.insert(0, f"{total:.2f}")
                
                update_profit_display()
            finally:
                self._edit_updating = False

        def update_profit_display() -> None:
             try:
                sale_price = float(sale_price_entry.get() or "0")
             except ValueError:
                return
             
             # Calculate profit (normalize to per kg for weight-based products)
             if unit_type == "g":
                actual_sale_price_per_unit = sale_price * 1000.0
             else:
                actual_sale_price_per_unit = sale_price

             profit_per_unit = actual_sale_price_per_unit - cost_price
             
             profit_display_value = profit_per_unit / 1000.0 if unit_type == "g" else profit_per_unit
             profit_label.configure(
                text=f"{profit_display_value:.2f}",
                text_color="red" if profit_per_unit < 0 else "green",
            )

        qty_entry.bind("<KeyRelease>", update_from_qty)
        total_price_entry.bind("<KeyRelease>", update_from_total)
        sale_price_entry.bind("<KeyRelease>", update_from_price)
        
        # Initial calc
        update_profit_display()

        def update_item() -> None:
            """Update cart item with new values."""
            try:
                new_qty = float(qty_entry.get() or "0")
                new_total_price = float(total_price_entry.get() or "0")
                new_sale_price = float(sale_price_entry.get() or "0")
            except ValueError:
                self._show_error_popup("Invalid values. Please enter valid numbers.")
                win.destroy()
                return

            if new_qty <= 0:
                 self._show_error_popup("Quantity must be greater than 0.")
                 return

            if new_total_price < 0 or new_sale_price < 0:
                self._show_error_popup(
                    "Prices cannot be negative."
                )
                return

            # Normalize sale price for storage
            if unit_type == "g":
                 actual_sale_price_per_unit = new_sale_price * 1000.0
            else:
                 actual_sale_price_per_unit = new_sale_price

            # Calculate profit
            profit_per_unit = actual_sale_price_per_unit - cost_price

            # Calculate quantity for stock checking
            old_qty_for_stock = (
                normalize_to_kg(line["qty"], unit_type)
                if unit_type in ["kg", "g"]
                else line["qty"]
            )
            new_qty_for_stock = (
                normalize_to_kg(new_qty, unit_type)
                if unit_type in ["kg", "g"]
                else new_qty
            )

            # Check stock
            session = get_session()
            try:
                product = session.query(Product).get(line["product_id"])
                current_stock = (
                    product.stock_qty or 0
                ) + old_qty_for_stock  # Add back old qty
                if current_stock < new_qty_for_stock:
                    stock_display = format_quantity(current_stock, unit_type)
                    self._show_error_popup(
                        f"Insufficient stock! Available: {stock_display}"
                    )
                    # Don't destroy window, let user correct it
                    return

                # Update stock
                diff = new_qty_for_stock - old_qty_for_stock
                product.stock_qty = current_stock - new_qty_for_stock
                product.synced = False  # Ensure cloud uploader picks up the change
                if abs(diff) > 0.0001:  # Use small epsilon for float comparison
                    tx = StockTransaction(
                        product_id=product.id,
                        change_qty=-diff,
                        remaining_stock=product.stock_qty,
                        reason="Billing - Price/Quantity Update",
                    )
                    session.add(tx)
                session.commit()

                # Update Supabase
                try:
                    self._update_supabase_product_stock(product.sku, product.stock_qty)
                except Exception:
                    pass
            finally:
                session.close()

            # Update cart line
            line["qty"] = new_qty
            line["total"] = new_total_price
            line["actual_sale_price"] = actual_sale_price_per_unit
            line["profit"] = profit_per_unit

            # Update table display
            qty_display = format_quantity(new_qty, unit_type)
            unit_price_display = new_sale_price
            # Display profit per unit (convert to per gram for grams)
            profit_display_value = (
                profit_per_unit / 1000.0 if unit_type == "g" else profit_per_unit
            )
            profit_display = f"{profit_display_value:.2f}"

            self.lines_table.item(
                item_id,
                values=(
                    line["name"],
                    qty_display,
                    f"{unit_price_display:.2f}",
                    f"{new_total_price:.2f}",
                    profit_display,
                    "❌",
                ),
                tags=("profit_loss",) if profit_per_unit < 0 else (),
            )
            self._refresh_totals()
            self._on_search_change()
            win.destroy()

        btn_frame = ctk.CTkFrame(win)
        btn_frame.pack(pady=15)

        ctk.CTkButton(btn_frame, text="Update", command=update_item, width=100).pack(
            side="left", padx=5
        )
        ctk.CTkButton(
            btn_frame, text="Cancel", command=win.destroy, width=100, fg_color="gray50"
        ).pack(side="left", padx=5)

        total_price_entry.bind("<Return>", lambda e: update_item())
        sale_price_entry.bind("<Return>", lambda e: update_item())
        qty_entry.bind("<Return>", lambda e: update_item())

    def _on_cart_click(self, event) -> None:
        """Handle clicks on cart table, especially delete column."""
        region = self.lines_table.identify_region(event.x, event.y)
        if region == "cell":
            column = self.lines_table.identify_column(event.x)
            if (
                column == "#6"
            ):  # Delete column (now column 6 after adding profit column)
                item_id = self.lines_table.identify_row(event.y)
                if item_id:
                    self._delete_cart_item(item_id)

    def _delete_cart_item(self, item_id: str) -> None:
        """Delete a single item from cart and restore its stock."""
        children = list(self.lines_table.get_children())
        if item_id not in children:
            return

        idx = children.index(item_id)
        if idx >= len(self.lines):
            return

        line = self.lines[idx]

        # Only restore stock if bill was NOT generated
        if not self.bill_generated:
            session = get_session()
            try:
                product = session.query(Product).get(line["product_id"])
                if product:
                    unit_type = line.get("unit_type", "piece") or "piece"
                    qty_to_restore = (
                        normalize_to_kg(line["qty"], unit_type)
                        if unit_type in ["kg", "g"]
                        else line["qty"]
                    )
                    product.stock_qty = (product.stock_qty or 0) + qty_to_restore
                    product.synced = False  # Ensure cloud uploader picks up the change
                    tx = StockTransaction(
                        product_id=product.id,
                        change_qty=qty_to_restore,
                        remaining_stock=product.stock_qty,
                        reason="Billing - Item Removed from Cart",
                    )
                    session.add(tx)
                session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()

        # Remove from cart
        self.lines.pop(idx)
        self.lines_table.delete(item_id)
        self._refresh_totals()
        self._on_search_change()
        self._show_toast(f"{line['name']} removed from cart.")

    def _clear_cart(self) -> None:
        """Clear entire cart and restore stock (only if bill was not generated)."""
        if not self.lines:
            return

        # Only restore stock if bill was NOT generated
        if not self.bill_generated:
            session = get_session()
            try:
                for line in self.lines:
                    product = session.query(Product).get(line["product_id"])
                    if product:
                        unit_type = line.get("unit_type", "piece") or "piece"
                        qty_to_restore = (
                            normalize_to_kg(line["qty"], unit_type)
                            if unit_type in ["kg", "g"]
                            else line["qty"]
                        )
                        product.stock_qty = (product.stock_qty or 0) + qty_to_restore
                        product.synced = False  # Ensure cloud uploader picks up the change
                        tx = StockTransaction(
                            product_id=product.id,
                            change_qty=qty_to_restore,
                            remaining_stock=product.stock_qty,
                            reason="Billing - Cart Cleared",
                        )
                        session.add(tx)
                session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()

        # Clear UI
        was_generated = self.bill_generated  # Store flag before reset
        self.lines.clear()
        for row in self.lines_table.get_children():
            self.lines_table.delete(row)
        self.search_entry.delete(0, "end")
        self.qty_entry.delete(0, "end")
        self.discount_entry.delete(0, "end")
        self.discount_entry.insert(0, "0")
        self.tax_entry.delete(0, "end")
        self.tax_entry.insert(0, "0")
        self.discount_type_combo.set("Percentage")
        self.bill_generated = False  # Reset flag
        self._refresh_totals()
        self._on_search_change()
        if not was_generated:
            self._show_toast("Cart cleared. Stock restored.")
        else:
            self._show_toast("Cart cleared.")

    # ========== Totals Calculation ==========

    def _on_discount_type_change(self, value: str) -> None:
        """Update discount entry placeholder based on type."""
        self._refresh_totals()

    def _refresh_totals(self) -> None:
        """Recalculate and update all totals."""
        subtotal = sum(l["total"] for l in self.lines)

        # Discount calculation
        discount_type = self.discount_type_combo.get()
        try:
            discount_value = float(self.discount_entry.get() or "0")
        except ValueError:
            discount_value = 0.0

        if discount_type == "Percentage":
            self.discount_percent = discount_value
            self.discount_fixed = 0.0
            discount_amount = subtotal * (self.discount_percent / 100.0)
        else:  # Fixed
            self.discount_percent = 0.0
            self.discount_fixed = discount_value
            discount_amount = min(
                self.discount_fixed, subtotal
            )  # Can't discount more than subtotal

        # Tax calculation
        try:
            self.tax_percent = float(self.tax_entry.get() or "0")
        except ValueError:
            self.tax_percent = 0.0

        # Calculate on amount after discount
        amount_after_discount = subtotal - discount_amount
        tax_amount = amount_after_discount * (self.tax_percent / 100.0)
        net_total = amount_after_discount + tax_amount

        # Update UI
        self.subtotal_label.configure(text=f"{subtotal:.2f}")
        self.discount_label.configure(text=f"-{discount_amount:.2f}")
        self.tax_label.configure(text=f"{tax_amount:.2f}")
        self.total_label.configure(text=f"{net_total:.2f}")

    # ========== Bill Generation ==========

    def _generate_bill(self) -> None:
        """Show payment dialog to initiate bill generation."""
        if not self.lines:
            self._show_error_popup("Cart is empty. Add items to generate a bill.")
            return

        customer_name = self.customer_name_entry.get().strip()
        if not customer_name:
            self._show_error_popup("Customer name is required!")
            return
            
        self._show_checkout_dialog(customer_name)

    def _show_checkout_dialog(self, customer_name: str) -> None:
        """Show dialog to select payment method and account."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Checkout")
        dialog.geometry("400x350")
        dialog.grab_set()

        # Title
        ctk.CTkLabel(dialog, text="Payment Details", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        # Payment Method
        self.payment_method_var = ctk.StringVar(value="Cash")
        
        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(frame, text="Payment Method:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        radio_frame = ctk.CTkFrame(frame, fg_color="transparent")
        radio_frame.pack(fill="x", pady=5)
        
        ctk.CTkRadioButton(radio_frame, text="Cash", variable=self.payment_method_var, value="Cash", command=self._toggle_account_dropdown).pack(side="left", padx=10)
        ctk.CTkRadioButton(radio_frame, text="Online", variable=self.payment_method_var, value="Online", command=self._toggle_account_dropdown).pack(side="left", padx=10)

        # Account Selection (Initially hidden or disabled)
        account_frame_outer = ctk.CTkFrame(dialog, fg_color="transparent")
        account_frame_outer.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(account_frame_outer, text="Select Account:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        account_inner = ctk.CTkFrame(account_frame_outer, fg_color="transparent")
        account_inner.pack(fill="x", pady=5)

        self.account_var = ctk.StringVar()
        accounts = self._load_payment_accounts()
        self.account_combo = ctk.CTkComboBox(account_inner, values=accounts, variable=self.account_var)
        self.account_combo.pack(side="left", fill="x", expand=True)
        
        # Add Account Button
        self.add_account_btn = ctk.CTkButton(account_inner, text="+", width=30, command=lambda: self._add_new_account_popup(dialog, self._update_accounts_list))
        self.add_account_btn.pack(side="right", padx=5)

        # Initial state
        self._toggle_account_dropdown()

        # Confirm Button
        ctk.CTkButton(dialog, text="Confirm & Print", command=lambda: self._on_checkout_confirm(dialog)).pack(pady=20, fill="x", padx=20)

    def _toggle_account_dropdown(self) -> None:
        """Enable/Disable account selection based on payment method."""
        is_online = self.payment_method_var.get() == "Online"
        state = "normal" if is_online else "disabled"
        
        if hasattr(self, "account_combo"):
             self.account_combo.configure(state=state)
        if hasattr(self, "add_account_btn"):
             self.add_account_btn.configure(state=state)

    def _update_accounts_list(self, accounts: List[str]) -> None:
        self.account_combo.configure(values=accounts)
        if accounts:
             self.account_combo.set(accounts[-1])

    def _on_checkout_confirm(self, dialog) -> None:
        method = self.payment_method_var.get()
        account = self.account_var.get()
        
        if method == "Online" and not account:
            self._show_error_popup("Please select an account for Online payment.")
            return

        dialog.destroy()
        self._finalize_bill(method, account if method == "Online" else None)


    def _finalize_bill(self, payment_method: str, payment_account: Optional[str]) -> None:
        """Generate and save bill after payment selection."""
        # Validate again just in case
        if not self.lines:
            return

        customer_name = self.customer_name_entry.get().strip()
        if not customer_name:
            self._show_error_popup("Customer name is required!")
            return

        # Generate invoice number
        invoice_number = self._next_invoice_number()
        self.current_invoice_number = invoice_number

        # Ensure customer UID exists
        if not self.customer.get("uid"):
            self.customer["uid"] = self._generate_customer_uid()
        self.customer["name"] = customer_name

        # Calculate totals
        subtotal = sum(l["total"] for l in self.lines)
        discount_type = self.discount_type_combo.get()
        try:
            discount_value = float(self.discount_entry.get() or "0")
        except ValueError:
            discount_value = 0.0

        if discount_type == "Percentage":
            discount_amount = subtotal * (discount_value / 100.0)
        else:
            discount_amount = min(discount_value, subtotal)

        amount_after_discount = subtotal - discount_amount
        tax_amount = amount_after_discount * (self.tax_percent / 100.0)
        net_total = amount_after_discount + tax_amount

        # Save to database
        self.current_payment_method = payment_method
        self.current_payment_account = payment_account
        
        session = get_session()
        try:
            invoice = Invoice(
                number=invoice_number,
                user_id=(
                    getattr(self.app, "current_user", None).id
                    if getattr(self.app, "current_user", None)
                    else None
                ),
                customer_uid=self.customer["uid"],
                customer_name=customer_name,
                total_amount=subtotal,
                discount_percent=self.discount_percent,
                discount_fixed=self.discount_fixed,
                tax_percent=self.tax_percent,
                tax_amount=tax_amount,
                net_amount=net_total,
                payment_method=payment_method,
                payment_account=payment_account,
            )
            session.add(invoice)
            session.flush()

            # Add invoice items with profit tracking (FEATURE 2)
            for line in self.lines:
                unit_type = line.get("unit_type", "piece") or "piece"
                quantity = line["qty"]
                total_price = line.get("total", 0.0) or 0.0

                # Get prices for profit tracking
                cost_price = line.get("cost_price", 0.0) or 0.0
                default_sale_price = line.get(
                    "default_sale_price", line.get("base_unit_price", 0)
                ) or line.get("base_unit_price", 0)
                actual_sale_price = (
                    line.get("actual_sale_price", default_sale_price)
                    or default_sale_price
                )
                profit = line.get("profit", actual_sale_price - cost_price) or (
                    actual_sale_price - cost_price
                )

                # Calculate unit_price for display (per unit)
                if unit_type == "g":
                    unit_price_display = actual_sale_price / 1000.0  # Per gram
                else:
                    unit_price_display = actual_sale_price

                item = InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=line["product_id"],
                    quantity=quantity,
                    quantity_exact=quantity,
                    unit_type=unit_type,
                    unit_price=unit_price_display,
                    total_price=total_price,
                    cost_price=cost_price,
                    default_sale_price=default_sale_price,
                    actual_sale_price=actual_sale_price,
                    profit=profit,
                )
                session.add(item)

            session.commit()
            # Mark bill as generated successfully
            self.bill_generated = True
        except Exception:
            session.rollback()
            self._show_error_popup("Failed to save bill to database.")
            return
        finally:
            session.close()

        # Show bill preview popup
        self._show_bill_preview_popup(invoice_number, customer_name, net_total)

    def _show_bill_preview_popup(
        self, invoice_number: str, customer_name: str, total_amount: float
    ) -> None:
        """Show bill preview popup with actions."""
        win = ctk.CTkToplevel(self)
        win.title("Bill Created Successfully")
        win.grab_set()
        win.geometry("450x350")

        # Header
        primary_color = get_theme_color("primary")
        header = ctk.CTkFrame(win, fg_color=primary_color)
        header.pack(fill="x", padx=0, pady=0)

        ctk.CTkLabel(
            header,
            text="✓ Bill Created Successfully",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white",
        ).pack(pady=15)

        # Content
        content = ctk.CTkFrame(win)
        content.pack(fill="both", expand=True, padx=20, pady=20)

        info_frame = ctk.CTkFrame(content, fg_color="transparent")
        info_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            info_frame, text="Invoice Number:", font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(info_frame, text=invoice_number, font=ctk.CTkFont(size=14)).grid(
            row=0, column=1, padx=10, pady=8, sticky="w"
        )

        ctk.CTkLabel(
            info_frame, text="Customer Name:", font=ctk.CTkFont(weight="bold")
        ).grid(row=1, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(info_frame, text=customer_name, font=ctk.CTkFont(size=14)).grid(
            row=1, column=1, padx=10, pady=8, sticky="w"
        )

        ctk.CTkLabel(
            info_frame, text="Total Amount:", font=ctk.CTkFont(weight="bold")
        ).grid(row=2, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(
            info_frame,
            text=f"RS. {total_amount:.2f}",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=2, column=1, padx=10, pady=8, sticky="w")

        # Buttons
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(pady=20)

        primary_color = get_theme_color("primary")
        success_color = get_theme_color("success")

        print_btn = ctk.CTkButton(
            btn_frame,
            text="Print Bill",
            command=lambda: self._print_bill_from_popup(win),
            width=120,
            fg_color=primary_color,
        )
        print_btn.pack(side="left", padx=5)

        pdf_btn = ctk.CTkButton(
            btn_frame,
            text="Download PDF",
            command=lambda: self._download_pdf_from_popup(win),
            width=120,
            fg_color=success_color,
        )
        pdf_btn.pack(side="left", padx=5)

        new_btn = ctk.CTkButton(
            btn_frame,
            text="Create New Bill",
            command=lambda: self._create_new_bill_from_popup(win),
            width=120,
            fg_color="gray50",
        )
        new_btn.pack(side="left", padx=5)

    def _print_bill_from_popup(self, popup_win) -> None:
        """Print bill and close popup."""
        self._print_bill()
        popup_win.destroy()

    def _download_pdf_from_popup(self, popup_win) -> None:
        """Download PDF and optionally open it."""
        if not self.current_invoice_number:
            return

        invoices_dir = Path("invoices")
        invoices_dir.mkdir(exist_ok=True)
        output_path = invoices_dir / f"{self.current_invoice_number}.pdf"

        # Generate PDF with enhanced invoice data
        # Prepare lines with unit_type for invoice generation
        invoice_lines = []
        for l in self.lines:
            line_copy = l.copy()
            # Ensure unit_type is included
            if "unit_type" not in line_copy:
                line_copy["unit_type"] = "piece"
            invoice_lines.append(line_copy)

        subtotal = sum(l["total"] for l in self.lines)
        discount_type = self.discount_type_combo.get()
        try:
            discount_value = float(self.discount_entry.get() or "0")
        except ValueError:
            discount_value = 0.0

        if discount_type == "Percentage":
            discount_amount = subtotal * (discount_value / 100.0)
        else:
            discount_amount = min(discount_value, subtotal)

        amount_after_discount = subtotal - discount_amount
        tax_amount = amount_after_discount * (self.tax_percent / 100.0)

        # Get current user's username
        current_user = getattr(self.app, "current_user", None)
        username = current_user.username if current_user else None

        generate_invoice_pdf(
            self.current_invoice_number,
            invoice_lines,
            output_path,
            customer=self.customer,
            subtotal=subtotal,
            discount_amount=discount_amount,
            discount_type=discount_type,
            discount_value=discount_value,
            tax_percent=self.tax_percent,
            tax_amount=tax_amount,
            username=username,
            payment_method=getattr(self, "current_payment_method", "Cash"),
            payment_account=getattr(self, "current_payment_account", None),
        )

        self._show_toast(f"PDF saved to: {output_path}")
        # Optionally open PDF
        try:
            webbrowser.open(str(output_path))
        except Exception:
            pass

    def _create_new_bill_from_popup(self, popup_win) -> None:
        """Clear cart and start new bill."""
        popup_win.destroy()
        self._clear_cart()
        self.customer_name_entry.delete(0, "end")
        self.customer = {}
        self.current_invoice_number = None

    def _print_bill(self) -> None:
        """Print bill (same as download PDF)."""
        if not self.current_invoice_number:
            self._show_error_popup("No bill generated yet.")
            return
        self._download_pdf_from_popup(None)

    # ========== Helpers ==========

    def _next_invoice_number(self) -> str:
        """Generate next invoice number."""
        session = get_session()
        try:
            rows = (
                session.query(Invoice.number)
                .order_by(Invoice.created_at.desc())
                .limit(100)
                .all()
            )
        finally:
            session.close()

        max_num = 0
        for (num,) in rows:
            if isinstance(num, str) and num.startswith("INV-"):
                tail = num[4:]
                if tail.isdigit():
                    try:
                        max_num = max(max_num, int(tail))
                    except Exception:
                        pass
        next_num = max_num + 1
        return f"INV-{next_num:06d}"

    def _update_supabase_product_stock(self, sku: str | None, new_stock: float) -> None:
        """Update product stock in Supabase."""
        if not sku:
            return
        cfg = load_config()
        if not cfg.api_url or not cfg.supabase_key:
            return

        url = cfg.api_url.rstrip("/") + "/rest/v1/products?on_conflict=sku"
        headers = {
            "apikey": cfg.supabase_key,
            "Authorization": f"Bearer {cfg.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        # Fixed: Use float for stock_qty to avoid precision loss for kg/g items
        payload = [{"sku": sku, "stock_qty": float(new_stock), "synced": True}]
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=5)
            if not resp.ok:
                pass  # Silent fail
        except Exception:
            pass  # Silent fail

    def _show_error_popup(self, message: str) -> None:
        """Show error popup."""
        win = ctk.CTkToplevel(self)
        win.title("Error")
        win.grab_set()
        frame = ctk.CTkFrame(win)
        frame.pack(padx=20, pady=20)
        lbl = ctk.CTkLabel(
            frame, text=message, text_color="red", font=ctk.CTkFont(weight="bold")
        )
        lbl.pack(padx=15, pady=15)
        btn = ctk.CTkButton(frame, text="OK", command=win.destroy, width=100)
        btn.pack(padx=15, pady=(0, 15))

    def _show_yes_no_popup(self, title: str, message: str) -> bool:
        """Show yes/no confirmation popup. Returns True if Yes, False if No."""
        result = {"choice": False}

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.grab_set()

        frame = ctk.CTkFrame(win)
        frame.pack(padx=20, pady=20)

        lbl = ctk.CTkLabel(
            frame, text=message, text_color="orange", font=ctk.CTkFont(weight="bold")
        )
        lbl.pack(padx=15, pady=15)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(padx=15, pady=(0, 15))

        def on_yes():
            result["choice"] = True
            win.destroy()

        def on_no():
            result["choice"] = False
            win.destroy()

        yes_btn = ctk.CTkButton(btn_frame, text="Yes", command=on_yes, width=80)
        yes_btn.grid(row=0, column=0, padx=5)

        no_btn = ctk.CTkButton(btn_frame, text="No", command=on_no, width=80)
        no_btn.grid(row=0, column=1, padx=5)

        win.wait_window()
        return result["choice"]

    def _show_toast(self, message: str) -> None:
        """Show toast notification."""
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        primary_color = get_theme_color("primary")
        frame = ctk.CTkFrame(toast, fg_color=primary_color)
        lbl = ctk.CTkLabel(
            frame, text=message, text_color="white", font=ctk.CTkFont(weight="bold")
        )
        lbl.pack(padx=15, pady=12)
        frame.pack()
        self.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - 300
        y = self.winfo_rooty() + self.winfo_height() - 100
        toast.geometry(f"280x50+{x}+{y}")
        self.after(3000, toast.destroy)

    # ========== Payment Account Management ==========

    def _load_payment_accounts(self) -> List[str]:
        """Load list of payment accounts from settings."""
        session = get_session()
        try:
            setting = session.query(Setting).filter(Setting.key == "payment_accounts").first()
            if setting:
                return json.loads(setting.value)
            return ["EasyPaisa", "JazzCash", "Bank Transfer"] # Default defaults
        except Exception:
            return ["EasyPaisa", "JazzCash", "Bank Transfer"]
        finally:
            session.close()

    def _save_payment_accounts(self, accounts: List[str]) -> None:
        """Save list of payment accounts to settings."""
        session = get_session()
        try:
            setting = session.query(Setting).filter(Setting.key == "payment_accounts").first()
            if not setting:
                setting = Setting(key="payment_accounts", value=json.dumps(accounts))
                session.add(setting)
            else:
                setting.value = json.dumps(accounts)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def _add_new_account_popup(self, parent_win, callback) -> None:
        """Show popup to add a new account."""
        dialog = ctk.CTkInputDialog(text="Enter new account name:", title="Add Account")
        new_account = dialog.get_input()
        if new_account and new_account.strip():
            accounts = self._load_payment_accounts()
            if new_account not in accounts:
                accounts.append(new_account)
                self._save_payment_accounts(accounts)
                callback(accounts)
            else:
                self._show_error_popup("Account already exists!")
