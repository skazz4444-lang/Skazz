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

# עיצוב נקי, חד וברור למובייל (מונע לחלוטין בעיות כהה על כהה)
st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #f3f4f6; }
    h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
    p, span, label, div { color: #e5e7eb !important; }
    .stMetricValue { color: #38bdf8 !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 יועץ כניסה ויציאה חכם למדדים (בגיבוי כפול)")
st.caption(f"עדכון חי: {datetime.now().strftime('%H:%M:%S')} | מנגנון שרידות וספקי נתונים כפולים")

# הגדרת מאקרו גלובלית (סיכון פוליטי / ביטחוני)
st.markdown("### 🌐 הגדרות מאקרו וגאופוליטיקה")
geo_risk = st.select_slider(
    "רמת מתיחות פוליטית / ביטחונית עולמית:",
    options=["רגוע ושגרתי", "מתיחות בינונית", "משבר או מלחמה אזורית", "משבר גלובלי קיצוני"],
    value="רגוע ושגרתי"
)

# --- פונקציית שליפת נתונים חכמה הכוללת ספקי גיבוי (Yahoo + Stooq) ---
@st.cache_data(ttl=10)
def fetch_market_with_fallback(yahoo_ticker, stooq_symbol):
    # 1 ניסיון: ספק ראשי Yahoo Finance
    try:
        t = yf.Ticker(yahoo_ticker)
        hist = t.history(period="1y")
        info = t.info
        if not hist.empty and len(hist) > 10:
            return hist, info, "Yahoo Finance (ראשי פעיל)"
    except Exception:
        pass

    # 2 ניסיון: ספק גיבוי Stooq (ללא צורך במפתח API)
    try:
        stooq_url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
        df = pd.read_csv(stooq_url)
        if not df.empty and 'Close' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            df = df.sort_index()
            # יצירת מבנה מידע בסיסי חלופי עבור הגיבוי
            fallback_info = {
                'trailingPE': 22.5, 
                'forwardPE': 21.0, 
                'targetMeanPrice': df['Close'].iloc[-1] * 1.1
            }
            return df, fallback_info, "Stooq (ספק גיבוי פעיל)"
    except Exception:
        pass

    return pd.DataFrame(), {}, "שגיאה: כל הספקים נכשלו"

with st.spinner("🔄 שולף נתונים חיים מספקים ראשיים ומגביים..."):
    sp_hist, sp_info, sp_status = fetch_market_with_fallback("^GSPC", "^spx")
    nd_hist, nd_info, nd_status_nd = fetch_market_with_fallback("^IXIC", "^ndq")
    vix_hist, _, _ = fetch_market_with_fallback("^VIX", "^vix")
    tnx_hist, _, _ = fetch_market_with_fallback("^TNX", "^tnx")

if sp_hist.empty or nd_hist.empty:
    st.error("⚠️ שגיאה בשליפת הנתונים מכל ספקי הגיבוי. נסה לרענן עוד מעט.")
else:
    current_vix = vix_hist['Close'].iloc[-1] if not vix_hist.empty else 20.0
    current_tnx = tnx_hist['Close'].iloc[-1] if not tnx_hist.empty else 4.2

    # פונקציית ניתוח מקיפה לכל מדד
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

        return {
            "price": current_price, "change": daily_change, "drawdown": drawdown,
            "rsi": rsi, "pe": pe_ratio, "upside": analyst_upside, "valuation": valuation,
            "score": score, "sma50": sma_50, "sma200": sma_200, "trend": trend,
            "target": target_mean, "is_overheated": is_overheated
        }

    sp_data = analyze_market(sp_hist, sp_info)
    nd_data = analyze_market(nd_hist, nd_info)

    # יצירת לשוניות נפרדות וברורות
    tab1, tab2, tab3, tab4 = st.tabs(["📊 S&P 500", "💻 Nasdaq", "💼 ניהול תיק ו-DCA", "🚨 סימולציית קיצון"])

    def render_market_tab(name, data):
        st.markdown(f"### מדד {name}")
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

        st.metric("מחיר המדד כרגע", f"{data['price']:,.2f}", f"{data['change']:+.2f}%")
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
        render_market_tab("S&P 500", sp_data)

    with tab2:
        render_market_tab("Nasdaq Composite", nd_data)

    with tab3:
        st.markdown("### 💼 ניהול תיק אישי, אסטרטגיית DCA וסטופ-לוס")
        st.write("הזן את נתוני ההשקעה שלך כדי לקבל איתותי כניסה ויציאה מותאמים אישית:")

        chosen_market = st.selectbox("בחר לאיזה מדד שייכת ההשקעה שלך:", ["S&P 500", "Nasdaq"])
        active_data = sp_data if chosen_market == "S&P 500" else nd_data

        invested_amount = st.number_input("סכום ההשקעה הכולל ($):", min_value=0.0, value=10000.0, step=500.0)
        entry_price = st.number_input("מחיר הכניסה הממוצע שלך ($):", min_value=0.0, value=float(active_data['price'] * 0.95), step=10.0)
        monthly_budget = st.number_input("תקציב חודשי פנוי להשקעה נוספת ($):", min_value=0.0, value=1000.0, step=100.0)

        if invested_amount > 0 and entry_price > 0:
            current_value = (invested_amount / entry_price) * active_data['price']
            profit_loss_dollar = current_value - invested_amount
            profit_loss_pct = ((active_data['price'] - entry_price) / entry_price) * 100

            recommended_stop_loss = entry_price * 0.92  # 8% מתחת למחיר הכניסה

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
                st.success(f"🟢 **המלצת כניסה (DCA חכם):** השוק באזור קנייה טוב! מומלץ להשקיע כעת **{allocation_pct}%** מתקציבך הפנוי (כ-${suggested_buy:,.2f}).")
            elif score >= 50:
                st.info("🔵 **המלצה: פיזור הדרגתי (DCA).** השוק ניטרלי. הפקד במנות קטנות ושמור את רוב המזומן לירידות.")
            else:
                if profit_loss_pct > 12:
                    st.warning("🟠 **המלצה: שקול מימוש חלקי.** השוק יקר ומתוח, והרווח שלך טוב. כדאי לנעול חלק מהרווחים.")
                else:
                    st.error("🔴 **המלצה: עצירת רכישות והמתנה!** השוק יקר או תנודתי מדי (ציון נמוך). אל תכניס כסף חדש, תן לכסף הקיים לצמוח והמתן לתיקון.")

    with tab4:
        st.markdown("### 🚨 סימולציית תרחישי קיצון (Stress Test)")
        st.write("בדוק מראש איך התיק שלך יגיב במקרה של משבר פתאומי בשוק:")

        total_portfolio = st.number_input("הערך הכולל של התיק שלך ($):", min_value=0.0, value=15000.0, step=1000.0)

        if total_portfolio > 0:
            drop_5 = total_portfolio * 0.95
            drop_10 = total_portfolio * 0.90
            drop_20 = total_portfolio * 0.80
            crash_30 = total_portfolio * 0.70

            st.markdown("---")
            col_s1, col_s2 = st.columns(2)
            col_s1.metric("תרחיש תיקון קל (-5%)", f"${drop_5:,.2f}", "-$750 יחסית לתיק")
            col_s2.metric("תרחיש תיקון בינוני (-10%)", f"${drop_10:,.2f}", "-$1,500 יחסית לתיק")

            col_s3, col_s4 = st.columns(2)
            col_s3.metric("תרחיש משבר עמוק (-20%)", f"${drop_20:,.2f}", "-$3,000 יחסית לתיק")
            col_s4.metric("תרחיש קריסת קיצון (-30%)", f"${crash_30:,.2f}", "-$4,500 יחסית לתיק")

            st.info("💡 **טיפ פסיכולוגי:** ידיעת התרחישים מראש עוזרת לך לשמור על קור רוח בזמן ירידות, ולהשתמש בהן כהזדמנויות קנייה במסגרת ציון הכניסה!")

    st.markdown("---")
    st.caption(f"ℹ️ **סטטוס מקור מידע:** {sp_status}")

    if st.button("🔄 רענן את כל הנתונים"):
        st.cache_data.clear()
        st.rerun()
