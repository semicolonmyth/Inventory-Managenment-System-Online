"""Thermal-printer (80mm) receipt PDF generation.

This replaces the earlier A4 invoice layout with a narrow, continuous
receipt suited to a standard 80mm POS thermal printer.

Design notes
------------
* Public API (``generate_invoice_pdf``) keeps the same name and the same
  positional/keyword arguments, so callers in ``ui/new_sale.py`` and
  ``ui/reports.py`` keep working unchanged.
* The receipt is rendered as a SINGLE continuous page whose height is
  measured from the actual content (two-pass render). This avoids the
  trailing blank space a fixed-height page would waste on thermal paper
  and lets 50+ items simply produce a longer roll instead of awkward
  page breaks.
* Colors/fonts/margins/company info live in one constants block.
* All output handles missing/empty fields gracefully (never prints
  "None"/"null"/"undefined").
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

from fpdf import FPDF
from utils.units import format_quantity


class InvoiceLine(Protocol):
    product_name: str
    quantity: float
    unit_price: float


# ---------------------------------------------------------------------------
# Configuration / constants (colors, fonts, margins, company info)
# ---------------------------------------------------------------------------

# Thermal printers are effectively monochrome; keep everything black so the
# output prints reliably on any 80mm device.
TEXT_COLOR = (0, 0, 0)
RULE_COLOR = (0, 0, 0)

FONT_FAMILY = "Helvetica"      # one clean font family (fpdf2 core font)
COMPANY_SIZE = 11              # shop name
BODY_SIZE = 8                  # line items / rows
SMALL_SIZE = 7                 # secondary info
TOTAL_SIZE = 11                # grand total

RECEIPT_WIDTH_MM = 80          # standard 80mm thermal roll
MARGIN_MM = 3                  # left/right/top margin
CONTENT_W = RECEIPT_WIDTH_MM - 2 * MARGIN_MM   # printable width (~74mm)
BOTTOM_PAD_MM = 6              # trailing feed after the last line
MIN_HEIGHT_MM = 60             # never emit a degenerate tiny page
MEASURE_HEIGHT_MM = 4000       # scratch page height used for measuring

CURRENCY = "Rs"
COMPANY_NAME = "Inventory Management System"
COMPANY_ADDRESS = "Main Market, Kasur"
COMPANY_PHONE = "Phone: 0324-4246145"
COMPANY_EMAIL = ""             # fill in when available
COMPANY_TAX_ID = ""            # NTN / GST number, fill in when available
DEVELOPER_NOTE = (
    "Developed by Semicolon | Abdullah Hashmi - 0325-3260029"
)
THANK_YOU = "Thank you for your business!"

LOGO_PATH = Path(__file__).resolve().parent.parent / "Icons" / "Bk_Logo.png"
LOGO_MAX_W = 34                # mm
LOGO_MAX_H = 16                # mm


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

def _clean(text: Any) -> str:
    """Convert any value to a latin-1 safe string; None becomes ''."""
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _to_float(value: Any, default: float = 0.0) -> float:
    """Safe float conversion (never raises, never returns None)."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_money(amount: float) -> str:
    """Currency with thousands separators and 2 decimals, e.g. 1,234.50."""
    return f"{_to_float(amount):,.2f}"


def fmt_number(value: Optional[float]) -> str:
    """Trim trailing zeros for percents/quantities: 5.0 -> '5', 2.5 -> '2.5'."""
    return f"{_to_float(value):g}"


def fmt_date(dt: Optional[datetime]) -> str:
    """Consistent date format: 30 Sep 2026. Empty string when missing."""
    if not isinstance(dt, datetime):
        return ""
    return dt.strftime("%d %b %Y")


def fmt_datetime(dt: Optional[datetime]) -> str:
    """Date + time for receipts: 30 Sep 2026 14:05."""
    if not isinstance(dt, datetime):
        return ""
    return dt.strftime("%d %b %Y %H:%M")


def _get(line: Any, *keys: str, default: Any = None) -> Any:
    """Read the first present key from a dict or object attribute."""
    for key in keys:
        if isinstance(line, dict):
            if line.get(key) not in (None, ""):
                return line[key]
        else:
            value = getattr(line, key, None)
            if value not in (None, ""):
                return value
    return default


_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
    "Eighty", "Ninety",
]


