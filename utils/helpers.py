"""
Helper functions for Ganpati Mandal Management System (Phase 2 Foundation).
"""

import sys
import streamlit as st
from typing import Dict, Any


def get_environment_info() -> Dict[str, Any]:
    """
    Returns python version, streamlit secrets presence, and runtime environment status.
    Safely handles cases where .streamlit/secrets.toml does not exist.
    """
    has_secrets = False
    has_sa_credentials = False
    has_spreadsheet_id = False
    
    try:
        if hasattr(st, "secrets") and st.secrets:
            has_secrets = True
            if "google_service_account" in st.secrets:
                has_sa_credentials = True
            if "spreadsheet_id" in st.secrets or "spreadsheet_name" in st.secrets:
                has_spreadsheet_id = True
    except Exception:
        # st.secrets raises StreamlitSecretNotFoundError if secrets file is missing
        has_secrets = False
        has_sa_credentials = False
        has_spreadsheet_id = False
            
    return {
        "python_version": sys.version.split()[0],
        "streamlit_version": st.__version__,
        "has_secrets": has_secrets,
        "has_sa_credentials": has_sa_credentials,
        "has_spreadsheet_id": has_spreadsheet_id,
        "status": "Ready" if (has_sa_credentials and has_spreadsheet_id) else "Secrets Missing"
    }
