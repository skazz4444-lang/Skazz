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
# MARKET RADAR - FINAL PRO STREAMLIT APP
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


# ---------------- ROBUST DATA SOURCES & FALLBACKS ----------------

@st.cache_data(ttl=60)
def get_history(ticker, period="2y"):
    """
    שליפת היסטוריה עם מנגנון גיבוי (Fallback) למניעת קריסות
    """
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False, threads=False)
        if df.empty:
            raise ValueError("Empty data from yfinance")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        return df.dropna()
    except Exception:
        # גיבוי שניוני במקרה של תקלה ברשת או בספק המרכזי
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=period)
            if not df.empty:
                df.index = pd.to_datetime(df.index)
                return df.dropna()
        except Exception:
            pass
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
            timeout=15
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
        st.warning("אין נתונים להצגה כרגע.")
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
        return None, {}, "אין מספיק נתונים"

    score = round(float(np.mean(list(factors.values()))), 1)

    if score >= 75:
        verdict = "🟢 מצב שוק אטרקטיבי: התנאים טובים לכניסה או להשקעה נוספת."
    elif score >= 50:
        verdict = "🟡 מצב שוק ניטרלי: כדאי להשקיע בסכומים מדודים או להמתין להזדמנות."
    else:
        verdict = "🔴 שוק תנודתי או יקר: מומלץ לנקוט משנה זהירות ולהשקיע בהדרגה."

    return score, factors, verdict


# ---------------- PORTFOLIO LOGIC & LIVE UPDATES ----------------

def add_transaction(tx_date, ticker, action, quantity, price, fee, currency, notes):
    with connect_db() as con:
        con.execute("""
        INSERT INTO transactions (tx_date,ticker,action,quantity,price,fee,currency,notes)
        VALUES (?,?,?,?,?,?,?,?)
        """, (str(tx_date), ticker.upper(), action, quantity, price, fee, currency, notes))

def load_transactions():
    with connect_db() as con:
        return pd.read_sql_query("SELECT * FROM transactions ORDER BY tx_date, id", con)

def calculate_positions(tx):
    if tx.empty:
        return pd.DataFrame()

    results = []
    for ticker, group in tx.groupby("ticker"):
        units = 0.0
        cost = 0.0
        fees = 0.0
        realized = 0.0

        for _, row in group.iterrows():
            qty = float(row["quantity"])
            price = float(row["price"])
            fee = float(row["fee"])

            if row["action"] == "קנייה":
                units += qty
                cost += qty * price + fee
                fees += fee
            elif row["action"] == "מכירה":
                if qty > units:
                    continue
                avg_cost = cost / units if units else 0
                realized += qty * price - qty * avg_cost - fee
                cost -= qty * avg_cost
                units -= qty
                fees += fee

        if units > 0:
            df = get_history(ticker, "5d")
            close = close_series(df)
            current = float(close.iloc[-1]) if not close.empty else np.nan

            value = current * units if np.isfinite(current) else np.nan
            pnl = value - cost if np.isfinite(value) else np.nan
            pnl_pct = (pnl / cost * 100) if cost > 0 and np.isfinite(pnl) else 0

            if pnl_pct > 15:
                suggestion = "💡 שקול לממש חלק רווחים או להשאיר לטווח ארוך"
            elif pnl_pct < -10:
                suggestion = "➕ מחיר כרגע נמוך מעלות הקנייה - הזדמנות טובה להוסיף כסף (DCA)"
            else:
                suggestion = "🛡️ להשאיר את הכסף בנכס - המגמה תקינה"

            results.append({
                "סימול": ticker,
                "כמות": units,
                "עלות כוללת ($)": round(cost, 2),
                "מחיר אחרון ($)": round(current, 2) if np.isfinite(current) else "לא זמין",
                "שווי נוכחי ($)": round(value, 2) if np.isfinite(value) else "לא זמין",
                "רווח/הפסד ($)": round(pnl, 2) if np.isfinite(pnl) else "לא זמין",
                "תשואה (%)": f"{pnl_pct:+.2f}%" if np.isfinite(pnl_pct) else "לא זמין",
                "המלצה חכמה": suggestion
            })

    return pd.DataFrame(results)


# =====================================================
# SIDEBAR NAVIGATION
# =====================================================

st.sidebar.title("📊 MARKET RADAR")
st.sidebar.caption("מערכת השקעות וניתוח חכם בדולרים ($)")

page = st.sidebar.radio(
    "ניווט באפליקציה",
    [
        "סקירת שוק חכמה",
        "המלצות Top 5 יומיות",
        "קרנות ממונפות",
        "ניתוח מדדים",
        "תמחור ומחירים",
        "מאקרו וכלכלה",
        "חדשות שוק",
        "תיק השקעות והמלצות",
        "ניהול סיכונים",
        "Backtesting"
    ]
)

if st.sidebar.button("🔄 רענון נתונים"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("כל הנתונים המוצגים מחושבים בדולרים ($).")


# =====================================================
# 1. SMART MARKET OVERVIEW
# =====================================================

if page == "סקירת שוק חכמה":

    st.title("🌎 סקירת שוק ותזמון כניסה חכם")
    st.markdown("כלי זה משקלל את כל מדדי המאקרו, המומנטום ומדד הפחד כדי לומר לך האם הזמן נכון להשקיע כעת.")

    assets = {
        "S&P 500": "^GSPC",
        "Nasdaq 100": "^NDX",
        "מדד הפחד (VIX)": "^VIX",
        "דולר / שקל": "ILS=X"
    }

    cols = st.columns(len(assets))
    for i, (name, ticker) in enumerate(assets.items()):
        df = get_history(ticker, "5d")
        close = close_series(df)
        with cols[i]:
            if len(close) >= 2:
                change = (close.iloc[-1] / close.iloc[-2] - 1) * 100
                st.metric(name, f"${close.iloc[-1]:,.2f}", f"{change:+.2f}%")
            elif len(close) == 1:
                st.metric(name, f"${close.iloc[-1]:,.2f}")
            else:
                st.metric(name, "לא זמין")

    st.divider()

    sp_df = get_history("^GSPC", "2y")
    vix_df = get_history("^VIX", "5d")
    vix_close = close_series(vix_df)
    vix_value = float(vix_close.iloc[-1]) if not vix_close.empty else None

    score, factors, verdict = calculate_market_score(sp_df, vix_value)

    st.subheader("🎯 מדד תנאי שוק משולב (האם המחיר כרגע זול/כדאי?)")

    if score is not None:
        col_a, col_b = st.columns([1, 2])
        with col_a:
            st.metric("ציון תנאי שוק", f"{score}/100")
            st.progress(int(score))
        with col_b:
            st.markdown(f"### {verdict}")
            st.caption("הציון נגזר משקלול של: מחירי המדד ביחס לממוצעים, מדד הפחד VIX, והמומנטום בשוק.")

        st.markdown("---")
        st.subheader("פירוט הגורמים ששוקללו למדד:")
        st.dataframe(
            pd.DataFrame([{"גורם בשוק": k, "ציון חיוביות (0-100)": v} for k, v in factors.items()]),
            use_container_width=True
        )
    else:
        st.warning("אין מספיק נתונים לחישוב מדד השוק כרגע.")

    st.divider()
    price_chart(sp_df, "גרף מחיר S&P 500 ($) עם ממוצעים נעים")


# =====================================================
# 2. DAILY TOP 5 RECOMMENDATIONS
# =====================================================

elif page == "המלצות Top 5 יומיות":

    st.title("⭐ המלצות Top 5 יומיות להשקעה")
    st.markdown("רשימת נכסים מובילים שעברו סריקה טכנית יומית ונמצאים כרגע בנקודת כניסה נוחה או במחיר אטרקטיבי.")

    top_candidates = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AMD", "TSLA"]
    
    analyzed_list = []
    for ticker in top_candidates:
        df = get_history(ticker, "6m")
        tech = technical(df)
        if tech and tech.get("rsi") is not None:
            rsi = tech["rsi"]
            price = tech["price"]
            ma50 = tech["ma50"]
            
            if ma50 and price > ma50 * 0.95:
                attractiveness = (100 - rsi) if rsi < 60 else rsi * 0.5
                analyzed_list.append({
                    "סימול": ticker,
                    "מחיר נוכחי ($)": round(price, 2),
                    "RSI (מומנטום)": round(rsi, 1),
                    "שינוי חודשי (%)": f"{tech.get('month', 0):+.2f}%" if tech.get('month') is not None else "N/A",
                    "ציון אטרקטיביות": round(attractiveness, 1),
                    "המלצת מערכת": "🟢 מומלץ לבחינה והשקעה לטווח קצר-בינוני" if rsi < 55 else "🟡 במחיר סביר, לשקול כניסה מדורגת"
                })

    if analyzed_list:
        df_top = pd.DataFrame(analyzed_list).sort_values(by="ציון אטרקטיביות", ascending=False).head(5)
        st.dataframe(df_top.drop(columns=["ציון אטרקטיביות"]), use_container_width=True)
        st.info("💡 המלצות אלו מתעדכנות באופן שוטף לפי נתוני מחיר לייב וממוצעים נעים.")
    else:
        st.warning("לא נמצאו מספיק נתונים להצגת הטופ 5 כרגע.")


# =====================================================
# 3. LEVERAGED FUNDS
# =====================================================

elif page == "קרנות ממונפות":

    st.title("⚡ ניתוח והמלצות על קרנות ממונפות")
    st.warning("⚠️ אזהרה: קרנות ממונפות (כמו 2x או 3x) מתאימות למשקיעים מתקדמים בלבד, שכן הן מגדילות רווחים אך גם הפסדים ושחיקה במצבי שוק תנודתיים.")

    lev_tickers = {
        "TQQQ (3x Nasdaq - טכנולוגיה ממונפת)": "TQQQ",
        "UPRO (3x S&P 500 - מדד רחב ממונף)": "UPRO",
        "QLD (2x Nasdaq - ממונף מתון)": "QLD",
        "SSO (2x S&P 500 - ממונף מתון)": "SSO"
    }

    selected_lev = st.selectbox("בחר קרנות ממונפות לבדיקה", list(lev_tickers.keys()))
    ticker_symbol = lev_tickers[selected_lev]

    df_lev = get_history(ticker_symbol, "1y")
    tech_lev = technical(df_lev)

    if not df_lev.empty and tech_lev:
        col1, col2, col3 = st.columns(3)
        col1.metric("מחיר נוכחי", f"${tech_lev['price']:,.2f}")
        col2.metric("תנודתיות שנתית (סיכון)", f"{tech_lev['volatility']:.1f}%")
        col3.metric("ירידה מהשיא", f"{tech_lev['drawdown']:.1f}%")

        st.divider()
        st.subheader("🤖 ניתוח מצב ומומלצות לקרן ממונפות זו:")
        
        if tech_lev["price"] > tech_lev.get("ma200", 0) and tech_lev.get("rsi", 50) < 65:
            st.success(f"**המלצה: כניסה זהירה אפשרית.** הנכס נמצא מעל ממוצע 200 (מגמת עליה ראשית חיובית), מה שמפחית את סיכון השחיקה.")
        elif tech_lev.get("rsi", 50) > 70:
            st.warning(f"**המלצה: לא מומלץ להיכנס עכשיו.** המדד נמצא ב-RSI גבוה מאוד (קנוי יתר).")
        else:
            st.error(f"**המלצה: סיכון גבוה כרגע.** המגמה מעורבת או שהנכס מתחת לממוצעים.")

        price_chart(df_lev, f"ביצועי {ticker_symbol} בדולרים ($)")
    else:
        st.warning("אין מספיק נתונים להצגת הקרן הממונפות.")


# =====================================================
# 4. INDEX ANALYSIS
# =====================================================

elif page == "ניתוח מדדים":

    st.title("📈 ניתוח מדדים מובילים")

    choices = {
        "S&P 500 (SPY / GSPC)": "^GSPC",
        "Nasdaq 100 (QQQ / NDX)": "^NDX"
    }

    selected = st.selectbox("בחר מדד", list(choices))
    df = get_history(choices[selected], "5y")

    if not df.empty:
        price_chart(df, selected)
        t = technical(df)

        if t:
            cols = st.columns(3)
            cols[0].metric("RSI (מומנטום)", money(t["rsi"], ""))
            cols[1].metric("תנודתיות שנתית", f"{t['volatility']:.2f}%")
            cols[2].metric("ירידה מהשיא", f"{t['drawdown']:.2f}%")

            cols2 = st.columns(3)
            cols2[0].metric("שינוי יומי", f"{t['change']:+.2f}%")
            cols2[1].metric("תשואה חודשית", f"{t['month']:+.2f}%" if t["month"] is not None else "לא זמין")
            cols2[2].metric("תשואה רבעונית", f"{t['quarter']:+.2f}%" if t["quarter"] is not None else "לא זמין")
    else:
        st.error("לא התקבלו נתונים עבור המדד הנבחר.")


# =====================================================
# 5. VALUATION
# =====================================================

elif page == "תמחור ומחירים":

    st.title("💰 תמחור נכסים מרכזיים")

    ticker = st.selectbox("בחר קרן סל או מניה מובילה", ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"])
    info = get_info(ticker)

    fields = {
        "מכפיל רווח נוכחי (Trailing P/E)": "trailingPE",
        "מכפיל רווח עתידי (Forward P/E)": "forwardPE",
        "יחס מחיר להון (Price to Book)": "priceToBook",
        "שולי רווח (Profit Margin)": "profitMargins",
        "תחזית מחיר ממוצעת מאנליסטים": "targetMeanPrice",
        "תחזית מחיר גבוהה מאנליסטים": "targetHighPrice"
    }

    rows = []
    for label, key in fields.items():
        value = info.get(key)
        if value is None:
            value = "לא זמין"
        elif isinstance(value, (float, int, np.number)):
            value = round(float(value), 2)
            if "מחיר" in label:
                value = f"${value}"
        rows.append({"נתון פיננסי": label, "ערך": value})

    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.info("💡 כל המחירים והתחזיות מוצגים בדולרים ($).")


# =====================================================
# 6. MACRO
# =====================================================

elif page == "מאקרו וכלכלה":

    st.title("🏦 נתוני מאקרו כלכליים")

    series = {
        "ריבית הפד האמריקאית": "FEDFUNDS",
        "תשואת אגח ארהב 10 שנים": "DGS10",
        "אינפלציה בארהב (CPI)": "CPIAUCSL",
        "שיעור האבטלה": "UNRATE"
    }

    selected = st.selectbox("בחר נתון מאקרו", list(series))
    df = get_fred(series[selected])

    if not df.empty:
        latest = df.iloc[-1]
        st.metric(selected, f"{latest['value']:.3f}", str(latest["date"].date()))

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"], y=df["value"], mode="lines", name=selected, line=dict(color="#3b82f6")))
        fig.update_layout(template="plotly_dark", height=400, paper_bgcolor="#0b1220", plot_bgcolor="#0b1220")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("הנתון אינו זמין כרגע.")


# =====================================================
# 7. NEWS
# =====================================================

elif page == "חדשות":

    st.title("📰 חדשות שוק ההון")

    topics = {
        "כלכלה אמריקאית ושווקים": "US stock market economy",
        "ריבית ואינפלציה": "Federal Reserve inflation interest rates",
        "טכנולוגיה ובינה מלאכותית": "technology AI stocks"
    }

    topic = st.selectbox("בחר נושא חדשותי", list(topics))
    articles = get_news(topics[topic])

    if articles:
        for article in articles:
            with st.container(border=True):
                st.markdown(f"**{article.get('title', 'ללא כותרת')}**")
                st.caption(str(article.get("domain", "")) + " | " + str(article.get("seendate", "")))
                url = article.get("url")
                if url:
                    st.link_button("לקריאת הכתבה המלאה", url)
    else:
        st.warning("לא התקבלו כתבות כרגע.")


# =====================================================
# 8. PORTFOLIO & SMART RECOMMENDATIONS
# =====================================================

elif page == "תיק השקעות והמלצות":

    st.title("💼 ניהול תיק השקעות חכם בדולרים ($)")
    st.markdown("הזן את עסקאות הרכישה שלך. הנתונים נשמרים במסד הנתונים ומתעדכנים חי מול מחירי השוק עם המלצות ניהול.")

    with st.form("add_transaction"):
        col1, col2 = st.columns(2)
        with col1:
            ticker = st.text_input("סימול הנכס (למשל: SPY, QQQ, AAPL)", "SPY").upper()
            action = st.selectbox("פעולה", ["קנייה", "מכירה"])
            quantity = st.number_input("כמות יחידות", min_value=0.000001, value=10.0)
        with col2:
            price = st.number_input("מחיר קנייה ליחידה בדולרים ($)", min_value=0.0, value=450.0)
            fee = st.number_input("עמלה בדולרים ($)", min_value=0.0, value=0.0)
            tx_date = st.date_input("תאריך עסקה", date.today())

        notes = st.text_input("הערות אישיות")
        submit = st.form_submit_button("שמור עסקה בתיק")

        if submit:
            if ticker and quantity > 0 and price > 0:
                add_transaction(tx_date, ticker, action, quantity, price, fee, "USD", notes)
                st.success("העסקה נוספה בהצלחה ונשמרה!")
                st.rerun()

    tx = load_transactions()

    if not tx.empty:
        st.divider()
        st.subheader("📋 היסטוריית עסקאות שמורות")
        st.dataframe(tx, use_container_width=True)

        st.download_button(
            "הורדת עסקאות כקובץ CSV",
            tx.to_csv(index=False).encode("utf-8-sig"),
            "my_portfolio_transactions.csv",
            "text/csv"
        )

        positions = calculate_positions(tx)

        st.subheader("📊 פוזיציות פתוחות מעודכנות והמלצות חכמות")

        if not positions.empty:
            st.dataframe(positions, use_container_width=True)

            total_profit = positions["רווח/הפסד ($)"].sum() if "רווח/הפסד ($)" in positions.columns else 0
            total_value = positions["שווי נוכחי ($)"].sum() if "שווי נוכחי ($)" in positions.columns else 0

            col_p1, col_p2 = st.columns(2)
            col_p1.metric("שווי כולל של התיק ($)", money(total_value))
            col_p2.metric("סך רווח / הפסד בתיק ($)", money(total_profit))

            valid = positions.dropna(subset=["שווי נוכחי ($)"])
            if not valid.empty:
                fig = go.Figure(data=[go.Pie(labels=valid["סימול"], values=valid["שווי נוכחי ($)"], hole=0.45)])
                fig.update_layout(title="פיזור נכסים בתיק ($)", template="plotly_dark", paper_bgcolor="#0b1220", plot_bgcolor="#0b1220")
                st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("מחיקת עסקה מההיסטוריה")
        delete_id = st.number_input("מספר מזהה (ID) של העסקה למחיקה", min_value=0, step=1)
        if st.button("מחק עסקה"):
            if delete_id:
                with connect_db() as con:
                    con.execute("DELETE FROM transactions WHERE id=?", (int(delete_id),))
                st.success("העסקה נמחקה בהצלחה מהתיק.")
                st.rerun()

    else:
        st.info("עדיין לא הוזנו עסקאות לתיק. התחל להזין למעלה כדי לראות את הפוזיציות וההמלצות החכמות.")


# =====================================================
# 9. RISK ANALYSIS
# =====================================================

elif page == "ניהול סיכונים":

    st.title("⚠️ ניהול סיכונים ותרחישי קיצון")
    st.markdown("בדיקת השפעת תרחישי ירידה בשוק על התיק שלך (במונחי דולרים).")

    capital = st.number_input("הערך הכולל של תיק ההשקעות שלך ($)", min_value=0.0, value=10000.0, step=1000.0)

    scenarios = [-5, -10, -20, -30, -40]
    scenario_df = pd.DataFrame({
        "תרחיש ירידה בשוק": [f"ירידה של {abs(x)}%" for x in scenarios],
        "הפסד כספי מוערך ($)": [round(capital * abs(x) / 100, 2) for x in scenarios],
        "שווי התיק לאחר הירידה ($)": [round(capital * (1 + x / 100), 2) for x in scenarios]
    })

    st.dataframe(scenario_df, use_container_width=True)


# =====================================================
# 10. BACKTESTING
# =====================================================

elif page == "Backtesting":

    st.title("🧪 בדיקת ביצועים היסטוריים (Backtesting)")

    ticker = st.selectbox("בחר נכס לבדיקה", ["SPY", "QQQ"])
    
    df_bt = get_history(ticker, "5y")
    close_bt = close_series(df_bt)

    if len(close_bt) >= 220:
        ma50 = close_bt.rolling(50).mean()
        ma200 = close_bt.rolling(200).mean()

        signal = (ma50 > ma200).astype(int)
        daily_returns = close_bt.pct_change().fillna(0)
        model_returns = signal.shift(1).fillna(0) * daily_returns

        buy_hold = 10000 * (1 + daily_returns).cumprod()
        model = 10000 * (1 + model_returns).cumprod()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=close_bt.index, y=buy_hold, name="החזקה רגילה (Buy & Hold)", line=dict(color="#3b82f6")))
        fig.add_trace(go.Scatter(x=close_bt.index, y=model, name="אסטרטגיית ממוצעים נעים", line=dict(color="#10b981")))

        fig.update_layout(title=f"השוואת תשואה היסטורית על סך $10,000 עבור {ticker}", template="plotly_dark", height=450, paper_bgcolor="#0b1220", plot_bgcolor="#0b1220")
        st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        c1.metric("שווי סופי בשיטת החזקה רגילה", f"${buy_hold.iloc[-1]:,.2f}")
        c2.metric("שווי סופי בשיטת ממוצעים נעים", f"${model.iloc[-1]:,.2f}")
    else:
        st.warning("אין מספיק נתונים היסטוריים לביצוע הבדיקה.")


# =====================================================
# FOOTER
# =====================================================

st.markdown("---")
st.caption("Market Radar | כלי מתקדם לניתוח שוק והשקעות בדולרים ($). התוכן הינו לימודי ואינו מהווה ייעוץ השקעות פיננסי.")
