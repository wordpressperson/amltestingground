# fin_guard_aml_app.py
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import time

# ==================== CUSTOM CSS - Professional dark theme ====================
st.markdown("""
<style>
    .main {background-color: #0f172a; color: #f1f5f9;}
    .stMetric {background: linear-gradient(135deg, #1e2937, #334155); border-radius: 16px; padding: 15px 20px; box-shadow: 0 10px 30px rgba(245, 166, 35, 0.25);}
    .stMetric label {color: #f5a623 !important; font-size: 1.1rem;}
    .stMetric div[data-testid="stMetricValue"] {font-size: 2.4rem; font-weight: 700;}
    h1, h2, h3 {color: #f5a623 !important;}
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .css-1d391kg {background-color: #1e2937; border-radius: 12px; padding: 1rem;}
    .alert-card {background: #1e2937; border-radius: 12px; padding: 15px; margin-bottom: 10px; border-left: 5px solid #f5a623;}
    .dataframe {background-color: #1e2937 !important;}
</style>
""", unsafe_allow_html=True)

# ==================== SECRETS ====================
try:
    BASE_URL = st.secrets["api"]["base_url"]
    BEARER_TOKEN = st.secrets["api"]["bearer_token"]
    OPENAI_API_KEY = st.secrets["openai"]["api_key"]
except Exception:
    st.error("Missing secrets. Please add [api] and [openai] sections in Streamlit Secrets.")
    st.stop()

headers = {"Authorization": f"Bearer {BEARER_TOKEN}", "accept": "application/json"}

st.set_page_config(page_title="FinGuard AML", layout="wide", page_icon="🛡️")

# ==================== SIDEBAR ====================
st.sidebar.image("https://via.placeholder.com/220x60/1e2937/f5a623?text=FinGuard+AML", width=220)
page = st.sidebar.radio("Navigation", ["Dashboard", "Customers", "Transactions", "Alerts", "Screening", "Reports"])

