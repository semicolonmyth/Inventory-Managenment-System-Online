"""Integration tests for the 80mm thermal receipt PDF generator.

Verifies the real generate_invoice_pdf() output: correct page width (80mm),
single continuous page even for 50+ items, non-empty valid PDF, and graceful
handling of missing customer/fields. Nothing is written outside tmp_path.
"""

import re
import zlib
from pathlib import Path

import pytest

from utils.invoice import generate_invoice_pdf


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _mediabox(path: Path):
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", _read(path))
    assert m, "no /MediaBox found"
    return float(m.group(1)), float(m.group(2))


def _page_count(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", _read(path)))


def _rendered_text(path: Path) -> str:
    """Extract visible text from compressed content streams (drawn strings)."""
    data = _read(path)
    chunks = []
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        if stream[:2] == b"x\x9c":
            try:
                chunks.append(zlib.decompress(stream))
            except Exception:
                continue
    joined = b"".join(chunks).decode("latin-1", "replace")
    return " ".join(re.findall(r"\((.*?)\)\s*Tj", joined))


def _lines(n: int):
    return [
        {"name": f"Product {i}", "sku": f"SKU-{i}",
         "qty": 1 + (i % 3), "unit_type": "piece",
         "unit_price": 10.0 * (i % 7 + 1),
         "total": (1 + (i % 3)) * 10.0 * (i % 7 + 1)}
        for i in range(1, n + 1)
    ]


@pytest.mark.pdf
class TestReceiptPdf:
    def test_single_item_produces_80mm_pdf(self, tmp_path):
        out = tmp_path / "one.pdf"
        generate_invoice_pdf("INV-1", _lines(1), out,
                             customer={"name": "Ali"}, tax_percent=17)
        assert out.exists() and out.stat().st_size > 1000
        assert _read(out)[:5] == b"%PDF-"
        w, _ = _mediabox(out)
        # 80mm == 226.77pt
        assert w == pytest.approx(226.77, abs=0.5)

    def test_long_receipt_stays_one_continuous_page(self, tmp_path):
        out = tmp_path / "many.pdf"
        generate_invoice_pdf("INV-2", _lines(60), out,
                             customer={"name": "Ali", "phone": "0300"},
                             discount_type="Percentage", discount_value=5,
                             tax_percent=17, shipping=50, amount_paid=100)
        assert _page_count(out) == 1, "thermal receipt must be one continuous page"
        _, h = _mediabox(out)
        assert h > 300, "60-item receipt should be tall"

    def test_empty_customer_and_none_fields_do_not_crash(self, tmp_path):
        out = tmp_path / "walkin.pdf"
        generate_invoice_pdf(
            "INV-3",
            [{"name": None, "qty": 2, "unit_price": 5}],  # missing name
            out,
            customer={},  # no customer info
        )
        assert out.exists() and out.stat().st_size > 500
        text = _rendered_text(out)
        for token in ("None", "null", "undefined"):
            assert token not in text, f"leaked {token!r} into rendered receipt"
        assert "Item" in text  # missing name degrades to "Item"

    def test_parent_directory_is_created(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "r.pdf"
        generate_invoice_pdf("INV-4", _lines(1), out)
        assert out.exists()
