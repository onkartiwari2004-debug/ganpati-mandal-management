"""
Payment QR Service
Ganpati Mandal Management System

Purpose:
- Store only ONE current Payment QR image.
- New QR replaces the existing QR.
- QR is NOT stored in Google Sheets.
- No QR history is maintained.
"""

from pathlib import Path
from typing import Optional, Tuple


# ============================================================
# PROJECT STORAGE PATH
# ============================================================

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Payment QR storage directory
QR_DIR = BASE_DIR / "storage" / "payment_qr"

# Only ONE current QR file will exist
QR_FILE = QR_DIR / "current_qr.png"


# ============================================================
# STORAGE INITIALIZATION
# ============================================================

def ensure_qr_storage() -> None:
    """
    Creates the Payment QR storage directory if it does not exist.
    """
    QR_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CHECK CURRENT QR
# ============================================================

def qr_exists() -> bool:
    """
    Checks whether the current Payment QR image exists.

    Returns:
        True  -> QR exists
        False -> QR does not exist
    """
    return QR_FILE.exists() and QR_FILE.is_file()


# ============================================================
# GET CURRENT QR PATH
# ============================================================

def get_qr_path() -> Optional[str]:
    """
    Returns the file path of the current Payment QR.

    Returns:
        QR file path if available.
        None if no QR exists.
    """
    ensure_qr_storage()

    if qr_exists():
        return str(QR_FILE)

    return None


# ============================================================
# SAVE / REPLACE PAYMENT QR
# ============================================================

def save_payment_qr(uploaded_file) -> Tuple[bool, str]:
    """
    Saves the uploaded Payment QR image.

    Behaviour:
    - If no QR exists -> creates current_qr.png
    - If QR already exists -> replaces it
    - No QR history is maintained
    - Nothing is written to Google Sheets

    Args:
        uploaded_file:
            Streamlit UploadedFile object.

    Returns:
        (success, message)
    """

    if uploaded_file is None:
        return False, "Please select a QR image first."

    try:
        # Make sure storage directory exists
        ensure_qr_storage()

        # Allowed image formats
        allowed_types = {
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
        }

        file_type = getattr(uploaded_file, "type", "")

        if file_type not in allowed_types:
            return (
                False,
                "Please upload a PNG, JPG, JPEG, or WEBP image.",
            )

        # Read uploaded file
        file_bytes = uploaded_file.getvalue()

        if not file_bytes:
            return False, "Uploaded QR image is empty."

        # ----------------------------------------------------
        # Replace existing QR
        # ----------------------------------------------------

        with open(QR_FILE, "wb") as file:
            file.write(file_bytes)

        return True, "Payment QR updated successfully."

    except Exception as e:
        return False, f"Failed to save Payment QR: {str(e)}"


# ============================================================
# DELETE CURRENT PAYMENT QR
# ============================================================

def delete_payment_qr() -> Tuple[bool, str]:
    """
    Deletes the current Payment QR image.

    Google Sheets is NOT affected.
    QR history is NOT maintained.
    """

    try:
        if QR_FILE.exists():
            QR_FILE.unlink()
            return True, "Payment QR removed successfully."

        return True, "No Payment QR was available."

    except Exception as e:
        return False, f"Failed to remove Payment QR: {str(e)}"