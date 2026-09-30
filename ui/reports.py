import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import webbrowser

import customtkinter as ctk
import tkinter.ttk as ttk
from tkinter import filedialog
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from db.local_db import get_session, get_by_id
from db.models import Invoice, InvoiceItem, Product, User, StockTransaction
from utils.invoice import generate_invoice_pdf
from utils.theme_utils import get_theme_color, adjust_color_brightness

try:
    import openpyxl
    from openpyxl import Workbook

    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


class ReportsFrame(ctk.CTkFrame):
    """Modern comprehensive reports module with insights and analytics."""

    def __init__(self, master: ctk.CTk, app=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self.current_page = 0
        self.items_per_page = 50

        self.configure(fg_color="transparent")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)  # Content frame should expand, not tabs

        # Check admin access
        self.is_admin = self._check_admin_access()

        # Build UI
        self._build_summary_cards()
        self._build_tabs()
        self._load_initial_data()

    def _check_admin_access(self) -> bool:
        """Check if current user is admin."""
        if not self.app:
            return False
        current_user = getattr(self.app, "current_user", None)
        return bool(current_user and getattr(current_user, "is_admin", False))

    # ========== Summary Cards ==========

    def _build_summary_cards(self) -> None:
        """Build summary cards at the top."""
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.grid(
            row=0, column=0, sticky="nw", padx=10, pady=(5, 5)
        )  # Changed to nw and reduced top padding
        for i in range(7):
            cards_frame.columnconfigure(i, weight=1)

        # Get theme-aware colors
        primary_color = get_theme_color("primary")
        success_color = get_theme_color("success")
        warning_color = get_theme_color("warning")
        info_color = get_theme_color("info")
        error_color = get_theme_color("error")
        
        discount_color = adjust_color_brightness(warning_color, 0.8) if warning_color else "#F59E0B"

        # Card 1: Today's Profit
        self.today_card = self._create_summary_card(
            cards_frame, "Today's Profit", "₨0.00", 0, primary_color
        )

        # Card 2: Monthly Profit
        self.month_card = self._create_summary_card(
            cards_frame, "Monthly Profit", "₨0.00", 1, success_color
        )

        # Card 3: Total Customers
        self.customers_card = self._create_summary_card(
            cards_frame, "Total Customers", "0", 2, warning_color
        )

        # Card 4: Total Invoices
        self.invoices_card = self._create_summary_card(
            cards_frame, "Total Invoices", "0", 3, info_color
        )

        # Card 5: Low Stock
        self.low_stock_card = self._create_summary_card(
            cards_frame, "Low Stock Items", "0", 4, error_color
        )

        # Card 6: Total Discount
        self.total_discount_card = self._create_summary_card(
            cards_frame, "Total Discount", "₨0.00", 5, discount_color
        )

        # Card 7: Total Sale
        total_sale_color = (
            adjust_color_brightness(primary_color, 0.6) if primary_color else "#6C757D"
        )
        self.total_sale_card = self._create_summary_card(
            cards_frame, "Total Sale", "₨0.00", 6, total_sale_color
        )

    def _create_summary_card(
        self, parent: ctk.CTkFrame, title: str, value: str, column: int, color: str
    ) -> ctk.CTkFrame:
        """Create a summary card."""
        card = ctk.CTkFrame(parent, fg_color=color, corner_radius=8)
        card.grid(row=0, column=column, padx=5, pady=5, sticky="ew")

        title_label = ctk.CTkLabel(
            card, text=title, font=ctk.CTkFont(size=11), text_color="white"
        )
        title_label.pack(padx=12, pady=(10, 2), anchor="w")

        value_label = ctk.CTkLabel(
            card,
            text=value,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white",
        )
        value_label.pack(padx=12, pady=(0, 10), anchor="w")

        return value_label

    # ========== Tabs ==========

    def _build_tabs(self) -> None:
        """Build tabbed interface for different report types."""
        # Tab buttons
        tabs_frame = ctk.CTkFrame(self, fg_color="transparent")
        tabs_frame.grid(
            row=1, column=0, sticky="nw", padx=10, pady=(5, 5)
        )  # Changed to nw and reduced padding
        for i in range(5):
            tabs_frame.columnconfigure(i, weight=1)

        self.tab_buttons = {}
        tabs = [
            ("Sales Reports", "sales"),
            ("Customer Insights", "customers"),
            ("Product Insights", "products"),
            ("Invoice List", "invoices"),
            ("Export", "export"),
        ]

        # Get theme primary color for active tab
        primary_color = get_theme_color("primary")

        for idx, (label, key) in enumerate(tabs):
            btn = ctk.CTkButton(
                tabs_frame,
                text=label,
                command=lambda k=key: self._switch_tab(k),
                fg_color="gray50" if idx != 0 else primary_color,
                hover_color="gray60",
                width=140,
            )
            btn.grid(row=0, column=idx, padx=2, pady=2)
            self.tab_buttons[key] = btn

        # Content area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)

        # Create tab content frames
        self.tab_frames = {}
        self._create_sales_tab()
        self._create_customers_tab()
        self._create_products_tab()
        self._create_invoices_tab()
        self._create_export_tab()

        # Show default tab
        self._switch_tab("sales")

    def _switch_tab(self, tab_key: str) -> None:
        """Switch between tabs."""
        # Get theme primary color
        primary_color = get_theme_color("primary")
        # Update button colors
        for key, btn in self.tab_buttons.items():
            btn.configure(fg_color="gray50" if key != tab_key else primary_color)

        # Hide all frames
        for frame in self.tab_frames.values():
            frame.grid_remove()

        # Show selected frame
        if tab_key in self.tab_frames:
            self.tab_frames[tab_key].grid(row=0, column=0, sticky="nsew")
            # Refresh data for the tab
            if tab_key == "sales":
                self._refresh_sales_reports()
            elif tab_key == "customers":
                self._refresh_customer_insights()
            elif tab_key == "products":
                self._refresh_product_insights()
            elif tab_key == "invoices":
                self._refresh_invoice_list()

    # ========== Sales Reports Tab ==========

    def _create_sales_tab(self) -> None:
        """Create sales reports tab."""
        frame = ctk.CTkFrame(self.content_frame)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Date range selector
        date_frame = ctk.CTkFrame(frame, fg_color="transparent")
        date_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        date_frame.columnconfigure(1, weight=1)
        date_frame.columnconfigure(3, weight=1)

        ctk.CTkLabel(date_frame, text="Period:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        self.period_combo = ctk.CTkComboBox(
            date_frame,
            values=["Today", "This Week", "This Month", "Last Month", "Custom"],
            width=150,
            command=self._on_period_change,
        )
        self.period_combo.set("This Month")
        self.period_combo.grid(row=0, column=1, padx=5, sticky="w")

        ctk.CTkLabel(date_frame, text="From:").grid(
            row=0, column=2, padx=(20, 5), sticky="w"
        )
        self.from_date_entry = ctk.CTkEntry(
            date_frame, width=120, placeholder_text="YYYY-MM-DD"
        )
        self.from_date_entry.grid(row=0, column=3, padx=5, sticky="w")

        ctk.CTkLabel(date_frame, text="To:").grid(
            row=0, column=4, padx=(10, 5), sticky="w"
        )
        self.to_date_entry = ctk.CTkEntry(
            date_frame, width=120, placeholder_text="YYYY-MM-DD"
        )
        self.to_date_entry.grid(row=0, column=5, padx=5, sticky="w")

        refresh_btn = ctk.CTkButton(
            date_frame, text="Refresh", command=self._refresh_sales_reports, width=100
        )
        refresh_btn.grid(row=0, column=6, padx=10, sticky="e")

        # Stats frame
        stats_frame = ctk.CTkFrame(frame)
        stats_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        for i in range(5):
            stats_frame.columnconfigure(i, weight=1)

        self.total_sales_label = ctk.CTkLabel(
            stats_frame,
            text="Total Sales: ₨0.00",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.total_sales_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.total_orders_label = ctk.CTkLabel(
            stats_frame,
            text="Total Orders: 0",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.total_orders_label.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        self.total_discounts_label = ctk.CTkLabel(
            stats_frame,
            text="Total Discounts: ₨0.00",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.total_discounts_label.grid(row=0, column=2, padx=10, pady=10, sticky="w")

        self.net_profit_label = ctk.CTkLabel(
            stats_frame,
            text="Net Profit: ₨0.00",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.net_profit_label.grid(row=0, column=3, padx=10, pady=10, sticky="w")

        self.avg_order_label = ctk.CTkLabel(
            stats_frame,
            text="Avg Order: ₨0.00",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.avg_order_label.grid(row=0, column=4, padx=10, pady=10, sticky="w")

        # Table
        table_frame = ctk.CTkFrame(frame)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        style = ttk.Style()
        style.configure(
            "Reports.Treeview",
            background="white",
            foreground="black",
            fieldbackground="white",
            borderwidth=0,
        )
        style.configure("Reports.Treeview.Heading", font=("TkDefaultFont", 9, "bold"))

        self.sales_table = ttk.Treeview(
            table_frame,
            columns=("date", "orders", "revenue", "discount", "tax", "net", "profit"),
            show="headings",
            style="Reports.Treeview",
        )
        for col, text, width in [
            ("date", "Date", 100),
            ("orders", "Orders", 80),
            ("revenue", "Revenue", 100),
            ("discount", "Discount", 100),
            ("tax", "Tax", 100),
            ("net", "Net Amount", 100),
            ("profit", "Profit", 100),
        ]:
            self.sales_table.heading(col, text=text)
            self.sales_table.column(
                col, width=width, anchor="e" if col != "date" else "w"
            )

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.sales_table.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.sales_table.configure(yscrollcommand=scrollbar.set)
        self.sales_table.grid(row=0, column=0, sticky="nsew")

        self.tab_frames["sales"] = frame

    def _on_period_change(self, value: str) -> None:
        """Handle period selection change."""
        today = date.today()
        if value == "Today":
            self.from_date_entry.delete(0, "end")
            self.from_date_entry.insert(0, today.isoformat())
            self.to_date_entry.delete(0, "end")
            self.to_date_entry.insert(0, today.isoformat())
        elif value == "This Week":
            start = today - timedelta(days=today.weekday())
            self.from_date_entry.delete(0, "end")
            self.from_date_entry.insert(0, start.isoformat())
            self.to_date_entry.delete(0, "end")
            self.to_date_entry.insert(0, today.isoformat())
        elif value == "This Month":
            start = today.replace(day=1)
            self.from_date_entry.delete(0, "end")
            self.from_date_entry.insert(0, start.isoformat())
            self.to_date_entry.delete(0, "end")
            self.to_date_entry.insert(0, today.isoformat())
        elif value == "Last Month":
            if today.month == 1:
                start = date(today.year - 1, 12, 1)
                end = date(today.year - 1, 12, 31)
            else:
                start = today.replace(month=today.month - 1, day=1)
                end = start.replace(month=start.month + 1) - timedelta(days=1)
            self.from_date_entry.delete(0, "end")
            self.from_date_entry.insert(0, start.isoformat())
            self.to_date_entry.delete(0, "end")
            self.to_date_entry.insert(0, end.isoformat())

    def _refresh_sales_reports(self) -> None:
        """Refresh sales reports data."""
        from_date = self._parse_date(self.from_date_entry.get())
        to_date = self._parse_date(self.to_date_entry.get())

        session = get_session()
        try:
            query = session.query(Invoice)
            if from_date:
                query = query.filter(
                    func.date(Invoice.created_at) >= from_date.isoformat()
                )
            if to_date:
                query = query.filter(
                    func.date(Invoice.created_at) <= to_date.isoformat()
                )

            invoices = query.all()

            # Calculate totals
            total_sales = sum(inv.total_amount or 0 for inv in invoices)
            total_orders = len(invoices)
            total_discounts = sum(
                (inv.total_amount or 0) * (inv.discount_percent or 0) / 100.0
                + (inv.discount_fixed or 0)
                for inv in invoices
            )
            total_tax = sum(inv.tax_amount or 0 for inv in invoices)

            # Calculate profit: sum of (sale_price - cost_price) * quantity for all invoice items
            total_profit = 0.0
            invoice_items = (
                session.query(InvoiceItem)
                .join(InvoiceItem.invoice)
                .join(InvoiceItem.product)
                .filter(Invoice.id.in_([inv.id for inv in invoices]))
                .all()
            )
            for item in invoice_items:
                unit_type = getattr(item, "unit_type", "piece") or "piece"
                quantity = item.quantity or 0.0
                item_profit_per_unit = getattr(item, "profit", 0.0) or 0.0
                
                if unit_type == "g":
                    total_profit += item_profit_per_unit * (quantity / 1000.0)
                else:
                    total_profit += item_profit_per_unit * quantity

            # Deduct overall discounts from total profit
            total_profit -= total_discounts

            avg_order = total_sales / total_orders if total_orders > 0 else 0

            # Update labels
            self.total_sales_label.configure(text=f"Total Sales: ₨{total_sales:.2f}")
            self.total_orders_label.configure(text=f"Total Orders: {total_orders}")
            self.total_discounts_label.configure(
                text=f"Total Discounts: ₨{total_discounts:.2f}"
            )
            self.net_profit_label.configure(text=f"Total Profit: ₨{total_profit:.2f}")
            self.avg_order_label.configure(text=f"Avg Order: ₨{avg_order:.2f}")

            # Daily summary with profit calculation
            daily_data = {}
            # Get all invoice items for these invoices
            invoice_ids = [inv.id for inv in invoices]
            daily_items = (
                session.query(InvoiceItem)
                .join(InvoiceItem.invoice)
                .join(InvoiceItem.product)
                .filter(InvoiceItem.invoice_id.in_(invoice_ids))
                .all()
            )

            for item in daily_items:
                inv = item.invoice
                day = inv.created_at.date() if inv.created_at else date.today()
                if day not in daily_data:
                    daily_data[day] = {
                        "orders": set(),
                        "revenue": 0.0,
                        "discount": 0.0,
                        "tax": 0.0,
                        "net": 0.0,
                        "profit": 0.0,
                    }
                
                # Add invoice-level totals only once per invoice
                is_new_invoice = inv.id not in daily_data[day]["orders"]
                if is_new_invoice:
                    daily_data[day]["orders"].add(inv.id)
                    daily_data[day]["revenue"] += inv.total_amount or 0
                    inv_discount = (inv.total_amount or 0) * (
                        inv.discount_percent or 0
                    ) / 100.0 + (inv.discount_fixed or 0)
                    daily_data[day]["discount"] += inv_discount
                    daily_data[day]["tax"] += inv.tax_amount or 0
                    daily_data[day]["net"] += inv.net_amount or 0
                    # Deduct the invoice-level discount from profit
                    daily_data[day]["profit"] -= inv_discount

                # Calculate profit for this item
                unit_type = getattr(item, "unit_type", "piece") or "piece"
                quantity = item.quantity or 0.0
                item_profit_per_unit = getattr(item, "profit", 0.0) or 0.0
                
                if unit_type == "g":
                    daily_data[day]["profit"] += item_profit_per_unit * (quantity / 1000.0)
                else:
                    daily_data[day]["profit"] += item_profit_per_unit * quantity

            # Convert orders sets to counts
            for day in daily_data:
                daily_data[day]["orders"] = len(daily_data[day]["orders"])

            # Populate table
            for row in self.sales_table.get_children():
                self.sales_table.delete(row)

            for day in sorted(daily_data.keys()):
                data = daily_data[day]
                self.sales_table.insert(
                    "",
                    "end",
                    values=(
                        str(day),
                        data["orders"],
                        f"₨{data['revenue']:.2f}",
                        f"₨{data['discount']:.2f}",
                        f"₨{data['tax']:.2f}",
                        f"₨{data['net']:.2f}",
                        f"₨{data['profit']:.2f}",
                    ),
                )

        finally:
            session.close()

    # ========== Customer Insights Tab ==========

    def _create_customers_tab(self) -> None:
        """Create customer insights tab."""
        frame = ctk.CTkFrame(self.content_frame)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Search frame
        search_frame = ctk.CTkFrame(frame, fg_color="transparent")
        search_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        search_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(search_frame, text="Search Customer:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        self.customer_search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="Name or Customer UID..."
        )
        self.customer_search_entry.grid(row=0, column=1, padx=5, sticky="ew")
        self.customer_search_entry.bind(
            "<KeyRelease>", lambda e: self._search_customer()
        )

        search_btn = ctk.CTkButton(
            search_frame, text="Search", command=self._search_customer, width=100
        )
        search_btn.grid(row=0, column=2, padx=5)

        # Customer info frame
        self.customer_info_frame = ctk.CTkFrame(frame)
        self.customer_info_frame.grid(
            row=1, column=0, sticky="ew", padx=10, pady=(0, 10)
        )
        for i in range(4):
            self.customer_info_frame.columnconfigure(i, weight=1)

        self.customer_name_label = ctk.CTkLabel(
            self.customer_info_frame,
            text="Customer: -",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.customer_name_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.customer_total_label = ctk.CTkLabel(
            self.customer_info_frame,
            text="Total Spent: ₨0.00",
            font=ctk.CTkFont(size=12),
        )
        self.customer_total_label.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        self.customer_orders_label = ctk.CTkLabel(
            self.customer_info_frame, text="Total Orders: 0", font=ctk.CTkFont(size=12)
        )
        self.customer_orders_label.grid(row=0, column=2, padx=10, pady=10, sticky="w")

        self.customer_last_label = ctk.CTkLabel(
            self.customer_info_frame, text="Last Order: -", font=ctk.CTkFont(size=12)
        )
        self.customer_last_label.grid(row=0, column=3, padx=10, pady=10, sticky="w")

        # Tables frame
        tables_frame = ctk.CTkFrame(frame, fg_color="transparent")
        tables_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        tables_frame.columnconfigure(0, weight=1)
        tables_frame.columnconfigure(1, weight=1)
        tables_frame.rowconfigure(0, weight=1)

        # Bills table
        bills_frame = ctk.CTkFrame(tables_frame)
        bills_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        bills_frame.columnconfigure(0, weight=1)
        bills_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(
            bills_frame, text="Customer Bills", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.customer_bills_table = ttk.Treeview(
            bills_frame,
            columns=("invoice", "date", "amount"),
            show="headings",
            style="Reports.Treeview",
        )
        for col, text, width in [
            ("invoice", "Invoice", 120),
            ("date", "Date", 100),
            ("amount", "Amount", 100),
        ]:
            self.customer_bills_table.heading(col, text=text)
            self.customer_bills_table.column(
                col, width=width, anchor="e" if col == "amount" else "w"
            )
        self.customer_bills_table.grid(
            row=1, column=0, sticky="nsew", padx=5, pady=(0, 5)
        )
        self.customer_bills_table.bind("<Double-1>", self._view_customer_invoice)

        # Products table
        products_frame = ctk.CTkFrame(tables_frame)
        products_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        products_frame.columnconfigure(0, weight=1)
        products_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(
            products_frame,
            text="Frequently Purchased",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.customer_products_table = ttk.Treeview(
            products_frame,
            columns=("product", "qty", "revenue"),
            show="headings",
            style="Reports.Treeview",
        )
        for col, text, width in [
            ("product", "Product", 150),
            ("qty", "Quantity", 80),
            ("revenue", "Revenue", 100),
        ]:
            self.customer_products_table.heading(col, text=text)
            self.customer_products_table.column(
                col, width=width, anchor="e" if col != "product" else "w"
            )
        self.customer_products_table.grid(
            row=1, column=0, sticky="nsew", padx=5, pady=(0, 5)
        )

        self.tab_frames["customers"] = frame

    def _search_customer(self) -> None:
        """Search for customer and display insights."""
        search_term = self.customer_search_entry.get().strip()
        if not search_term:
            return

        session = get_session()
        try:
            # Find invoices by customer name or UID
            invoices = (
                session.query(Invoice)
                .filter(
                    or_(
                        Invoice.customer_name.ilike(f"%{search_term}%"),
                        Invoice.customer_uid.ilike(f"%{search_term}%"),
                    )
                )
                .order_by(Invoice.created_at.desc())
                .all()
            )

            if not invoices:
                self.customer_name_label.configure(text="Customer: Not Found")
                self.customer_total_label.configure(text="Total Spent: ₨0.00")
                self.customer_orders_label.configure(text="Total Orders: 0")
                self.customer_last_label.configure(text="Last Order: -")
                # Clear tables
                for row in self.customer_bills_table.get_children():
                    self.customer_bills_table.delete(row)
                for row in self.customer_products_table.get_children():
                    self.customer_products_table.delete(row)
                return

            # Get customer info from first invoice
            first_inv = invoices[0]
            customer_name = first_inv.customer_name or "Unknown"
            customer_uid = first_inv.customer_uid or ""

            # Calculate totals
            total_spent = sum(inv.net_amount or 0 for inv in invoices)
            total_orders = len(invoices)
            last_order = max(
                inv.created_at.date() for inv in invoices if inv.created_at
            )

            # Update labels
            self.customer_name_label.configure(
                text=f"Customer: {customer_name} ({customer_uid})"
            )
            self.customer_total_label.configure(text=f"Total Spent: ₨{total_spent:.2f}")
            self.customer_orders_label.configure(text=f"Total Orders: {total_orders}")
            self.customer_last_label.configure(text=f"Last Order: {last_order}")

            # Populate bills table
            for row in self.customer_bills_table.get_children():
                self.customer_bills_table.delete(row)
            for inv in invoices[:50]:  # Limit to 50
                date_str = (
                    inv.created_at.date().isoformat() if inv.created_at else "Unknown"
                )
                self.customer_bills_table.insert(
                    "",
                    "end",
                    iid=str(inv.id),
                    values=(
                        inv.number,
                        date_str,
                        f"₨{inv.net_amount or 0:.2f}",
                    ),
                )

            # Get product insights
            product_data = {}
            for inv in invoices:
                items = (
                    session.query(InvoiceItem)
                    .filter(InvoiceItem.invoice_id == inv.id)
                    .all()
                )
                for item in items:
                    product = get_by_id(session, Product, item.product_id)
                    if product:
                        name = product.name
                        if name not in product_data:
                            product_data[name] = {"qty": 0.0, "revenue": 0.0}
                        quantity = (
                            getattr(item, "quantity_exact", item.quantity)
                            or item.quantity
                        )
                        product_data[name]["qty"] += quantity
                        total = getattr(
                            item,
                            "total_price",
                            (quantity or 0) * (item.unit_price or 0),
                        ) or ((quantity or 0) * (item.unit_price or 0))
                        product_data[name]["revenue"] += total

            # Populate products table
            for row in self.customer_products_table.get_children():
                self.customer_products_table.delete(row)
            for name, data in sorted(
                product_data.items(), key=lambda x: x[1]["qty"], reverse=True
            )[:20]:
                self.customer_products_table.insert(
                    "",
                    "end",
                    values=(
                        name,
                        f"{data['qty']:.0f}",
                        f"₨{data['revenue']:.2f}",
                    ),
                )

        finally:
            session.close()

    def _view_customer_invoice(self, event=None) -> None:
        """View selected invoice details."""
        selection = self.customer_bills_table.selection()
        if not selection:
            return
        invoice_id = int(selection[0])
        self._show_invoice_preview(invoice_id)

    # ========== Product Insights Tab ==========

    def _create_products_tab(self) -> None:
        """Create product insights tab."""
        frame = ctk.CTkFrame(self.content_frame)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        # Filter frame
        filter_frame = ctk.CTkFrame(frame, fg_color="transparent")
        filter_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        filter_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(filter_frame, text="View:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        self.product_view_combo = ctk.CTkComboBox(
            filter_frame,
            values=["All Products", "Low Stock", "Fast Selling", "Stock History"],
            width=150,
            command=self._on_product_view_change,
        )
        self.product_view_combo.set("All Products")
        self.product_view_combo.grid(row=0, column=1, padx=5, sticky="w")

        refresh_btn = ctk.CTkButton(
            filter_frame,
            text="Refresh",
            command=self._refresh_product_insights,
            width=100,
        )
        refresh_btn.grid(row=0, column=2, padx=10, sticky="e")

        # Table
        table_frame = ctk.CTkFrame(frame)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.products_table = ttk.Treeview(
            table_frame,
            columns=("product", "stock", "sold", "revenue", "profit", "category"),
            show="headings",
            style="Reports.Treeview",
        )
        for col, text, width in [
            ("product", "Product", 200),
            ("stock", "Stock", 80),
            ("sold", "Sold", 80),
            ("revenue", "Revenue", 100),
            ("profit", "Profit", 100),
            ("category", "Category", 120),
        ]:
            self.products_table.heading(col, text=text)
            self.products_table.column(
                col,
                width=width,
                anchor="e" if col != "product" and col != "category" else "w",
            )

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.products_table.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.products_table.configure(yscrollcommand=scrollbar.set)
        self.products_table.grid(row=0, column=0, sticky="nsew")

        self.tab_frames["products"] = frame

    def _on_product_view_change(self, value: str) -> None:
        """Handle product view change."""
        self._refresh_product_insights()

    def _refresh_product_insights(self) -> None:
        """Refresh product insights data."""
        view_type = self.product_view_combo.get()
        session = get_session()
        try:
            # Get all products
            if view_type == "Low Stock":
                products = (
                    session.query(Product)
                    .filter(Product.is_active == True, Product.stock_qty <= 5)
                    .order_by(Product.stock_qty.asc())
                    .all()
                )
            else:
                products = (
                    session.query(Product)
                    .filter(Product.is_active == True)
                    .order_by(Product.name)
                    .all()
                )

            # Get sales data for each product
            product_stats = {}
            for product in products:
                items = (
                    session.query(InvoiceItem)
                    .filter(InvoiceItem.product_id == product.id)
                    .all()
                )
                unit_type = getattr(product, "unit_type", "piece") or "piece"
                total_sold = 0.0
                total_revenue = 0.0
                for item in items:
                    quantity = (
                        getattr(item, "quantity_exact", item.quantity) or item.quantity
                    )
                    total_sold += quantity
                    total = getattr(
                        item, "total_price", (quantity or 0) * (item.unit_price or 0)
                    ) or ((quantity or 0) * (item.unit_price or 0))
                    total_revenue += total

                # Calculate profit: (sale_price - cost_price) * quantity for all items
                profit = 0.0
                for item in items:
                    sale_price = item.unit_price or 0.0
                    cost_price = getattr(product, "cost_price", 0.0) or 0.0
                    quantity = (
                        getattr(item, "quantity_exact", item.quantity) or item.quantity
                    )
                    profit += (sale_price - cost_price) * quantity

                product_stats[product.id] = {
                    "product": product,
                    "sold": total_sold,
                    "revenue": total_revenue,
                    "profit": profit,
                    "unit_type": unit_type,
                }

            # Sort by view type
            if view_type == "Fast Selling":
                sorted_products = sorted(
                    product_stats.items(), key=lambda x: x[1]["sold"], reverse=True
                )
            else:
                sorted_products = sorted(
                    product_stats.items(), key=lambda x: x[1]["product"].name
                )

            # Populate table
            for row in self.products_table.get_children():
                self.products_table.delete(row)

            for product_id, stats in sorted_products[:100]:  # Limit to 100
                product = stats["product"]
                stock = product.stock_qty or 0
                unit_type = stats.get("unit_type", "piece") or "piece"
                tags = []
                threshold = 0.1 if unit_type in ["kg", "g"] else 5
                if stock < threshold:
                    tags = ("low_stock",)

                # Format sold quantity with unit
                from utils.units import format_quantity

                sold_display = format_quantity(stats["sold"], unit_type)
                stock_display = (
                    f"{stock:.2f}" if unit_type in ["kg", "g"] else f"{stock:.0f}"
                )

                self.products_table.insert(
                    "",
                    "end",
                    iid=str(product_id),
                    tags=tags,
                    values=(
                        product.name,
                        stock_display,
                        sold_display,
                        f"₨{stats['revenue']:.2f}",
                        f"₨{stats['profit']:.2f}",
                        product.category or "-",
                    ),
                )

            # Configure tag colors
            self.products_table.tag_configure("low_stock", background="#ffcccc")

        finally:
            session.close()

    # ========== Invoice List Tab ==========

    def _create_invoices_tab(self) -> None:
        """Create invoice list tab."""
        frame = ctk.CTkFrame(self.content_frame)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        # Search and filter frame
        search_frame = ctk.CTkFrame(frame, fg_color="transparent")
        search_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        search_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(search_frame, text="Search:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        self.invoice_search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="Invoice number, customer name, or UID..."
        )
        self.invoice_search_entry.grid(row=0, column=1, padx=5, sticky="ew")
        self.invoice_search_entry.bind(
            "<KeyRelease>", lambda e: self._refresh_invoice_list()
        )

        # Pagination
        pagination_frame = ctk.CTkFrame(frame, fg_color="transparent")
        pagination_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        pagination_frame.columnconfigure(1, weight=1)

        self.prev_btn = ctk.CTkButton(
            pagination_frame,
            text="◀ Previous",
            command=self._prev_page,
            width=100,
            state="disabled",
        )
        self.prev_btn.grid(row=0, column=0, padx=5)

        self.page_label = ctk.CTkLabel(
            pagination_frame, text="Page 1 of 1", font=ctk.CTkFont(size=11)
        )
        self.page_label.grid(row=0, column=1, padx=10)

        self.next_btn = ctk.CTkButton(
            pagination_frame,
            text="Next ▶",
            command=self._next_page,
            width=100,
            state="disabled",
        )
        self.next_btn.grid(row=0, column=2, padx=5)

        # Table
        table_frame = ctk.CTkFrame(frame)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.invoices_table = ttk.Treeview(
            table_frame,
            columns=("invoice", "customer", "uid", "amount", "discount", "date"),
            show="headings",
            style="Reports.Treeview",
        )
        for col, text, width in [
            ("invoice", "Invoice #", 120),
            ("customer", "Customer", 150),
            ("uid", "Customer UID", 120),
            ("amount", "Amount", 100),
            ("discount", "Discount", 100),
            ("date", "Date", 100),
        ]:
            self.invoices_table.heading(col, text=text)
            self.invoices_table.column(
                col, width=width, anchor="e" if col in ["amount", "discount"] else "w"
            )
        self.invoices_table.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.invoices_table.bind("<Double-1>", self._view_invoice_details)

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.invoices_table.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.invoices_table.configure(yscrollcommand=scrollbar.set)

        self.tab_frames["invoices"] = frame

    def _refresh_invoice_list(self) -> None:
        """Refresh invoice list with pagination."""
        search_term = self.invoice_search_entry.get().strip().lower()
        session = get_session()
        try:
            query = session.query(Invoice).order_by(Invoice.created_at.desc())

            if search_term:
                query = query.filter(
                    or_(
                        Invoice.number.ilike(f"%{search_term}%"),
                        Invoice.customer_name.ilike(f"%{search_term}%"),
                        Invoice.customer_uid.ilike(f"%{search_term}%"),
                    )
                )

            total_invoices = query.count()
            total_pages = (
                total_invoices + self.items_per_page - 1
            ) // self.items_per_page

            # Update pagination
            self.page_label.configure(
                text=f"Page {self.current_page + 1} of {max(1, total_pages)}"
            )
            self.prev_btn.configure(
                state="normal" if self.current_page > 0 else "disabled"
            )
            self.next_btn.configure(
                state="normal" if self.current_page < total_pages - 1 else "disabled"
            )

            # Get page data
            invoices = (
                query.offset(self.current_page * self.items_per_page)
                .limit(self.items_per_page)
                .all()
            )

            # Populate table
            for row in self.invoices_table.get_children():
                self.invoices_table.delete(row)

            for inv in invoices:
                date_str = (
                    inv.created_at.date().isoformat() if inv.created_at else "Unknown"
                )
                discount = (inv.total_amount or 0) * (
                    inv.discount_percent or 0
                ) / 100.0 + (inv.discount_fixed or 0)
                self.invoices_table.insert(
                    "",
                    "end",
                    iid=str(inv.id),
                    values=(
                        inv.number,
                        inv.customer_name or "-",
                        inv.customer_uid or "-",
                        f"₨{inv.net_amount or 0:.2f}",
                        f"₨{discount:.2f}",
                        date_str,
                    ),
                )

        finally:
            session.close()

    def _prev_page(self) -> None:
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self._refresh_invoice_list()

    def _next_page(self) -> None:
        """Go to next page."""
        self.current_page += 1
        self._refresh_invoice_list()

    def _view_invoice_details(self, event=None) -> None:
        """View invoice details."""
        selection = self.invoices_table.selection()
        if not selection:
            return
        invoice_id = int(selection[0])
        self._show_invoice_preview(invoice_id)

    def _show_invoice_preview(self, invoice_id: int) -> None:
        """Show invoice preview popup."""
        session = get_session()
        try:
            invoice = get_by_id(session, Invoice, invoice_id)
            if not invoice:
                return

            items = (
                session.query(InvoiceItem)
                .filter(InvoiceItem.invoice_id == invoice_id)
                .all()
            )

            # Create preview window
            win = ctk.CTkToplevel(self)
            win.title(f"Invoice Preview - {invoice.number}")
            win.geometry("600x500")
            win.grab_set()

            # Content
            content = ctk.CTkScrollableFrame(win)
            content.pack(fill="both", expand=True, padx=20, pady=20)

            # Invoice header
            ctk.CTkLabel(
                content,
                text=f"Invoice: {invoice.number}",
                font=ctk.CTkFont(size=16, weight="bold"),
            ).pack(anchor="w", pady=(0, 10))

            ctk.CTkLabel(
                content, text=f"Customer: {invoice.customer_name or 'N/A'}"
            ).pack(anchor="w")
            ctk.CTkLabel(
                content, text=f"Customer UID: {invoice.customer_uid or 'N/A'}"
            ).pack(anchor="w")
            ctk.CTkLabel(
                content,
                text=f"Date: {invoice.created_at.date().isoformat() if invoice.created_at else 'N/A'}",
            ).pack(anchor="w", pady=(0, 5))

            ctk.CTkLabel(
                content, text=f"Payment Method: {invoice.payment_method or 'Cash'}"
            ).pack(anchor="w")
            if invoice.payment_method == "Online" and invoice.payment_account:
                ctk.CTkLabel(
                    content, text=f"Account: {invoice.payment_account}"
                ).pack(anchor="w")
            
            pdf_spacing = ctk.CTkLabel(content, text="") # Spacing
            pdf_spacing.pack(pady=5)

            # Items
            ctk.CTkLabel(
                content, text="Items:", font=ctk.CTkFont(size=12, weight="bold")
            ).pack(anchor="w", pady=(10, 5))

            items_text = ""
            for item in items:
                product = get_by_id(session, Product, item.product_id)
                product_name = product.name if product else "Unknown"
                unit_type = getattr(item, "unit_type", "piece") or "piece"
                quantity = (
                    getattr(item, "quantity_exact", item.quantity) or item.quantity
                )
                from utils.units import format_quantity

                qty_display = format_quantity(quantity, unit_type)
                total = getattr(
                    item, "total_price", (quantity or 0) * (item.unit_price or 0)
                ) or ((quantity or 0) * (item.unit_price or 0))
                items_text += f"{product_name} x {qty_display} @ ₨{item.unit_price:.2f} = ₨{total:.2f}\n"

            items_label = ctk.CTkLabel(content, text=items_text, justify="left")
            items_label.pack(anchor="w", pady=(0, 10))

            # Totals
            ctk.CTkLabel(
                content, text="Totals:", font=ctk.CTkFont(size=12, weight="bold")
            ).pack(anchor="w", pady=(10, 5))

            ctk.CTkLabel(
                content, text=f"Subtotal: ₨{invoice.total_amount or 0:.2f}"
            ).pack(anchor="w")
            discount = (invoice.total_amount or 0) * (
                invoice.discount_percent or 0
            ) / 100.0 + (invoice.discount_fixed or 0)
            ctk.CTkLabel(
                content, 
                text=f"Discount: ₨{discount:.2f}",
                font=ctk.CTkFont(weight="bold")
            ).pack(anchor="w")
            ctk.CTkLabel(content, text=f"Tax: ₨{invoice.tax_amount or 0:.2f}").pack(
                anchor="w"
            )
            ctk.CTkLabel(
                content,
                text=f"Net Amount: ₨{invoice.net_amount or 0:.2f}",
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", pady=(5, 10))

            # Buttons
            btn_frame = ctk.CTkFrame(content, fg_color="transparent")
            btn_frame.pack(fill="x", pady=10)

            print_btn = ctk.CTkButton(
                btn_frame,
                text="Print PDF",
                command=lambda: self._print_invoice_pdf(invoice, items),
                width=120,
            )
            print_btn.pack(side="left", padx=5)

            close_btn = ctk.CTkButton(
                btn_frame,
                text="Close",
                command=win.destroy,
                width=120,
                fg_color="gray50",
            )
            close_btn.pack(side="left", padx=5)

        finally:
            session.close()

    def _print_invoice_pdf(self, invoice: Invoice, items: List[InvoiceItem]) -> None:
        """Generate and print invoice PDF."""
        invoices_dir = Path("invoices")
        invoices_dir.mkdir(exist_ok=True)
        output_path = invoices_dir / f"{invoice.number}.pdf"

        # Convert items to dict format
        lines = []
        session = get_session()
        try:
            for item in items:
                product = get_by_id(session, Product, item.product_id)
                unit_type = getattr(item, "unit_type", "piece") or "piece"
                quantity = (
                    getattr(item, "quantity_exact", item.quantity) or item.quantity
                )
                total = getattr(
                    item, "total_price", (quantity or 0) * (item.unit_price or 0)
                ) or ((quantity or 0) * (item.unit_price or 0))
                lines.append(
                    {
                        "name": product.name if product else "Unknown",
                        "qty": quantity,
                        "unit_type": unit_type,
                        "unit_price": item.unit_price or 0,
                        "total": total,
                    }
                )
        finally:
            session.close()

        customer = {
            "name": invoice.customer_name or "",
            "uid": invoice.customer_uid or "",
        }

        discount_type = "Percentage" if invoice.discount_percent else "Fixed"
        discount_value = invoice.discount_percent or invoice.discount_fixed or 0

        # Get username from invoice user
        username = None
        if invoice.user_id:
            user = get_by_id(session, User, invoice.user_id)
            if user:
                username = user.username

        generate_invoice_pdf(
            invoice.number,
            lines,
            output_path,
            customer=customer,
            subtotal=invoice.total_amount or 0,
            discount_amount=(
                (invoice.total_amount or 0) * (invoice.discount_percent or 0) / 100.0
                + (invoice.discount_fixed or 0)
            ),
            discount_type=discount_type,
            discount_value=discount_value,
            tax_percent=invoice.tax_percent or 0,
            tax_amount=invoice.tax_amount or 0,
            username=username,
            payment_method=getattr(invoice, "payment_method", "Cash"),
            payment_account=getattr(invoice, "payment_account", None),
        )

        try:
            webbrowser.open(str(output_path))
        except Exception:
            pass

    # ========== Export Tab ==========

    def _create_export_tab(self) -> None:
        """Create export tab."""
        frame = ctk.CTkFrame(self.content_frame)
        frame.columnconfigure(0, weight=1)

        # Export options
        options_frame = ctk.CTkFrame(frame)
        options_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        options_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            options_frame,
            text="Export Reports",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        # CSV Export
        csv_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        csv_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        csv_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(csv_frame, text="CSV Export:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        ctk.CTkButton(
            csv_frame,
            text="Export Sales Report",
            command=self._export_sales_csv,
            width=150,
        ).grid(row=0, column=1, padx=5, sticky="w")
        ctk.CTkButton(
            csv_frame,
            text="Export Invoice List",
            command=self._export_invoices_csv,
            width=150,
        ).grid(row=0, column=2, padx=5, sticky="w")

        # Excel Export
        excel_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        excel_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        excel_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(excel_frame, text="Excel Export:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        excel_btn = ctk.CTkButton(
            excel_frame,
            text="Export to Excel",
            command=self._export_to_excel,
            width=150,
            state="disabled" if not OPENPYXL_AVAILABLE else "normal",
        )
        excel_btn.grid(row=0, column=1, padx=5, sticky="w")
        if not OPENPYXL_AVAILABLE:
            ctk.CTkLabel(
                excel_frame,
                text="(Install openpyxl: pip install openpyxl)",
                font=ctk.CTkFont(size=10),
                text_color="gray",
            ).grid(row=0, column=2, padx=5, sticky="w")

        # PDF Export
        pdf_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        pdf_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        pdf_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(pdf_frame, text="PDF Export:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        ctk.CTkButton(
            pdf_frame,
            text="Export Summary Report",
            command=self._export_summary_pdf,
            width=150,
        ).grid(row=0, column=1, padx=5, sticky="w")

        # Print
        print_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        print_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        print_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(print_frame, text="Print:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        ctk.CTkButton(
            print_frame,
            text="Print Current Report",
            command=self._print_current_report,
            width=150,
        ).grid(row=0, column=1, padx=2, sticky="w")

        self.tab_frames["export"] = frame

    def _export_sales_csv(self) -> None:
        """Export sales report to CSV."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Export Sales Report",
        )
        if not file_path:
            return

        from_date = self._parse_date(self.from_date_entry.get())
        to_date = self._parse_date(self.to_date_entry.get())

        session = get_session()
        try:
            query = session.query(Invoice)
            if from_date:
                query = query.filter(
                    func.date(Invoice.created_at) >= from_date.isoformat()
                )
            if to_date:
                query = query.filter(
                    func.date(Invoice.created_at) <= to_date.isoformat()
                )

            invoices = query.order_by(Invoice.created_at).all()

            # Ensure output directory exists to avoid FileNotFoundError
            try:
                Path(file_path).resolve().parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Date",
                        "Invoice Number",
                        "Customer Name",
                        "Customer UID",
                        "Total Amount",
                        "Discount",
                        "Tax",
                        "Net Amount",
                    ]
                )

                for inv in invoices:
                    discount = (inv.total_amount or 0) * (
                        inv.discount_percent or 0
                    ) / 100.0 + (inv.discount_fixed or 0)
                    date_str = (
                        inv.created_at.date().isoformat() if inv.created_at else ""
                    )
                    writer.writerow(
                        [
                            date_str,
                            inv.number,
                            inv.customer_name or "",
                            inv.customer_uid or "",
                            inv.total_amount or 0,
                            discount,
                            inv.tax_amount or 0,
                            inv.net_amount or 0,
                        ]
                    )

            self._show_toast(f"Sales report exported to {file_path}")

        finally:
            session.close()

    def _export_invoices_csv(self) -> None:
        """Export invoice list to CSV."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Export Invoice List",
        )
        if not file_path:
            return

        session = get_session()
        try:
            invoices = session.query(Invoice).order_by(Invoice.created_at.desc()).all()

            # Ensure output directory exists to avoid FileNotFoundError
            try:
                Path(file_path).resolve().parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Invoice Number",
                        "Customer Name",
                        "Customer UID",
                        "Date",
                        "Total Amount",
                        "Discount",
                        "Tax",
                        "Net Amount",
                    ]
                )

                for inv in invoices:
                    discount = (inv.total_amount or 0) * (
                        inv.discount_percent or 0
                    ) / 100.0 + (inv.discount_fixed or 0)
                    date_str = (
                        inv.created_at.date().isoformat() if inv.created_at else ""
                    )
                    writer.writerow(
                        [
                            inv.number,
                            inv.customer_name or "",
                            inv.customer_uid or "",
                            date_str,
                            inv.total_amount or 0,
                            discount,
                            inv.tax_amount or 0,
                            inv.net_amount or 0,
                        ]
                    )

            self._show_toast(f"Invoice list exported to {file_path}")

        finally:
            session.close()

    def _export_to_excel(self) -> None:
        """Export to Excel."""
        if not OPENPYXL_AVAILABLE:
            self._show_error(
                "Excel export requires openpyxl. Install with: pip install openpyxl"
            )
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            title="Export to Excel",
        )
        if not file_path:
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "Sales Report"

        session = get_session()
        try:
            invoices = session.query(Invoice).order_by(Invoice.created_at).all()

            # Headers
            ws.append(
                [
                    "Date",
                    "Invoice Number",
                    "Customer Name",
                    "Customer UID",
                    "Total Amount",
                    "Discount",
                    "Tax",
                    "Net Amount",
                ]
            )

            # Data
            for inv in invoices:
                discount = (inv.total_amount or 0) * (
                    inv.discount_percent or 0
                ) / 100.0 + (inv.discount_fixed or 0)
                date_str = inv.created_at.date().isoformat() if inv.created_at else ""
                ws.append(
                    [
                        date_str,
                        inv.number,
                        inv.customer_name or "",
                        inv.customer_uid or "",
                        inv.total_amount or 0,
                        discount,
                        inv.tax_amount or 0,
                        inv.net_amount or 0,
                    ]
                )

            wb.save(file_path)
            self._show_toast(f"Report exported to {file_path}")

        finally:
            session.close()

    def _export_summary_pdf(self) -> None:
        """Export summary report to PDF."""
        # This would generate a comprehensive PDF report
        # For now, just show a message
        self._show_toast("PDF export feature coming soon!")

    def _print_current_report(self) -> None:
        """Print current report."""
        self._show_toast("Print feature - Use export to PDF and print from there")

    # ========== Helper Methods ==========

    def _parse_date(self, value: str) -> Optional[date]:
        """Parse date string."""
        value = (value or "").strip()
        if not value:
            return None
        try:
            year, month, day = map(int, value.split("-"))
            return date(year, month, day)
        except Exception:
            return None

    def refresh_data(self) -> None:
        """Refresh all report data from the database."""
        self._refresh_summary_cards()
        self._refresh_sales_reports()
        if hasattr(self, "invoices_table"): # if invoice tab initialized
            self._refresh_invoice_list()

    def _load_initial_data(self) -> None:
        """Load initial summary data."""
        self.refresh_data()

    def _refresh_summary_cards(self) -> None:
        """Refresh summary cards."""
        today = date.today()
        month_start = today.replace(day=1)

        session = get_session()
        try:
            # Today's profit: sum of (sale_price - cost_price) * quantity for all invoice items today
            today_invoice_items = (
                session.query(InvoiceItem)
                .join(InvoiceItem.invoice)
                .join(InvoiceItem.product)
                .filter(func.date(Invoice.created_at) == today.isoformat())
                .all()
            )
            today_profit = 0.0
            for item in today_invoice_items:
                # Use stored profit if available and correct for units
                unit_type = getattr(item, "unit_type", "piece") or "piece"
                quantity = item.quantity or 0.0
                
                # Preferred: Use the profit field we saved during sale
                # item.profit is per kg or per piece
                item_profit_per_unit = getattr(item, "profit", 0.0) or 0.0
                
                if unit_type == "g":
                    today_profit += item_profit_per_unit * (quantity / 1000.0)
                else:
                    today_profit += item_profit_per_unit * quantity
            
            # Deduct today's discount from today's profit
            today_invoices = session.query(Invoice).filter(func.date(Invoice.created_at) == today.isoformat()).all()
            today_discount = sum((inv.total_amount or 0) * (inv.discount_percent or 0) / 100.0 + (inv.discount_fixed or 0) for inv in today_invoices)
            today_profit -= today_discount

            self.today_card.configure(text=f"₨{today_profit:.2f}")

            # Monthly profit: sum of (sale_price - cost_price) * quantity for all invoice items this month
            month_invoice_items = (
                session.query(InvoiceItem)
                .join(InvoiceItem.invoice)
                .join(InvoiceItem.product)
                .filter(func.date(Invoice.created_at) >= month_start.isoformat())
                .all()
            )
            month_profit = 0.0
            for item in month_invoice_items:
                unit_type = getattr(item, "unit_type", "piece") or "piece"
                quantity = item.quantity or 0.0
                
                item_profit_per_unit = getattr(item, "profit", 0.0) or 0.0
                
                if unit_type == "g":
                    month_profit += item_profit_per_unit * (quantity / 1000.0)
                else:
                    month_profit += item_profit_per_unit * quantity
            
            # Deduct this month's discount from monthly profit
            month_invoices = session.query(Invoice).filter(func.date(Invoice.created_at) >= month_start.isoformat()).all()
            month_discount = sum((inv.total_amount or 0) * (inv.discount_percent or 0) / 100.0 + (inv.discount_fixed or 0) for inv in month_invoices)
            month_profit -= month_discount
            
            self.month_card.configure(text=f"₨{month_profit:.2f}")

            # Total customers (unique customer UIDs)
            customer_count = (
                session.query(func.count(func.distinct(Invoice.customer_uid)))
                .filter(Invoice.customer_uid.isnot(None))
                .scalar()
            )
            self.customers_card.configure(text=str(customer_count or 0))

            # Total invoices
            invoice_count = session.query(func.count(Invoice.id)).scalar()
            self.invoices_card.configure(text=str(invoice_count or 0))

            # Low stock items (considering unit types)
            # For piece-based: < 5, for weight-based: < 0.1
            low_stock_products = (
                session.query(Product).filter(Product.is_active == True).all()
            )
            low_stock_count = 0
            for p in low_stock_products:
                unit_type = getattr(p, "unit_type", "piece") or "piece"
                threshold = 0.1 if unit_type in ["kg", "g"] else 5
                if (p.stock_qty or 0) < threshold:
                    low_stock_count += 1
            self.low_stock_card.configure(text=str(low_stock_count))

            # Total Sale: sum of all invoice net_amount
            total_sale = session.query(
                func.coalesce(func.sum(Invoice.net_amount), 0.0)
            ).scalar()
            self.total_sale_card.configure(text=f"₨{total_sale:.2f}")

            # Total overall discount
            all_invoices = session.query(Invoice).all()
            total_discount_overall = sum((inv.total_amount or 0) * (inv.discount_percent or 0) / 100.0 + (inv.discount_fixed or 0) for inv in all_invoices)
            self.total_discount_card.configure(text=f"₨{total_discount_overall:.2f}")

        finally:
            session.close()

    def _refresh_customer_insights(self) -> None:
        """Refresh customer insights (called when tab is switched)."""
        # Data loaded on search
        pass

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

    def _show_error(self, message: str) -> None:
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
