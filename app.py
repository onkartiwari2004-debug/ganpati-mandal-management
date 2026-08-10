"""
Ganpati Mandal Management System
Phase 3 - Authentication, RBAC, Database Diagnostics & Mandal Identity

This app.py is intentionally limited to the functionality already implemented:
- Google Sheets connection / diagnostics
- Schema validation
- Safe worksheet initialization
- Initial user seeding when Users sheet is empty
- Login / logout
- RBAC permission overview
- President-only Mandal Identity configuration
- Single current Payment QR image with President/Treasurer management

Business modules such as Collections, Expenses, Reports and PDF Receipts
are not added here until their services are implemented.
"""

import io
from datetime import date, datetime

import streamlit as st
import pandas as pd

from utils.helpers import get_environment_info

from utils.rbac import (
    init_session_state,
    login_session,
    logout_session,
    current_user,
    has_permission,
    PERMISSIONS,
)

from services.sheets_service import (
    check_db_connection,
    get_spreadsheet,
    validate_schema,
    safe_initialize_missing_sheets,
)

from services.auth_service import (
    authenticate_user,
    seed_initial_users_if_empty,
)

from services.mandal_service import (
    get_mandal_details,
    save_mandal_details,
)

from services.payment_qr_service import (
    get_qr_path,
    qr_exists,
    save_payment_qr,
    delete_payment_qr,
)

from services.collections_service import (
    add_collection,
    get_all_collections,
    get_own_collections,
)

from services.expense_service import (
    EXPENSE_CATEGORIES,
    PAYMENT_MODES,
    add_expense,
    get_all_expenses,
    get_pending_expenses,
    get_own_expenses,
    get_approval_threshold,
    update_expense_decision,
)

from services.receipt_service import build_receipt_pdf


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Ganpati Mandal Management System",
    page_icon="🪔",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION INITIALIZATION
# ============================================================

init_session_state()
user_ctx = current_user()


# ============================================================
# SMALL UI HELPERS
# ============================================================

def _money(value):
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def show_financial_dashboard():
    """President/Treasurer financial overview using existing collection/expense services."""
    if current_role not in {"PRESIDENT", "TREASURER"}:
        return

    st.subheader("📊 Mandal Financial Dashboard")
    st.caption("Live summary from Collections and Expenses.")

    try:
        collections = get_all_collections()
    except Exception:
        collections = []

    try:
        expenses = get_all_expenses()
    except Exception:
        expenses = []

    valid_collections = [
        row for row in collections
        if str(row.get("status", "VALID")).strip().upper() == "VALID"
    ]
    total_collection = sum(_money(row.get("amount")) for row in valid_collections)
    cash_collection = sum(
        _money(row.get("amount"))
        for row in valid_collections
        if str(row.get("payment_mode", "")).strip().upper() == "CASH"
    )
    upi_collection = sum(
        _money(row.get("amount"))
        for row in valid_collections
        if str(row.get("payment_mode", "")).strip().upper() == "UPI"
    )

    approved_expenses = [
        row for row in expenses
        if str(row.get("status", "")).strip().upper() == "APPROVED"
    ]
    pending_expenses = [
        row for row in expenses
        if str(row.get("status", "")).strip().upper() == "PENDING"
    ]
    total_expenses = sum(_money(row.get("amount")) for row in expenses)
    approved_expense_total = sum(_money(row.get("amount")) for row in approved_expenses)
    pending_expense_total = sum(_money(row.get("amount")) for row in pending_expenses)
    current_balance = total_collection - approved_expense_total

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric("💰 Total Collection", f"₹{total_collection:,.2f}")
    with k2:
        st.metric("💸 Approved Expenses", f"₹{approved_expense_total:,.2f}")
    with k3:
        st.metric("🟢 Remaining Balance", f"₹{current_balance:,.2f}")
    with k4:
        st.metric("⏳ Pending Expenses", f"₹{pending_expense_total:,.2f}", f"{len(pending_expenses)} item(s)")
    with k5:
        st.metric("🧾 Total Receipts", f"{len(valid_collections):,}")

    d1, d2, d3 = st.columns(3)
    with d1:
        st.metric("💵 Cash Collection", f"₹{cash_collection:,.2f}")
    with d2:
        st.metric("📱 UPI Collection", f"₹{upi_collection:,.2f}")
    with d3:
        st.metric("📋 Total Expenses", f"₹{total_expenses:,.2f}")

    chart_data = pd.DataFrame({
        "Category": ["Collection", "Approved Expenses", "Remaining Balance"],
        "Amount": [total_collection, approved_expense_total, current_balance],
    }).set_index("Category")
    st.bar_chart(chart_data)

    # Detailed analytics required by the master dashboard specification.
    st.markdown("### 📈 Financial Analytics")
    a1, a2 = st.columns(2)

    with a1:
        collection_rows = []
        for row in valid_collections:
            date_value = str(row.get("date") or row.get("collection_date") or "").strip()
            amount = _money(row.get("amount"))
            if date_value and amount:
                collection_rows.append({"Date": date_value, "Collection": amount})
        if collection_rows:
            daily = pd.DataFrame(collection_rows)
            daily["Date"] = pd.to_datetime(daily["Date"], errors="coerce").dt.date
            daily = daily.dropna(subset=["Date"]).groupby("Date", as_index=True)["Collection"].sum().sort_index()
            st.caption("Daily Collection Trend")
            st.bar_chart(daily)
        else:
            st.info("No dated collection data available yet.")

    with a2:
        collector_rows = []
        for row in valid_collections:
            collector = str(row.get("collector") or row.get("collector_name") or row.get("created_by") or "Unknown").strip() or "Unknown"
            collector_rows.append({"Collector": collector, "Collection": _money(row.get("amount"))})
        if collector_rows:
            collector_df = pd.DataFrame(collector_rows).groupby("Collector")["Collection"].sum().sort_values(ascending=False)
            st.caption("Collection by Collector")
            st.bar_chart(collector_df)
        else:
            st.info("No collector collection data available yet.")

    category_rows = []
    for row in expenses:
        category = str(row.get("category") or row.get("expense_category") or "Other").strip() or "Other"
        category_rows.append({"Category": category, "Expense": _money(row.get("amount"))})
    if category_rows:
        category_df = pd.DataFrame(category_rows).groupby("Category")["Expense"].sum().sort_values(ascending=False)
        st.caption("Expense by Category")
        st.bar_chart(category_df)

    if pending_expenses:
        st.warning(
            f"⚠️ {len(pending_expenses)} expense(s) pending approval, totaling ₹{pending_expense_total:,.2f}."
        )



