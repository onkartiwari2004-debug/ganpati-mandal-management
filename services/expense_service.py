"""
Expense & Approval Service
Ganpati Mandal Management System - Phase 6.

Business rules:
- Expenses <= configured threshold are AUTO-APPROVED.
- Expenses > threshold remain PENDING.
- Only President/Treasurer can approve/reject pending expenses.
- Expense records are append-only; approval changes only status fields.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

import streamlit as st

from services.sheets_service import get_spreadsheet


EXPENSES_SHEET = "Expenses"
SETTINGS_SHEET = "Settings"
AUDIT_SHEET = "Audit_Log"

DEFAULT_APPROVAL_THRESHOLD = Decimal("2000.00")

EXPENSE_CATEGORIES = [
    "Pandal",
    "Decoration",
    "Idol",
    "Pooja",
    "Sound",
    "Security",
    "Food",
    "Misc",
]

PAYMENT_MODES = [
    "Cash",
    "UPI",
    "Bank Transfer",
]

VALID_STATUSES = {"PENDING", "APPROVED", "REJECTED"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _parse_amount(value: Any) -> Optional[Decimal]:
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return None

    if amount <= 0:
        return None

    return amount.quantize(Decimal("0.01"))


def _get_worksheet(sheet_name: str):
    spreadsheet, err = get_spreadsheet()

    if err or not spreadsheet:
        raise RuntimeError(
            err or "Google Sheets database connection failed."
        )

    try:
        return spreadsheet.worksheet(sheet_name)
    except Exception as exc:
        raise RuntimeError(
            f"Google Sheets worksheet '{sheet_name}' was not found."
        ) from exc


def get_approval_threshold() -> Decimal:
    """
    Reads auto_approval_threshold from Settings.
    Falls back safely to ₹2,000 if the setting is missing/invalid.
    """
    try:
        worksheet = _get_worksheet(SETTINGS_SHEET)
        records = worksheet.get_all_records()

        for record in records:
            key = _clean(record.get("key")).lower()
            if key == "auto_approval_threshold":
                value = _parse_amount(record.get("value"))
                if value is not None:
                    return value

    except Exception:
        pass

    return DEFAULT_APPROVAL_THRESHOLD


def _next_expense_id(records: List[Dict[str, Any]]) -> str:
    year = datetime.now().year
    prefix = f"EXP-{year}-"
    highest = 0

    for record in records:
        expense_id = _clean(record.get("expense_id"))
        if not expense_id.startswith(prefix):
            continue

        try:
            highest = max(
                highest,
                int(expense_id[len(prefix):]),
            )
        except ValueError:
            continue

    return f"{prefix}{highest + 1:03d}"


def _save_bill(uploaded_file: Any, expense_id: str) -> str:
    """
    Save an uploaded bill into local application storage.

    The current project architecture keeps uploaded media local,
    consistent with the existing Payment QR implementation.
    """
    if uploaded_file is None:
        return ""

    original_name = Path(
        _clean(getattr(uploaded_file, "name", "bill.jpg"))
    ).name

    suffix = Path(original_name).suffix.lower()
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}

    if suffix not in allowed_suffixes:
        raise ValueError(
            "Bill must be PNG, JPG, JPEG, WEBP or PDF."
        )

    storage_dir = (
        Path(__file__).resolve().parent.parent
        / "storage"
        / "expense_bills"
    )
    storage_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (
        f"{expense_id}_{uuid.uuid4().hex[:8]}{suffix}"
    )
    target = storage_dir / safe_name

    target.write_bytes(uploaded_file.getvalue())

    return str(target)


def _audit(
    username: str,
    action: str,
    details: str,
) -> None:
    """Best-effort audit entry; never blocks a financial operation."""
    try:
        worksheet = _get_worksheet(AUDIT_SHEET)

        log_id = f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

        worksheet.append_row(
            [
                log_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                _clean(username),
                action,
                details,
                "",
            ],
            value_input_option="USER_ENTERED",
        )
    except Exception:
        pass


def get_all_expenses() -> List[Dict[str, Any]]:
    try:
        return _get_worksheet(EXPENSES_SHEET).get_all_records()
    except Exception:
        return []


def get_pending_expenses() -> List[Dict[str, Any]]:
    return [
        record
        for record in get_all_expenses()
        if _clean(record.get("status")).upper() == "PENDING"
    ]


def get_own_expenses(requested_by: str) -> List[Dict[str, Any]]:
    username = _clean(requested_by).lower()

    if not username:
        return []

    return [
        record
        for record in get_all_expenses()
        if _clean(record.get("requested_by")).lower() == username
    ]


def validate_expense_data(
    category: str,
    description: str,
    amount: Any,
    paid_to: str,
    payment_mode: str,
    requested_by: str,
    date_value: Any,
) -> Tuple[bool, str]:
    if _clean(category) not in EXPENSE_CATEGORIES:
        return False, "Please select a valid expense category."

    if not _clean(description):
        return False, "Expense description is required."

    if _parse_amount(amount) is None:
        return False, "Expense amount must be greater than ₹0."

    if not _clean(paid_to):
        return False, "Paid To / Vendor is required."

    if _clean(payment_mode) not in PAYMENT_MODES:
        return False, "Please select a valid payment mode."

    if not _clean(requested_by):
        return False, "Requesting user is required."

    if not _clean(date_value):
        return False, "Expense date is required."

    return True, "Valid"


def add_expense(
    category: str,
    description: str,
    amount: Any,
    paid_to: str,
    payment_mode: str,
    requested_by: str,
    date_value: Any,
    bill_file: Any = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    valid, message = validate_expense_data(
        category=category,
        description=description,
        amount=amount,
        paid_to=paid_to,
        payment_mode=payment_mode,
        requested_by=requested_by,
        date_value=date_value,
    )

    if not valid:
        return False, message, None

    try:
        worksheet = _get_worksheet(EXPENSES_SHEET)
        existing = worksheet.get_all_records()

        expense_id = _next_expense_id(existing)
        parsed_amount = _parse_amount(amount)
        threshold = get_approval_threshold()

        if parsed_amount <= threshold:
            status = "APPROVED"
            approved_by = "SYSTEM"
            approval_date = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            approval_remark = (
                f"Auto-approved: amount <= ₹{threshold:.2f}"
            )
        else:
            status = "PENDING"
            approved_by = ""
            approval_date = ""
            approval_remark = ""

        bill_path = _save_bill(
            bill_file,
            expense_id,
        )

        row = [
            expense_id,
            _clean(category),
            _clean(description),
            f"{parsed_amount:.2f}",
            _clean(paid_to),
            _clean(payment_mode),
            _clean(requested_by),
            _clean(date_value),
            bill_path,
            status,
            approved_by,
            approval_date,
            approval_remark,
        ]

        worksheet.append_row(
            row,
            value_input_option="USER_ENTERED",
        )

        st.cache_data.clear()

        record = dict(
            zip(
                [
                    "expense_id",
                    "category",
                    "description",
                    "amount",
                    "paid_to",
                    "payment_mode",
                    "requested_by",
                    "date",
                    "bill_url",
                    "status",
                    "approved_by",
                    "approval_date",
                    "approval_remark",
                ],
                row,
            )
        )

        _audit(
            requested_by,
            "ADD_EXPENSE",
            (
                f"{expense_id}: ₹{parsed_amount:.2f}, "
                f"status={status}"
            ),
        )

        return (
            True,
            (
                f"Expense {expense_id} saved as {status}. "
                f"Approval threshold: ₹{threshold:.2f}."
            ),
            record,
        )

    except Exception as exc:
        return False, f"Failed to save expense: {exc}", None


def _find_expense_row(
    worksheet: Any,
    expense_id: str,
) -> Optional[int]:
    values = worksheet.get_all_values()

    if not values:
        return None

    headers = values[0]
    try:
        id_index = headers.index("expense_id")
    except ValueError:
        return None

    target = _clean(expense_id)

    for row_number, row in enumerate(values[1:], start=2):
        if id_index < len(row) and _clean(row[id_index]) == target:
            return row_number

    return None


def update_expense_decision(
    expense_id: str,
    decision: str,
    approved_by: str,
    approval_remark: str = "",
) -> Tuple[bool, str]:
    """
    Approve or reject a pending expense.

    Only the UI/RBAC layer exposes this to President/Treasurer.
    The service also verifies that the record is currently PENDING.
    """
    normalized = _clean(decision).upper()

    if normalized not in {"APPROVED", "REJECTED"}:
        return False, "Decision must be APPROVED or REJECTED."

    try:
        worksheet = _get_worksheet(EXPENSES_SHEET)
        records = worksheet.get_all_records()

        target = next(
            (
                record
                for record in records
                if _clean(record.get("expense_id")) == _clean(expense_id)
            ),
            None,
        )

        if not target:
            return False, "Expense record not found."

        current_status = _clean(target.get("status")).upper()

        if current_status != "PENDING":
            return False, (
                f"Expense is already {current_status}. "
                "Only PENDING expenses can be decided."
            )

        row_number = _find_expense_row(
            worksheet,
            expense_id,
        )

        if row_number is None:
            return False, "Expense row could not be located."

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headers = worksheet.row_values(1)
        header_map = {
            header: index + 1
            for index, header in enumerate(headers)
        }

        worksheet.update_cell(
            row_number,
            header_map["status"],
            normalized,
        )
        worksheet.update_cell(
            row_number,
            header_map["approved_by"],
            _clean(approved_by),
        )
        worksheet.update_cell(
            row_number,
            header_map["approval_date"],
            now,
        )
        worksheet.update_cell(
            row_number,
            header_map["approval_remark"],
            _clean(approval_remark),
        )

        st.cache_data.clear()

        _audit(
            approved_by,
            "APPROVE_EXPENSE"
            if normalized == "APPROVED"
            else "REJECT_EXPENSE",
            (
                f"{expense_id}: {normalized}. "
                f"{_clean(approval_remark)}"
            ),
        )

        return True, f"{expense_id} marked as {normalized}."

    except Exception as exc:
        return False, f"Failed to update expense: {exc}"


def get_expense_by_id(
    expense_id: str,
) -> Optional[Dict[str, Any]]:
    target = _clean(expense_id)

    for record in get_all_expenses():
        if _clean(record.get("expense_id")) == target:
            return record

    return None