# ==================== DATA LOADING ====================
@st.cache_data(ttl=60)
def load_data():
    """
    Attempts to fetch:
      - /health (optional)
      - /v1/alerts (documented)
      - /v1/transactions (if available)
      - /v1/customers (if available)
    Falls back to fixtures if list endpoints are not present.
    Returns: customers_df, accounts_df, transactions_df, alerts_df, health_status
    """
    alerts_df = pd.DataFrame()
    customers_df = pd.DataFrame()
    accounts_df = pd.DataFrame()
    transactions_df = pd.DataFrame()
    health_status = {"ok": False, "detail": None}

    # 1) Health check
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        resp.raise_for_status()
        health_json = resp.json()
        health_status = {"ok": True, "detail": health_json}
    except Exception as e:
        health_status = {"ok": False, "detail": str(e)}

    # 2) Alerts (documented endpoint)
    try:
        resp = requests.get(f"{BASE_URL}/v1/alerts", headers=headers, params={"limit": 200}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        alerts_list = data.get("alerts", data if isinstance(data, list) else [])
        alerts_df = pd.DataFrame(alerts_list)
    except Exception:
        alerts_df = pd.DataFrame()

    # 3) Try to fetch transactions list if backend exposes it
    try:
        resp_tx = requests.get(f"{BASE_URL}/v1/transactions", headers=headers, params={"limit": 500}, timeout=10)
        if resp_tx.status_code == 200:
            tx_json = resp_tx.json()
            # try common shapes
            if isinstance(tx_json, dict) and "transactions" in tx_json:
                transactions_df = pd.DataFrame(tx_json.get("transactions", []))
            elif isinstance(tx_json, list):
                transactions_df = pd.DataFrame(tx_json)
            else:
                transactions_df = pd.DataFrame()
    except Exception:
        # endpoint may not exist; keep empty to fallback to fixtures
        pass

    # 4) Try to fetch customers list if backend exposes it
    try:
        resp_cust = requests.get(f"{BASE_URL}/v1/customers", headers=headers, params={"limit": 500}, timeout=10)
        if resp_cust.status_code == 200:
            cust_json = resp_cust.json()
            if isinstance(cust_json, dict) and "customers" in cust_json:
                customers_df = pd.DataFrame(cust_json.get("customers", []))
            elif isinstance(cust_json, list):
                customers_df = pd.DataFrame(cust_json)
            else:
                customers_df = pd.DataFrame()
    except Exception:
        pass

    # 5) Fallback to fixtures if still empty
    if transactions_df.empty or customers_df.empty:
        try:
            customers_df = customers_df if not customers_df.empty else pd.read_json("fixtures/customers.json")
            accounts_df = pd.read_json("fixtures/accounts.json")
            transactions_df = transactions_df if not transactions_df.empty else pd.read_json("fixtures/transactions.json")
        except Exception:
            # minimal demo fallback
            if customers_df.empty:
                customers_df = pd.DataFrame([{"customer_id": "C001", "full_name": "Client Johnson", "risk_category": "high"}])
            if transactions_df.empty:
                transactions_df = pd.DataFrame([{"txn_id": "T001", "timestamp": "2026-04-23 08:15", "amount": 550000}])
            if accounts_df.empty:
                accounts_df = pd.DataFrame()

    # Normalize timestamp column if present
    if "timestamp" in transactions_df.columns:
        try:
            transactions_df["timestamp"] = pd.to_datetime(transactions_df["timestamp"], errors="coerce")
        except Exception:
            pass

    return customers_df, accounts_df, transactions_df, alerts_df, health_status

# Load data
customers_df, accounts_df, transactions_df, alerts_df, health_status = load_data()

# ==================== DASHBOARD PAGE ====================
if page == "Dashboard":
    st.title("🛡️ AML & Fraud Monitoring Dashboard")
    st.caption("Real-time Anti-Money Laundering & Fraud Detection | Powered by AzurizedAMLSolution")

    # Connection status
    col_status, _, _ = st.columns([1, 8, 1])
    with col_status:
        if health_status.get("ok"):
            st.success("API Health: OK")
        else:
            st.error("API Health: Unreachable")
            if st.button("Show API error detail"):
                st.write(health_status.get("detail"))

    # compute KPIs
    total_txns = len(transactions_df) if not transactions_df.empty else 36421
    total_amount = transactions_df['amount'].sum() if 'amount' in transactions_df.columns and not transactions_df.empty else None
    unusual_txns = len(alerts_df) if not alerts_df.empty else 250
    aml_entities = len(customers_df) if not customers_df.empty else 10108

    amount_display = f"₵{total_amount:,.2f}" if total_amount is not None else "₵36.19B"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Transactions", f"{total_txns:,}", "↑ 12%")
    with col2:
        st.metric("Unusual Transactions", f"{unusual_txns:,}", "🔥", delta_color="inverse")
    with col3:
        st.metric("AML Entities", f"{aml_entities:,}")
    with col4:
        st.metric("Amount Transacted", amount_display, "↑ 8%")

    # Main layout
    left_col, center_col, right_col = st.columns([1.2, 2.5, 1.2])

    with left_col:
        st.subheader("Recent Activity")
        # show top alerts if available
        if not alerts_df.empty:
            top_alerts = alerts_df.sort_values(by="created_at", ascending=False).head(5)
            for _, row in top_alerts.iterrows():
                created = row.get("created_at", "")
                risk = row.get("risk_score", "")
                text = f"Alert {row.get('alert_id','')} — {row.get('alert_type','Unknown')} — Risk {risk} — {created}"
                st.markdown(f"""
                <div class="alert-card">
                    <strong>⚠️ {text}</strong>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.metric("Total Today", "2,847", "↑ 18%")
            st.metric("Unusual Today", "41", "🔥")

    with center_col:
        st.subheader("Transactions by Time of Day")
        # Build hourly stacked counts from transactions_df if possible
        if "timestamp" in transactions_df.columns and not transactions_df.empty:
            tx = transactions_df.dropna(subset=["timestamp"]).copy()
            tx["hour"] = tx["timestamp"].dt.hour
            hourly = tx.groupby("hour").size().reindex(range(0,24), fill_value=0).reset_index()
            hourly.columns = ["hour", "count"]
            # For demo, split into Valid/Fraud/Unassigned heuristically if risk_score exists
            if "risk_score" in tx.columns:
                valid = tx[tx["risk_score"] < 0.5].groupby("hour").size().reindex(range(0,24), fill_value=0)
                fraud = tx[tx["risk_score"] >= 0.8].groupby("hour").size().reindex(range(0,24), fill_value=0)
                unassigned = hourly["count"] - valid - fraud
                hourly_df = pd.DataFrame({
                    "hour": list(range(0,24)),
                    "Valid": valid.values,
                    "Fraud": fraud.values,
                    "Unassigned": unassigned.values
                })
            else:
                # fallback: simple split by quantiles of amount
                if "amount" in tx.columns:
                    q = tx["amount"].quantile([0.33, 0.66]).values
                    valid = tx[tx["amount"] <= q[0]].groupby("hour").size().reindex(range(0,24), fill_value=0)
                    fraud = tx[tx["amount"] >= q[1]].groupby("hour").size().reindex(range(0,24), fill_value=0)
                    unassigned = hourly["count"] - valid - fraud
                    hourly_df = pd.DataFrame({
                        "hour": list(range(0,24)),
                        "Valid": valid.values,
                        "Fraud": fraud.values,
                        "Unassigned": unassigned.values
                    })
                else:
                    # fallback demo slice
                    hourly_df = pd.DataFrame({
                        'hour': list(range(8,16)),
                        'Valid': [17, 12, 14, 15, 5, 4, 20, 16],
                        'Fraud': [3, 5, 6, 9, 3, 2, 8, 10],
                        'Unassigned': [8, 4, 5, 10, 2, 1, 14, 11]
                    })
        else:
            hourly_df = pd.DataFrame({
                'hour': list(range(8,16)),
                'Valid': [17, 12, 14, 15, 5, 4, 20, 16],
                'Fraud': [3, 5, 6, 9, 3, 2, 8, 10],
                'Unassigned': [8, 4, 5, 10, 2, 1, 14, 11]
            })

        fig_bar = px.bar(
            hourly_df, x='hour', y=['Valid', 'Fraud', 'Unassigned'],
            color_discrete_sequence=['#f5a623', '#ef553b', '#a3bffa'],
            barmode='stack', title="Valid vs Fraud vs Unassigned"
        )
        fig_bar.update_layout(template="plotly_dark", plot_bgcolor="#1e2937", paper_bgcolor="#1e2937", height=380)
        st.plotly_chart(fig_bar, use_container_width=True)

    with right_col:
        st.subheader("Today – Verification")
        # Pie chart from alerts status if available
        if not alerts_df.empty and "status" in alerts_df.columns:
            status_counts = alerts_df["status"].value_counts().to_dict()
            labels = list(status_counts.keys())
            values = list(status_counts.values())
            colors = ["#f5a623", "#ef553b", "#64748b"][:len(labels)]
            fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.65, marker_colors=colors)])
        else:
            fig_pie = go.Figure(data=[go.Pie(
                labels=["Verified as valid", "Confirmed as fraudulent", "Unassigned"],
                values=[130, 80, 40],
                hole=0.65,
                marker_colors=["#f5a623", "#ef553b", "#64748b"]
            )])
        fig_pie.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), height=300)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Lower sections
    tab1, tab2, tab3 = st.tabs(["Unusual Transaction Alerts", "Ongoing Investigations", "Risk Monitoring"])

    with tab1:
        st.subheader("Unusual Transaction Alerts")
        if not alerts_df.empty:
            for _, row in alerts_df.sort_values(by="created_at", ascending=False).head(6).iterrows():
                text = f"{row.get('alert_type','Unknown')} — Risk {row.get('risk_score','')}"
                st.markdown(f"""
                <div class="alert-card">
                    <strong>⚠️ {text}</strong>
                </div>
                """, unsafe_allow_html=True)
        else:
            alert_examples = [
                {"icon": "⚠️", "text": "Client Johnson did more than 10 transactions at same time a day totaling GH₵550,000"},
                {"icon": "⚠️", "text": "Client Martha did more than 25 transactions in same month totaling GH₵2,550,000"}
            ]
            for alert in alert_examples:
                st.markdown(f"""
                <div class="alert-card">
                    <strong>{alert['icon']} {alert['text']}</strong>
                </div>
                """, unsafe_allow_html=True)

    with tab2:
        st.subheader("Ongoing Investigation")
        investigation_data = pd.DataFrame({
            "Bank": ["Federal bank USA", "Add text here", "Add text here", "Add text here"],
            "Client": ["Johnson", "Martha", "Add text here", "Add text here"],
            "Assigned to": ["Agent Smith", "Agent Smith", "Agent Smith", "Agent Smith"],
            "Progress": ["Investigation opened", "In peer review", "Complete", "Confirmed as unusual"]
        })
        st.dataframe(investigation_data, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("Synthetic Identities – Risk Alerts")
        risk_data = pd.DataFrame({
            "Risk Category": ["Low risk", "Medium risk", "High risk"],
            "Transactions": [98, 8, 4]
        })
        fig_risk = px.bar(risk_data, x="Transactions", y="Risk Category", orientation='h',
                          color="Risk Category", color_discrete_sequence=["#ec4899", "#f43f5e", "#be123c"])
        fig_risk.update_layout(template="plotly_dark", height=280)
        st.plotly_chart(fig_risk, use_container_width=True)

        st.subheader("Transaction Summary (by Country)")
        # If transactions have 'country' and 'timestamp' and 'amount', build area chart; else demo
        if not transactions_df.empty and {"timestamp", "amount"}.issubset(transactions_df.columns):
            # demo grouping by country if present
            if "country" in transactions_df.columns:
                area_df = transactions_df.copy()
                area_df["Date"] = area_df["timestamp"].dt.date
                area_pivot = area_df.groupby(["Date", "country"])["amount"].sum().reset_index()
                area_pivot = area_pivot.pivot(index="Date", columns="country", values="amount").fillna(0).reset_index()
                fig_area = px.area(area_pivot, x="Date", y=area_pivot.columns.drop("Date"),
                                   color_discrete_sequence=px.colors.sequential.Plasma_r)
            else:
                # fallback demo
                dates = pd.date_range(start="2026-04-15", periods=7, freq='D')
                area_data = pd.DataFrame({
                    "Date": dates,
                    "US": [320, 180, 250, 380, 450, 390, 480],
                    "Sweden": [150, 90, 220, 180, 300, 420, 490],
                    "France": [280, 120, 90, 210, 340, 280, 310],
                    "India": [90, 70, 110, 250, 400, 370, 460]
                })
                fig_area = px.area(area_data, x="Date", y=["US","Sweden","France","India"],
                                   color_discrete_sequence=px.colors.sequential.Plasma_r)
        else:
            dates = pd.date_range(start="2026-04-15", periods=7, freq='D')
            area_data = pd.DataFrame({
                "Date": dates,
                "US": [320, 180, 250, 380, 450, 390, 480],
                "Sweden": [150, 90, 220, 180, 300, 420, 490],
                "France": [280, 120, 90, 210, 340, 280, 310],
                "India": [90, 70, 110, 250, 400, 370, 460]
            })
            fig_area = px.area(area_data, x="Date", y=["US","Sweden","France","India"],
                               color_discrete_sequence=px.colors.sequential.Plasma_r)

        fig_area.update_layout(template="plotly_dark", height=340)
        st.plotly_chart(fig_area, use_container_width=True)

# ==================== OTHER PAGES ====================
elif page == "Customers":
    st.subheader("Customer Directory")
    st.dataframe(customers_df, use_container_width=True, height=700)

elif page == "Transactions":
    st.subheader("All Transactions")
    st.dataframe(transactions_df, use_container_width=True, height=700)

elif page == "Alerts":
    st.subheader("Alert Queue")
    st.caption("Manage and investigate all AML/CFT alerts.")
    if alerts_df.empty:
        st.info("No alerts from API – showing demo alerts")
        display_alerts = transactions_df.head(8).copy() if not transactions_df.empty else pd.DataFrame()
    else:
        display_alerts = alerts_df.copy()

    if not display_alerts.empty:
        st.dataframe(display_alerts, use_container_width=True, height=500)

    st.subheader("SAR Narratives (AI Generated)")
    model_choice = st.selectbox("OpenAI Model", ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"], index=0)
    if st.button("Generate New SAR Narrative", type="primary"):
        with st.spinner("Generating professional SAR narrative with OpenAI..."):
            try:
                import openai
                openai.api_key = OPENAI_API_KEY
                prompt = f"""You are a senior AML compliance officer. Generate a formal Suspicious Activity Report (SAR) narrative.
Customer: {display_alerts.iloc[0].get('full_name', 'Unknown') if not display_alerts.empty else 'Unknown'}
Risk Score: 0.92
Alert Type: Multiple rapid high-value transfers"""
                response = openai.chat.completions.create(
                    model=model_choice,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7
                )
                st.success("SAR Generated!")
                st.markdown(response.choices[0].message.content)
            except Exception as e:
                st.error(f"OpenAI error: {e}")

elif page == "Screening":
    st.subheader("Screening Results")
    st.dataframe(customers_df, use_container_width=True)

elif page == "Reports":
    st.subheader("Generated Reports")
    reports = pd.DataFrame([
        {"Report Name": "SAR-2026-04-001", "Type": "SAR", "Generated Date": "2026-04-23", "Status": "Draft"},
        {"Report Name": "CTR-Q2-2026", "Type": "CTR", "Generated Date": "2026-04-20", "Status": "Submitted"},
    ])
    st.dataframe(reports, use_container_width=True)

# Footer and refresh
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Connected to {BASE_URL} | Demo Ready 🚀")
if st.button("🔄 Refresh All Data"):
    st.cache_data.clear()
    st.experimental_rerun()