def _report_date(value):
    """Normalize a stored date/datetime value to a Python date."""
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(str(value).strip(), errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _report_frame(rows):
    """Return a safe DataFrame from Google Sheets row dictionaries."""
    return pd.DataFrame(rows or [])


def _build_excel_report(collection_df, expense_df, summary_df):
    """Create a formatted Excel workbook in memory."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        collection_df.to_excel(writer, sheet_name="Collections", index=False)
        expense_df.to_excel(writer, sheet_name="Expenses", index=False)

        workbook = writer.book
        for worksheet in workbook.worksheets:
            worksheet.freeze_panes = "A2"
            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter
                for cell in column_cells:
                    value = "" if cell.value is None else str(cell.value)
                    max_length = max(max_length, len(value))
                worksheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 35)

    output.seek(0)
    return output.getvalue()


def _build_pdf_summary(summary, start_date, end_date):
    """Create a compact meeting-friendly PDF summary."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return None

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Ganpati Mandal - Financial Summary", styles["Title"]),
        Paragraph(
            f"Report Period: {start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}",
            styles["Normal"],
        ),
        Spacer(1, 8),
    ]

    rows = [
        ["Metric", "Amount / Count"],
        ["Total Collection", f"₹{summary['total_collection']:,.2f}"],
        ["Total Receipts", str(summary["total_receipts"])],
        ["Cash Collection", f"₹{summary['cash_collection']:,.2f}"],
        ["UPI Collection", f"₹{summary['upi_collection']:,.2f}"],
        ["Total Expenses", f"₹{summary['total_expenses']:,.2f}"],
        ["Approved Expenses", f"₹{summary['approved_expenses']:,.2f}"],
        ["Pending Expenses", f"₹{summary['pending_expenses']:,.2f}"],
        ["Current Balance", f"₹{summary['current_balance']:,.2f}"],
    ]
    table = Table(rows, colWidths=[90 * mm, 70 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, "#999999"),
        ("BACKGROUND", (0, 0), (-1, 0), "#EEEEEE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph("गणपती बाप्पा मोरया!", styles["Heading2"]))
    doc.build(story)
    output.seek(0)
    return output.getvalue()


def show_reports():
    """Reports, filters and CSV/Excel/PDF exports for authorized roles."""
    if not has_permission("export_reports"):
        return

    st.markdown("---")
    st.subheader("📈 Reports & Data Export")
    st.caption("Filter collection and expense records, then export the report for Mandal review.")

    try:
        collections = get_all_collections()
    except Exception:
        collections = []
    try:
        expenses = get_all_expenses()
    except Exception:
        expenses = []

    collection_df = _report_frame(collections)
    expense_df = _report_frame(expenses)

    collection_date_col = next((c for c in ["date", "collection_date", "created_at"] if c in collection_df.columns), None)
    expense_date_col = next((c for c in ["date", "expense_date", "created_at"] if c in expense_df.columns), None)

    all_dates = []
    if collection_date_col:
        all_dates.extend([_report_date(v) for v in collection_df[collection_date_col].tolist()])
    if expense_date_col:
        all_dates.extend([_report_date(v) for v in expense_df[expense_date_col].tolist()])
    all_dates = [d for d in all_dates if d is not None]
    default_start = min(all_dates) if all_dates else date.today()
    default_end = max(all_dates) if all_dates else date.today()

    f1, f2 = st.columns(2)
    with f1:
        start_date = st.date_input("Start Date", value=default_start, key="report_start_date")
    with f2:
        end_date = st.date_input("End Date", value=default_end, key="report_end_date")

    f3, f4 = st.columns(2)
    with f3:
        payment_values = {"All", "CASH", "UPI"}
        collection_modes = []
        if not collection_df.empty and "payment_mode" in collection_df.columns:
            collection_modes = [str(v).strip().upper() for v in collection_df["payment_mode"].dropna().unique()]
        expense_modes = []
        if not expense_df.empty and "payment_mode" in expense_df.columns:
            expense_modes = [str(v).strip().upper() for v in expense_df["payment_mode"].dropna().unique()]
        modes = sorted(payment_values.union(collection_modes).union(expense_modes))
        payment_mode = st.selectbox("Payment Mode", modes, key="report_payment_mode")
    with f4:
        collector_options = ["All Collectors"]
        if not collection_df.empty:
            collector_col = next((c for c in ["collector", "collector_name", "created_by"] if c in collection_df.columns), None)
            if collector_col:
                names = sorted({str(v).strip() for v in collection_df[collector_col].dropna() if str(v).strip()})
                collector_options.extend(names)
        collector_filter = st.selectbox("Collector", collector_options, key="report_collector")

    category_options = ["All Categories"]
    if not expense_df.empty:
        category_col = next((c for c in ["category", "expense_category"] if c in expense_df.columns), None)
        if category_col:
            categories = sorted({str(v).strip() for v in expense_df[category_col].dropna() if str(v).strip()})
            category_options.extend(categories)
    expense_category_filter = st.selectbox("Expense Category", category_options, key="report_category")

    if start_date > end_date:
        st.error("Start Date cannot be after End Date.")
        return

    def in_range(value):
        d = _report_date(value)
        return d is not None and start_date <= d <= end_date

    filtered_collections = collection_df.copy()
    if collection_date_col:
        filtered_collections = filtered_collections[filtered_collections[collection_date_col].apply(in_range)]
    if payment_mode != "All" and "payment_mode" in filtered_collections.columns:
        filtered_collections = filtered_collections[
            filtered_collections["payment_mode"].astype(str).str.strip().str.upper() == payment_mode
        ]
    if collector_filter != "All Collectors":
        collector_col = next((c for c in ["collector", "collector_name", "created_by"] if c in filtered_collections.columns), None)
        if collector_col:
            filtered_collections = filtered_collections[
                filtered_collections[collector_col].astype(str).str.strip() == collector_filter
            ]

    filtered_expenses = expense_df.copy()
    if expense_date_col:
        filtered_expenses = filtered_expenses[filtered_expenses[expense_date_col].apply(in_range)]
    if payment_mode != "All" and "payment_mode" in filtered_expenses.columns:
        filtered_expenses = filtered_expenses[
            filtered_expenses["payment_mode"].astype(str).str.strip().str.upper() == payment_mode
        ]
    if expense_category_filter != "All Categories":
        category_col = next((c for c in ["category", "expense_category"] if c in filtered_expenses.columns), None)
        if category_col:
            filtered_expenses = filtered_expenses[
                filtered_expenses[category_col].astype(str).str.strip() == expense_category_filter
            ]

    valid_collections = filtered_collections[
        filtered_collections.get("status", pd.Series(["VALID"] * len(filtered_collections), index=filtered_collections.index)).astype(str).str.upper().eq("VALID")
    ] if not filtered_collections.empty else filtered_collections
    amount_col = "amount" if "amount" in valid_collections.columns else None
    total_collection = valid_collections[amount_col].apply(_money).sum() if amount_col else 0.0
    cash_collection = valid_collections.loc[valid_collections.get("payment_mode", "").astype(str).str.upper().eq("CASH"), amount_col].apply(_money).sum() if amount_col and "payment_mode" in valid_collections.columns else 0.0
    upi_collection = valid_collections.loc[valid_collections.get("payment_mode", "").astype(str).str.upper().eq("UPI"), amount_col].apply(_money).sum() if amount_col and "payment_mode" in valid_collections.columns else 0.0

    if not filtered_expenses.empty and "amount" in filtered_expenses.columns:
        expense_amounts = filtered_expenses["amount"].apply(_money)
        total_expenses = expense_amounts.sum()
        approved_mask = filtered_expenses.get("status", "").astype(str).str.upper().eq("APPROVED")
        pending_mask = filtered_expenses.get("status", "").astype(str).str.upper().eq("PENDING")
        approved_expenses = expense_amounts[approved_mask].sum()
        pending_expenses = expense_amounts[pending_mask].sum()
        pending_count = int(pending_mask.sum())
    else:
        total_expenses = approved_expenses = pending_expenses = 0.0
        pending_count = 0

    summary = {
        "total_collection": total_collection,
        "total_receipts": len(valid_collections),
        "cash_collection": cash_collection,
        "upi_collection": upi_collection,
        "total_expenses": total_expenses,
        "approved_expenses": approved_expenses,
        "pending_expenses": pending_expenses,
        "current_balance": total_collection - approved_expenses,
    }

    st.markdown("### 📊 Report Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Collection", f"₹{total_collection:,.2f}")
    m2.metric("Approved Expenses", f"₹{approved_expenses:,.2f}")
    m3.metric("Current Balance", f"₹{summary['current_balance']:,.2f}")
    m4.metric("Pending Expenses", f"₹{pending_expenses:,.2f}", f"{pending_count} item(s)")

    st.markdown("### 💰 Collections")
    st.dataframe(filtered_collections, use_container_width=True, hide_index=True)
    st.markdown("### 💸 Expenses")
    st.dataframe(filtered_expenses, use_container_width=True, hide_index=True)

    summary_df = pd.DataFrame([
        ["Total Collection", total_collection],
        ["Total Receipts", len(valid_collections)],
        ["Cash Collection", cash_collection],
        ["UPI Collection", upi_collection],
        ["Total Expenses", total_expenses],
        ["Approved Expenses", approved_expenses],
        ["Pending Expenses", pending_expenses],
        ["Current Balance", summary["current_balance"]],
    ], columns=["Metric", "Value"])

    combined_csv = pd.concat([
        filtered_collections.assign(Record_Type="Collection"),
        filtered_expenses.assign(Record_Type="Expense"),
    ], ignore_index=True).to_csv(index=False).encode("utf-8")

    excel_bytes = _build_excel_report(filtered_collections, filtered_expenses, summary_df)
    pdf_bytes = _build_pdf_summary(summary, start_date, end_date)

    st.markdown("### 📥 Export")
    e1, e2, e3 = st.columns(3)
    with e1:
        st.download_button("📄 Download CSV", data=combined_csv, file_name="mandal_report.csv", mime="text/csv", use_container_width=True)
    with e2:
        st.download_button("📊 Download Excel", data=excel_bytes, file_name="mandal_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with e3:
        if pdf_bytes:
            st.download_button("📜 Download PDF Summary", data=pdf_bytes, file_name="mandal_report_summary.pdf", mime="application/pdf", use_container_width=True)
        else:
            st.warning("PDF export requires ReportLab in the environment.")

def show_database_status():
    """
    Returns the current Google Sheets connection state.
    Also renders a friendly error if the connection fails.
    """
    is_connected, db_msg, db_meta = check_db_connection()

    if is_connected and db_meta:
        st.success(
            f"🟢 Google Sheets Database: Connected "
            f"(`{db_meta.get('title', 'Unknown')}`)"
        )
    else:
        st.error(
            f"🔴 Google Sheets Database: "
            f"{db_msg or 'Connection failed'}"
        )

    return is_connected, db_msg, db_meta


def show_schema_status(spreadsheet):
    """
    Validates all required worksheets and displays useful details.
    Does not modify data.
    """
    schema_results = validate_schema(spreadsheet)

    if schema_results["is_valid"]:
        st.success(
            "🎉 All required worksheets and headers are valid."
        )
        return schema_results

    st.warning("⚠️ Schema discrepancies detected.")

    if schema_results.get("missing_sheets"):
        st.error(
            "Missing worksheets: "
            + ", ".join(schema_results["missing_sheets"])
        )

    if schema_results.get("header_mismatches"):
        st.warning(
            "Header mismatches: "
            + ", ".join(schema_results["header_mismatches"])
        )

    return schema_results


def show_initial_user_setup(spreadsheet):
    """
    Initial user setup is intentionally independent of schema validity.

    This fixes the previous condition where the seed button appeared
    only when schema validation failed.

    The auth service itself must still enforce the rule:
    seed ONLY when Users contains no accounts.
    """
    st.markdown("---")
    st.subheader("🌱 Initial User Setup")

    try:
        users_ws = spreadsheet.worksheet("Users")
        user_records = users_ws.get_all_records()

        if user_records:
            st.info(
                f"👥 Users worksheet already contains "
                f"{len(user_records)} user account(s). "
                f"Seeding is skipped."
            )
            return

        st.warning(
            "⚠️ No user accounts are currently present in the Users worksheet."
        )

        st.caption(
            "The button below will create the default users only if "
            "the Users worksheet is empty."
        )

        if st.button(
            "🌱 Seed Default Users",
            type="primary",
            use_container_width=True,
            key="seed_default_users_button",
        ):
            try:
                seed_result = seed_initial_users_if_empty(
                    spreadsheet
                )

                if seed_result.get("seeded"):
                    st.success(
                        seed_result.get(
                            "reason",
                            "Default users created successfully.",
                        )
                    )

                    credentials = seed_result.get(
                        "credentials"
                    )

                    if credentials:
                        st.warning(
                            "⚠️ Save these temporary passwords securely. "
                            "They may not be shown again automatically."
                        )
                        st.json(credentials)
                    else:
                        st.info(
                            "Users were created, but no temporary "
                            "credentials were returned by auth_service.py."
                        )

                else:
                    st.info(
                        seed_result.get(
                            "reason",
                            "Users were not seeded.",
                        )
                    )

            except Exception as exc:
                st.error(
                    "❌ User seeding failed. "
                    f"Details: {exc}"
                )

    except Exception as exc:
        st.error(
            "❌ Unable to inspect the Users worksheet. "
            f"Details: {exc}"
        )


def show_database_diagnostics(show_seed_button=True):
    """
    Common diagnostics block used for both logged-out and logged-in users.
    """
    with st.expander(
        "⚙️ System Status & Database Setup Diagnostics",
        expanded=not st.session_state.get("authenticated", False),
    ):
        env_info = get_environment_info()

        st.write(
            f"**Environment:** Python "
            f"{env_info.get('python_version', 'Unknown')} "
            f"| Streamlit "
            f"{env_info.get('streamlit_version', 'Unknown')}"
        )

        is_connected, db_msg, db_meta = check_db_connection()

        if not is_connected or not db_meta:
            st.error(
                f"🔴 Google Sheets Database: "
                f"{db_msg or 'Connection failed'}"
            )
            return

        st.success(
            f"🟢 Google Sheets Database: Connected "
            f"(`{db_meta.get('title', 'Unknown')}`)"
        )

        spreadsheet, spreadsheet_error = get_spreadsheet()

        if not spreadsheet:
            st.error(
                "❌ Spreadsheet could not be opened. "
                f"{spreadsheet_error or ''}"
            )
            return

        schema_results = show_schema_status(
            spreadsheet
        )

        # ----------------------------------------------------
        # Safe worksheet initialization
        # ----------------------------------------------------

        if not schema_results["is_valid"]:
            st.markdown("#### 🛠️ Worksheet Repair")

            st.caption(
                "This action is non-destructive. It creates missing "
                "worksheets / empty header rows and does not clear "
                "existing records."
            )

            if st.button(
                "🛠️ Safely Initialize / Repair Worksheets",
                use_container_width=True,
                key="safe_initialize_worksheets",
            ):
                try:
                    result = safe_initialize_missing_sheets(
                        spreadsheet
                    )

                    for message in result.get("log", []):
                        st.write(message)

                    st.success(
                        "Worksheet initialization completed."
                    )
                    st.rerun()

                except Exception as exc:
                    st.error(
                        f"❌ Worksheet initialization failed: {exc}"
                    )

        # ----------------------------------------------------
        # Initial users
        # ----------------------------------------------------

        if show_seed_button:
            show_initial_user_setup(
                spreadsheet
            )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🪔 गणपती मंडळ")

    # Load Mandal identity for display, but never allow this
    # to break login if the Mandal sheet is empty.
    sidebar_mandal = None

    try:
        sidebar_mandal = get_mandal_details()
    except Exception:
        sidebar_mandal = None

    if sidebar_mandal:
        mandal_name = str(
            sidebar_mandal.get(
                "mandal_name",
                "गणपती मंडळ",
            )
        ).strip()

        festival_name = str(
            sidebar_mandal.get(
                "festival_name",
                "",
            )
        ).strip()

        if mandal_name:
            st.markdown(
                f"### {mandal_name}"
            )

        if festival_name:
            st.caption(
                festival_name
            )

    if st.session_state.get("authenticated", False):
        st.markdown("---")
        st.markdown("### 👤 Logged In User")

        st.markdown(
            f"**Name:** "
            f"`{user_ctx.get('full_name') or '-'}`"
        )

        st.markdown(
            f"**Username:** "
            f"`{user_ctx.get('username') or '-'}`"
        )

        st.markdown(
            f"**Role:** "
            f"`{user_ctx.get('role') or '-'}`"
        )

        st.markdown("---")

        if st.button(
            "🔒 Logout",
            type="secondary",
            use_container_width=True,
            key="sidebar_logout",
        ):
            logout_session()

    else:
        st.info(
            "🔐 Please log in to access "
            "Mandal management tools."
        )


# ============================================================
# UNAUTHENTICATED - LOGIN PAGE
# ============================================================

if not st.session_state.get(
    "authenticated",
    False,
):

    st.title(
        "🪔 Ganpati Mandal Management System"
    )

    st.caption(
        "Sign in to your Mandal Account"
    )

    st.markdown("---")

    col1, col2, col3 = st.columns(
        [1, 2, 1]
    )

    with col2:
        with st.form(
            "login_form",
            clear_on_submit=False,
        ):
            st.subheader("🔐 Sign In")

            username_input = st.text_input(
                "Username or Email",
                placeholder="Enter username or email",
            )

            password_input = st.text_input(
                "Password",
                type="password",
                placeholder="Enter password",
            )

            submit_login = st.form_submit_button(
                "🚀 Sign In",
                type="primary",
                use_container_width=True,
            )

            if submit_login:
                username_clean = (
                    username_input.strip()
                )

                if not username_clean:
                    st.error(
                        "❌ Please enter your username or email."
                    )

                elif not password_input:
                    st.error(
                        "❌ Please enter your password."
                    )

                else:
                    try:
                        user_dict, message = authenticate_user(
                            username_clean,
                            password_input,
                        )

                        if user_dict:
                            login_session(
                                user_dict
                            )

                            st.success(
                                "✅ Login successful."
                            )

                            st.rerun()

                        else:
                            st.error(
                                f"❌ {message}"
                            )

                    except Exception as exc:
                        st.error(
                            "❌ Authentication failed. "
                            f"Details: {exc}"
                        )

    st.markdown("---")

    # Diagnostics are available without login so setup can
    # be completed before the first user exists.
    show_database_diagnostics(
        show_seed_button=True
    )


# ============================================================
# AUTHENTICATED USER - MAIN APPLICATION
# ============================================================

else:

    # --------------------------------------------------------
    # Defensive session validation
    # --------------------------------------------------------

    if not user_ctx:
        st.session_state["authenticated"] = False
        st.rerun()

    current_role = user_ctx.get(
        "role"
    )

    # Financial dashboard is visible to President and Treasurer only.
    show_financial_dashboard()

    # Reports & exports are available to roles granted export_reports.
    show_reports()

    st.title(
        f"🪔 Welcome, "
        f"{user_ctx.get('full_name') or 'User'}!"
    )

    st.caption(
        f"Role: **{current_role or '-'}** | "
        f"User ID: `{user_ctx.get('user_id') or '-'}`"
    )

    st.markdown("---")

    # ========================================================
    # SYSTEM STATUS CARDS
    # ========================================================

    st.subheader(
        "📌 System Status & Role Permissions"
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "Auth Session",
            "Active 🟢",
            f"User: {user_ctx.get('username') or '-'}",
        )

    with c2:
        st.metric(
            "Role Access Level",
            current_role or "Unknown",
            "RBAC Enforced",
        )

    with c3:
        is_conn, db_msg, db_meta = (
            check_db_connection()
        )

        st.metric(
            "Database Health",
            "Connected 🟢"
            if is_conn
            else "Failed 🔴",
            db_meta.get("title", "No DB")
            if db_meta
            else "No DB",
        )

    # ========================================================
    # MANDAL HEADER / IDENTITY PREVIEW
    # ========================================================

    try:
        active_mandal = get_mandal_details()
    except Exception:
        active_mandal = None

    if active_mandal:

        mandal_name = str(
            active_mandal.get(
                "mandal_name",
                "",
            )
        ).strip()

        festival_name = str(
            active_mandal.get(
                "festival_name",
                "",
            )
        ).strip()

        festival_year = str(
            active_mandal.get(
                "festival_year",
                "",
            )
        ).strip()

        if mandal_name:
            st.subheader(
                f"🚩 {mandal_name}"
            )

        if festival_name or festival_year:
            st.caption(
                " | ".join(
                    value
                    for value in [
                        festival_name,
                        festival_year,
                    ]
                    if value
                )
            )

        # Display only if a URL was configured.
        ganpati_img_url = str(
            active_mandal.get(
                "ganpati_img_url",
                "",
            )
        ).strip()

        if ganpati_img_url:
            try:
                st.image(
                    ganpati_img_url,
                    use_container_width=True,
                )
            except Exception:
                st.warning(
                    "⚠️ Ganpati image URL could not be displayed."
                )

    st.markdown("---")

    # ========================================================
    # ROLE PERMISSIONS OVERVIEW
    # ========================================================

    st.subheader(
        "📋 Your Role Permissions Overview"
    )

    perm_table = []

    for permission_key, allowed_roles in (
        PERMISSIONS.items()
    ):

        can_access = (
            current_role in allowed_roles
        )

        perm_table.append(
            {
                "Feature / Capability":
                    permission_key
                    .replace("_", " ")
                    .title(),

                "Access Status":
                    "✅ Granted"
                    if can_access
                    else "⛔ Restricted",

                "Permitted Roles":
                    ", ".join(
                        allowed_roles
                    ),
            }
        )

    df_permissions = pd.DataFrame(
        perm_table
    )

    st.dataframe(
        df_permissions,
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================
    # MANDAL IDENTITY MANAGEMENT
    # PRESIDENT ONLY
    # ========================================================

    st.markdown("---")

    if has_permission(
        "manage_mandal_identity"
    ):

        st.subheader(
            "🏠 Mandal Identity Management"
        )

        try:
            mandal = (
                get_mandal_details()
                or {}
            )
        except Exception as exc:
            mandal = {}
            st.error(
                "❌ Unable to load Mandal details. "
                f"Details: {exc}"
            )

        with st.form(
            "mandal_identity_form",
            clear_on_submit=False,
        ):

            st.caption(
                "Configure Mandal identity, branding "
                "and receipt information."
            )

            col1, col2 = st.columns(2)

            # ------------------------------------------------
            # LEFT COLUMN
            # ------------------------------------------------

            with col1:

                mandal_name = st.text_input(
                    "Mandal Name *",
                    value=str(
                        mandal.get(
                            "mandal_name",
                            "",
                        )
                    ),
                    placeholder=(
                        "श्री गणेश मित्र मंडळ"
                    ),
                )

                festival_name = st.text_input(
                    "Festival Name *",
                    value=str(
                        mandal.get(
                            "festival_name",
                            "",
                        )
                    ),
                    placeholder=(
                        "गणेशोत्सव २०२६"
                    ),
                )

                festival_year = st.text_input(
                    "Festival Year *",
                    value=str(
                        mandal.get(
                            "festival_year",
                            "2026",
                        )
                    ),
                    placeholder="2026",
                )

                logo_url = st.text_input(
                    "Mandal Logo URL",
                    value=str(
                        mandal.get(
                            "logo_url",
                            "",
                        )
                    ),
                    placeholder=(
                        "Paste logo image URL"
                    ),
                )

                ganpati_img_url = st.text_input(
                    "Ganpati Image URL",
                    value=str(
                        mandal.get(
                            "ganpati_img_url",
                            "",
                        )
                    ),
                    placeholder=(
                        "Paste Ganpati image URL"
                    ),
                )

            # ------------------------------------------------
            # RIGHT COLUMN
            # ------------------------------------------------

            with col2:

                receipt_header = st.text_area(
                    "Receipt Header *",
                    value=str(
                        mandal.get(
                            "receipt_header",
                            "",
                        )
                    ),
                    placeholder=(
                        "श्री गणेश मित्र मंडळ, "
                        "सार्वजनिक उत्सव"
                    ),
                    height=120,
                )

                receipt_footer = st.text_area(
                    "Receipt Footer *",
                    value=str(
                        mandal.get(
                            "receipt_footer",
                            "",
                        )
                    ),
                    placeholder=(
                        "गणपती बाप्पा मोरया! "
                        "मंगलमूर्ती मोरया!"
                    ),
                    height=120,
                )

                st.info(
                    "🔐 Mandal identity can be modified only by the President."
                )

            # ------------------------------------------------
            # SAVE BUTTON
            # ------------------------------------------------

            save_button = st.form_submit_button(
                "💾 Save Mandal Details",
                type="primary",
                use_container_width=True,
            )

            if save_button:

                validation_errors = []

                # Required text fields
                if not mandal_name.strip():
                    validation_errors.append(
                        "Mandal Name is required."
                    )

                if not festival_name.strip():
                    validation_errors.append(
                        "Festival Name is required."
                    )

                if not festival_year.strip():
                    validation_errors.append(
                        "Festival Year is required."
                    )

                if not receipt_header.strip():
                    validation_errors.append(
                        "Receipt Header is required."
                    )

                if not receipt_footer.strip():
                    validation_errors.append(
                        "Receipt Footer is required."
                    )

                # Festival year validation
                year_value = festival_year.strip()

                if year_value:
                    if (
                        not year_value.isdigit()
                        or len(year_value) != 4
                    ):
                        validation_errors.append(
                            "Festival Year must be a valid "
                            "4-digit year, e.g. 2026."
                        )

                if validation_errors:

                    for error in validation_errors:
                        st.error(
                            f"❌ {error}"
                        )

                else:

                    try:

                        success, message = (
                            save_mandal_details(
                                mandal_name=mandal_name,
                                festival_name=festival_name,
                                festival_year=festival_year,
                                logo_url=logo_url,
                                ganpati_img_url=ganpati_img_url,
                                receipt_header=receipt_header,
                                receipt_footer=receipt_footer,
                                updated_by=(
                                    user_ctx.get(
                                        "username",
                                        "",
                                    )
                                ),
                            )
                        )

                        if success:
                            st.success(
                                f"✅ {message}"
                            )
                            st.rerun()

                        else:
                            st.error(
                                f"❌ {message}"
                            )

                    except Exception as exc:
                        st.error(
                            "❌ Failed to save Mandal details. "
                            f"Details: {exc}"
                        )

    else:

        st.info(
            "🔒 Mandal Identity Management is available only to the President."
        )

    # ========================================================
    # PAYMENT QR MANAGEMENT
    # ========================================================

    st.markdown("---")

    if has_permission("view_payment_qr"):
        st.subheader("💳 Payment Receive")
        st.caption(
            "One current Payment QR is maintained locally. "
            "Uploading a new QR replaces the previous QR."
        )

        qr_path = get_qr_path()

        if qr_path and qr_exists():
            st.success("🟢 Current Payment QR is available.")
            qr_col1, qr_col2 = st.columns([1, 2])

            with qr_col1:
                st.image(
                    qr_path,
                    caption="Current Payment QR",
                    use_container_width=True,
                )

            with qr_col2:
                if has_permission("manage_payment_qr"):
                    st.markdown("### 📤 Update Payment QR")
                    uploaded_qr = st.file_uploader(
                        "Upload new QR photo",
                        type=["png", "jpg", "jpeg", "webp"],
                        key="payment_qr_uploader",
                        help="Select the QR image from your phone gallery or computer.",
                    )

                    if uploaded_qr is not None:
                        st.image(
                            uploaded_qr,
                            caption="New QR Preview",
                            use_container_width=True,
                        )

                    qr_action_col1, qr_action_col2 = st.columns(2)

                    with qr_action_col1:
                        if st.button(
                            "💾 Save / Replace QR",
                            type="primary",
                            use_container_width=True,
                            key="save_payment_qr",
                        ):
                            if uploaded_qr is None:
                                st.error("❌ Please select a QR image first.")
                            else:
                                success, message = save_payment_qr(uploaded_qr)
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")

                    with qr_action_col2:
                        if st.button(
                            "🗑️ Remove Current QR",
                            use_container_width=True,
                            key="delete_payment_qr",
                        ):
                            success, message = delete_payment_qr()
                            if success:
                                st.success(f"✅ {message}")
                                st.rerun()
                            else:
                                st.error(f"❌ {message}")
                else:
                    st.info(
                        "👀 You can view and use the current Payment QR. "
                        "Only President and Treasurer can update it."
                    )
        else:
            st.warning("⚠️ No Payment QR has been uploaded yet.")

            if has_permission("manage_payment_qr"):
                st.markdown("### 📤 Upload Payment QR")
                uploaded_qr = st.file_uploader(
                    "Select QR photo from Gallery",
                    type=["png", "jpg", "jpeg", "webp"],
                    key="payment_qr_uploader_empty",
                )

                if uploaded_qr is not None:
                    st.image(
                        uploaded_qr,
                        caption="QR Preview",
                        use_container_width=True,
                    )

                    if st.button(
                        "💾 Save Payment QR",
                        type="primary",
                        use_container_width=True,
                        key="save_payment_qr_first",
                    ):
                        success, message = save_payment_qr(uploaded_qr)
                        if success:
                            st.success(f"✅ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
            else:
                st.info(
                    "🔒 Payment QR is not available yet. "
                    "President or Treasurer must upload it first."
                )
    else:
        st.info("🔒 You do not have access to Payment Receive.")

    # ========================================================
    # COLLECTIONS & DONATION ENTRY
    # ========================================================

    st.markdown("---")

    if has_permission("add_collection"):
        st.subheader("💰 New Collection & Receipt")
        st.caption(
            "Record a donation received from a donor. "
            "A unique receipt number is generated automatically."
        )

        with st.form(
            "new_collection_form",
            clear_on_submit=True,
        ):
            donor_col1, donor_col2 = st.columns(2)

            with donor_col1:
                donor_name = st.text_input(
                    "Donor Name *",
                    placeholder="Enter donor full name",
                )
                building = st.text_input(
                    "Building *",
                    placeholder="e.g. Sai Ganesh Chawl",
                )

            with donor_col2:
                flat_no = st.text_input(
                    "Flat No. *",
                    placeholder="e.g. Flat 204",
                )
                amount = st.number_input(
                    "Amount (₹) *",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                )

            payment_col1, payment_col2 = st.columns(2)

            with payment_col1:
                payment_mode = st.selectbox(
                    "Payment Mode *",
                    ["Cash", "UPI"],
                )

            with payment_col2:
                upi_ref_no = st.text_input(
                    "UPI Reference No.",
                    placeholder="Required for UPI",
                    disabled=(payment_mode != "UPI"),
                )

            remark = st.text_area(
                "Remark",
                placeholder="Optional note, e.g. Annual वर्गणी",
                height=90,
            )

            st.info(
                f"👤 Collection will be recorded under "
                f"`{user_ctx.get('username', '')}` "
                f"({user_ctx.get('full_name', '')})."
            )

            save_collection_button = st.form_submit_button(
                "💾 Save Collection & Generate Receipt",
                type="primary",
                use_container_width=True,
            )

        if save_collection_button:
            success, message, saved_record = add_collection(
                donor_name=donor_name,
                building=building,
                flat_no=flat_no,
                amount=amount,
                payment_mode=payment_mode,
                upi_ref_no=upi_ref_no,
                collected_by=user_ctx.get("username", ""),
                collector_name=user_ctx.get("full_name", ""),
                remark=remark,
            )

            if success and saved_record:
                st.success(f"✅ {message}")
                st.markdown("### 🧾 Collection Receipt")

                receipt_col1, receipt_col2 = st.columns(2)

                with receipt_col1:
                    st.write(
                        f"**Receipt No:** `{saved_record['receipt_no']}`"
                    )
                    st.write(
                        f"**Donor:** {saved_record['donor_name']}"
                    )
                    st.write(
                        f"**Building:** {saved_record['building']}"
                    )
                    st.write(
                        f"**Flat No.:** {saved_record['flat_no']}"
                    )
                    st.write(
                        f"**Amount:** ₹{saved_record['amount']}"
                    )

                with receipt_col2:
                    st.write(
                        f"**Payment Mode:** {saved_record['payment_mode']}"
                    )

                    if saved_record["upi_ref_no"]:
                        st.write(
                            f"**UPI Ref:** {saved_record['upi_ref_no']}"
                        )

                    st.write(
                        f"**Collected By:** {saved_record['collector_name']}"
                    )
                    st.write(
                        f"**Date:** {saved_record['date']}"
                    )
                    st.write(
                        f"**Time:** {saved_record['time']}"
                    )

                if saved_record["remark"]:
                    st.write(
                        f"**Remark:** {saved_record['remark']}"
                    )

                # Generate a PDF from the saved record.
                mandal_details = get_mandal_details() or {}

                try:
                    receipt_pdf = build_receipt_pdf(
                        collection=saved_record,
                        mandal=mandal_details,
                    )

                    st.download_button(
                        "📄 Download Receipt PDF",
                        data=receipt_pdf,
                        file_name=f"{saved_record['receipt_no']}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                    st.success("🙏 गणपती बाप्पा मोरया!")
                except Exception as exc:
                    st.warning(
                        "Collection was saved, but the PDF receipt "
                        f"could not be generated: {exc}"
                    )
            else:
                st.error(f"❌ {message}")

    else:
        st.info(
            "🔒 You do not have permission to add collection entries."
        )

    # ========================================================
    # COLLECTION HISTORY
    # ========================================================

    if has_permission("view_all_collections"):
        st.markdown("### 📋 Collection History")
        collections = get_all_collections()

        if collections:
            st.dataframe(
                pd.DataFrame(collections),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No collection records found yet.")

    elif has_permission("view_own_collections"):
        st.markdown("### 📋 My Collection History")
        own_collections = get_own_collections(
            user_ctx.get("username", "")
        )

        if own_collections:
            st.dataframe(
                pd.DataFrame(own_collections),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No collection records found for your account.")


    # ========================================================
    # EXPENSE MANAGEMENT & APPROVAL
    # ========================================================

    st.markdown("---")

    if has_permission("submit_expense"):
        st.subheader("💸 Expense Management")
        st.caption(
            "Submit Mandal expenses. Expenses up to the configured "
            "threshold are auto-approved; higher amounts require "
            "President/Treasurer approval."
        )

        threshold = get_approval_threshold()

        st.info(
            f"⚙️ Current auto-approval threshold: "
            f"₹{threshold:,.2f}"
        )

        with st.form(
            "new_expense_form",
            clear_on_submit=True,
        ):
            exp_col1, exp_col2 = st.columns(2)

            with exp_col1:
                expense_category = st.selectbox(
                    "Category *",
                    EXPENSE_CATEGORIES,
                )
                expense_description = st.text_input(
                    "Description *",
                    placeholder="e.g. Pooja material purchase",
                )
                expense_paid_to = st.text_input(
                    "Paid To / Vendor *",
                    placeholder="Vendor / person name",
                )

            with exp_col2:
                expense_amount = st.number_input(
                    "Amount (₹) *",
                    min_value=0.0,
                    step=100.0,
                    format="%.2f",
                )
                expense_payment_mode = st.selectbox(
                    "Payment Mode *",
                    PAYMENT_MODES,
                )
                expense_date = st.date_input(
                    "Expense Date *",
                )

            expense_bill = st.file_uploader(
                "Bill / Proof (optional)",
                type=["png", "jpg", "jpeg", "webp", "pdf"],
                key="expense_bill_uploader",
            )

            expense_submit = st.form_submit_button(
                "💾 Submit Expense",
                type="primary",
                use_container_width=True,
            )

        if expense_submit:
            success, message, saved_expense = add_expense(
                category=expense_category,
                description=expense_description,
                amount=expense_amount,
                paid_to=expense_paid_to,
                payment_mode=expense_payment_mode,
                requested_by=user_ctx.get("username", ""),
                date_value=expense_date.isoformat(),
                bill_file=expense_bill,
            )

            if success:
                st.success(f"✅ {message}")

                if saved_expense:
                    st.write(
                        f"**Expense ID:** `{saved_expense['expense_id']}`"
                    )
                    st.write(
                        f"**Status:** `{saved_expense['status']}`"
                    )
            else:
                st.error(f"❌ {message}")

    # --------------------------------------------------------
    # PRESIDENT / TREASURER APPROVAL QUEUE
    # --------------------------------------------------------

    if has_permission("approve_expense"):
        st.markdown("### ⏳ Expense Approval Queue")

        pending_expenses = get_pending_expenses()

        if not pending_expenses:
            st.success("🟢 No pending expenses.")
        else:
            for pending in pending_expenses:
                expense_id = pending.get("expense_id", "")

                with st.container(border=True):
                    p1, p2, p3 = st.columns([2, 2, 1])

                    with p1:
                        st.write(
                            f"**{pending.get('category', '')}**"
                        )
                        st.caption(
                            pending.get("description", "")
                        )
                        st.write(
                            f"Paid To: {pending.get('paid_to', '')}"
                        )

                    with p2:
                        st.metric(
                            "Amount",
                            f"₹{pending.get('amount', '0')}",
                        )
                        st.write(
                            f"Requested By: "
                            f"{pending.get('requested_by', '')}"
                        )
                        st.write(
                            f"Date: {pending.get('date', '')}"
                        )

                        bill_url = str(
                            pending.get("bill_url", "")
                        ).strip()

                        if bill_url:
                            st.caption(
                                f"Bill stored: `{bill_url}`"
                            )

                    with p3:
                        approve_key = f"approve_{expense_id}"
                        reject_key = f"reject_{expense_id}"

                        if st.button(
                            "✅ Approve",
                            key=approve_key,
                            use_container_width=True,
                        ):
                            ok, msg = update_expense_decision(
                                expense_id=expense_id,
                                decision="APPROVED",
                                approved_by=user_ctx.get(
                                    "username",
                                    "",
                                ),
                                approval_remark="Approved by authorized user.",
                            )

                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                        if st.button(
                            "❌ Reject",
                            key=reject_key,
                            use_container_width=True,
                        ):
                            ok, msg = update_expense_decision(
                                expense_id=expense_id,
                                decision="REJECTED",
                                approved_by=user_ctx.get(
                                    "username",
                                    "",
                                ),
                                approval_remark="Rejected by authorized user.",
                            )

                            if ok:
                                st.warning(msg)
                                st.rerun()
                            else:
                                st.error(msg)

    # --------------------------------------------------------
    # EXPENSE HISTORY
    # --------------------------------------------------------

    if has_permission("view_all_collections"):
        st.markdown("### 📋 Expense History")

        all_expenses = get_all_expenses()

        if all_expenses:
            st.dataframe(
                pd.DataFrame(all_expenses),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No expense records found yet.")

    elif has_permission("view_own_collections"):
        st.markdown("### 📋 My Expense History")

        own_expenses = get_own_expenses(
            user_ctx.get("username", "")
        )

        if own_expenses:
            st.dataframe(
                pd.DataFrame(own_expenses),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No expense records found for your account.")

    # ========================================================
    # ADVANCED DATABASE DIAGNOSTICS
    # ========================================================

    st.markdown("---")

    with st.expander(
        "🛠️ Advanced Database & System Health Diagnostics"
    ):

        is_conn, db_msg, db_meta = (
            check_db_connection()
        )

        if is_conn and db_meta:

            st.success(
                f"**Connected Database:** "
                f"`{db_meta.get('title', 'Unknown')}`"
            )

            st.caption(
                f"Spreadsheet ID: "
                f"`{db_meta.get('id', 'Unknown')}`"
            )

            spreadsheet, spreadsheet_error = (
                get_spreadsheet()
            )

            if spreadsheet:

                schema_results = validate_schema(
                    spreadsheet
                )

                if schema_results["is_valid"]:

                    st.success(
                        "🎉 All 6 required worksheets "
                        "exist and match the expected schema."
                    )

                else:

                    st.warning(
                        "⚠️ Schema discrepancies detected."
                    )

                    if schema_results.get(
                        "missing_sheets"
                    ):
                        st.write(
                            "**Missing worksheets:**",
                            schema_results[
                                "missing_sheets"
                            ],
                        )

                    if schema_results.get(
                        "header_mismatches"
                    ):
                        st.write(
                            "**Header mismatches:**",
                            schema_results[
                                "header_mismatches"
                            ],
                        )

                    if st.button(
                        "🛠️ Safely Fix Worksheets",
                        use_container_width=True,
                        key="advanced_fix_worksheets",
                    ):

                        try:

                            result = (
                                safe_initialize_missing_sheets(
                                    spreadsheet
                                )
                            )

                            for message in result.get(
                                "log",
                                [],
                            ):
                                st.write(message)

                            st.success(
                                "Worksheet repair completed."
                            )

                            st.rerun()

                        except Exception as exc:
                            st.error(
                                "❌ Worksheet repair failed: "
                                f"{exc}"
                            )

                # ------------------------------------------------
                # USER COUNT DIAGNOSTIC
                # ------------------------------------------------

                try:

                    users_ws = spreadsheet.worksheet(
                        "Users"
                    )

                    user_records = (
                        users_ws.get_all_records()
                    )

                    if user_records:
                        st.success(
                            f"👥 Users worksheet: "
                            f"{len(user_records)} account(s)"
                        )
                    else:
                        st.warning(
                            "⚠️ Users worksheet is empty. "
                            "Initial user setup is required."
                        )

                except Exception as exc:
                    st.error(
                        "❌ Could not inspect Users worksheet: "
                        f"{exc}"
                    )

        else:

            st.error(
                f"🔴 Google Sheets Database: "
                f"{db_msg or 'Connection failed'}"
            )
