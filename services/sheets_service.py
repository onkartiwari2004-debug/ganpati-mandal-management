"""
Google Sheets Database Service for Ganpati Mandal Management System.
Handles secure connection via gspread and google-auth, schema validation,
and non-destructive worksheet initialization.
"""

from typing import Dict, List, Tuple, Any, Optional
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Required OAuth Scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Expected Schema Header Definitions matching DATABASE_SCHEMA.md
EXPECTED_SCHEMAS: Dict[str, List[str]] = {
    "Mandal": [
        "mandal_id", "mandal_name", "festival_name", "festival_year",
        "logo_url", "ganpati_img_url", "payment_qr_url",
        "receipt_header", "receipt_footer", "updated_at", "updated_by"
    ],
    "Users": [
        "user_id", "username", "full_name", "email",
        "password_hash", "role", "is_active", "created_at"
    ],
    "Collections": [
        "receipt_no", "donor_name", "building", "flat_no",
        "amount", "payment_mode", "upi_ref_no", "collected_by",
        "collector_name", "date", "time", "remark", "status"
    ],
    "Expenses": [
        "expense_id", "category", "description", "amount",
        "paid_to", "payment_mode", "requested_by", "date",
        "bill_url", "status", "approved_by", "approval_date", "approval_remark"
    ],
    "Settings": [
        "key", "value", "description"
    ],
    "Audit_Log": [
        "log_id", "timestamp", "username", "action", "details", "ip_address"
    ]
}


def get_service_account_credentials() -> Optional[Credentials]:
    """
    Safely retrieves Google Service Account Credentials from Streamlit secrets.
    Does NOT leak secrets in raw logs or exception tracebacks.
    """
    try:
        if not hasattr(st, "secrets") or not st.secrets:
            return None
            
        if "google_service_account" not in st.secrets:
            return None
        
        # Convert Streamlit AttrDict to a standard Python dictionary
        sa_dict = dict(st.secrets["google_service_account"])
        
        # Format private key if needed (handling escaped newlines in TOML)
        if "private_key" in sa_dict and isinstance(sa_dict["private_key"], str):
            sa_dict["private_key"] = sa_dict["private_key"].replace("\\n", "\n")
            
        credentials = Credentials.from_service_account_info(
            sa_dict,
            scopes=SCOPES
        )
        return credentials
    except Exception:
        # Return None on failure without raising or exposing raw credentials
        return None


def get_gspread_client() -> Tuple[Optional[gspread.Client], Optional[str]]:
    """
    Initializes and returns a gspread Client instance.
    Returns (client, error_message).
    """
    credentials = get_service_account_credentials()
    if not credentials:
        return None, "Google Service Account credentials not found in Streamlit secrets ([google_service_account])."
    
    try:
        client = gspread.authorize(credentials)
        return client, None
    except Exception as e:
        return None, f"Failed to authorize Google Sheets API client: {str(e)}"


def get_spreadsheet() -> Tuple[Optional[gspread.Spreadsheet], Optional[str]]:
    """
    Opens and returns the Google Spreadsheet specified in Streamlit secrets.
    Expects 'spreadsheet_id' or 'spreadsheet_name' in st.secrets.
    Returns (spreadsheet_object, error_message).
    """
    client, err = get_gspread_client()
    if err or not client:
        return None, err
    
    spreadsheet_id = None
    spreadsheet_name = None
    
    try:
        if hasattr(st, "secrets") and st.secrets:
            spreadsheet_id = st.secrets.get("spreadsheet_id", None)
            spreadsheet_name = st.secrets.get("spreadsheet_name", None)
    except Exception:
        pass
    
    try:
        if spreadsheet_id and spreadsheet_id != "YOUR_GOOGLE_SPREADSHEET_ID_HERE":
            spreadsheet = client.open_by_key(spreadsheet_id)
            return spreadsheet, None
        elif spreadsheet_name and spreadsheet_name != "YOUR_SPREADSHEET_NAME_HERE":
            spreadsheet = client.open(spreadsheet_name)
            return spreadsheet, None
        else:
            return None, "Spreadsheet ID/Name not configured in Streamlit secrets ('spreadsheet_id')."
    except gspread.exceptions.SpreadsheetNotFound:
        return None, "Spreadsheet not found. Please verify the spreadsheet_id and ensure the Google Service Account email has Edit permissions."
    except Exception as e:
        return None, f"Error accessing spreadsheet: {str(e)}"


def check_db_connection() -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Performs a database health check.
    Returns (is_connected, status_message, spreadsheet_metadata_dict).
    """
    spreadsheet, err = get_spreadsheet()
    if err or not spreadsheet:
        return False, err or "Connection failed", None
    
    try:
        metadata = {
            "title": spreadsheet.title,
            "id": spreadsheet.id,
            "worksheets": [ws.title for ws in spreadsheet.worksheets()]
        }
        return True, "🟢 Connected", metadata
    except Exception as e:
        return False, f"Connected to client but failed to fetch spreadsheet metadata: {str(e)}", None


def validate_schema(spreadsheet: gspread.Spreadsheet) -> Dict[str, Any]:
    """
    Validates whether expected worksheets exist and whether their header rows match DATABASE_SCHEMA.md.
    Does NOT modify any data.
    """
    results = {
        "is_valid": True,
        "missing_sheets": [],
        "header_mismatches": [],
        "sheet_statuses": {}
    }
    
    existing_worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}
    
    for sheet_name, expected_headers in EXPECTED_SCHEMAS.items():
        if sheet_name not in existing_worksheets:
            results["is_valid"] = False
            results["missing_sheets"].append(sheet_name)
            results["sheet_statuses"][sheet_name] = {
                "exists": False,
                "headers_match": False,
                "found_headers": [],
                "expected_headers": expected_headers,
                "status": "❌ Missing Worksheet"
            }
        else:
            ws = existing_worksheets[sheet_name]
            try:
                # Read the first row (headers)
                row_1 = ws.row_values(1)
                # Normalize string headers
                found_headers = [str(h).strip() for h in row_1]
                
                headers_match = (found_headers == expected_headers)
                if not headers_match:
                    results["is_valid"] = False
                    results["header_mismatches"].append(sheet_name)
                
                results["sheet_statuses"][sheet_name] = {
                    "exists": True,
                    "headers_match": headers_match,
                    "found_headers": found_headers,
                    "expected_headers": expected_headers,
                    "status": "🟢 Valid" if headers_match else "⚠️ Header Mismatch"
                }
            except Exception as e:
                results["is_valid"] = False
                results["sheet_statuses"][sheet_name] = {
                    "exists": True,
                    "headers_match": False,
                    "found_headers": [],
                    "expected_headers": expected_headers,
                    "status": f"🔴 Read Error: {str(e)}"
                }
                
    return results


def safe_initialize_missing_sheets(spreadsheet: gspread.Spreadsheet) -> Dict[str, Any]:
    """
    Safely creates missing worksheets and writes the default header row.
    Will NOT delete, overwrite, or clear any existing worksheet or data.
    """
    log = []
    existing_titles = [ws.title for ws in spreadsheet.worksheets()]
    
    for sheet_name, expected_headers in EXPECTED_SCHEMAS.items():
        if sheet_name not in existing_titles:
            try:
                ws = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=len(expected_headers))
                ws.append_row(expected_headers)
                log.append(f"✅ Created missing worksheet '{sheet_name}' with expected headers.")
            except Exception as e:
                log.append(f"❌ Failed to create worksheet '{sheet_name}': {str(e)}")
        else:
            # Check if headers are empty
            ws = spreadsheet.worksheet(sheet_name)
            first_row = ws.row_values(1)
            if not first_row:
                try:
                    ws.append_row(expected_headers)
                    log.append(f"✅ Added missing header row to existing worksheet '{sheet_name}'.")
                except Exception as e:
                    log.append(f"❌ Failed to write headers for '{sheet_name}': {str(e)}")
            else:
                log.append(f"ℹ️ Worksheet '{sheet_name}' already exists. Preserved existing data.")
                
    return {"log": log}