def _words_below_1000(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10])
        n %= 10
    if n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def amount_in_words(amount: float) -> str:
    """Amount in words using the Pakistani numbering system (lakh/crore).

    Returns '' for negative or absurdly large values (graceful fallback).
    """
    amount = _to_float(amount)
    if amount < 0 or amount >= 1_000_000_000:
        return ""
    rupees = int(amount)
    paisa = int(round((amount - rupees) * 100))

    if rupees == 0:
        words = "Zero"
    else:
        groups = []  # (value, scale name), highest scale first
        crore, rem = divmod(rupees, 10_000_000)
        lakh, rem = divmod(rem, 100_000)
        thousand, rem = divmod(rem, 1_000)
        if crore:
            groups.append((crore, "Crore"))
        if lakh:
            groups.append((lakh, "Lakh"))
        if thousand:
            groups.append((thousand, "Thousand"))
        if rem:
            groups.append((rem, ""))
        words = " ".join(f"{_words_below_1000(v)} {s}".strip() for v, s in groups)

    result = f"{words} Rupees"
    if paisa:
        result += f" and {_words_below_1000(paisa)} Paisa"
    return result + " Only"


def _qty_str(qty: float, unit_type: str) -> str:
    """Format quantity consistently with the billing screen."""
    try:
        return format_quantity(qty, unit_type)
    except Exception:
        if unit_type == "kg":
            return f"{qty:.3f}"
        return f"{int(qty)}" if float(qty).is_integer() else f"{qty:.2f}"


# ---------------------------------------------------------------------------
# Low-level drawing primitives
# ---------------------------------------------------------------------------

def _rule(pdf: FPDF, gap: float = 1.5) -> None:
    """Draw a thin horizontal divider across the printable width."""
    pdf.ln(gap)
    y = pdf.get_y()
    pdf.set_draw_color(*RULE_COLOR)
    pdf.set_line_width(0.2)
    pdf.line(MARGIN_MM, y, RECEIPT_WIDTH_MM - MARGIN_MM, y)
    pdf.ln(gap)


def _center(pdf: FPDF, text: str, size: int, bold: bool = False,
            h: float = 4.0) -> None:
    if not text:
        return
    pdf.set_font(FONT_FAMILY, "B" if bold else "", size)
    pdf.set_text_color(*TEXT_COLOR)
    pdf.multi_cell(CONTENT_W, h, _clean(text), align="C",
                   new_x="LMARGIN", new_y="NEXT")


def _kv_row(pdf: FPDF, label: str, value: str, size: int = BODY_SIZE,
            bold: bool = False, h: float = 4.2, label_frac: float = 0.52,
            indent: float = 0.0) -> None:
    """Left label + right-aligned value on one row (skips empty values)."""
    if not value:
        return
    pdf.set_font(FONT_FAMILY, "B" if bold else "", size)
    pdf.set_text_color(*TEXT_COLOR)
    left_w = CONTENT_W * label_frac - indent
    right_w = CONTENT_W - left_w - indent
    if indent:
        pdf.set_x(MARGIN_MM + indent)
    pdf.cell(left_w, h, _clean(label), align="L")
    pdf.cell(right_w, h, _clean(value), align="R",
             new_x="LMARGIN", new_y="NEXT")


def _draw_logo(pdf: FPDF) -> None:
    """Draw the company logo centered, if available (never fails the build)."""
    try:
        if LOGO_PATH.exists():
            from PIL import Image

            with Image.open(LOGO_PATH) as img:
                iw, ih = img.size
            if iw and ih:
                scale = min(LOGO_MAX_W / iw, LOGO_MAX_H / ih)
                w, h = iw * scale, ih * scale
                x = (RECEIPT_WIDTH_MM - w) / 2
                pdf.image(str(LOGO_PATH), x=x, y=pdf.get_y(), w=w, h=h)
                pdf.set_y(pdf.get_y() + h + 1)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Receipt sections (small reusable builders)
# ---------------------------------------------------------------------------

def _render_header(pdf: FPDF) -> None:
    """Logo + company name/address/phone/email/tax id, all centered."""
    _draw_logo(pdf)
    _center(pdf, COMPANY_NAME, COMPANY_SIZE, bold=True, h=5)
    for line_text in (COMPANY_ADDRESS, COMPANY_PHONE, COMPANY_EMAIL,
                      f"NTN/GST: {COMPANY_TAX_ID}" if COMPANY_TAX_ID else ""):
        _center(pdf, line_text, SMALL_SIZE, h=3.6)
    _rule(pdf, 1.5)


