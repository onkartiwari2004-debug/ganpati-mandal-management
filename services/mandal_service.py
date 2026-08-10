"""
Mandal Identity & Configuration Service
for Ganpati Mandal Management System.

Handles Mandal identity/configuration only.
Payment QR is intentionally NOT stored in Google Sheets.
"""

import datetime
from typing import Dict, Any, Optional, Tuple

from services.sheets_service import get_spreadsheet


MANDAL_HEADERS = [
    "mandal_id",
    "mandal_name",
    "festival_name",
    "festival_year",
    "logo_url",
    "ganpati_img_url",
    "payment_qr_url",
    "receipt_header",
    "receipt_footer",
    "updated_at",
    "updated_by",
]


def get_mandal_details() -> Optional[Dict[str, Any]]:
    """Fetch the first Mandal configuration record."""
    spreadsheet, err = get_spreadsheet()

    if err or not spreadsheet:
        return None

    try:
        worksheet = spreadsheet.worksheet("Mandal")
        records = worksheet.get_all_records()

        if not records:
            return None

        return records[0]
    except Exception:
        return None


def save_mandal_details(
    mandal_name: str,
    festival_name: str,
    festival_year: str,
    logo_url: str,
    ganpati_img_url: str,
    receipt_header: str,
    receipt_footer: str,
    updated_by: str,
) -> Tuple[bool, str]:
    """
    Creates or updates the Mandal configuration.

    Payment QR is deliberately written as an empty value because QR
    images are managed separately by payment_qr_service.py.
    """
    spreadsheet, err = get_spreadsheet()

    if err or not spreadsheet:
        return False, err or "Google Sheets database connection failed."

    try:
        worksheet = spreadsheet.worksheet("Mandal")

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        mandal_values = [
            "MANDAL-001",
            mandal_name.strip(),
            festival_name.strip(),
            str(festival_year).strip(),
            logo_url.strip(),
            ganpati_img_url.strip(),
            "",  # Payment QR is NOT stored in Google Sheets.
            receipt_header.strip(),
            receipt_footer.strip(),
            now,
            updated_by.strip(),
        ]

        existing_records = worksheet.get_all_records()

        if existing_records:
            worksheet.update("A2:K2", [mandal_values])
            return True, "Mandal details updated successfully."

        worksheet.append_row(mandal_values)
        return True, "Mandal details saved successfully."

    except Exception as e:
        return False, f"Failed to save Mandal details: {str(e)}"