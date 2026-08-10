"""
Collections & Donation Service
Ganpati Mandal Management System

Phase 4 - Collection & Receipt foundation.

Responsibilities:
- Validate collection input
- Generate the next receipt number
- Append collection records to Google Sheets
- Read all collection records
- Read only the current user's collection records
- Keep collection records append-only (no delete/update helpers)
"""

import datetime
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from services.sheets_service import get_spreadsheet


COLLECTIONS_SHEET = "Collections"

COLLECTION_HEADERS = [
    "receipt_no",
    "donor_name",
    "building",
    "flat_no",
    "amount",
    "payment_mode",
    "upi_ref_no",
    "collected_by",
    "collector_name",
    "date",
    "time",
    "remark",
    "status",
]

ALLOWED_PAYMENT_MODES = {"CASH", "UPI"}
ACTIVE_STATUS = "RECORDED"


def _clean(value: Any) -> str:
    """Convert a value to a trimmed string."""
    return str(value or "").strip()


def _normalize_payment_mode(payment_mode: str) -> str:
    """Normalize payment mode to CASH or UPI."""
    return _clean(payment_mode).upper()


def _parse_amount(amount: Any) -> Optional[Decimal]:
    """Return a positive Decimal amount, otherwise None."""
    try:
        value = Decimal(str(amount).strip())
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return None

    if value <= 0:
        return None

    return value.quantize(Decimal("0.01"))


def validate_collection_data(
    donor_name: str,
    building: str,
    flat_no: str,
    amount: Any,
    payment_mode: str,
    upi_ref_no: str = "",
    collected_by: str = "",
    collector_name: str = "",
) -> Tuple[bool, str]:
    """
    Validates a collection before it is written to Google Sheets.

    Rules:
    - Donor name is required.
    - Amount must be greater than zero.
    - Payment mode must be Cash or UPI.
    - UPI reference is required for UPI.
    - Collector identity is required.
    """
    if not _clean(donor_name):
        return False, "Donor name is required."

    if not _clean(building):
        return False, "Building is required."

    if not _clean(flat_no):
        return False, "Flat number is required."

    parsed_amount = _parse_amount(amount)
    if parsed_amount is None:
        return False, "Amount must be a valid value greater than ₹0."

    mode = _normalize_payment_mode(payment_mode)
    if mode not in ALLOWED_PAYMENT_MODES:
        return False, "Payment mode must be Cash or UPI."

    if mode == "UPI" and not _clean(upi_ref_no):
        return False, "UPI reference number is required for UPI payments."

    if not _clean(collected_by):
        return False, "Collector user ID is required."

    if not _clean(collector_name):
        return False, "Collector name is required."

    return True, "Valid"


def _next_receipt_number(records: List[Dict[str, Any]]) -> str:
    """
    Finds the highest existing numeric receipt suffix and increments it.

    Example:
        REC-2026-0001 -> REC-2026-0002

    If there are no valid receipt numbers, numbering starts at 0001.
    """
    year = datetime.datetime.now().year
    prefix = f"REC-{year}-"
    highest = 0

    pattern = re.compile(r"^REC-(\d{4})-(\d+)$", re.IGNORECASE)

    for record in records:
        receipt_no = _clean(record.get("receipt_no"))
        match = pattern.match(receipt_no)
        if not match:
            continue

        receipt_year = int(match.group(1))
        receipt_number = int(match.group(2))

        if receipt_year == year:
            highest = max(highest, receipt_number)

    return f"{prefix}{highest + 1:04d}"


def _get_collections_worksheet():
    """Return the Collections worksheet or raise a useful error."""
    spreadsheet, err = get_spreadsheet()

    if err or not spreadsheet:
        raise RuntimeError(err or "Google Sheets database connection failed.")

    try:
        return spreadsheet.worksheet(COLLECTIONS_SHEET)
    except Exception as exc:
        raise RuntimeError(
            "Collections worksheet was not found. "
            "Initialize the Google Sheets schema first."
        ) from exc


def get_all_collections() -> List[Dict[str, Any]]:
    """
    Fetch all collection records.

    Used by President, Treasurer and App Owner.
    """
    try:
        worksheet = _get_collections_worksheet()
        return worksheet.get_all_records()
    except Exception:
        return []


def get_own_collections(collected_by: str) -> List[Dict[str, Any]]:
    """
    Fetch only collection records created by the supplied user ID.

    Used for Collector's own-history view.
    """
    user_id = _clean(collected_by).lower()

    if not user_id:
        return []

    records = get_all_collections()

    return [
        record
        for record in records
        if _clean(record.get("collected_by")).lower() == user_id
    ]


def add_collection(
    donor_name: str,
    building: str,
    flat_no: str,
    amount: Any,
    payment_mode: str,
    upi_ref_no: str,
    collected_by: str,
    collector_name: str,
    remark: str = "",
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validates and appends one collection entry.

    Collection records are append-only:
    this service intentionally provides no delete/update operation.
    """
    is_valid, message = validate_collection_data(
        donor_name=donor_name,
        building=building,
        flat_no=flat_no,
        amount=amount,
        payment_mode=payment_mode,
        upi_ref_no=upi_ref_no,
        collected_by=collected_by,
        collector_name=collector_name,
    )

    if not is_valid:
        return False, message, None

    try:
        worksheet = _get_collections_worksheet()

        # Read existing records before generating the next receipt number.
        existing_records = worksheet.get_all_records()
        receipt_no = _next_receipt_number(existing_records)

        now = datetime.datetime.now()
        parsed_amount = _parse_amount(amount)
        payment_mode_normalized = _normalize_payment_mode(payment_mode)

        collection_row = [
            receipt_no,
            _clean(donor_name),
            _clean(building),
            _clean(flat_no),
            f"{parsed_amount:.2f}",
            payment_mode_normalized,
            _clean(upi_ref_no) if payment_mode_normalized == "UPI" else "",
            _clean(collected_by),
            _clean(collector_name),
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            _clean(remark),
            ACTIVE_STATUS,
        ]

        worksheet.append_row(
            collection_row,
            value_input_option="USER_ENTERED",
        )

        saved_record = dict(zip(COLLECTION_HEADERS, collection_row))

        return True, f"Collection saved successfully. Receipt: {receipt_no}", saved_record

    except Exception as exc:
        return False, f"Failed to save collection: {str(exc)}", None


def get_collection_by_receipt(receipt_no: str) -> Optional[Dict[str, Any]]:
    """
    Fetch one collection record using its receipt number.
    """
    target = _clean(receipt_no).upper()

    if not target:
        return None

    for record in get_all_collections():
        if _clean(record.get("receipt_no")).upper() == target:
            return record

    return None