def _render_meta(pdf: FPDF, ctx: dict) -> None:
    """Receipt title + invoice number/date/due/status/cashier."""
    _center(pdf, ctx["status_title"], TOTAL_SIZE, bold=True, h=5)
    pdf.ln(0.5)
    _kv_row(pdf, "Invoice #:", ctx["invoice_number"] or "-")
    _kv_row(pdf, "Date:", fmt_datetime(ctx["invoice_date"]))
    if ctx["due_date"]:
        _kv_row(pdf, "Due Date:", fmt_date(ctx["due_date"]))
    _kv_row(pdf, "Status:", ctx["status"])
    if ctx["username"]:
        _kv_row(pdf, "Cashier:", ctx["username"])
    _rule(pdf, 1.5)


def _render_customer(pdf: FPDF, ctx: dict) -> None:
    """Compact 'Bill To' block; falls back to Walk-in Customer."""
    pdf.set_font(FONT_FAMILY, "B", BODY_SIZE)
    pdf.set_text_color(*TEXT_COLOR)
    pdf.cell(CONTENT_W, 4.2, "Bill To:", new_x="LMARGIN", new_y="NEXT")

    entries = ctx["bill_to"]
    pdf.set_font(FONT_FAMILY, "", BODY_SIZE)
    for label, value in entries:
        pdf.set_x(MARGIN_MM)
        pdf.multi_cell(CONTENT_W, 4.0, f"{label}: {_clean(value)}",
                       align="L", new_x="LMARGIN", new_y="NEXT")
    _rule(pdf, 1.5)


def _render_items(pdf: FPDF, ctx: dict) -> None:
    """Item list: name (wrapping) then 'qty x price' left / total right."""
    if not ctx["rows"]:
        _center(pdf, "No items on this receipt.", BODY_SIZE, h=4.5)
        _rule(pdf, 1.5)
        return

    # Column header
    pdf.set_font(FONT_FAMILY, "B", SMALL_SIZE)
    pdf.set_text_color(*TEXT_COLOR)
    pdf.cell(CONTENT_W * 0.62, 4, "ITEM / QTY x PRICE", align="L")
    pdf.cell(CONTENT_W * 0.38, 4, "AMOUNT", align="R",
             new_x="LMARGIN", new_y="NEXT")
    _rule(pdf, 1.0)

    for row in ctx["rows"]:
        # Line 1: item name (wraps without breaking layout)
        pdf.set_font(FONT_FAMILY, "", BODY_SIZE)
        pdf.set_text_color(*TEXT_COLOR)
        pdf.multi_cell(CONTENT_W, 4.0, row["name"], align="L",
                       new_x="LMARGIN", new_y="NEXT")

        # Line 2: qty x unit price (left) ... line total (right)
        pdf.set_font(FONT_FAMILY, "", BODY_SIZE)
        left = f"{row['qty_str']} x {fmt_money(row['price'])}"
        pdf.cell(CONTENT_W * 0.62, 4.0, _clean(left), align="L")
        pdf.cell(CONTENT_W * 0.38, 4.0, fmt_money(row["total"]), align="R",
                 new_x="LMARGIN", new_y="NEXT")

        # Optional per-line discount / tax note
        note_bits = []
        if row["discount"]:
            note_bits.append(f"Disc: {_clean(row['discount'])}")
        if row["tax"]:
            note_bits.append(f"Tax: {_clean(row['tax'])}%")
        if note_bits:
            pdf.set_font(FONT_FAMILY, "I", SMALL_SIZE)
            pdf.set_x(MARGIN_MM + 3)
            pdf.cell(CONTENT_W - 3, 3.6, "  ".join(note_bits), align="L",
                     new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.8)

    _rule(pdf, 1.5)


def _render_totals(pdf: FPDF, ctx: dict) -> None:
    """Subtotal -> discount -> tax -> shipping -> GRAND TOTAL -> paid/balance."""
    _kv_row(pdf, "Subtotal:", f"{CURRENCY} {fmt_money(ctx['subtotal'])}")
    if ctx["discount_amount"] > 0:
        _kv_row(pdf, "Discount:", f"- {CURRENCY} {fmt_money(ctx['discount_amount'])}")
    if ctx["tax_amount"] > 0:
        tax_label = (f"Tax ({fmt_number(ctx['tax_percent'])}%):"
                     if ctx["tax_percent"] else "Tax:")
        _kv_row(pdf, tax_label, f"{CURRENCY} {fmt_money(ctx['tax_amount'])}")
    if ctx["shipping"] > 0:
        _kv_row(pdf, "Shipping:", f"{CURRENCY} {fmt_money(ctx['shipping'])}")

    _rule(pdf, 1.0)
    _kv_row(pdf, "GRAND TOTAL:", f"{CURRENCY} {fmt_money(ctx['grand_total'])}",
            size=TOTAL_SIZE, bold=True, h=6)
    _rule(pdf, 1.0)

    if ctx["amount_paid"] is not None:
        _kv_row(pdf, "Amount Paid:", f"{CURRENCY} {fmt_money(ctx['amount_paid'])}")
    _kv_row(pdf, "Balance Due:", f"{CURRENCY} {fmt_money(ctx['balance_due'])}",
            bold=True)


