import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(
    page_title="US Market Entry Live",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #161b22; padding: 10px; border-radius: 10px; border: 1px solid #30363d; }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 בוחן כניסה למדדים (Live)")
st.caption(f"עדכון אחרון: {datetime.now().strftime('%H:%M:%S')} | מותאם למובייל")

market_choice = st.selectbox("בחר מדד לבדיקה:", ["S&P 500 (^GSPC)", "Nasdaq Composite (^IXIC)"])
ticker_sym = "^GSPC" if "S&P" in market_choice else "^IXIC"

@st.cache_data(ttl=15)
def fetch_market_data(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        info = t.info
        return hist, info, "Primary (Yahoo)"
    except Exception as e:
        return pd.DataFrame(), {}, f"Error: {str(e)}"

with st.spinner("🔄 טוען נתוני שוק חיים..."):
    hist, info, source_status = fetch_market_data(ticker_sym)
    vix_hist, _, _ = fetch_market_data("^VIX")
    tnx_hist, _, _ = fetch_market_data("^TNX")

if hist.empty:
    st.error("⚠️ שגיאה בטעינת הנתונים מהשרת. מנסה שוב בעוד רגע...")
else:
    current_price = hist['Close'].iloc[-1]
    prev_close = hist['Close'].iloc[-2]
    daily_change = ((current_price - prev_close) / prev_close) * 100
    
    sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
    sma_200 = hist['Close'].rolling(window=200).mean().iloc[-1]
    yearly_high = hist['High'].max()
    drawdown = ((current_price - yearly_high) / yearly_high) * 100

    current_vix = vix_hist['Close'].iloc[-1] if not vix_hist.empty else 20.0
    current_tnx = tnx_hist['Close'].iloc[-1] if not tnx_hist.empty else 4.2
    pe_ratio = info.get('trailingPE', info.get('forwardPE', 21.5))
    if not pe_ratio: pe_ratio = 21.5

    score = 50

    if current_vix > 30: score += 25
    elif current_vix > 22: score += 15
    elif current_vix < 14: score -= 15

    if drawdown < -15: score += 25
    elif drawdown < -10: score += 15
    elif drawdown < -5: score += 5
    elif drawdown > -2: score -= 10

    if current_price < sma_200: score += 20
    else: score += 5

    if pe_ratio < 18: score += 15
    elif pe_ratio > 26: score -= 20

    if current_tnx > 4.5: score -= 10
    elif current_tnx < 3.8: score += 10

    score = max(0, min(100, int(score)))

    st.markdown("---")
    st.subheader("📊 מד סיכון ונקודת כניסה")
    
    st.progress(score / 100)

    if score >= 75:
        st.success(f"**ציון כניסה: {score}/100 – אזור קנייה חזק מאוד! (הזדמנות בשל פחד/תיקון)**")
    elif score >= 55:
        st.info(f"**ציון כניסה: {score}/100 – כניסה סבירה / ניטרלי (מומלץ פיזור D.C.A)**")
    elif score >= 35:
        st.warning(f"**ציון כניסה: {score}/100 – זהירות, שוק ללא תמריצי קנייה חזקים.**")
    else:
        st.error(f"**ציון כניסה: {score}/100 – שוק יקר או אופורי בקיצוניות. עדיף להמתין.**")

    st.markdown("### 📈 נתונים בזמן אמת")
    col1, col2 = st.columns(2)
    col1.metric("מחיר נוכחי", f"{current_price:,.2f}", f"{daily_change:+.2f}%")
    col2.metric("מדד הפחד (VIX)", f"{current_vix:.2f}")

    col3, col4 = st.columns(2)
    col3.metric("מרחק מהשיא", f"{drawdown:.2f}%")
    col4.metric("מכפיל רווח (PE)", f"{pe_ratio:.1f}")

    if st.button("🔄 רענן נתונים עכשיו"):
        st.cache_data.clear()
        st.rerun()

    with st.expander("🔍 פירוט פרמטרים וצפי מאקרו"):
        st.write(f"- **ממוצע נע 50 ימים:** {sma_50:,.2f}")
        st.write(f"- **ממוצע נע 200 ימים:** {sma_200:,.2f}")
        st.write(f"- **תשואת אג\"ח 10 שנים (TNX):** {current_tnx}%")
        st.write(f"- **סטטוס מקור מידע:** פעיל תקין ({source_status})")
