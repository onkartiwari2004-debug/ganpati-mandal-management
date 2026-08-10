"""
Role-Based Access Control (RBAC) & Session State Management
for Ganpati Mandal Management System.
"""

from typing import List, Dict, Any, Optional
import streamlit as st

ROLE_APP_OWNER = "APP_OWNER"
ROLE_PRESIDENT = "PRESIDENT"
ROLE_TREASURER = "TREASURER"
ROLE_COLLECTOR = "COLLECTOR"
ROLE_VIEWER = "VIEWER"

ALL_ROLES = [
    ROLE_APP_OWNER,
    ROLE_PRESIDENT,
    ROLE_TREASURER,
    ROLE_COLLECTOR,
    ROLE_VIEWER,
]

PERMISSIONS: Dict[str, List[str]] = {
    "system_diagnostics": [ROLE_APP_OWNER, ROLE_PRESIDENT],
    "manage_mandal_identity": [ROLE_PRESIDENT],

    # Payment QR: President + Treasurer can manage it.
    "manage_payment_qr": [ROLE_PRESIDENT, ROLE_TREASURER],
    "view_payment_qr": [
        ROLE_APP_OWNER,
        ROLE_PRESIDENT,
        ROLE_TREASURER,
        ROLE_COLLECTOR,
    ],

    "user_admin": [ROLE_APP_OWNER, ROLE_PRESIDENT],
    "configure_expense_threshold": [ROLE_PRESIDENT],
    "add_collection": [
        ROLE_APP_OWNER,
        ROLE_PRESIDENT,
        ROLE_TREASURER,
        ROLE_COLLECTOR,
    ],
    "generate_receipt": [
        ROLE_APP_OWNER,
        ROLE_PRESIDENT,
        ROLE_TREASURER,
        ROLE_COLLECTOR,
    ],
    "view_all_collections": [
        ROLE_APP_OWNER,
        ROLE_PRESIDENT,
        ROLE_TREASURER,
    ],
    "view_own_collections": [ROLE_COLLECTOR],
    "submit_expense": [
        ROLE_APP_OWNER,
        ROLE_PRESIDENT,
        ROLE_TREASURER,
        ROLE_COLLECTOR,
    ],
    "approve_expense": [ROLE_PRESIDENT, ROLE_TREASURER],
    "view_dashboard": ALL_ROLES,
    "export_reports": [
        ROLE_APP_OWNER,
        ROLE_PRESIDENT,
        ROLE_TREASURER,
        ROLE_VIEWER,
    ],
    "view_audit_log": [
        ROLE_APP_OWNER,
        ROLE_PRESIDENT,
        ROLE_TREASURER,
    ],
}


def init_session_state() -> None:
    """Initialize Streamlit authentication/session keys."""
    defaults = {
        "authenticated": False,
        "user_id": None,
        "username": None,
        "full_name": None,
        "email": None,
        "role": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def login_session(user_dict: Dict[str, Any]) -> None:
    """Populate session state after successful authentication."""
    st.session_state["authenticated"] = True
    st.session_state["user_id"] = user_dict.get("user_id")
    st.session_state["username"] = user_dict.get("username")
    st.session_state["full_name"] = user_dict.get("full_name")
    st.session_state["email"] = user_dict.get("email")
    st.session_state["role"] = user_dict.get("role")


def logout_session() -> None:
    """Clear authentication context and rerun."""
    st.session_state["authenticated"] = False
    st.session_state["user_id"] = None
    st.session_state["username"] = None
    st.session_state["full_name"] = None
    st.session_state["email"] = None
    st.session_state["role"] = None
    st.rerun()


def current_user() -> Optional[Dict[str, Any]]:
    """Return the current logged-in user context, or None."""
    if not st.session_state.get("authenticated", False):
        return None

    return {
        "user_id": st.session_state.get("user_id"),
        "username": st.session_state.get("username"),
        "full_name": st.session_state.get("full_name"),
        "email": st.session_state.get("email"),
        "role": st.session_state.get("role"),
    }


def has_permission(permission_key_or_roles: Any) -> bool:
    """Check whether the current user has a permission or allowed role."""
    if not st.session_state.get("authenticated", False):
        return False

    user_role = st.session_state.get("role")
    if not user_role:
        return False

    if isinstance(permission_key_or_roles, list):
        return user_role in permission_key_or_roles

    if isinstance(permission_key_or_roles, str):
        allowed_roles = PERMISSIONS.get(permission_key_or_roles, [])
        return user_role in allowed_roles

    return False


def require_role(allowed_roles: List[str]) -> bool:
    """UI guard that displays an access-denied message when needed."""
    if not has_permission(allowed_roles):
        st.error(
            "⛔ Access Denied: You do not have permission to view or access this section."
        )
        return False

    return True
