"""
Print Shop Data Warehouse — single-file version
--------------------------------------------------
Store order data from any source (manual entry, CSV/Excel upload) in one
local SQLite warehouse, then explore it with an analytics dashboard.

Run with:
    pip install -r requirements.txt
    streamlit run printshop_app.py
"""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

# ----------------------------------------------------------------------
# CONFIG / CONSTANTS
# ----------------------------------------------------------------------
DB_PATH = "printshop_dw.db"

SERVICE_TYPES = [
    "Printing",
    "Spiral Binding",
    "Photocopy (PF)",
    "Application Filling",
    "Challan",
    "Life Certificate",
    "Lamination",
    "Scanning",
    "Other",
]
PAYMENT_STATUSES = ["Paid", "Pending", "Partially Paid"]
PAYMENT_MODES = ["Cash", "UPI", "Card", "Other"]


# ----------------------------------------------------------------------
# DATABASE LAYER
# ----------------------------------------------------------------------
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_date TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT,
                service TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                unit_price REAL DEFAULT 0,
                total_amount REAL NOT NULL,
                payment_status TEXT DEFAULT 'Paid',
                payment_mode TEXT DEFAULT 'Cash',
                source TEXT DEFAULT 'manual',
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                rows_imported INTEGER,
                imported_at TEXT
            )
            """
        )


def add_order(order_date_, customer_name, phone, service, quantity,
              unit_price, total_amount, payment_status, payment_mode,
              notes="", source="manual"):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO orders
                (order_date, customer_name, phone, service, quantity,
                 unit_price, total_amount, payment_status, payment_mode,
                 source, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order_date_, customer_name, phone, service, quantity,
             unit_price, total_amount, payment_status, payment_mode,
             source, notes, datetime.now().isoformat()),
        )


def bulk_insert_dataframe(df: pd.DataFrame, source_name: str):
    required_defaults = {
        "phone": "",
        "quantity": 1,
        "unit_price": 0.0,
        "payment_status": "Paid",
        "payment_mode": "Cash",
        "notes": "",
    }
    for col, default in required_defaults.items():
        if col not in df.columns:
            df[col] = default

    df["source"] = source_name
    df["created_at"] = datetime.now().isoformat()

    cols = ["order_date", "customer_name", "phone", "service", "quantity",
            "unit_price", "total_amount", "payment_status", "payment_mode",
            "source", "notes", "created_at"]

    with get_conn() as conn:
        df[cols].to_sql("orders", conn, if_exists="append", index=False)
        conn.execute(
            "INSERT INTO import_log (filename, rows_imported, imported_at) VALUES (?, ?, ?)",
            (source_name, len(df), datetime.now().isoformat()),
        )


def get_all_orders() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM orders ORDER BY order_date DESC", conn)


def delete_order(order_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))


def get_import_log() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM import_log ORDER BY imported_at DESC", conn)


# ----------------------------------------------------------------------
# STREAMLIT APP
# ----------------------------------------------------------------------
st.set_page_config(page_title="Print Shop Data Warehouse", page_icon="🖨️", layout="wide")
init_db()

st.title("🖨️ Print Shop Data Warehouse")
st.caption("Store data from any source, then explore it for insight.")

page = st.sidebar.radio(
    "Navigate",
    ["📊 Dashboard", "➕ Add Order", "📁 Import CSV", "🗂️ Browse / Manage Data"],
)

# --- DASHBOARD ---
if page == "📊 Dashboard":
    df = get_all_orders()

    if df.empty:
        st.info("No data yet. Add an order manually or import a CSV to get started.")
    else:
        df["order_date"] = pd.to_datetime(df["order_date"])

        col_a, col_b, col_c = st.columns(3)
        min_d, max_d = df["order_date"].min().date(), df["order_date"].max().date()
        date_range = col_a.date_input("Date range", (min_d, max_d), min_value=min_d, max_value=max_d)
        service_filter = col_b.multiselect("Service", sorted(df["service"].unique()))
        status_filter = col_c.multiselect("Payment status", sorted(df["payment_status"].unique()))

        f = df.copy()
        if len(date_range) == 2:
            f = f[(f["order_date"].dt.date >= date_range[0]) & (f["order_date"].dt.date <= date_range[1])]
        if service_filter:
            f = f[f["service"].isin(service_filter)]
        if status_filter:
            f = f[f["payment_status"].isin(status_filter)]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Revenue", f"₹{f['total_amount'].sum():,.0f}")
        k2.metric("Total Orders", f"{len(f):,}")
        k3.metric("Avg Order Value", f"₹{f['total_amount'].mean():,.0f}" if len(f) else "₹0")
        pending = f.loc[f["payment_status"] != "Paid", "total_amount"].sum()
        k4.metric("Pending Amount", f"₹{pending:,.0f}")

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Revenue Over Time")
            daily = f.groupby(f["order_date"].dt.date)["total_amount"].sum().reset_index()
            daily.columns = ["Date", "Revenue"]
            st.plotly_chart(px.line(daily, x="Date", y="Revenue", markers=True), use_container_width=True)

        with c2:
            st.subheader("Revenue by Service")
            by_service = f.groupby("service")["total_amount"].sum().sort_values(ascending=False).reset_index()
            by_service.columns = ["Service", "Revenue"]
            st.plotly_chart(px.bar(by_service, x="Service", y="Revenue"), use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Payment Status Breakdown")
            status_counts = f["payment_status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            st.plotly_chart(px.pie(status_counts, names="Status", values="Count"), use_container_width=True)

        with c4:
            st.subheader("Top Customers")
            top_cust = (f.groupby("customer_name")["total_amount"].sum()
                        .sort_values(ascending=False).head(10).reset_index())
            top_cust.columns = ["Customer", "Total Spent"]
            st.plotly_chart(px.bar(top_cust, x="Customer", y="Total Spent"), use_container_width=True)

        st.subheader("Orders by Data Source")
        src_counts = f["source"].value_counts().reset_index()
        src_counts.columns = ["Source", "Orders"]
        st.dataframe(src_counts, use_container_width=True, hide_index=True)

# --- ADD ORDER ---
elif page == "➕ Add Order":
    st.subheader("Add a single order manually")
    with st.form("add_order_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        order_date_val = c1.date_input("Order date", value=date.today())
        customer_name = c2.text_input("Customer name")

        c3, c4 = st.columns(2)
        phone = c3.text_input("Phone (optional)")
        service = c4.selectbox("Service", SERVICE_TYPES)

        c5, c6, c7 = st.columns(3)
        quantity = c5.number_input("Quantity", min_value=1, value=1)
        unit_price = c6.number_input("Unit price (₹)", min_value=0.0, value=0.0, step=1.0)
        total_amount = c7.number_input("Total amount (₹)", min_value=0.0,
                                        value=float(quantity * unit_price), step=1.0)

        c8, c9 = st.columns(2)
        payment_status = c8.selectbox("Payment status", PAYMENT_STATUSES)
        payment_mode = c9.selectbox("Payment mode", PAYMENT_MODES)

        notes = st.text_area("Notes (optional)")

        submitted = st.form_submit_button("Save order")
        if submitted:
            if not customer_name:
                st.error("Customer name is required.")
            else:
                add_order(
                    order_date_val.isoformat(), customer_name, phone, service,
                    int(quantity), float(unit_price), float(total_amount),
                    payment_status, payment_mode, notes, source="manual",
                )
                st.success(f"Order for {customer_name} saved.")

# --- IMPORT CSV ---
elif page == "📁 Import CSV":
    st.subheader("Bulk import from a CSV / Excel file")
    st.write(
        "Expected columns: **order_date, customer_name, service, total_amount** "
        "(optional: phone, quantity, unit_price, payment_status, payment_mode, notes). "
        "You'll be able to map your file's columns below if the names don't match exactly."
    )

    uploaded = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx", "xls"])

    if uploaded is not None:
        try:
            if uploaded.name.endswith(".csv"):
                raw = pd.read_csv(uploaded)
            else:
                raw = pd.read_excel(uploaded)
        except Exception as e:
            st.error(f"Could not read file: {e}")
            raw = None

        if raw is not None:
            st.write("Preview of uploaded file:")
            st.dataframe(raw.head(10), use_container_width=True)

            st.write("### Map your columns")
            cols = ["-- none --"] + list(raw.columns)

            def pick(label, default_guess):
                guess_idx = cols.index(default_guess) if default_guess in cols else 0
                return st.selectbox(label, cols, index=guess_idx)

            c1, c2 = st.columns(2)
            with c1:
                map_date = pick("Order date column*", "order_date")
                map_customer = pick("Customer name column*", "customer_name")
                map_service = pick("Service column*", "service")
                map_amount = pick("Total amount column*", "total_amount")
            with c2:
                map_phone = pick("Phone column", "phone")
                map_qty = pick("Quantity column", "quantity")
                map_price = pick("Unit price column", "unit_price")
                map_status = pick("Payment status column", "payment_status")

            if st.button("Import into warehouse"):
                required = [map_date, map_customer, map_service, map_amount]
                if "-- none --" in required:
                    st.error("Please map all four required columns (marked with *).")
                else:
                    clean = pd.DataFrame()
                    clean["order_date"] = pd.to_datetime(raw[map_date], errors="coerce").dt.strftime("%Y-%m-%d")
                    clean["customer_name"] = raw[map_customer].astype(str)
                    clean["service"] = raw[map_service].astype(str)
                    clean["total_amount"] = pd.to_numeric(raw[map_amount], errors="coerce").fillna(0)

                    if map_phone != "-- none --":
                        clean["phone"] = raw[map_phone].astype(str)
                    if map_qty != "-- none --":
                        clean["quantity"] = pd.to_numeric(raw[map_qty], errors="coerce").fillna(1).astype(int)
                    if map_price != "-- none --":
                        clean["unit_price"] = pd.to_numeric(raw[map_price], errors="coerce").fillna(0)
                    if map_status != "-- none --":
                        clean["payment_status"] = raw[map_status].astype(str)

                    clean = clean.dropna(subset=["order_date"])
                    bulk_insert_dataframe(clean, source_name=uploaded.name)
                    st.success(f"Imported {len(clean)} rows from {uploaded.name}.")

    st.divider()
    st.write("#### Import history")
    log = get_import_log()
    if not log.empty:
        st.dataframe(log, use_container_width=True, hide_index=True)
    else:
        st.caption("No imports yet.")

# --- BROWSE / MANAGE ---
elif page == "🗂️ Browse / Manage Data":
    st.subheader("All stored orders")
    df = get_all_orders()

    if df.empty:
        st.info("No data yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Export all data as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"printshop_export_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

        st.divider()
        st.write("#### Delete a record")
        del_id = st.number_input("Order ID to delete", min_value=0, step=1)
        if st.button("Delete", type="secondary"):
            if del_id > 0:
                delete_order(int(del_id))
                st.success(f"Deleted order {del_id}. Refresh the page to see the update.")
