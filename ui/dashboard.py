from datetime import date

import customtkinter as ctk
from sqlalchemy import func

from db.local_db import get_session
from db.models import Invoice, InvoiceItem, Product
from utils.theme_utils import get_card_colors, get_theme_color


class DashboardFrame(ctk.CTkFrame):
    """Dashboard with navigation buttons and today's sales summary."""

    def __init__(self, master: ctk.CTk, app=None, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self.app = app

        self.configure(fg_color="transparent")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Main inner content frame similar to Admin Dashboard layout
        main = ctk.CTkFrame(self)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)  # title
        main.rowconfigure(1, weight=1)  # cards
        main.rowconfigure(2, weight=0)  # quick actions

        # ---- Title ----
        title = ctk.CTkLabel(
            main,
            text="Admin Dashboard",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, padx=10, pady=(16, 8), sticky="n")

        # ---- Stats and info cards ----
        cards_container = ctk.CTkFrame(main,)
        cards_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 8))
        cards_container.columnconfigure(0, weight=1)
        cards_container.columnconfigure(1, weight=1)
        cards_container.columnconfigure(2, weight=1)
        cards_container.rowconfigure(0, weight=0)
        cards_container.rowconfigure(1, weight=1)

        # Get theme-aware colors for cards
        card_colors = get_card_colors()
        primary_color = get_theme_color("primary")
        warning_color = get_theme_color("warning")
        error_color = get_theme_color("error")
        accent_color = get_theme_color("accent")
        
        # Row 0: three top cards (reuse existing labels for values)
        sales_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=primary_color,
        )
        sales_card.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        sales_title = ctk.CTkLabel(
            sales_card,
            text="Sales Today",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=primary_color,
        )
        sales_title.pack(padx=16, pady=(14, 4), anchor="n")
        self.sales_label = ctk.CTkLabel(
            sales_card,
            text="Sales: 0",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.sales_label.pack(padx=16, pady=(0, 12), anchor="n")

        revenue_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=card_colors.get("revenue", primary_color),
        )
        revenue_card.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        revenue_title = ctk.CTkLabel(
            revenue_card,
            text="Total Revenue",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=card_colors.get("revenue", primary_color),
        )
        revenue_title.pack(padx=16, pady=(14, 4), anchor="n")
        self.revenue_label = ctk.CTkLabel(
            revenue_card,
            text="Revenue: 0.00",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.revenue_label.pack(padx=16, pady=(0, 12), anchor="n")

        profit_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=warning_color,
        )
        profit_card.grid(row=0, column=2, sticky="nsew", padx=6, pady=6)
        profit_title = ctk.CTkLabel(
            profit_card,
            text="Profit Today",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=warning_color,
        )
        profit_title.pack(padx=16, pady=(14, 4), anchor="n")
        self.profit_label = ctk.CTkLabel(
            profit_card,
            text="Profit: ₨0.00",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.profit_label.pack(padx=16, pady=(0, 12), anchor="n")

        # Row 1: low stock / top items + today's summary card
        low_stock_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=error_color,
        )
        low_stock_card.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        low_stock_title = ctk.CTkLabel(
            low_stock_card,
            text="Low Stock / Top Items",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=error_color,
        )
        low_stock_title.pack(padx=16, pady=(10, 4), anchor="w")
        
        # Low stock items label
        self.low_stock_label = ctk.CTkLabel(
            low_stock_card,
            text="Low stock: (none)",
            font=ctk.CTkFont(size=12),
            text_color=error_color,
        )
        self.low_stock_label.pack(padx=16, pady=(4, 2), anchor="w")
        
        # Top items label
        self.top_items_label = ctk.CTkLabel(
            low_stock_card,
            text="Top items: (none)",
            font=ctk.CTkFont(size=12),
        )
        self.top_items_label.pack(padx=16, pady=(2, 12), anchor="w")

        today_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=accent_color,
        )
        today_card.grid(row=1, column=2, sticky="nsew", padx=6, pady=6)
        today_title = ctk.CTkLabel(
            today_card,
            text="Today's Summary",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=accent_color,
        )
        today_title.pack(padx=16, pady=(10, 4), anchor="w")
        refresh_btn = ctk.CTkButton(
            today_card,
            text="Refresh",
            command=self.refresh_summary,
            width=110,
        )
        refresh_btn.pack(padx=16, pady=(4, 10), anchor="w")

        # ---- Quick actions row ----
        actions = ctk.CTkFrame(main)
        actions.grid(row=2, column=0, sticky="ew", padx=0, pady=(4, 8))
        # Center the buttons by making outer columns expand
        actions.columnconfigure(0, weight=1)
        for i in range(1, 6):
            actions.columnconfigure(i, weight=0)
        actions.columnconfigure(6, weight=1)  # Right spacer

        actions_title = ctk.CTkLabel(
            actions,
            text="Quick Actions",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        actions_title.grid(row=0, column=0, columnspan=7, padx=10, pady=(8, 4))

        # Buttons aligned like screenshot, reusing existing navigation targets
        quick_buttons = [
            ("Billing", "billing"),
            ("Products", "products"),
            ("Reports", "reports"),
            ("Upload", "upload"),
            ("Settings", "settings"),
        ]
        for idx, (text, key) in enumerate(quick_buttons, start=1):
            btn = ctk.CTkButton(
                actions,
                text=text,
                command=lambda k=key: self._go(k),
                width=120,
            )
            btn.grid(row=1, column=idx, padx=6, pady=(4, 10), sticky="")

        self.refresh_summary()

    def _go(self, key: str) -> None:
        if self.app is not None:
            self.app.show_frame(key)

    def refresh_summary(self) -> None:
        """Load today's summary stats from the database."""
        today = date.today()

        session = get_session()
        try:
            # Filter invoices created today
            q_invoices = session.query(Invoice).filter(
                func.date(Invoice.created_at) == today.isoformat()
            )

            sales_count = q_invoices.count()

            total_revenue = (
                session.query(func.coalesce(func.sum(Invoice.total_amount), 0.0))
                .filter(func.date(Invoice.created_at) == today.isoformat())
                .scalar()
            )

            # Calculate profit: sum of (sale_price - cost_price) * quantity for all invoice items today
            profit = 0.0
            invoice_items_today = (
                session.query(InvoiceItem)
                .join(InvoiceItem.invoice)
                .join(InvoiceItem.product)
                .filter(func.date(Invoice.created_at) == today.isoformat())
                .all()
            )
            for item in invoice_items_today:
                product = item.product
                sale_price = item.unit_price or 0.0
                cost_price = getattr(product, "cost_price", 0.0) or 0.0
                quantity = item.quantity or 0.0
                profit += (sale_price - cost_price) * quantity

            # Top items by quantity sold today
            top_items = (
                session.query(
                    Product.name,
                    func.sum(InvoiceItem.quantity).label("qty"),
                )
                .join(InvoiceItem.product)
                .join(InvoiceItem.invoice)
                .filter(func.date(Invoice.created_at) == today.isoformat())
                .group_by(Product.id)
                .order_by(func.sum(InvoiceItem.quantity).desc())
                .limit(3)
                .all()
            )
            
            # Get low stock items (stock < 5 for pieces, < 0.1 for weight-based)
            all_products = session.query(Product).filter(Product.is_active == True).all()
            low_stock_items = []
            for product in all_products:
                unit_type = getattr(product, "unit_type", "piece") or "piece"
                stock = product.stock_qty or 0
                threshold = 0.1 if unit_type in ["kg", "g"] else 5
                if stock < threshold and stock > 0:  # Only show if stock > 0 (not out of stock)
                    from utils.units import format_quantity
                    stock_display = format_quantity(stock, unit_type)
                    low_stock_items.append(f"{product.name} ({stock_display})")
            
        finally:
            session.close()

        self.sales_label.configure(text=f"{sales_count}")
        self.revenue_label.configure(text=f"₨{total_revenue:.2f}")
        self.profit_label.configure(text=f" ₨{profit:.2f}")

        # Display low stock items
        if low_stock_items:
            low_stock_text = ", ".join(low_stock_items[:5])  # Limit to 5 items
            if len(low_stock_items) > 5:
                low_stock_text += f" (+{len(low_stock_items) - 5} more)"
            self.low_stock_label.configure(text=f"⚠ Low stock: {low_stock_text}")
        else:
            self.low_stock_label.configure(text="Low stock: (Nothng Here!)")

        # Display top items
        if top_items:
            items_text = ", ".join(f"{name} ({qty:.0f})" for name, qty in top_items)
        else:
            items_text = "(none)"
        self.top_items_label.configure(text=f"Top items: {items_text}")

class AdminDashboardFrame(DashboardFrame):
    pass

class UserDashboardFrame(ctk.CTkFrame):
    def __init__(self, master: ctk.CTk, app=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self.configure(fg_color="transparent")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main = ctk.CTkFrame(self)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(2, weight=0)

        title = ctk.CTkLabel(
            main,
            text="User Dashboard",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, padx=10, pady=(16, 8), sticky="n")

        # Get theme-aware colors for cards
        card_colors = get_card_colors()
        primary_color = get_theme_color("primary")
        error_color = get_theme_color("error")
        accent_color = get_theme_color("accent")
        card_colors = get_card_colors()
        
        cards_container = ctk.CTkFrame(main,fg_color="transparent")
        cards_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 8))
        cards_container.columnconfigure(0, weight=1)
        cards_container.columnconfigure(1, weight=1)
        cards_container.columnconfigure(2, weight=1)

        sales_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=primary_color,
        )
        sales_card.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(
            sales_card,
            text="Sales Today",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=primary_color,
        ).pack(padx=16, pady=(14, 4), anchor="n")
        self.user_sales_label = ctk.CTkLabel(
            sales_card,
            text="Sales: 0",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.user_sales_label.pack(padx=16, pady=(0, 12), anchor="n")

        revenue_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=card_colors.get("revenue", primary_color),
        )
        revenue_card.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(
            revenue_card,
            text="Total Revenue",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=card_colors.get("revenue", primary_color),
        ).pack(padx=16, pady=(14, 4), anchor="n")
        self.user_revenue_label = ctk.CTkLabel(
            revenue_card,
            text="Revenue: 0.00",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.user_revenue_label.pack(padx=16, pady=(0, 12), anchor="n")

        action_card = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=accent_color,
        )
        action_card.grid(row=0, column=2, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(
            action_card,
            text="Actions",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=accent_color,
        ).pack(padx=16, pady=(14, 4), anchor="n")
        ctk.CTkButton(
            action_card,
            text="Start New Sale",
            command=lambda: self._go("billing"),
            width=140,
        ).pack(padx=16, pady=(4, 10), anchor="n")
        
        # Add low stock card for user dashboard
        low_stock_card_user = ctk.CTkFrame(
            cards_container,
            corner_radius=12,
            border_width=2,
            border_color=error_color,
        )
        low_stock_card_user.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=6, pady=6)
        low_stock_title_user = ctk.CTkLabel(
            low_stock_card_user,
            text="Low Stock Items",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=error_color,
        )
        low_stock_title_user.pack(padx=16, pady=(10, 4), anchor="w")
        self.user_low_stock_label = ctk.CTkLabel(
            low_stock_card_user,
            text="Low stock: (none)",
            font=ctk.CTkFont(size=12),
            text_color=error_color,
        )
        self.user_low_stock_label.pack(padx=16, pady=(4, 12), anchor="w")

        actions = ctk.CTkFrame(main)
        actions.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 8))
        # Center the buttons by making outer columns expand
        actions.columnconfigure(0, weight=1)
        for i in range(1, 4):
            actions.columnconfigure(i, weight=0)
        actions.columnconfigure(4, weight=1)  # Right spacer

        for idx, (text, key) in enumerate([
            ("Products", "products"),
            ("Reports", "reports"),
            ("Settings", "settings"),
        ], start=1):
            btn = ctk.CTkButton(
                actions,
                text=text,
                command=lambda k=key: self._go(k),
                width=120,
            )
            btn.grid(row=0, column=idx, padx=6, pady=(8, 10), sticky="")

        self.refresh_user_summary()

    def _go(self, key: str) -> None:
        if self.app is not None:
            self.app.show_frame(key)

    def refresh_user_summary(self) -> None:
        from datetime import date
        today = date.today()
        session = get_session()
        try:
            q = session.query(Invoice)
            if getattr(self.app, "current_user", None):
                q = q.filter(Invoice.user_id == self.app.current_user.id)
            q = q.filter(func.date(Invoice.created_at) == today.isoformat())
            sales_count = q.count()
            revenue = (
                session.query(func.coalesce(func.sum(Invoice.total_amount), 0.0))
                .filter(func.date(Invoice.created_at) == today.isoformat())
                .scalar()
            )
            
            # Get low stock items (stock < 5 for pieces, < 0.1 for weight-based)
            all_products = session.query(Product).filter(Product.is_active == True).all()
            low_stock_items = []
            for product in all_products:
                unit_type = getattr(product, "unit_type", "piece") or "piece"
                stock = product.stock_qty or 0
                threshold = 0.1 if unit_type in ["kg", "g"] else 5
                if stock < threshold and stock > 0:  # Only show if stock > 0 (not out of stock)
                    from utils.units import format_quantity
                    stock_display = format_quantity(stock, unit_type)
                    low_stock_items.append(f"{product.name} ({stock_display})")
        finally:
            session.close()
        self.user_sales_label.configure(text=f"Sales: {sales_count}")
        self.user_revenue_label.configure(text=f"Revenue: {revenue:.2f}")
        
        # Display low stock items
        if low_stock_items:
            low_stock_text = ", ".join(low_stock_items[:5])  # Limit to 5 items
            if len(low_stock_items) > 5:
                low_stock_text += f" (+{len(low_stock_items) - 5} more)"
            self.user_low_stock_label.configure(text=f"⚠ Low stock: {low_stock_text}")
        else:
            self.user_low_stock_label.configure(text="Low stock: (none)")