def _render_amount_in_words(pdf: FPDF, ctx: dict) -> None:
    words = amount_in_words(ctx["grand_total"])
    if not words:
        return
    pdf.ln(1)
    pdf.set_font(FONT_FAMILY, "I", SMALL_SIZE)
    pdf.set_text_color(*TEXT_COLOR)
    pdf.multi_cell(CONTENT_W, 3.6, _clean(words), align="C",
                   new_x="LMARGIN", new_y="NEXT")


def _render_footer(pdf: FPDF, ctx: dict) -> None:
    """Payment method, terms/notes, thank-you and developer credit."""
    _rule(pdf, 1.5)
    method = ctx["payment_method"] or "Cash"
    if ctx["payment_account"]:
        method = f"{method} ({_clean(ctx['payment_account'])})"
    _kv_row(pdf, "Payment:", method)

    if ctx["notes"]:
        pdf.ln(1)
        pdf.set_font(FONT_FAMILY, "", SMALL_SIZE)
        pdf.set_text_color(*TEXT_COLOR)
        pdf.multi_cell(CONTENT_W, 3.6, _clean(ctx["notes"]), align="L",
                       new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    _center(pdf, THANK_YOU, BODY_SIZE, bold=True, h=4.5)
    _center(pdf, DEVELOPER_NOTE, SMALL_SIZE - 1, h=3.4)


def _build_receipt(pdf: FPDF, ctx: dict) -> None:
    """Draw the full receipt. Called twice: once to measure, once for real."""
    _render_header(pdf)
    _render_meta(pdf, ctx)
    if ctx["bill_to"]:
        _render_customer(pdf, ctx)
    _render_items(pdf, ctx)
    _render_totals(pdf, ctx)
    _render_amount_in_words(pdf, ctx)
    _render_footer(pdf, ctx)


# ---------------------------------------------------------------------------
# Context preparation (normalize lines + compute totals)
# ---------------------------------------------------------------------------

def _build_context(invoice_number, lines, customer, subtotal, discount_amount,
                   discount_type, discount_value, tax_percent, tax_amount,
                   username, payment_method, payment_account, invoice_date,
                   due_date, due_days, shipping, amount_paid, status,
                   notes) -> dict:
    lines = list(lines or [])
    invoice_date = invoice_date if isinstance(invoice_date, datetime) else datetime.now()
    if not isinstance(due_date, datetime):
        due_date = invoice_date + timedelta(days=due_days) if due_days else None

    # --- Normalize line items ------------------------------------------------
    rows = []
    calc_subtotal = 0.0
    for line in lines:
        name = _clean(_get(line, "name", "product_name", default="Item")) or "Item"
        sku = _clean(_get(line, "sku", default=""))
        unit_type = _clean(_get(line, "unit_type", default="piece")) or "piece"
        qty = _to_float(_get(line, "qty", "quantity", default=0))
        price = _to_float(_get(line, "unit_price", default=0))
        total = _to_float(_get(line, "total", "total_price", default=None),
                          default=qty * price)
        calc_subtotal += total
        rows.append({
            "name": f"{name} [{sku}]" if sku else name,
            "qty_str": _qty_str(qty, unit_type),
            "price": price,
            "total": total,
            "discount": _clean(_get(line, "discount", default="")),
            "tax": _clean(_get(line, "tax_percent", default="")),
        })

    if subtotal is None:
        subtotal = calc_subtotal
    subtotal = _to_float(subtotal)

    # --- Discount / tax / grand total (same logic as before) -----------------
    if discount_amount is None:
        if discount_type == "Percentage" and discount_value:
            discount_amount = subtotal * (_to_float(discount_value) / 100.0)
        elif discount_type == "Fixed" and discount_value:
            discount_amount = min(_to_float(discount_value), subtotal)
        else:
            discount_amount = 0.0
    discount_amount = max(_to_float(discount_amount), 0.0)

    amount_after_discount = subtotal - discount_amount
    if tax_amount is None:
        tax_amount = (amount_after_discount * (_to_float(tax_percent) / 100.0)
                      if tax_percent else 0.0)
    tax_amount = _to_float(tax_amount)
    shipping = _to_float(shipping)

    grand_total = amount_after_discount + tax_amount + shipping
    paid = _to_float(amount_paid) if amount_paid is not None else None
    balance_due = grand_total - (paid or 0.0)

    if status:
        status = _clean(status)
    elif paid is None or paid <= 0:
        status = "Unpaid"
    elif paid >= grand_total - 0.005:
        status = "Paid"
    else:
        status = "Partially Paid"

    # --- Bill To entries (skip anything empty) -------------------------------
    customer = customer or {}
    bill_fields = (("Name", "name"), ("Phone", "phone"), ("Email", "email"),
                   ("Address", "address"), ("Tax ID", "tax_id"))
    bill_to = [(label, _clean(customer.get(key)))
               for label, key in bill_fields if customer.get(key)]

    return {
        "invoice_number": _clean(invoice_number),
        "status_title": "PAID RECEIPT" if status == "Paid" else "RECEIPT",
        "invoice_date": invoice_date,
        "due_date": due_date,
        "status": status,
        "username": _clean(username),
        "payment_method": _clean(payment_method),
        "payment_account": _clean(payment_account),
        "notes": _clean(notes),
        "bill_to": bill_to,
        "rows": rows,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "tax_percent": tax_percent,
        "tax_amount": tax_amount,
        "shipping": shipping,
        "grand_total": grand_total,
        "amount_paid": paid,
        "balance_due": balance_due,
    }


def _new_pdf(height_mm: float) -> FPDF:
    pdf = FPDF(orientation="P", unit="mm",
               format=(RECEIPT_WIDTH_MM, height_mm))
    pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
    pdf.set_auto_page_break(auto=False)  # continuous roll, no page breaks
    pdf.add_page()
    return pdf


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

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
    invoice_date: Optional[datetime] = None,
    due_date: Optional[datetime] = None,
    due_days: int = 0,
    shipping: float = 0.0,
    amount_paid: Optional[float] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Generate an 80mm thermal-printer receipt PDF.

    The signature is unchanged from the previous invoice generator, so all
    existing callers keep working. New optional kwargs (invoice_date,
    due_date, due_days, shipping, amount_paid, status, notes) are additive.

    Args:
        invoice_number: Invoice/receipt number (e.g., INV-000123)
        lines: Iterable of line items (dicts or objects)
        output_path: Path to save the PDF
        customer: Optional dict (name, phone, email, address, tax_id, uid)
        subtotal: Optional subtotal (calculated from lines when omitted)
        discount_amount: Optional discount amount (calculated when omitted)
        discount_type: "Percentage" or "Fixed" (used when amount omitted)
        discount_value: Discount percentage or fixed amount
        tax_percent: Tax percentage (GST/VAT)
        tax_amount: Tax amount (calculated when omitted)
        username: Cashier username
        payment_method: "Cash" or "Online"
        payment_account: Account name when Online
        invoice_date: Receipt date (defaults to now)
        due_date: Explicit due date (defaults to invoice_date + due_days)
        due_days: Days until due when due_date is not given
        shipping: Shipping charges (0 by default)
        amount_paid: Amount already paid (None hides Paid/Balance detail)
        status: Payment status text (auto-derived when omitted)
        notes: Optional free-text note printed above the thank-you line
    """
    ctx = _build_context(
        invoice_number, lines, customer, subtotal, discount_amount,
        discount_type, discount_value, tax_percent, tax_amount, username,
        payment_method, payment_account, invoice_date, due_date, due_days,
        shipping, amount_paid, status, notes,
    )

    # Pass 1: render onto a tall scratch page to measure the real height.
    measure = _new_pdf(MEASURE_HEIGHT_MM)
    _build_receipt(measure, ctx)
    height = max(min(measure.get_y() + BOTTOM_PAD_MM, MEASURE_HEIGHT_MM),
                 MIN_HEIGHT_MM)

    # Pass 2: render the final receipt sized exactly to its content.
    pdf = _new_pdf(height)
    pdf.set_title(f"Receipt {_clean(invoice_number)}")
    pdf.set_author(_clean(COMPANY_NAME))
    _build_receipt(pdf, ctx)

    # --- Save (parent dirs created; last-resort fallback to bare filename) ---
    out_path = Path(output_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(out_path))
    except OSError:
        pdf.output(out_path.name)
