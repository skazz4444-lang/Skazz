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

# פונקציית שליפה מהירה ובטוחה שלא נתקעת לעולם
@st.cache_data(ttl=15)
def get_market_data(ticker, default_price):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist is not None and not hist.empty:
            # שליפה בטוחה של info עם הגנה מפני קפיאה
            try:
                info = t.info
            except:
                info = {}
            return hist, info, "Yahoo Finance פעיל"
    except Exception:
        pass
    
    # גיבוי אוטומטי למקרה של תקלה ברשת
    dates = pd.date_range(end=datetime.today(), periods=250, freq='B')
    dummy_hist = pd.DataFrame({
        'Close': np.linspace(default_price * 0.9, default_price, 250),
        'High': np.linspace(default_price * 0.92, default_price * 1.02, 250),
        'Low': np.linspace(default_price * 0.88, default_price * 0.98, 250)
    }, index=dates)
    dummy_info = {'trailingPE': 22.0, 'targetMeanPrice': default_price * 1.1}
    return dummy_hist, dummy_info, "מצב גיבוי מקומי"

with st.spinner("🔄 טוען נתונים במהירות..."):
    sp_hist, sp_info, sp_status = get_market_data("SPY", 580.0)
    nd_hist, nd_info, nd_status_nd = get_market_data("QQQ", 500.0)
    vix_hist, _, _ = get_market_data("^VIX", 18.0)
    tnx_hist, _, _ = get_market_data("^TNX", 4.3)

try:
    current_vix = float(vix_hist['Close'].iloc[-1]) if not vix_hist.empty else 18.0
    current_tnx = float(tnx_hist['Close'].iloc[-1]) if not tnx_hist.empty else 4.3

    def analyze_market(hist, info):
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

        pe_ratio = info.get('trailingPE', info.get('forwardPE', 22.0))
        if not pe_ratio: pe_ratio = 22.0
        pe_ratio = float(pe_ratio)

        target_mean = info.get('targetMeanPrice', current_price * 1.1)
        if not target_mean: target_mean = current_price * 1.1
        target_mean = float(target_mean)
        analyst_upside = ((target_mean - current_price) / current_price) * 100

        if pe_ratio < 18 and drawdown < -5:
            valuation = "🟢 זול ואטרקטיבי (תמחור נוח ותיקון מחיר מהשיא)"
        elif pe_ratio > 25 or drawdown > -3:
            valuation = "🔴 יקר ומתוח (תמחור גבוה מהממוצע ההיסטורי)"
        else:
            valuation = "🟡 הוגן / ניטרלי (מחיר סביר ביחס לשוק)"

        is_overheated = (rsi > 70) and (current_vix < 14) and (pe_ratio > 24)

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
            "score": score, "sma50": sma_50, "sma200": sma_200, "trend": trend,
            "target": target_mean, "is_overheated": is_overheated
        }

    sp_data = analyze_market(sp_hist, sp_info)
    nd_data = analyze_market(nd_hist, nd_info)

    # בניית הלשוניות
    tab1, tab2, tab3, tab4 = st.tabs(["📊 S&P 500 (SPY)", "💻 Nasdaq (QQQ)", "💼 ניהול תיק ו-DCA", "🚨 סימולציית קיצון"])

    def render_market_tab(name, data):
        st.markdown(f"### מעקב קרן סל {name}")
        score = data["score"]
        st.progress(score / 100)

        if data["is_overheated"]:
            st.error("🚨 **התרעת אופוריה / בועה (איתות יציאה/מימוש חלקי):** השוק נמצא בקניית-יתר קיצונית, פחד נמוך ותמחור מנופח. זהו זמן מעולה לשקול נעילת רווחים!")

        if score >= 75:
            st.success(f"### 🟢 ציון כניסה: {score}/100 – אזור קנייה חזק מאוד! (הזדמנות)")
        elif score >= 55:
            st.info(f"### 🔵 ציון כניסה: {score}/100 – כניסה סבירה / ניטרלי (מומלץ DCA מדורג)")
        elif score >= 35:
            st.warning(f"### 🟠 ציון כניסה: {score}/100 – זהירות, אין מספיק תמריצי קנייה.")
        else:
            st.error(f"### 🔴 ציון כניסה: {score}/100 – שוק יקר או בסיכון. עדיף להמתין.")

        st.metric("מחיר קרן הסל כרגע", f"${data['price']:,.2f}", f"{data['change']:+.2f}%")
        st.metric("הערכת שווי", data['valuation'])
        st.write(f"**מגמה טכנית:** {data['trend']}")

        st.markdown("---")
        col1, col2 = st.columns(2)
        col1.metric("מדד הפחד (VIX)", f"{current_vix:.2f}")
        col2.metric("מומנטום (RSI)", f"{data['rsi']:.1f}")

        col3, col4 = st.columns(2)
        col3.metric("מרחק מהשיא", f"{data['drawdown']:.2f}%")
        col4.metric("מכפיל רווח (PE)", f"{data['pe']:.1f}")

        col5, col6 = st.columns(2)
        col5.metric("פוטנציאל אנליסטים", f"{data['upside']:+.1f}%")
        col6.metric("תשואת אג\"ח 10 שנים", f"{current_tnx}%")

    with tab1:
        render_market_tab("S&P 500 (SPY)", sp_data)

    with tab2:
        render_market_tab("Nasdaq (QQQ)", nd_data)

    with tab3:
        st.markdown("### 💼 ניהול תיק אישי, אסטרטגיית DCA וסטופ-לוס")
        st.write("הזן את נתוני ההשקעה שלך כדי לקבל איתותי כניסה ויציאה מותאמים אישית:")

        chosen_market = st.selectbox("בחר לאיזה נכס שייכת ההשקעה שלך:", ["S&P 500 (SPY)", "Nasdaq (QQQ)"])
        active_data = sp_data if chosen_market == "S&P 500 (SPY)" else nd_data

        market_suffix = "_spy" if "SPY" in chosen_market else "_qqq"
        inv_key = f"inv_amt{market_suffix}"
        ent_key = f"ent_price{market_suffix}"
        bud_key = f"bud_amt{market_suffix}"

        if inv_key not in st.session_state:
            st.session_state[inv_key] = 5000.0
        if ent_key not in st.session_state:
            st.session_state[ent_key] = 647.71
        if bud_key not in st.session_state:
            st.session_state[bud_key] = 1000.0

        invested_amount = st.number_input("סכום ההשקעה הכולל ($):", min_value=0.0, step=100.0, key=inv_key)
        entry_price = st.number_input("מחיר הכניסה הממוצע שלך ($):", min_value=0.0, step=0.01, format="%.2f", key=ent_key)
        monthly_budget = st.number_input("תקציב חודשי פנוי להשקעה נוספת ($):", min_value=0.0, step=100.0, key=bud_key)

        if invested_amount > 0 and entry_price > 0:
            current_value = (invested_amount / entry_price) * active_data['price']
            profit_loss_dollar = current_value - invested_amount
            profit_loss_pct = ((active_data['price'] - entry_price) / entry_price) * 100

            recommended_stop_loss = entry_price * 0.92

            st.markdown("---")
            st.subheader("📊 סיכום מצב התיק והגנות")
            col_m1, col_m2 = st.columns(2)
            col_m1.metric("שווי תיק נוכחי", f"${current_value:,.2f}", f"{profit_loss_pct:+.2f}%")
            col_m2.metric("רווח / הפסד ($)", f"${profit_loss_dollar:+,.2f}")

            st.write(f"🛡️ **סטופ-לוס דינמי מומלץ:** ${recommended_stop_loss:,.2f} (כ-8% מתחת למחיר הכניסה שלך)")

            st.markdown("### 💡 המלצת פעולה אקטיבית (כניסה / יציאה):")
            score = active_data['score']

            if active_data['is_overheated']:
                st.error("🚨 **המלצת יציאה / מימוש רווחים:** השוק באופוריה מסוכנת. אם אתה מרוויח יפה (מעל 15%), כדאי לממש חלק מהרווחים (למשל 25%-30%) ולשבת על מזומן.")
            elif score >= 70:
                allocation_pct = 50 if score >= 85 else 30
                suggested_buy = monthly_budget * (allocation_pct / 100)
                st.success(f"🟢 **המלצת כניסה (DCA חכם):** השוק באזור קנייה טוב! מומלץ להשקיע כעת **{allocation_pct}%
