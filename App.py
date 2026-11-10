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

# הגדרת מאקרו גלובלית (סיכון פוליטי / ביטחוני)
st.markdown("### 🌐 הגדרות מאקרו וגאופוליטיקה")
geo_risk = st.select_slider(
    "רמת מתיחות פוליטית / ביטחונית עולמית:",
    options=["רגוע ושגרתי", "מתיחות בינונית", "משבר או מלחמה אזורית", "משבר גלובלי קיצוני"],
    value="רגוע ושגרתי"
)

# --- פונקציית שליפת נתונים מעודכנת לקרנות סל (SPY / QQQ) ---
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
                'targetMeanPrice': df['Close'].iloc[-1] * 1.1
            }
            return df, fallback_info, "Stooq (ספק גיבוי פעיל)"
    except Exception:
        pass

    return pd.DataFrame(), {}, "שגיאה: כל הספקים נכשלו"

with st.spinner("🔄 שולף נתונים חיים עבור SPY ו-QQQ..."):
    # מעבר ממעקב אחרי מדדים גולמיים למעקב אחרי קרנות סל אמיתיות (SPY ו-QQQ)
    sp_hist, sp_info, sp_status = fetch_market_with_fallback("SPY", "spy")
    nd_hist, nd_info, nd_status_nd = fetch_market_with_fallback("QQQ", "qqq")
    vix_hist, _, _ = fetch_market_with_fallback("^VIX", "^vix")
    tnx_hist, _, _ = fetch_market_with_fallback("^TNX", "^tnx")

if sp_hist.empty or nd_hist.empty:
    st.error("⚠️ שגיאה בשליפת הנתונים מכל ספקי הגיבוי. נסה לרענן עוד מעט.")
else:
    current_vix = vix_hist['Close'].iloc[-1] if not vix_hist.empty else 20.0
    current_tnx = tnx_hist['Close'].iloc[-1] if not tnx_hist.empty else 4.2

    # פונקציית ניתוח מקיפה
    def analyze_market(hist, info):
        current_price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2]
        daily_change = ((current_price - prev_close) / prev_close) * 100
        
        sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        sma_200 = hist['Close'].rolling(window=200).mean().iloc[-1]
        trend = "🟢 מגמת שור בריאה (Golden Cross)" if sma_50 > sma_200 else "🔴 מגמת דוב / לחץ (Death Cross)"
        
        yearly_high = hist['High'].max()
        drawdown = ((current_price - yearly_high) / yearly_high) * 100

        # חישוב RSI (14)
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        pe_ratio = info.get('trailingPE', info.get('forwardPE', 22.0))
        if not pe_ratio: pe_ratio = 22.0

        target_mean = info.get('targetMeanPrice', current_price * 1.1)
        if not target_mean: target_mean = current_price * 1.1
        analyst_upside = ((target_mean - current_price) / current_price) * 100

        # הערכת שווי (זול / יקר)
        if pe_ratio < 18 and drawdown < -5:
            valuation = "🟢 זול ואטרקטיבי (תמחור נוח ותיקון מחיר מהשיא)"
        elif pe_ratio > 25 or drawdown > -3:
            valuation = "🔴 יקר ומתוח (תמחור גבוה מהממוצע ההיסטורי)"
        else:
            valuation = "🟡 הוגן / ניטרלי (מחיר סביר ביחס לשוק)"

        # זיהוי אופוריה / שוק מנופח (איתות יציאה)
        is_overheated = (rsi > 70) and (current_vix < 14) and (pe_ratio > 24)

        # אלגוריתם שקלול ציון הכניסה (0-100)
        score = 50

        if current_vix > 30: score += 20
        elif current_vix > 22: score += 12
        elif current_vix < 14: score -= 10

        if drawdown < -15: score += 20
        elif drawdown < -10: score += 12
        elif drawdown < -5: score += 5
        elif drawdown > -2: score -= 10

        if rsi < 30: score += 15
        elif rsi < 40: score += 8
        elif rsi > 70: score -= 15

        if pe_ratio < 18: score += 12
        elif pe_ratio > 26: score -= 15

        if analyst_upside > 15: score += 12
        elif analyst_upside < 3: score -= 8

        if current_tnx > 4.5: score -= 8
        elif current_tnx < 3.8: score += 8

        if geo_risk == "משבר גלובלי קיצוני": score += 15
        elif geo_risk == "משבר או מלחמה אזורית": score += 8
        elif geo_risk == "מתיחות בינונית": score -= 5

        score = max(0, min(100, int(score)))

        return {
            "price": current_price, "change": daily_change, "drawdown": drawdown,
            "rsi": rsi, "pe": pe_ratio, "upside": analyst_upside, "valuation": valuation,
            "score": score, "sma50": sma_50, "sma200": sma
