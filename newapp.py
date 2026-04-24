import time
import random
import uuid
from datetime import datetime, timedelta
 
import pandas as pd
import streamlit as st
 
st.set_page_config(page_title="Manufacturing Dashboard", layout="wide")
 
# -----------------------------
# CUSTOM CSS
# -----------------------------
st.markdown("""
<style>
.stApp {
    background: #ffffff;
}
 
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 1.2rem;
    max-width: 1400px;
}
 
* {
    color: #111111 !important;
}
 
.main-title {
    font-size: 2rem;
    font-weight: 800;
    margin-bottom: 0.2rem;
}
 
.sub-text {
    font-size: 1rem;
    color: #444444 !important;
    margin-bottom: 1rem;
}
 
.card {
    background: white;
    border: 1px solid #dddddd;
    border-radius: 18px;
    padding: 18px 20px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    margin-bottom: 16px;
}
 
.small-label {
    font-size: 0.85rem;
    font-weight: 700;
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #555555 !important;
}
 
.big-value {
    font-size: 1.6rem;
    font-weight: 800;
    color: #111111 !important;
}
 
.normal-value {
    font-size: 1.03rem;
    font-weight: 700;
    color: #111111 !important;
}
 
.table-heading {
    font-size: 1.35rem;
    font-weight: 800;
    margin-bottom: 14px;
    color: #111111 !important;
}
 
.status-running {
    color: #1a7a1a !important;
    font-weight: 800 !important;
}
 
.status-paused {
    color: #b85000 !important;
    font-weight: 800 !important;
}
 
.status-completed {
    color: #0a4f9e !important;
    font-weight: 800 !important;
}
 
.status-ready {
    color: #666666 !important;
    font-weight: 800 !important;
}
 
.delay-green {
    color: #1a7a1a !important;
    font-weight: 800 !important;
}
 
.delay-red {
    color: #c62828 !important;
    font-weight: 800 !important;
}
 
.stButton > button {
    background: #f4d52c !important;
    color: #111111 !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    height: 2.8rem !important;
}
 
.stButton > button:hover {
    background: #e8c91d !important;
    color: #111111 !important;
}
 
.custom-table {
    border: 1px solid #d9d9d9;
    border-radius: 14px;
    overflow: hidden;
    width: 100%;
    background: white;
    margin-bottom: 24px;
}
 
.custom-table table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    margin: 0;
}
 
.custom-table thead th {
    background: #f5f5f5;
    color: #111111 !important;
    text-align: center !important;
    font-weight: 800;
    font-size: 13px;
    padding: 11px 8px;
    border: 1px solid #dddddd;
}
 
.custom-table tbody td {
    text-align: center;
    padding: 10px 8px;
    border: 1px solid #eeeeee;
    font-size: 13px;
    color: #111111 !important;
    font-weight: 600;
}
 
.custom-table tbody tr:nth-child(even) td {
    background: #fafafa;
}
 
.progress-label {
    font-size: 14px;
    color: #111111 !important;
    font-weight: 700;
    margin-top: 8px;
}
 
.home-card {
    background: white;
    border: 1px solid #dddddd;
    border-radius: 18px;
    padding: 18px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)
 
# -----------------------------
# HELPERS
# -----------------------------
def format_duration(seconds):
    seconds = max(0, int(seconds))
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"
 
def format_status(status):
    return status.capitalize()
 
def fmt_ts(ts):
    if ts is None:
        return "-"
    return pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M:%S")
 
def get_delay_class(order):
    return "delay-red" if get_live_delay_sec(order) > 0 else "delay-green"
 
def log_event(order, event_type, note=""):
    now = datetime.now()
    order["EVENT LOG"].append({
        "Timestamp": now,
        "Event": event_type,
        "Status": order["ORDER STATUS"],
        "Completed Qty": int(order["COMPLETED QUANTITIES"]),
        "Note": note
    })
 
    if event_type == "STARTED" and order["STARTED AT"] is None:
        order["STARTED AT"] = now
    elif event_type == "PAUSED":
        order["LAST PAUSED AT"] = now
    elif event_type == "RESUMED":
        order["LAST RESUMED AT"] = now
    elif event_type == "COMPLETED":
        order["COMPLETED AT"] = now
 
def get_live_delay_sec(order):
    total_delay = order["TOTAL DELAY SEC"]
    if order["ORDER STATUS"] == "PAUSED" and order["PAUSE START"] is not None:
        total_delay += (datetime.now() - order["PAUSE START"]).total_seconds()
    return total_delay
 
def get_updated_end_time(order):
    live_delay = get_live_delay_sec(order)
    return order["PLANNED END DATE"] + timedelta(seconds=live_delay)
 
def calculate_dynamic_eta(order):
    remaining_qty = max(0, order["TOTAL QUANTITIES"] - order["COMPLETED QUANTITIES"])
    if remaining_qty <= 0:
        return datetime.now()
 
    production_per_sec = order["DAILY CAPACITY"] / 86400
    seconds_left = remaining_qty / production_per_sec
    return datetime.now() + timedelta(seconds=seconds_left)
 
def auto_update_order(order):
    now = datetime.now()
    elapsed_sec = (now - order["LAST UPDATE"]).total_seconds()
 
    if elapsed_sec <= 0:
        return
 
    if order["ORDER STATUS"] == "RUNNING":
        production_per_sec = order["DAILY CAPACITY"] / 86400
        produced_now = production_per_sec * elapsed_sec
 
        old_qty = order["COMPLETED QUANTITIES"]
        new_qty = min(order["TOTAL QUANTITIES"], old_qty + produced_now)
        order["COMPLETED QUANTITIES"] = new_qty
 
        if int(new_qty) > int(old_qty):
            log_event(order, "PRODUCTION UPDATE", f"+{int(new_qty) - int(old_qty)} units")
 
        order["CURRENT ETA"] = calculate_dynamic_eta(order)
 
        if order["COMPLETED QUANTITIES"] >= order["TOTAL QUANTITIES"]:
            order["COMPLETED QUANTITIES"] = float(order["TOTAL QUANTITIES"])
            order["ORDER STATUS"] = "COMPLETED"
            order["CURRENT ETA"] = get_updated_end_time(order)
            log_event(order, "COMPLETED", "Order finished")
 
    elif order["ORDER STATUS"] == "PAUSED":
        order["CURRENT ETA"] = get_updated_end_time(order)
 
    order["LAST UPDATE"] = now
 
def get_status_class(status):
    if status == "RUNNING":
        return "status-running"
    if status == "PAUSED":
        return "status-paused"
    if status == "COMPLETED":
        return "status-completed"
    return "status-ready"
 
def color_delay(val):
    if val == "Delay":
        return "color: #c62828; font-weight: 800;"
    return "color: #1a7a1a; font-weight: 800;"
 
def create_orders_from_db():
    orders = []
    now = datetime.now()
 
    for row in WORK_ORDER_DB:
        total = row["total"]
        completed = float(row["completed"])
        daily_cap = row["daily_cap"]
        status = row["status"]
 
        start_time = now - timedelta(minutes=random.randint(10, 120))
        production_per_sec = daily_cap / 86400
        remaining = max(0, total - completed)
 
        if production_per_sec > 0 and remaining > 0:
            seconds_left = remaining / production_per_sec
            planned_end = now + timedelta(seconds=seconds_left)
        else:
            planned_end = now
 
        pause_start = None
        last_paused_at = None
        last_resumed_at = None
        started_at = None
        completed_at = None
 
        if status == "PAUSED":
            pause_start = now - timedelta(minutes=random.randint(1, 15))
            last_paused_at = pause_start
 
        if status in ["RUNNING", "PAUSED"]:
            started_at = start_time
 
        if status == "COMPLETED":
            completed_at = planned_end
 
        order = {
            "WORK CENTER": row["wc"],
            "WORK ORDER NO.": row["wo"],
            "MAT NO.": row["mat"],
            "MAT. DESC.": row["desc"],
            "TOTAL QUANTITIES": total,
            "COMPLETED QUANTITIES": completed,
            "DAILY CAPACITY": daily_cap,
            "ORDER STATUS": status,
            "ORDER START DATE": start_time,
            "PLANNED END DATE": planned_end,
            "CURRENT ETA": planned_end,
            "PAUSE START": pause_start,
            "TOTAL DELAY SEC": 0.0,
            "LAST UPDATE": now,
            "STARTED AT": started_at,
            "LAST PAUSED AT": last_paused_at,
            "LAST RESUMED AT": last_resumed_at,
            "COMPLETED AT": completed_at,
            "EVENT LOG": [{
                "Timestamp": now,
                "Event": "INITIALIZED",
                "Status": status,
                "Completed Qty": int(completed),
                "Note": "Loaded from database"
            }]
        }
 
        orders.append(order)
 
    return orders
 
# -----------------------------
# HARDCODED 15-ROW DATABASE
# -----------------------------
WORK_ORDER_DB = [
    {"wo": "WO-TEST-001", "wc": "WC-1", "mat": "MAT-201", "desc": "ALUMINIUM BRACKET",    "total": 500,  "daily_cap": 14400, "completed": 500, "status": "COMPLETED"},
    {"wo": "WO-TEST-002", "wc": "WC-2", "mat": "MAT-342", "desc": "STEEL SHAFT",           "total": 320,  "daily_cap": 9600,  "completed": 180, "status": "READY"},
    {"wo": "WO-TEST-003", "wc": "WC-3", "mat": "MAT-115", "desc": "COPPER BUSHING",        "total": 250,  "daily_cap": 7200,  "completed": 250, "status": "COMPLETED"},
    {"wo": "WO-TEST-004", "wc": "WC-1", "mat": "MAT-478", "desc": "PLASTIC HOUSING",       "total": 400,  "daily_cap": 12000, "completed": 90,  "status": "READY"},
    {"wo": "WO-TEST-005", "wc": "WC-4", "mat": "MAT-561", "desc": "RUBBER GASKET",         "total": 600,  "daily_cap": 18000, "completed": 300, "status": "PAUSED"},
    {"wo": "WO-TEST-006", "wc": "WC-2", "mat": "MAT-234", "desc": "STAINLESS BOLT M12",    "total": 1000, "daily_cap": 28800, "completed": 450, "status": "READY"},
    {"wo": "WO-TEST-007", "wc": "WC-5", "mat": "MAT-389", "desc": "CAST IRON FLANGE",      "total": 150,  "daily_cap": 4320,  "completed": 60,  "status": "READY"},
    {"wo": "WO-TEST-008", "wc": "WC-3", "mat": "MAT-502", "desc": "TITANIUM ROD 10MM",     "total": 200,  "daily_cap": 5760,  "completed": 200, "status": "COMPLETED"},
    {"wo": "WO-TEST-009", "wc": "WC-4", "mat": "MAT-677", "desc": "BRASS FITTING NPT",     "total": 350,  "daily_cap": 10080, "completed": 120, "status": "PAUSED"},
    {"wo": "WO-TEST-010", "wc": "WC-1", "mat": "MAT-190", "desc": "CARBON FIBRE PANEL",    "total": 80,   "daily_cap": 2400,  "completed": 20,  "status": "READY"},
    {"wo": "WO-TEST-011", "wc": "WC-5", "mat": "MAT-845", "desc": "NYLON GEAR 32T",        "total": 500,  "daily_cap": 14400, "completed": 380, "status": "READY"},
    {"wo": "WO-TEST-012", "wc": "WC-2", "mat": "MAT-321", "desc": "ZINC DIE CAST COVER",   "total": 280,  "daily_cap": 8640,  "completed": 280, "status": "COMPLETED"},
    {"wo": "WO-TEST-013", "wc": "WC-3", "mat": "MAT-456", "desc": "SPRING STEEL CLIP",     "total": 750,  "daily_cap": 21600, "completed": 210, "status": "READY"},
    {"wo": "WO-TEST-014", "wc": "WC-4", "mat": "MAT-733", "desc": "POLYURETHANE SEAL",     "total": 420,  "daily_cap": 12960, "completed": 140, "status": "PAUSED"},
    {"wo": "WO-TEST-015", "wc": "WC-1", "mat": "MAT-910", "desc": "MAGNESIUM ALLOY PLATE", "total": 90,   "daily_cap": 2880,  "completed": 0,   "status": "READY"},
]
 
# -----------------------------
# SESSION STATE
# -----------------------------
if "orders" not in st.session_state:
    st.session_state.orders = create_orders_from_db()
 
if "page" not in st.session_state:
    st.session_state.page = "home"
 
if "selected_wo" not in st.session_state:
    st.session_state.selected_wo = None
 
if "activated_orders" not in st.session_state:
    st.session_state.activated_orders = set()
 
if "page" not in st.session_state:
    st.session_state.page = "home"
 
 
# -----------------------------
# UPDATE ACTIVATED ORDERS ONLY
# -----------------------------
for order in st.session_state.orders:
    if order["WORK ORDER NO."] in st.session_state.activated_orders:
        auto_update_order(order)
 
# -----------------------------
# HEADER
# -----------------------------
st.markdown('<div class="main-title">🏭 Real-Time Manufacturing Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">Track work orders, monitor progress, and test completion in real time.</div>', unsafe_allow_html=True)
 
# -----------------------------
# HOME PAGE
# -----------------------------
if st.session_state.page == "home":
    st.markdown('<div class="table-heading">Work Orders</div>', unsafe_allow_html=True)

    with st.expander("➕ Create New Work Order"):
        with st.form("create_wo_form", clear_on_submit=True):
            f1, f2 = st.columns(2)
            new_wo   = f1.text_input("Work Order No.")
            new_wc   = f2.text_input("Work Center")
            f3, f4 = st.columns(2)
            new_mat  = f3.text_input("Material No.")
            new_desc = f4.text_input("Description")
            f5, f6, f7 = st.columns(3)
            new_tq  = f5.number_input("Total Qty",      min_value=1, value=100)
            new_dc  = f6.number_input("Daily Capacity", min_value=1, value=2880)
            new_sd  = f7.date_input("Start Date")

            submitted = st.form_submit_button("Create Work Order")
            if submitted:
                if not new_wo or not new_wc:
                    st.error("Work Order No. and Work Center are required.")
                else:
                    now = datetime.now()
                    start_dt = datetime.combine(new_sd, datetime.min.time())
                    days = max(1, (new_tq + new_dc - 1) // new_dc)
                    planned_end = start_dt + timedelta(days=days)

                    new_order = {
                        "WORK CENTER": new_wc,
                        "WORK ORDER NO.": new_wo,
                        "MAT NO.": new_mat,
                        "MAT. DESC.": new_desc,
                        "TOTAL QUANTITIES": float(new_tq),
                        "COMPLETED QUANTITIES": 0.0,
                        "DAILY CAPACITY": float(new_dc),
                        "ORDER STATUS": "READY",
                        "ORDER START DATE": start_dt,
                        "PLANNED END DATE": planned_end,
                        "CURRENT ETA": planned_end,
                        "PAUSE START": None,
                        "TOTAL DELAY SEC": 0.0,
                        "LAST UPDATE": now,
                        "STARTED AT": None,
                        "LAST PAUSED AT": None,
                        "LAST RESUMED AT": None,
                        "COMPLETED AT": None,
                        "EVENT LOG": [{
                            "Timestamp": now,
                            "Event": "INITIALIZED",
                            "Status": "READY",
                            "Completed Qty": 0,
                            "Note": "Created via dashboard"
                        }]
                    }
                    st.session_state.orders.append(new_order)
                    st.success(f"Work Order **{new_wo}** created successfully!")
                    st.rerun()

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    grid_cols = st.columns(3)
    for idx, order in enumerate(st.session_state.orders):
        col = grid_cols[idx % 3]
        with col:
            delay_class = get_delay_class(order)
            updated_end = get_updated_end_time(order)
 
            st.markdown(f"""
            <div class="home-card">
                <div class="small-label">Work Order</div>
                <div class="big-value">{order["WORK ORDER NO."]}</div>
                <div class="small-label">Status</div>
                <div class="normal-value {get_status_class(order["ORDER STATUS"])}">{format_status(order["ORDER STATUS"])}</div>
                <div class="small-label">Updated End</div>
                <div class="normal-value">{updated_end.strftime("%Y-%m-%d %H:%M:%S")}</div>
                <div class="small-label">Delay</div>
                <div class="normal-value {delay_class}">{format_duration(get_live_delay_sec(order))}</div>
            </div>
            """, unsafe_allow_html=True)
 
            if st.button(f"Open {order['WORK ORDER NO.']}", key=f"open_{order['WORK ORDER NO.']}", width="stretch"):
                st.session_state.selected_wo = order["WORK ORDER NO."]
                st.session_state.page = "detail"
 
                if order["WORK ORDER NO."] not in st.session_state.activated_orders:
                    st.session_state.activated_orders.add(order["WORK ORDER NO."])
                    if order["ORDER STATUS"] == "READY":
                        order["ORDER STATUS"] = "RUNNING"
                        order["LAST UPDATE"] = datetime.now()
                        log_event(order, "STARTED", "Started after opening from home page")
 
                st.rerun()
 
    st.stop()
 
 
 
# -----------------------------
# DETAIL PAGE
# -----------------------------
selected_order = next(
    (order for order in st.session_state.orders if order["WORK ORDER NO."] == st.session_state.selected_wo),
    None
)
 
top1, top2, top3= st.columns([1, 1, 4])
 
with top1:
    if st.button("← Back", width="stretch"):
        st.session_state.page = "home"
        st.session_state.selected_wo = None
        st.rerun()
 
with top2:
    if st.button("Summary", width="stretch"):
        st.session_state.page = "summary"
        st.rerun()
 
if selected_order is None:
    st.warning("Selected work order not found.")
else:
    completion_pct = (selected_order["COMPLETED QUANTITIES"] / selected_order["TOTAL QUANTITIES"]) * 100
    live_delay = get_live_delay_sec(selected_order)
    updated_end = get_updated_end_time(selected_order)
    delay_class = get_delay_class(selected_order)
    delay_flag = "Delay" if live_delay > 0 else "On Time"
 
   
    # work order details
    st.markdown(f"""
    <div class="card">
        <div class="small-label">Selected Work Order Details</div>
        <div class="normal-value" style="margin-bottom:4px;">
            Work Center: <strong>{selected_order["WORK CENTER"]}</strong>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Material: <strong>{selected_order["MAT NO."]} — {selected_order["MAT. DESC."]}</strong>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Qty: <strong>{int(selected_order["COMPLETED QUANTITIES"])} / {int(selected_order["TOTAL QUANTITIES"])}</strong>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Planned End: <strong>{selected_order["PLANNED END DATE"].strftime("%Y-%m-%d %H:%M:%S")}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)
 
    # progress
    st.progress(min(completion_pct / 100, 1.0))
    st.markdown(
        f'<div class="progress-label">Progress: {completion_pct:.1f}%</div>',
        unsafe_allow_html=True
    )
 
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
 
    # buttons
    b1, b2, b3 = st.columns(3)
 
    with b1:
        if st.button("⏸ Pause", width="stretch"):
            if selected_order["ORDER STATUS"] == "RUNNING":
                selected_order["ORDER STATUS"] = "PAUSED"
                selected_order["PAUSE START"] = datetime.now()
                selected_order["LAST UPDATE"] = datetime.now()
                log_event(selected_order, "PAUSED", "Paused manually")
                st.rerun()
 
    with b2:
        if st.button("▶ Resume", width="stretch"):
            if selected_order["ORDER STATUS"] == "PAUSED" and selected_order["PAUSE START"] is not None:
                resume_time = datetime.now()
                pause_duration = (resume_time - selected_order["PAUSE START"]).total_seconds()
 
                # capture delay and add to estimated end
                selected_order["TOTAL DELAY SEC"] += pause_duration
                selected_order["PAUSE START"] = None
                selected_order["ORDER STATUS"] = "RUNNING"
                selected_order["LAST UPDATE"] = datetime.now()
                selected_order["CURRENT ETA"] = get_updated_end_time(selected_order)
                log_event(
                    selected_order,
                    "RESUMED",
                    f"Pause duration captured = {format_duration(pause_duration)}"
                )
                st.rerun()
 
    with b3:
        if st.button("🔄 Reset Orders", width="stretch"):
            st.session_state.orders = create_orders_from_db()
            st.session_state.selected_wo = None
            st.session_state.page = "home"
            st.session_state.activated_orders = set()
            st.rerun()
 
    # process tracking table - only selected order
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="table-heading">Process Tracking Table</div>', unsafe_allow_html=True)
 
    process_df = pd.DataFrame([{
        "WORK ORDER NO.": selected_order["WORK ORDER NO."],
        "STATUS": format_status(selected_order["ORDER STATUS"]),
        "STARTED AT": fmt_ts(selected_order["STARTED AT"]),
        "LAST PAUSED AT": fmt_ts(selected_order["LAST PAUSED AT"]),
        "LAST RESUMED AT": fmt_ts(selected_order["LAST RESUMED AT"]),
        "COMPLETED AT": fmt_ts(selected_order["COMPLETED AT"]),
        "COMPLETED QTY": int(selected_order["COMPLETED QUANTITIES"]),
        "TOTAL QTY": int(selected_order["TOTAL QUANTITIES"]),
        "ORIGINAL ETA": selected_order["PLANNED END DATE"].strftime("%Y-%m-%d %H:%M:%S"),
        "LIVE DELAY": format_duration(live_delay),
        "UPDATED END TIME": updated_end.strftime("%Y-%m-%d %H:%M:%S"),
        "DELAY STATUS": delay_flag
    }])
 
    styled_process = process_df.style.map(color_delay, subset=["DELAY STATUS"])
    st.dataframe(styled_process, use_container_width=True, hide_index=True)
 
    # completed orders table - only selected order
    st.markdown('<div class="table-heading">Completed Orders Table</div>', unsafe_allow_html=True)
 
    if selected_order["ORDER STATUS"] == "COMPLETED":
        completed_df = pd.DataFrame([{
            "WORK CENTER": selected_order["WORK CENTER"],
            "WORK ORDER NO.": selected_order["WORK ORDER NO."],
            "MAT NO.": selected_order["MAT NO."],
            "MAT. DESC.": selected_order["MAT. DESC."],
            "TOTAL QTY": int(selected_order["TOTAL QUANTITIES"]),
            "COMPLETED QTY": int(selected_order["COMPLETED QUANTITIES"]),
            "START DATE": selected_order["ORDER START DATE"].strftime("%Y-%m-%d %H:%M:%S"),
            "PLANNED END": selected_order["PLANNED END DATE"].strftime("%Y-%m-%d %H:%M:%S"),
            "UPDATED END": updated_end.strftime("%Y-%m-%d %H:%M:%S"),
            "FINAL STATUS": format_status(selected_order["ORDER STATUS"]),
            "DELAY STATUS": delay_flag
        }])
 
        styled_completed = completed_df.style.map(color_delay, subset=["DELAY STATUS"])
        st.dataframe(styled_completed, use_container_width=True, hide_index=True)
    else:
        st.info("This work order is not completed yet.")
 
    # event log - only selected order
    st.markdown('<div class="table-heading">Completed Orders Event Log</div>', unsafe_allow_html=True)
 
    if selected_order["ORDER STATUS"] == "COMPLETED":
        completed_log_rows = []
        for event in selected_order["EVENT LOG"]:
            completed_log_rows.append({
                "WORK ORDER NO.": selected_order["WORK ORDER NO."],
                "EVENT": event["Event"],
                "STATUS": format_status(event["Status"]),
                "TIMESTAMP": pd.to_datetime(event["Timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                "COMPLETED QTY": event["Completed Qty"],
                "NOTE": event["Note"]
            })
 
        completed_log_df = pd.DataFrame(completed_log_rows)
        st.dataframe(completed_log_df, use_container_width=True, hide_index=True)
    else:
        st.info("Event log for completed state will appear here once this work order is completed.")
 
# -----------------------------
# SUMMARY PAGE
# -----------------------------
if st.session_state.page == "summary":
    top1, top2 = st.columns([1, 5])
 
    with top1:
        if st.button("← Back to Home", width="stretch"):
            st.session_state.page = "home"
            st.session_state.selected_wo = None
            st.rerun()
 
    with top2:
        st.markdown('<div class="table-heading">Complete Summary Table</div>', unsafe_allow_html=True)
 
    summary_rows = []
    for order in st.session_state.orders:
        live_delay = get_live_delay_sec(order)
        updated_end = get_updated_end_time(order)
        delay_flag = "Delay" if live_delay > 0 else "On Time"
        completion_pct = (order["COMPLETED QUANTITIES"] / order["TOTAL QUANTITIES"]) * 100
 
        summary_rows.append({
            "WORK ORDER NO.": order["WORK ORDER NO."],
            "WORK CENTER": order["WORK CENTER"],
            "MAT NO.": order["MAT NO."],
            "MAT. DESC.": order["MAT. DESC."],
            "STATUS": format_status(order["ORDER STATUS"]),
            "TOTAL QTY": int(order["TOTAL QUANTITIES"]),
            "COMPLETED QTY": int(order["COMPLETED QUANTITIES"]),
            "COMPLETION %": f"{completion_pct:.1f}%",
            "PLANNED END": order["PLANNED END DATE"].strftime("%Y-%m-%d %H:%M:%S"),
            "UPDATED END": updated_end.strftime("%Y-%m-%d %H:%M:%S"),
            "LIVE DELAY": format_duration(live_delay),
            "DELAY STATUS": delay_flag,
            "STARTED AT": fmt_ts(order["STARTED AT"]),
            "LAST PAUSED AT": fmt_ts(order["LAST PAUSED AT"]),
            "LAST RESUMED AT": fmt_ts(order["LAST RESUMED AT"]),
            "COMPLETED AT": fmt_ts(order["COMPLETED AT"]),
        })
 
    summary_df = pd.DataFrame(summary_rows)
    styled_summary = summary_df.style.map(color_delay, subset=["DELAY STATUS"])
    st.dataframe(styled_summary, use_container_width=True, hide_index=True)
 
    st.stop()
 
# -----------------------------
# AUTO REFRESH
# -----------------------------
time.sleep(5)
st.rerun()

 