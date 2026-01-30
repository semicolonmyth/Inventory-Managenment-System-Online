import customtkinter as ctk
from typing import Optional, Callable
import tkinter.messagebox as messagebox

from db.local_db import get_session
from db.models import Product, StockTransaction

class InventoryActionsDialog(ctk.CTkToplevel):
    """Dialog for special inventory actions: Water Loss, Processing, Help."""
    
    def __init__(self, parent, product_id: int, refresh_callback: Callable):
        super().__init__(parent)
        self.title("Inventory Actions")
        self.geometry("400x450")
        self.resizable(False, False)
        self.grab_set()
        
        self.product_id = product_id
        self.refresh_callback = refresh_callback
        
        # Load product details
        self.product_name = "Unknown"
        self.current_stock = 0.0
        self.current_cost = 0.0
        self.unit_type = "piece"
        
        self._load_product()
        
        # UI Setup
        self.grid_columnconfigure(0, weight=1)
        
        # Title
        title = ctk.CTkLabel(self, text=f"Actions for: {self.product_name}", font=ctk.CTkFont(size=16, weight="bold"))
        title.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        stock_lbl = ctk.CTkLabel(self, text=f"Current Stock: {self.current_stock} {self.unit_type} | Cost: {self.current_cost:.2f}")
        stock_lbl.grid(row=1, column=0, padx=20, pady=(0, 20))
        
        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        
        self.btn_loss = ctk.CTkButton(btn_frame, text="Record Weight/Water Loss", command=self._show_loss_frame)
        self.btn_loss.grid(row=0, column=0, pady=5, sticky="ew")
        
        self.btn_process = ctk.CTkButton(btn_frame, text="Process (Whole -> Fillet)", command=self._show_process_frame)
        self.btn_process.grid(row=1, column=0, pady=5, sticky="ew")
        
        self.btn_help = ctk.CTkButton(btn_frame, text="Help (Roman Urdu)", command=self._show_help_frame, fg_color="#555")
        self.btn_help.grid(row=2, column=0, pady=5, sticky="ew")
        
        # Content Area (Dynamic)
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        self.rowconfigure(3, weight=1)
        
        # Initial View
        self._show_help_frame()

    def _load_product(self):
        session = get_session()
        try:
            p = session.query(Product).get(self.product_id)
            if p:
                self.product_name = p.name
                self.current_stock = p.stock_qty
                self.current_cost = p.cost_price
                self.unit_type = p.unit_type
        finally:
            session.close()

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _show_help_frame(self):
        self._clear_content()
        
        help_text = (
            "KAISE USE KAREIN:\n\n"
            "1. Record Weight/Water Loss:\n"
            "   Agar machli ka wazan paani nikalne ki wajah se\n"
            "   kam ho gaya hai, to is option ko use karein.\n"
            "   Is se stock kam ho jayega aur cost price barh\n"
            "   jayega taake 'Loss' cover ho sake.\n\n"
            "2. Process (Whole -> Fillet):\n"
            "   Agar aap bari machli (Whole) ko kaat kar\n"
            "   choti items (Fillet/Cut pieces) bana rahe\n"
            "   hain, to is option ko use karein.\n"
            "   Bari machli stock se nikal jayegi aur choti\n"
            "   machli stock mein add ho jayegi."
        )
        
        lbl = ctk.CTkLabel(self.content_frame, text=help_text, justify="left", wraplength=340)
        lbl.pack(padx=10, pady=10, expand=True, fill="both")

    def _show_loss_frame(self):
        self._clear_content()
        f = self.content_frame
        
        ctk.CTkLabel(f, text="Water/Processing Loss", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        
        ctk.CTkLabel(f, text="Final Weight (after loss):").pack(pady=(5,0))
        self.ent_final_weight = ctk.CTkEntry(f)
        self.ent_final_weight.pack(pady=5)
        
        btn_calc = ctk.CTkButton(f, text="Calculate & Apply", command=self._apply_loss)
        btn_calc.pack(pady=10)
        
        self.lbl_loss_result = ctk.CTkLabel(f, text="", text_color="yellow")
        self.lbl_loss_result.pack(pady=5)

    def _apply_loss(self):
        try:
            final_wgt = float(self.ent_final_weight.get())
        except ValueError:
            self.lbl_loss_result.configure(text="Invalid number!", text_color="red")
            return
            
        if final_wgt >= self.current_stock:
             self.lbl_loss_result.configure(text="Final weight must be less than current stock.", text_color="red")
             return
             
        loss_qty = self.current_stock - final_wgt
        yield_pct = (final_wgt / self.current_stock) * 100
        
        # Calculate new cost
        # Total value remains same, but spread over less quantity
        # Old Value = 100kg * 10 = 1000
        # New Cost = 1000 / 90kg = 11.11
        total_value = self.current_stock * self.current_cost
        new_cost = total_value / final_wgt if final_wgt > 0 else 0
        
        msg = (
            f"Original Stock: {self.current_stock}\n"
            f"New Stock: {final_wgt}\n"
            f"Loss: {loss_qty:.2f} ({100-yield_pct:.1f}%)\n\n"
            f"Old Cost: {self.current_cost:.2f}\n"
            f"New Cost: {new_cost:.2f}\n\n"
            "Apply details?"
        )
        
        if messagebox.askyesno("Confirm Inventory Adjustment", msg):
            self._save_loss(final_wgt, new_cost, loss_qty)

    def _save_loss(self, new_stock, new_cost, loss_qty):
        session = get_session()
        try:
            p = session.query(Product).get(self.product_id)
            if not p: return
            
            p.stock_qty = new_stock
            p.cost_price = new_cost
            
            # Record transaction
            txn = StockTransaction(
                product_id=p.id,
                change_qty=-loss_qty,
                remaining_stock=new_stock,
                reason="Water/Processing Loss Adjustment"
            )
            session.add(txn)
            session.commit()
            
            messagebox.showinfo("Success", "Stock updated successfully.")
            self.refresh_callback()
            self.destroy()
            
        except Exception as e:
            session.rollback()
            messagebox.showerror("Error", str(e))
        finally:
            session.close()

    def _show_process_frame(self):
        self._clear_content()
        f = self.content_frame
        
        ctk.CTkLabel(f, text="Process Fish (Whole -> Fillet)", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        
        # Source stock to use
        ctk.CTkLabel(f, text=f"Source Qty (Max {self.current_stock}):").pack(pady=(5,0))
        self.ent_src_qty = ctk.CTkEntry(f)
        self.ent_src_qty.pack(pady=5)
        
        # List of other products for target
        ctk.CTkLabel(f, text="Convert TO Product:").pack(pady=(5,0))
        self.target_product_map = {}
        
        session = get_session()
        products = session.query(Product).filter(Product.id != self.product_id, Product.is_active == True).all()
        session.close()
        
        values = [f"{p.name} (ID: {p.id})" for p in products]
        for p in products:
            self.target_product_map[f"{p.name} (ID: {p.id})"] = p
            
        self.combo_target = ctk.CTkComboBox(f, values=values)
        self.combo_target.pack(pady=5)
        
        # Resulting Quantity
        ctk.CTkLabel(f, text="Resulting Quantity (Yield):").pack(pady=(5,0))
        self.ent_res_qty = ctk.CTkEntry(f)
        self.ent_res_qty.pack(pady=5)
        
        btn_calc = ctk.CTkButton(f, text="Process & Transfer", command=self._apply_process)
        btn_calc.pack(pady=10)

    def _apply_process(self):
        try:
            src_qty = float(self.ent_src_qty.get())
            res_qty = float(self.ent_res_qty.get())
            target_str = self.combo_target.get()
        except ValueError:
            messagebox.showerror("Error", "Invalid numbers")
            return
            
        if src_qty <= 0 or res_qty <= 0:
            messagebox.showerror("Error", "Quantities must be positive")
            return
            
        if src_qty > self.current_stock:
             messagebox.showerror("Error", "Not enough source stock")
             return

        target_p = self.target_product_map.get(target_str)
        if not target_p:
            messagebox.showerror("Error", "Select a target product")
            return
            
        # Calculate Value Transfer
        # Value taken from source
        transfer_value = src_qty * self.current_cost
        
        # New cost for target product
        # Current Value of Target Stock + Transferred Value
        # Divided by (Current Target Stock + New Result Stock)
        # However, simpler approach: The new batch costs X.
        # We'll update the target product's WEIGHTED AVERAGE COST if it has stock, 
        # or just set it if it's 0.
        
        new_batch_cost_per_unit = transfer_value / res_qty
        
        msg = (
            f"Convert {src_qty} of {self.product_name}\n"
            f"Into {res_qty} of {target_p.name}\n\n"
            f"Value Transferred: {transfer_value:.2f}\n"
            f"Est. Yield: {(res_qty/src_qty)*100:.1f}%\n"
            f"Cost of new batch: {new_batch_cost_per_unit:.2f}/{target_p.unit_type}\n\n"
            "Proceed?"
        )
        
        if messagebox.askyesno("Confirm Processing", msg):
            self._save_process(target_p.id, src_qty, res_qty, transfer_value)

    def _save_process(self, target_id, src_qty, res_qty, transfer_value):
        session = get_session()
        try:
            # Update Source
            src = session.query(Product).get(self.product_id)
            src.stock_qty -= src_qty
            
            # Update Target
            tgt = session.query(Product).get(target_id)
            
            # Calculate new weighted average cost for target
            current_val = tgt.stock_qty * tgt.cost_price
            new_total_qty = tgt.stock_qty + res_qty
            new_total_val = current_val + transfer_value
            new_avg_cost = new_total_val / new_total_qty if new_total_qty > 0 else 0
            
            tgt.stock_qty = new_total_qty
            tgt.cost_price = new_avg_cost
            
            # Transactions
            t1 = StockTransaction(
                product_id=src.id,
                change_qty=-src_qty,
                remaining_stock=src.stock_qty,
                reason=f"Processed into {tgt.name}"
            )
            t2 = StockTransaction(
                product_id=tgt.id,
                change_qty=res_qty,
                remaining_stock=tgt.stock_qty,
                reason=f"Processed from {src.name}"
            )
            
            session.add(t1)
            session.add(t2)
            session.commit()
            
            messagebox.showinfo("Success", "Processing complete!")
            self.refresh_callback()
            self.destroy()
            
        except Exception as e:
            session.rollback()
            messagebox.showerror("Error", str(e))
        finally:
            session.close()
