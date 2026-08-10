"""
Authentication & Security Service for Ganpati Mandal Management System.
Handles bcrypt password hashing, credential verification, and secure initial user seeding.
"""

import datetime
import secrets
from typing import Dict, List, Tuple, Any, Optional
import streamlit as st
import bcrypt
from services.sheets_service import get_spreadsheet


def hash_password(password: str) -> str:
    """
    Hashes a plain text password using bcrypt with a random salt.
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verifies a plain text password against a stored bcrypt hash.
    Handles format errors gracefully without crashing.
    """
    try:
        if not password or not password_hash:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def get_all_users() -> List[Dict[str, Any]]:
    """
    Fetches all user records from the Google Sheets 'Users' worksheet.
    Returns a list of dictionary user records.
    """
    spreadsheet, err = get_spreadsheet()
    if err or not spreadsheet:
        return []
    
    try:
        ws = spreadsheet.worksheet("Users")
        records = ws.get_all_records()
        return records
    except Exception:
        return []


def authenticate_user(username_or_email: str, password: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Authenticates a user by Username or Email and Password.
    Returns (user_dict, status_message).
    Uses generic error message ('Invalid username or password.') for security.
    """
    if not username_or_email or not password:
        return None, "Invalid username or password."
    
    query = username_or_email.strip().lower()
    users = get_all_users()
    
    matching_user = None
    for u in users:
        u_name = str(u.get("username", "")).strip().lower()
        u_email = str(u.get("email", "")).strip().lower()
        if query == u_name or query == u_email:
            matching_user = u
            break
            
    if not matching_user:
        return None, "Invalid username or password."
    
    # Check active status
    is_active_val = str(matching_user.get("is_active", "")).strip().upper()
    if is_active_val not in ["TRUE", "1", "YES"]:
        return None, "Invalid username or password."
    
    # Verify password hash
    stored_hash = str(matching_user.get("password_hash", ""))
    if verify_password(password, stored_hash):
        user_dict = {
            "user_id": str(matching_user.get("user_id", "")),
            "username": str(matching_user.get("username", "")),
            "full_name": str(matching_user.get("full_name", "")),
            "email": str(matching_user.get("email", "")),
            "role": str(matching_user.get("role", "")).upper()
        }
        # Log successful login to Audit_Log if possible
        log_audit_event(user_dict["username"], "LOGIN", "User logged in successfully")
        return user_dict, "Success"
    else:
        return None, "Invalid username or password."


def log_audit_event(username: str, action: str, details: str) -> None:
    """
    Appends an immutable log entry to the Google Sheets 'Audit_Log' worksheet.
    """
    spreadsheet, err = get_spreadsheet()
    if not spreadsheet:
        return
    try:
        ws = spreadsheet.worksheet("Audit_Log")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_id = f"LOG-{secrets.token_hex(4).upper()}"
        ws.append_row([log_id, timestamp, username, action, details, "127.0.0.1"])
    except Exception:
        pass


def seed_initial_users_if_empty(spreadsheet: Any) -> Dict[str, Any]:
    """
    Safely seeds initial default user accounts ONLY IF the 'Users' worksheet has zero data rows.
    Never overwrites, resets, or duplicates existing users.
    Zero passwords hardcoded in Python source code.
    """
    try:
        ws = spreadsheet.worksheet("Users")
        all_values = ws.get_all_values()
        
        # If there are data rows (length > 1), skip seeding completely
        if len(all_values) > 1:
            return {
                "seeded": False,
                "reason": "Users worksheet already contains user accounts. Seeding skipped.",
                "credentials": []
            }
            
        # Get custom initial passwords from secrets if configured, otherwise generate temporary secure passwords
        initial_passwords = {}
        if hasattr(st, "secrets") and "initial_users" in st.secrets:
            secrets_cfg = st.secrets["initial_users"]
            initial_passwords["app_owner"] = secrets_cfg.get("app_owner_password")
            initial_passwords["president"] = secrets_cfg.get("president_password")
            initial_passwords["treasurer"] = secrets_cfg.get("treasurer_password")
            initial_passwords["collector1"] = secrets_cfg.get("collector1_password")
            initial_passwords["viewer1"] = secrets_cfg.get("viewer1_password")

        def get_or_gen_pass(role_key: str) -> str:
            val = initial_passwords.get(role_key)
            if val and len(val.strip()) > 0:
                return val.strip()
            # Generate 12-char secure random token
            return secrets.token_urlsafe(9)

        passwords_map = {
            "app_owner": get_or_gen_pass("app_owner"),
            "president": get_or_gen_pass("president"),
            "treasurer": get_or_gen_pass("treasurer"),
            "collector1": get_or_gen_pass("collector1"),
            "viewer1": get_or_gen_pass("viewer1")
        }

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        default_users = [
            ["USR-101", "app_owner", "System Technical Owner", "owner@mandal.local", hash_password(passwords_map["app_owner"]), "APP_OWNER", "TRUE", now_str],
            ["USR-102", "president", "Mandal President (अध्यक्ष)", "president@mandal.local", hash_password(passwords_map["president"]), "PRESIDENT", "TRUE", now_str],
            ["USR-103", "treasurer", "Mandal Treasurer", "treasurer@mandal.local", hash_password(passwords_map["treasurer"]), "TREASURER", "TRUE", now_str],
            ["USR-104", "collector1", "Donation Collector 1", "collector1@mandal.local", hash_password(passwords_map["collector1"]), "COLLECTOR", "TRUE", now_str],
            ["USR-105", "viewer1", "Public Auditor / Viewer", "viewer1@mandal.local", hash_password(passwords_map["viewer1"]), "VIEWER", "TRUE", now_str]
        ]

        # Batch append rows
        ws.append_rows(default_users)

        # Log audit entry
        log_audit_event("SYSTEM", "INITIAL_USER_SEEDING", "Seeded 5 default role accounts into empty Users sheet")

        credentials_info = [
            {"username": "app_owner", "role": "APP_OWNER", "temp_password": passwords_map["app_owner"]},
            {"username": "president", "role": "PRESIDENT", "temp_password": passwords_map["president"]},
            {"username": "treasurer", "role": "TREASURER", "temp_password": passwords_map["treasurer"]},
            {"username": "collector1", "role": "COLLECTOR", "temp_password": passwords_map["collector1"]},
            {"username": "viewer1", "role": "VIEWER", "temp_password": passwords_map["viewer1"]}
        ]

        return {
            "seeded": True,
            "reason": "Successfully seeded 5 default user accounts.",
            "credentials": credentials_info
        }

    except Exception as e:
        return {
            "seeded": False,
            "reason": f"Failed to seed users: {str(e)}",
            "credentials": []
        }
