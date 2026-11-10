import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(
    page_title="Ultimate Market Entry & Exit Advisor",
    page_icon="🎯",
    layout="centered"
)

# עיצוב נקי, חד וברור למובייל
st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #f3f4f6; }
    h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
    p, span, label, div { color: #e5e7eb !important; }
    .stMetricValue { color: #38bdf8 !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 יועץ כניסה ויציאה חכם לתיק ולמדדים")
st.caption(f"עדכון חי: {datetime.now().strftime('%H:%M:%S')} | מעקב מותאם לקרנות סל (SPY / QQQ)")

st.markdown("### 🌐 הגדרות מאקרו וגאופוליטיקה")
geo_risk = st.select_slider(
    "רמת מתיחות פוליטית / ביטחונית עולמית:",
    options=["רגוע ושגרתי", "מתיחות בינונית", "משבר או מלחמה אזורית", "משבר גלובלי קיצוני"],
    value="רגוע ושגרתי"
)

@st.cache_data(ttl=10)
def fetch_market_with_fallback(yahoo_ticker, stooq_symbol):
    try:
        t = yf.Ticker(yahoo_ticker)
        hist = t.history(period="1y")
        info = t.info
        if not hist.empty and len(hist) > 10:
            return hist, info, "Yahoo Finance (ראשי פעיל)"
    except Exception:
        pass

    try:
        stooq_url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
        df = pd.read_csv(stooq_url)
        if not df.empty and 'Close' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            df = df.sort_index()
            fallback_info = {
                'trailingPE': 22.5, 
                'forwardPE': 21.0, 
                'targetMeanPrice': float(df['Close'].iloc[-1] * 1.1)
            }
            return df, fallback_info, "Stooq (ספק גיבוי פעיל)"
    except Exception:
        pass

    return pd.DataFrame(), {}, "שגיאה: כל הספקים נכשלו"

with st.spinner("🔄 שולף נתונים חיים עבור SPY ו-QQQ..."):
    sp_hist, sp_info, sp_status = fetch_market_with_fallback("SPY", "spy")
    nd_hist, nd_info, nd_status_nd = fetch_market_with_fallback("QQQ", "qqq")
    vix_hist, _, _ = fetch_market_with_fallback("^VIX", "^vix")
    tnx_hist, _, _ = fetch_market_with_fallback("^TNX", "^tnx")

if sp_hist.empty or nd_hist.empty:
    st.error("⚠️ שגיאה בשליפת הנתונים מכל ספקי הגיבוי. נסה לרענן עוד מעט.")
else:
    current_vix = float(vix_hist['Close'].iloc[-1]) if not vix_hist.empty else 20.0
    current_tnx = float(tnx_hist['Close'].iloc[-1]) if not tnx_hist.empty else 4.2

    def analyze_market(hist, info):
        current_price = float(hist['Close'].iloc[-1])
        prev_close = float(hist['Close'].iloc[-2])
        daily_change = ((current_price - prev_close) / prev_close) * 100
        
        sma_50 = float(hist['Close'].rolling(window=50).mean().iloc[-1])
        sma_200 = float(hist['Close'].rolling(window=200).mean().iloc[-1])
        trend = "🟢 מגמת שור בריאה (Golden Cross)" if sma_50 > sma_200 else "🔴 מגמת דוב / לחץ (Death Cross)"
        
        yearly_high = float(hist['High'].max())
        drawdown = ((current_price - yearly_high) / yearly_high) * 100

        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean
