from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Protocol

from fpdf import FPDF
from utils.units import format_quantity


class InvoiceLine(Protocol):
    product_name: str
    quantity: float
    unit_price: float


def generate_invoice_pdf(
    invoice_number: str,
    lines: Iterable[InvoiceLine],
    output_path: Path,
    customer: Optional[dict] = None,
    subtotal: Optional[float] = None,
    discount_amount: Optional[float] = None,
    discount_type: str = "Percentage",
    discount_value: Optional[float] = None,
    tax_percent: Optional[float] = None,
    tax_amount: Optional[float] = None,
    username: Optional[str] = None,
    payment_method: str = "Cash",
    payment_account: Optional[str] = None,
) -> None:
    """Generate enhanced invoice PDF with customer info, discounts, and tax.

    Args:
        invoice_number: Invoice number (e.g., INV-000123)
        lines: Iterable of invoice line items
        output_path: Path to save PDF
        customer: Optional dict with customer info (name, phone, email, address, uid)
        subtotal: Optional subtotal (calculated if not provided)
        discount_amount: Optional discount amount (calculated if not provided)
        discount_type: "Percentage" or "Fixed"
        discount_value: Discount percentage or fixed amount
        tax_percent: Tax percentage (GST/VAT)
        tax_percent: Tax percentage (GST/VAT)
        tax_amount: Tax amount (calculated if not provided)
        payment_method: "Cash" or "Online"
        payment_account: Account name if Online
    """

    # Thermal printer format: 80mm width
    # Margins: 2mm to maximize space
    pdf = FPDF(orientation="P", unit="mm", format=(80, 297)) # 297mm height (A4 height) but continuous usually. 
    # For thermal, page height usually doesn't matter as it cuts, but we need enough space.
    # Let's set auto page break false or large height? FPDF standard is page based. 
    # We'll stick to a long format. standard thermal rolls don't equate to A4.
    # But FPDF requires a format. 80x200 should be fine for most receipts, or dynamic.
    pdf = FPDF(orientation="P", unit="mm", format=(80, 250))
    pdf.set_auto_page_break(auto=True, margin=5)
    pdf.add_page()
    pdf.set_margins(3, 3, 3)

    # Helper to clean text
    def clean(text):
        return str(text).encode('latin-1', 'replace').decode('latin-1')

    # Helper function to extract values
    def get_line_value(line, key):
        if isinstance(line, dict):
            return line.get(key, 0)
        return getattr(line, key, 0)

    # --- HEADER ---
    pdf.set_font("Courier", "B", 12)
    pdf.set_text_color(0, 0, 0)
    
    # Shop Name (Bold Uppercase)
    pdf.cell(0, 5, "BILAL KASUR FOODS", ln=1, align="C")
    
    pdf.set_font("Courier", size=8)
    pdf.cell(0, 4, "Main Market, Kasur", ln=1, align="C") # Generic address if not provided
    pdf.cell(0, 4, "Phone: 0324-4446145", ln=1, align="C")
    
    # Divider
    pdf.cell(0, 4, "*" * 42, ln=1, align="C")
    
    # Title
    pdf.set_font("Courier", "B", 10)
    pdf.cell(0, 6, "CASH RECEIPT", ln=1, align="C")
    
    # Date and Invoice Info
    pdf.set_font("Courier", size=8)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 4, f"Date: {date_str}", ln=1, align="L")
    pdf.cell(0, 4, f"Inv #: {invoice_number}", ln=1, align="L")
    if username:
        pdf.cell(0, 4, f"Cashier: {username}", ln=1, align="L")
    
    if customer:
        pdf.ln(2)
        cust_name = str(customer.get("name", ""))[:25]
        pdf.cell(0, 4, f"Customer: {cust_name}", ln=1, align="L")

    # Divider line
    pdf.ln(2)
    pdf.line(2, pdf.get_y(), 78, pdf.get_y())
    pdf.ln(2)

    # --- ITEMS ---
    # Headers: Description (Left) ...... Price (Right)
    # Actually, standard POS usually has Qty x Price
    # "Table format: Description (left aligned) Price (right aligned)"
    
    # We will do:
    # Item Name
    #   Qty x UnitPrice                    Total
    
    # Calculate totals if not provided
    if subtotal is None:
        subtotal = 0.0
        for line in lines:
             qty = float(get_line_value(line, "quantity") or getattr(line, "qty", 0))
             price = float(get_line_value(line, "unit_price") or getattr(line, "unit_price", 0))
             # check if total is in line
             if isinstance(line, dict):
                 line_total = float(line.get("total", qty * price))
             else:
                 line_total = float(getattr(line, "total", qty * price))
             subtotal += line_total

    pdf.set_font("Courier", size=8)
    
    for line in lines:
        # Get Data
        if isinstance(line, dict):
            name = str(line.get("name", "Item"))
            qty = float(line.get("qty", 0))
            price = float(line.get("unit_price", 0)) # Using displayed unit price
            total = float(line.get("total", qty * price))
            unit_type = line.get("unit_type", "piece")
        else:
            name = str(getattr(line, "product_name", "Item"))
            qty = float(getattr(line, "quantity", 0))
            price = float(getattr(line, "unit_price", 0))
            total = float(getattr(line, "total", qty * price))
            unit_type = getattr(line, "unit_type", "piece")

        # Format Qty
        qty_str = format_quantity(qty, unit_type)
        if unit_type == 'piece':
             qty_str = f"{int(qty)}"
        elif unit_type == 'kg':
             qty_str = f"{qty:.3f}"
        
        # Row 1: Item Name
        pdf.multi_cell(0, 4, clean(name), align="L")
        
        # Row 2: Qty x Price ... Total
        # detailed line: "1.000 x 100.00"
        detail = f"{qty_str} x {price:.2f}"
        
        # We want Total right aligned. 
        # FPDF doesn't support mixed alignment easily in one cell without X manipulation.
        # We print detail left, calculate X for total.
        
        current_y = pdf.get_y()
        pdf.cell(40, 4, detail, align ="L")
        
        # Move to end for total
        pdf.set_xy(50, current_y) 
        pdf.cell(28, 4, f"{total:.2f}", align="R")
        pdf.ln()

    # Divider
    pdf.ln(2)
    pdf.cell(0, 4, "-" * 42, ln=1, align="C")
    pdf.ln(1)

    # --- FOOTER ---
    
    # Helper for totals row
    def print_total_row(label, value, bold=False):
        pdf.set_font("Courier", "B" if bold else "", 9 if bold else 8)
        pdf.cell(45, 5, label, align="R")
        pdf.cell(30, 5, f"{value:.2f}", align="R", ln=1)

    print_total_row("Subtotal:", subtotal)
    
    # Discount
    if discount_amount is None:
        if discount_type == "Percentage" and discount_value:
            discount_amount = subtotal * (discount_value / 100.0)
        elif discount_type == "Fixed" and discount_value:
            discount_amount = min(discount_value, subtotal)
        else:
            discount_amount = 0.0

    if discount_amount > 0:
         print_total_row("Discount:", -discount_amount)

    # Tax
    amount_after_discount = subtotal - discount_amount
    if tax_amount is None:
        if tax_percent:
            tax_amount = amount_after_discount * (tax_percent / 100.0)
        else:
            tax_amount = 0.0
            
    if tax_amount > 0:
        print_total_row(f"Tax ({tax_percent}%):", tax_amount)

    grand_total = amount_after_discount + tax_amount

    # TOTAL
    pdf.ln(1)
    pdf.set_font("Courier", "B", 12)
    pdf.cell(40, 6, "TOTAL", align="R")
    pdf.cell(35, 6, f"{grand_total:.2f}", align="R", ln=1)
    
    pdf.ln(2)
    pdf.set_font("Courier", size=8)
    
    # Payment Info
    pdf.cell(40, 4, "Payment Method:", align="L")
    
    method_display = payment_method
    if payment_method == "Online" and payment_account:
        method_display = f"{payment_account}"
    
    pdf.cell(35, 4, method_display, align="R", ln=1)
    
    # Placeholders for Change/Card as requested (Visual only)
    # pdf.cell(40, 4, "Change:", align="L") 
    # pdf.cell(35, 4, "0.00", align="R", ln=1)
    
    pdf.ln(4)
    pdf.cell(0, 4, "THANK YOU!", align="C", ln=1)
    
    pdf.ln(2)
    pdf.set_font("Courier", "I", 7)
    pdf.multi_cell(0, 3, "this software is Developed by Semicolon, Contact Us : 03253260029", align="C")

    # Save
    try:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    pdf.output(str(output_path))
