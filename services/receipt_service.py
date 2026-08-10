"""
Receipt PDF Service
Ganpati Mandal Management System.

Creates a single-page donation receipt PDF from a saved collection
record and current Mandal identity settings.
"""

from io import BytesIO
from typing import Any, Dict, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_receipt_pdf(
    collection: Dict[str, Any],
    mandal: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Build a printable/downloadable donation receipt PDF."""
    mandal = mandal or {}

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    left = 22 * mm
    right = width - 22 * mm
    top = height - 22 * mm

    mandal_name = _text(mandal.get("mandal_name")) or "Ganpati Mandal"
    festival_name = _text(mandal.get("festival_name"))
    festival_year = _text(mandal.get("festival_year"))
    receipt_header = _text(mandal.get("receipt_header")) or "Donation Receipt"
    receipt_footer = (
        _text(mandal.get("receipt_footer"))
        or "Thank you for your valuable contribution."
    )

    pdf.setTitle(f"Donation Receipt - {_text(collection.get('receipt_no'))}")

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(width / 2, top, mandal_name)

    y = top - 9 * mm
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, y, receipt_header)

    if festival_name or festival_year:
        festival_line = " | ".join(
            value for value in [festival_name, festival_year] if value
        )
        y -= 7 * mm
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(width / 2, y, festival_line)

    y -= 7 * mm
    pdf.line(left, y, right, y)

    y -= 10 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, y, "Receipt No:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left + 30 * mm, y, _text(collection.get("receipt_no")))

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(width / 2, y, "Date:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(width / 2 + 14 * mm, y, _text(collection.get("date")))

    y -= 15 * mm
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left, y, "Donor Details")

    y -= 8 * mm
    details = [
        ("Donor Name", collection.get("donor_name")),
        ("Building", collection.get("building")),
        ("Flat No.", collection.get("flat_no")),
        ("Amount", f"Rs. {_text(collection.get('amount'))}"),
        ("Payment Mode", collection.get("payment_mode")),
    ]

    if _text(collection.get("upi_ref_no")):
        details.append(("UPI Reference", collection.get("upi_ref_no")))

    for label, value in details:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, f"{label}:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left + 42 * mm, y, _text(value))
        y -= 7 * mm

    y -= 5 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, y, "Collected By:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left + 42 * mm, y, _text(collection.get("collector_name")))

    if _text(collection.get("remark")):
        y -= 7 * mm
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, "Remark:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left + 42 * mm, y, _text(collection.get("remark")))

    y -= 16 * mm
    pdf.rect(left, y - 12 * mm, right - left, 16 * mm)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(
        left + 6 * mm,
        y - 6 * mm,
        f"Received Amount: Rs. {_text(collection.get('amount'))}",
    )

    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(width / 2, 35 * mm, receipt_footer)
    pdf.drawCentredString(width / 2, 25 * mm, "Ganpati Bappa Morya!")

    pdf.save()
    return buffer.getvalue()
