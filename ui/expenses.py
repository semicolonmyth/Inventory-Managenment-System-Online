import json
from datetime import datetime, timedelta
from typing import Optional, List

import customtkinter as ctk
import tkinter.ttk as ttk

from db.local_db import get_session
from db.models import Expense
from utils.theme_utils import get_theme_color


class ExpensesFrame(ctk.CTkFrame):
    """Expense management screen."""

    def __init__(self, master: ctk.CTk, app=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app

        self.configure(fg_color="transparent")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Outer container
        main = ctk.CTkFrame(self)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        # Style
        style = ttk.Style()
        style.configure(
            "Expenses.Treeview",
            background="white",
            foreground="black",
            fieldbackground="white",
            borderwidth=0,
        )
        style.configure(
            "Expenses.Treeview.Heading",
            font=("TkDefaultFont", 9, "bold"),
        )

        # Header row
        header = ctk.CTkFrame(main)
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
        header.columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header,
            text="Expense Management",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=16, pady=10, sticky="w")

        # Top buttons
        self.add_btn = ctk.CTkButton(
            header,
            text="Add Expense",
            command=self._add_expense,
        )
        self.add_btn.grid(row=0, column=1, padx=(0, 8), pady=10, sticky="e")

        self.refresh_btn = ctk.CTkButton(
            header,
            text="Refresh",
            command=self.load_expenses,
            width=90,
        )
        self.refresh_btn.grid(row=0, column=2, padx=(0, 12), pady=10, sticky="e")

        # Table
        table_frame = ctk.CTkFrame(main)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.table = ttk.Treeview(
            table_frame,
            columns=("date", "title", "category", "amount", "notes"),
            show="headings",
            style="Expenses.Treeview",
        )
        for col, text, width, anchor in [
            ("date", "Date", 100, "w"),
            ("title", "Title", 200, "w"),
            ("category", "Category", 120, "w"),
            ("amount", "Amount", 100, "e"),
            ("notes", "Notes", 250, "w"),
        ]:
            self.table.heading(col, text=text)
            self.table.column(col, width=width, anchor=anchor)

        self.table.grid(row=0, column=0, sticky="nsew")

        # Scrollbar
        scrollbar = ctk.CTkScrollbar(table_frame, orientation="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Footer summary and actions
        footer = ctk.CTkFrame(main)
        footer.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))
        footer.columnconfigure(1, weight=1)

        self.edit_btn = ctk.CTkButton(
            footer,
            text="Edit Expense",
            command=self._edit_expense,
            width=120,
        )
        self.edit_btn.grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")

        self.delete_btn = ctk.CTkButton(
            footer,
            text="Delete",
            command=self._delete_expense,
            fg_color="#e53e3e",
            hover_color="#c53030",
            width=100,
        )
        self.delete_btn.grid(row=0, column=1, padx=6, pady=8, sticky="w")

        self.total_label = ctk.CTkLabel(
            footer,
            text="Total Expenses: 0.00",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.total_label.grid(row=0, column=2, padx=16, pady=8, sticky="e")

        self.load_expenses()

    def _get_selected_id(self) -> Optional[int]:
        selection = self.table.selection()
        if not selection:
            return None
        return int(selection[0])

    def load_expenses(self) -> None:
        """Load expenses from database."""
        for row in self.table.get_children():
            self.table.delete(row)

        session = get_session()
        try:
            expenses = session.query(Expense).order_by(Expense.date.desc()).all()
            total = 0.0
            for e in expenses:
                total += e.amount
                self.table.insert(
                    "",
                    "end",
                    iid=str(e.id),
                    values=(
                        e.date.strftime("%Y-%m-%d"),
                        e.title,
                        e.category or "General",
                        f"{e.amount:.2f}",
                        e.notes or "",
                    ),
                )
            self.total_label.configure(text=f"Total Expenses: {total:.2f}")
        finally:
            session.close()

    def _add_expense(self) -> None:
        self._open_expense_dialog()

    def _edit_expense(self) -> None:
        expense_id = self._get_selected_id()
        if expense_id:
            self._open_expense_dialog(expense_id)

    def _open_expense_dialog(self, expense_id: Optional[int] = None) -> None:
        session = get_session()
        try:
            expense = get_by_id(session, Expense, expense_id) if expense_id else None
        finally:
            session.close()

        win = ctk.CTkToplevel(self)
        win.title("Add Expense" if not expense_id else "Edit Expense")
        win.geometry("400x450")
        win.grab_set()

        # Center window
        win.update_idletasks()
        x = self.winfo_screenwidth() // 2 - 200
        y = self.winfo_screenheight() // 2 - 225
        win.geometry(f"+{x}+{y}")

        ctk.CTkLabel(win, text="Title *", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 0), padx=20, anchor="w")
        title_entry = ctk.CTkEntry(win, width=360)
        title_entry.pack(pady=(5, 10), padx=20)
        if expense: title_entry.insert(0, expense.title)

        ctk.CTkLabel(win, text="Amount *", font=ctk.CTkFont(weight="bold")).pack(padx=20, anchor="w")
        amount_entry = ctk.CTkEntry(win, width=360)
        amount_entry.pack(pady=(5, 10), padx=20)
        if expense: amount_entry.insert(0, str(expense.amount))

        ctk.CTkLabel(win, text="Category", font=ctk.CTkFont(weight="bold")).pack(padx=20, anchor="w")
        category_combo = ctk.CTkComboBox(win, values=["Utility", "Rent", "Salary", "Purchase", "General", "Other"], width=360)
        category_combo.pack(pady=(5, 10), padx=20)
        if expense: category_combo.set(expense.category)
        else: category_combo.set("General")

        ctk.CTkLabel(win, text="Notes", font=ctk.CTkFont(weight="bold")).pack(padx=20, anchor="w")
        notes_entry = ctk.CTkTextbox(win, width=360, height=80)
        notes_entry.pack(pady=(5, 20), padx=20)
        if expense: notes_entry.insert("1.0", expense.notes or "")

        def save() -> None:
            title = title_entry.get().strip()
            amount_str = amount_entry.get().strip()
            category = category_combo.get()
            notes = notes_entry.get("1.0", "end").strip()

            if not title:
                self._show_error("Title is required!")
                return
            try:
                amount = float(amount_str)
                if amount <= 0: raise ValueError()
            except ValueError:
                self._show_error("Please enter a valid amount!")
                return

            session_local = get_session()
            try:
                if expense_id:
                    e = get_by_id(session_local, Expense, expense_id)
                else:
                    e = Expense()
                    session_local.add(e)
                
                e.title = title
                e.amount = amount
                e.category = category
                e.notes = notes
                e.synced = False  # Mark for cloud update
                session_local.commit()
                self.load_expenses()
                win.destroy()
                self._show_toast("Expense saved.")
            except Exception as ex:
                session_local.rollback()
                self._show_error(f"Failed to save: {str(ex)}")
            finally:
                session_local.close()

        save_btn = ctk.CTkButton(win, text="Save Expense", command=save, height=40)
        save_btn.pack(pady=10, padx=20, fill="x")

    def _delete_expense(self) -> None:
        expense_id = self._get_selected_id()
        if not expense_id: return
        
        if not self._confirm("Delete", "Are you sure you want to delete this expense?"):
            return

        session = get_session()
        try:
            e = get_by_id(session, Expense, expense_id)
            if e:
                session.delete(e)
                session.commit()
                self.load_expenses()
                self._show_toast("Expense deleted.")
        except Exception as ex:
            session.rollback()
            self._show_error(f"Failed to delete: {str(ex)}")
        finally:
            session.close()

    def _show_error(self, message: str) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Error")
        win.geometry("300x150")
        win.grab_set()
        ctk.CTkLabel(win, text=message, text_color="red", wraplength=250).pack(pady=20)
        ctk.CTkButton(win, text="OK", command=win.destroy).pack(pady=10)

    def _confirm(self, title: str, message: str) -> bool:
        """Show confirmation dialog and return True/False."""
        result = {"choice": False}

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.grab_set()

        # Center window
        win.update_idletasks()
        x = self.winfo_screenwidth() // 2 - 150
        y = self.winfo_screenheight() // 2 - 75
        win.geometry(f"+{x}+{y}")

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
        # Mimic toast if app supports it
        if hasattr(self.app, "_show_toast"):
            self.app._show_toast(message)
        else:
            print(f"Toast: {message}")
