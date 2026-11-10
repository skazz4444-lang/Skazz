import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import sqlite3
import plotly.graph_objects as go
from datetime import date
from io import StringIO

# =====================================================
# MARKET RADAR - PRO STREAMLIT APP
# =====================================================

st.set_page_config(
    page_title="Market Radar",
    page_icon="📊",
    layout="wide"
)

DB = "market_radar.db"

# ---------------- DESIGN & CLEAN CSS ----------------

st.markdown("""
<style>
.stApp {
    background: #0b1220;
    color: #e8eef7;
}
[data-testid="stSidebar"] {
    background: #111c2e;
    border-right: 1px solid #1e293b;
}
[data-testid="stMetric"] {
    background: #131d31;
    border: 1px solid #223249;
    padding: 16px;
    border-radius: 12px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
}
h1, h2, h3, h4 {
    color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}
.stCaption {
    color: #94a3b8;
}
div.stButton > button {
    background-color: #2563eb;
    color: white;
    border-radius: 8px;
    border: none;
    padding: 0.5rem 1rem;
    font-weight: 600;
}
div.stButton > button:hover {
    background-color: #1d4ed8;
}
</style>
""", unsafe_allow_html=True)


# ---------------- DATABASE SETUP ----------------

def connect_db():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    with connect_db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            fee REAL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            notes TEXT DEFAULT ''
        )
        """)

init_db()


# ---------------- DATA SOURCES & CACHE ----------------

@st.cache_data(ttl=60)
def get_history(ticker, period="2y"):
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False, threads=False)
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        return df.dropna()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

@st.cache_data(ttl=3600)
def get_fred(series):
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        if len(df.columns) < 2:
            return pd.DataFrame()
        df = df.iloc[:, :2]
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df.dropna().sort_values("date")
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=900)
def get_news(query):
    try:
        response = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": query, "mode": "ArtList", "format": "json", "maxrecords": 15, "sort": "DateDesc"},
            timeout=20
        )
        response.raise_for_status()
        return response.json().get("articles", [])
    except Exception:
        return []


# ---------------- HELPERS ----------------

def close_series(df):
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df["Close"], errors="coerce").dropna()

def safe_float(value):
    try:
        value = float(value)
        return value if np.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def money(value, currency="$"):
    if value is None or pd.isna(value):
        return "לא זמין"
    return f"{currency}{value:,.2f}"


# ---------------- TECHNICAL ANALYSIS ----------------

def technical(df):
    close = close_series(df)
    if len(close) < 30:
        return {}

    returns = close.pct_change().dropna()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    drawdown = close / close.cummax() - 1

    return {
        "price": float(close.iloc[-1]),
        "change": float(returns.iloc[-1] * 100),
        "month": safe_float((close.iloc[-1] / close.iloc[-22] - 1) * 100) if len(close) >= 22 else None,
        "quarter": safe_float((close.iloc[-1] / close.iloc[-64] - 1) * 100) if len(close) >= 64 else None,
        "ma20": safe_float(close.rolling(20).mean().iloc[-1]),
        "ma50": safe_float(close.rolling(50).mean().iloc[-1]),
        "ma200": safe_float(close.rolling(200).mean().iloc[-1]),
        "rsi": safe_float(rsi.iloc[-1]),
        "volatility": safe_float(returns.std() * np.sqrt(252) * 100),
        "drawdown": safe_float(drawdown.iloc[-1] * 100),
        "max_drawdown": safe_float(drawdown.min() * 100)
    }

def price_chart(df, title):
    if df.empty:
        st.warning("אין נתונים להצגה.")
        return

    close = close_series(df)
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=close.index, y=close, name="מחיר ($)", line=dict(color="#3b82f6", width=2)))

    for period in [50, 200]:
        if len(close) >= period:
            color = "#10b981" if period == 50 else "#f59e0b"
            fig.add_trace(go.Scatter(x=close.index, y=close.rolling(period).mean(), name=f"MA{period}", line=dict(color=color, width=1.5, dash="dot")))

    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor="#0b1220",
        plot_bgcolor="#0b1220",
        height=400,
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20)
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------- SMART MARKET SCORE ----------------

def calculate_market_score(sp_df, vix_value):
    tech = technical(sp_df)
    if not tech:
        return None, {}, "אין נתונים מספיקים לחישוב"

    factors = {}
    
    if tech["ma200"] is not None:
        factors["מגמה ארוכה"] = 100 if tech["price"] > tech["ma200"] else 25

    if tech["ma50"] is not None:
        factors["מגמה בינונית"] = 100 if tech["price"] > tech["ma50"] else 35

    if tech["rsi"] is not None:
        rsi = tech["rsi"]
        if 40 <= rsi <= 60:
            factors["מומנטום בריא"] = 85
        elif rsi < 40:
            factors["מחיר זול / הזדמנות איסוף"] = 100
        elif rsi > 70:
            factors["שוק יקר / קנוי יתר"] = 30
        else:
            factors["מומנטום"] = 65

    if vix_value is not None:
        if vix_value < 16:
            factors["רמת פחד בשוק"] = 90
        elif vix_value < 22:
            factors["רמת פחד בשוק"] = 70
        elif vix_value < 30:
            factors["רמת פחד בשוק"] = 45
        else:
            factors["רמת פחד בשוק"] = 20

    dd = tech.get("drawdown", 0)
    if dd is not None:
        if dd >= -2:
            factors["קרבה לשיא"] = 70
        elif -10 <= dd < -2:
            factors["תיקון בריא (זול יותר מהשיא)"] = 95
        elif -20 <= dd < -10:
            factors["ירידה משמעותית (הנחה טובה)"] = 100
        else:
            factors["ירידה חדה מאוד (סיכון גבוה)"] = 40

    if not factors:
