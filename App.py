import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(
    page_title="US Market Entry Live",
    page_icon="🎯",
    layout="centered"
)

# תיקון תצוגה: טקסט לבן וברור על רקע כהה (מונע בעיות כהה על כהה)
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    h1, h2, h3, h4, h5, h6, p, span, label, div { color: #ffffff !important; }
    .stMetricValue { color: #00ffcc !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 בוחן כניסה אולטימטיבי למדדים")
st.caption(f"עדכון חי: {datetime.now().strftime('%H:%M:%S')} | ניתוח מחיר, שווי, פחד ומגמות")

market_choice = st.selectbox("בחר מדד לבדיקה:", ["S&P 500 (^GSPC)", "Nasdaq Composite (^IXIC)"])
ticker_sym = "^GSPC" if "S&P" in market_choice else "^IXIC"

# רכיב אינטראקטיבי למצב פוליטי וביטחוני
geo_risk = st.select_slider(
    "רמת מתיחות פוליטית / ביטחונית עולמית:",
    options=["רגוע ושגרתי", "מתיחות בינונית", "משבר או מלחמה אזורית", "משבר גלובלי קיצוני"],
    value="רגוע ושגרתי"
)

@st.cache_data(ttl=15)
def fetch_data(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        info = t.info
        return hist, info, True
    except:
        return pd.DataFrame(), {}, False

with st.spinner("🔄 שולף נתונים חיים ומנתח את השוק..."):
    hist, info, success = fetch_data(ticker_sym)
    vix_hist, _, _ = fetch_data("^VIX")
    tnx_hist, _, _ = fetch_data("^TNX")

if not success or hist.empty:
    st.error("⚠️ שגיאה בשליפת הנתונים. נסה לרענן עוד מעט.")
else:
    current_price = hist['Close'].iloc[-1]
    prev_close = hist['Close'].iloc[-2]
    daily_change = ((current_price - prev_close) / prev_close) * 100
    
    # טכני ומגמות
    sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
    sma_200 = hist['Close'].rolling(window=200).mean().iloc[-1]
    yearly_high = hist['High'].max()
    drawdown = ((current_price - yearly_high) / yearly_high) * 100

    # חישוב RSI (14) למומנטום
    delta = hist['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).iloc[-1]

    # נתוני מאקרו ופונדמנטל
    current_vix = vix_hist['Close'].iloc[-1] if not vix_hist.empty else 20.0
    current_tnx = tnx_hist['Close'].iloc[-1] if not tnx_hist.empty else 4.2
    pe_ratio = info.get('trailingPE', info.get('forwardPE', 22.0))
    if not pe_ratio: pe_ratio = 22.0

    # תחזיות אנליסטים
    target_mean = info.get('targetMeanPrice', current_price * 1.1)
    if not target_mean: target_mean = current_price * 1.1
    analyst_upside = ((target_mean - current_price) / current_price) * 100

    # --- בדיקת האם המחיר זול או יקר (הערכת שווי) ---
    if pe_ratio < 18 and drawdown < -5:
        valuation_status = "🟢 זול ואטרקטיבי (תמחור נוח ותיקון מחיר מהשיא)"
    elif pe_ratio > 25 or drawdown > -3:
        valuation_status = "🔴 יקר ומתוח (תמחור גבוה מהממוצע ההיסטורי)"
    else:
        valuation_status = "🟡 הוגן / ניטרלי (מחיר סביר ביחס לשוק)"

    # --- אלגוריתם שקלול ציון הכניסה (0 עד 100) ---
    score = 50

    # 1. מדד הפחד VIX
    if current_vix > 30: score += 20
    elif current_vix > 22: score += 12
    elif current_vix < 14: score -= 10

    # 2. עומק תיקון מחיר (Drawdown)
    if drawdown < -15: score += 20
    elif drawdown < -10: score += 12
    elif drawdown < -5: score += 5
    elif drawdown > -2: score -= 10

    # 3. מומנטום (RSI)
    if rsi < 30: score += 15
    elif rsi < 40: score += 8
    elif rsi > 70: score -= 15

    # 4. מכפילים (PE)
    if pe_ratio < 18: score += 12
    elif pe_ratio > 26: score -= 15

    # 5. תחזיות אנליסטים
    if analyst_upside > 15: score += 12
    elif analyst_upside < 3: score -= 8

    # 6. ריבית אג"ח 10 שנים
    if current_tnx > 4.5: score -= 8
    elif current_tnx < 3.8: score += 8

    # 7. סיכון גאופוליטי
    if geo_risk == "משבר גלובלי קיצוני": score += 15
    elif geo_risk == "משבר או מלחמה אזורית": score += 8
    elif geo_risk == "מתיחות בינונית": score -= 5

    score = max(0, min(100, int(score)))

    # --- תצוגת מד ההחלטה המרכזי ---
    st.markdown("---")
    st.subheader("📊 מדד החלטת כניסה (0-100)")
    st.progress(score / 100)

    if score >= 75:
        st.success(f"### 🟢 ציון כניסה: {score}/100 – מומלץ להיכנס! (אזור קנייה חזק)")
    elif score >= 55:
        st.info(f"### 🔵 ציון כניסה: {score}/100 – כניסה סבירה / ניטרלי (מומלץ פיזור בהדרגה - DCA)")
    elif score >= 35:
        st.warning(f"### 🟠 ציון כניסה: {score}/100 – זהירות, אין מספיק תמריצי קנייה כרגע.")
    else:
        st.error(f"### 🔴 ציון כניסה: {score}/100 – לא מומלץ להיכנס! (שוק יקר או בסיכון גבוה)")

    # --- מחיר נוכחי ובדיקת זול/יקר ---
    st.markdown("---")
    st.subheader("🏷️ מחיר נוכחי והערכת שווי")
    col_p1, col_p2 = st.columns(2)
    col_p1.metric("מחיר המדד כרגע", f"{current_price:,.2f}", f"{daily_change:+.2f}%")
    col_p2.metric("האם המחיר זול או יקר?", valuation_status.split(" ")[1])
    st.write(f"**סיכום שווי:** {valuation_status}")

    # --- נתונים בזמן אמת ---
    st.markdown("---")
    st.subheader("📈 פירוט הפרמטרים המלאים")
    
    col1, col2 = st.columns(2)
    col1.metric("מדד הפחד (VIX)", f"{current_vix:.2f}")
    col2.metric("מומנטום (RSI)", f"{rsi:.1f}")

    col3, col4 = st.columns(2)
    col3.metric("מרחק מהשיא", f"{drawdown:.2f}%")
    col4.metric("מכפיל רווח (PE)", f"{pe_ratio:.1f}")

    col5, col6 = st.columns(2)
    col5.metric("פוטנציאל אנליסטים", f"{analyst_upside:+.1f}%")
    col6.metric("תשואת אג\"ח 10 שנים", f"{current_tnx}%")

    if st.button("🔄 רענן נתונים עכשיו"):
        st.cache_data.clear()
        st.rerun()

    with st.expander("🔍 נתונים טכניים נוספים"):
        st.write(f"- **ממוצע נע 50 ימים:** {sma_50:,.2f}")
        st.write(f"- **ממוצע נע 200 ימים:** {sma_200:,.2f}")
        st.write(f"- **מחיר יעד ממוצע (אנליסטים):** {target_mean:,.2f}")
        st.write(f"- **רמת סיכון גאופוליטי:** {geo_risk}")
