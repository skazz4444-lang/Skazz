import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(
    page_title="Ultimate Market & Portfolio Advisor",
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

st.title("🎯 יועץ השקעות אישי ומנהל תיק חכם")
st.caption(f"עדכון חי: {datetime.now().strftime('%H:%M:%S')} | SPY & QQQ Pro Analyzer")

st.markdown("### 🌐 הגדרות מאקרו וגאופוליטיקה")
geo_risk = st.select_slider(
    "רמת מתיחות פוליטית / ביטחונית עולמית:",
    options=["רגוע ושגרתי", "מתיחות בינונית", "משבר או מלחמה אזורית", "משבר גלובלי קיצוני"],
    value="רגוע ושגרתי"
)

@st.cache_data(ttl=15)
def get_market_data(ticker, default_price):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        info = t.info if hasattr(t, 'info') else {}
        if hist is not None and not hist.empty and len(hist) > 5:
            return hist, info, True
    except Exception:
        pass
    
    dates = pd.date_range(end=datetime.today(), periods=250, freq='B')
    dummy_hist = pd.DataFrame({
        'Close': np.linspace(default_price * 0.9, default_price, 250),
        'High': np.linspace(default_price * 0.92, default_price * 1.02, 250),
        'Low': np.linspace(default_price * 0.88, default_price * 0.98, 250)
    }, index=dates)
    dummy_info = {'trailingPE': 22.0, 'forwardPE': 21.0, 'targetMeanPrice': default_price * 1.1}
    return dummy_hist, dummy_info, False

with st.spinner("🔄 טוען נתונים חיים ומחשב מדדים..."):
    sp_hist, sp_info, _ = get_market_data("SPY", 580.0)
    nd_hist, nd_info, _ = get_market_data("QQQ", 500.0)
    vix_hist, _, _ = get_market_data("^VIX", 18.0)
    tnx_hist, _, _ = get_market_data("^TNX", 4.3)

def analyze_market(hist, info, default_pe=22.0):
    try:
        current_price = float(hist['Close'].iloc[-1])
        prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
        daily_change = ((current_price - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0
        
        sma_50 = float(hist['Close'].rolling(window=50).mean().iloc[-1]) if len(hist) >= 50 else current_price
        sma_200 = float(hist['Close'].rolling(window=200).mean().iloc[-1]) if len(hist) >= 200 else current_price
        trend = "🟢 מגמת שור בריאה (Golden Cross)" if sma_50 > sma_200 else "🔴 מגמת דוב / לחץ (Death Cross)"
        
        yearly_high = float(hist['High'].max()) if 'High' in hist else current_price * 1.05
        drawdown = ((current_price - yearly_high) / yearly_high) * 100 if yearly_high > 0 else 0.0

        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else 50.0

        pe_ratio = info.get('trailingPE', info.get('forwardPE', default_pe))
        if not pe_ratio or pd.isna(pe_ratio): pe_ratio = default_pe
        pe_ratio = float(pe_ratio)

        target_mean = info.get('targetMeanPrice', current_price * 1.1)
        if not target_mean or pd.isna(target_mean): target_mean = current_price * 1.1
        target_mean = float(target_mean)
        analyst_upside = ((target_mean - current_price) / current_price) * 100

        if pe_ratio < 18 and drawdown < -5:
            valuation = "🟢 זול ואטרקטיבי (תמחור נוח ותיקון מחיר מהשיא)"
        elif pe_ratio > 25 or drawdown > -3:
            valuation = "🔴 יקר ומתוח (תמחור גבוה מהממוצע ההיסטורי)"
        else:
            valuation = "🟡 הוגן / ניטרלי (מחיר סביר ביחס לשוק)"

        return current_price, daily_change, sma_50, sma_200, trend, drawdown, rsi, pe_ratio, target_mean, analyst_upside, valuation
    except Exception:
        return 500.0, 0.0, 500.0, 500.0, "ניטרלי", 0.0, 50.0, 22.0, 550.0, 10.0, "🟡 הוגן / ניטרלי"

sp_data = analyze_market(sp_hist, sp_info, 24.0)
nd_data = analyze_market(nd_hist, nd_info, 28.0)

current_vix = float(vix_hist['Close'].iloc[-1]) if not vix_hist.empty else 18.0
current_tnx = float(tnx_hist['Close'].iloc[-1]) if not tnx_hist.empty else 4.3

def calculate_score(drawdown, rsi, pe, upside, vix, tnx, geo):
    score = 50
    if vix > 30: score += 20
    elif vix > 22: score += 12
    elif vix < 14: score -= 10

    if drawdown < -15: score += 20
    elif drawdown < -10: score += 12
    elif drawdown < -5: score += 5
    elif drawdown > -2: score -= 10

    if rsi < 30: score += 15
    elif rsi < 40: score += 8
    elif rsi > 70: score -= 15

    if pe < 18: score += 12
    elif pe > 26: score -= 15

    if upside > 15: score += 12
    elif upside < 3: score -= 8

    if tnx > 4.5: score -= 8
    elif tnx < 3.8: score += 8

    if geo == "משבר גלובלי קיצוני": score += 15
    elif geo == "משבר או מלחמה אזורית": score += 8
    elif geo == "מתיחות בינונית": score -= 5

    return max(0, min(100, int(score)))

sp_score = calculate_score(sp_data[5], sp_data[6], sp_data[7], sp_data[9], current_vix, current_tnx, geo_risk)
nd_score = calculate_score(nd_data[5], nd_data[6], nd_data[7], nd_data[9], current_vix, current_tnx, geo_risk)

sp_overheated = (sp_data[6] > 70) and (current_vix < 14) and (sp_data[7] > 24)
nd_overheated = (nd_data[6] > 70) and (current_vix < 14) and (nd_data[7] > 24)

tab1, tab2, tab3, tab4 = st.tabs(["📊 SPY (S&P 500)", "💻 QQQ (Nasdaq)", "💼 ניהול תיק ו-DCA", "🚨 סימולציית קיצון"])

def render_market_tab(name, data, score, is_over):
    price, change, sma50, sma200, trend, drawdown, rsi, pe, target, upside, valuation = data
    st.markdown(f"### מעקב קרן סל {name}")
    st.progress(score / 100)

    if is_over:
        st.error("🚨 **התרעת אופוריה / בועה (איתות יציאה/מימוש חלקי):** השוק נמצא בקניית-יתר קיצונית ותמחור מנופח. זהו זמן מעולה לשקול נעילת רווחים!")

    if score >= 75:
        st.success(f"### 🟢 ציון כניסה: {score}/100 – אזור קנייה חזק מאוד! (הזדמנות)")
    elif score >= 55:
        st.info(f"### 🔵 ציון כניסה: {score}/100 – כניסה סבירה / ניטרלי (מומלץ DCA מדורג)")
    elif score >= 35:
        st.warning(f"### 🟠 ציון כניסה: {score}/100 – זהירות, אין מספיק תמריצי קנייה.")
    else:
        st.error(f"### 🔴 ציון כניסה: {score}/100 – שוק יקר או בסיכון. עדיף להמתין.")

    st.metric("מחיר קרן הסל כרגע", f"${price:,.2f}", f"{change:+.2f}%")
    st.metric("הערכת שווי", valuation)
    st.write(f"**מגמה טכנית:** {trend}")

    st.markdown("---")
    col1, col2 = st.columns(2)
    col1.metric("מדד הפחד (VIX)", f"{current_vix:.2f}")
    col2.metric("מומנטום (RSI)", f"{rsi:.1f}")

    col3, col4 = st.columns(2)
    col3.metric("מרחק מהשיא", f"{drawdown:.2f}%")
    col4.metric("מכפיל רווח (PE)", f"{pe:.1f}")

    col5, col6 = st.columns(2)
    col5.metric("פוטנציאל אנליסטים", f"{upside:+.1f}%")
    col6.metric("תשואת אג\"ח 10 שנים", f"{current_tnx:.2f}%")

with tab1:
    render_market_tab("SPY", sp_data, sp_score, sp_overheated)

with tab2:
    render_market_tab("QQQ", nd_data, nd_score, nd_overheated)

with tab3:
    st.markdown("### 💼 ניהול תיק אישי, אסטרטגיית DCA וסטופ-לוס")
    st.write("הזן את נתוני ההשקעה שלך כדי לקבל איתותי כניסה ויציאה מותאמים אישית:")

    chosen_market = st.selectbox("בחר לאיזה נכס שיי
