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
# MARKET RADAR PRO - ULTIMATE FULL VERSION (10 TABS)
# =====================================================

st.set_page_config(
    page_title="Market Radar Pro",
    page_icon="📊",
    layout="wide"
)

DB = "market_radar.db"

# ---------------- PROFESSIONAL UI DESIGN ----------------

st.markdown("""
<style>
.stApp {
    background: #f8fafc;
    color: #1e293b;
}
[data-testid="stSidebar"] {
    background: #f1f5f9;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    padding: 16px;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
h1, h2, h3, h4 {
    color: #0f172a;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}
.stCaption {
    color: #64748b;
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
        try:
            con.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                total_invested REAL DEFAULT 0,
                buy_price REAL DEFAULT 0,
                quantity REAL DEFAULT 0,
                notes TEXT DEFAULT ''
            )
            """)
        except Exception:
            pass

init_db()


# ---------------- ROBUST DATA SOURCES & LIVE PRICES ----------------

@st.cache_data(ttl=60)
def get_history(ticker, period="1y"):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, auto_adjust=True)
        if df.empty:
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


# ---------------- HELPERS ----------------

def close_series(df):
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df["Close"], errors="coerce").dropna()

def safe_float(value):
    try:
        value = float(value)
        return value if np.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0

def money(value, currency="$"):
    val = safe_float(value)
    return f"{currency}{val:,.2f}"


# ---------------- TECHNICAL ANALYSIS ----------------

def technical(df):
    close = close_series(df)
    if len(close) < 5:
        return {}

    returns = close.pct_change().dropna()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = -delta.clip(upper=0).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    drawdown = close / close.cummax() - 1

    curr_rsi = safe_float(rsi.iloc[-1]) if not rsi.empty and np.isfinite(rsi.iloc[-1]) else 50.0

    return {
        "price": float(close.iloc[-1]),
        "change": float(returns.iloc[-1] * 100) if not returns.empty else 0.0,
        "month": safe_float((close.iloc[-1] / close.iloc[-22] - 1) * 100) if len(close) >= 22 else 0.0,
        "ma50": safe_float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else float(close.iloc[-1]),
        "ma200": safe_float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float(close.iloc[-1]),
        "rsi": curr_rsi,
        "volatility": safe_float(returns.std() * np.sqrt(252) * 100) if not returns.empty else 15.0,
        "drawdown": safe_float(drawdown.iloc[-1] * 100) if not drawdown.empty else 0.0
    }

def price_chart(df, title):
    if df.empty:
        st.warning("אין נתונים להצגה כרגע.")
        return

    close = close_series(df)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=close.index, y=close, name="מחיר ($)", line=dict(color="#2563eb", width=2)))

    for period in [50, 200]:
        if len(close) >= period:
            color = "#059669" if period == 50 else "#d97706"
            fig.add_trace(go.Scatter(x=close.index, y=close.rolling(period).mean(), name=f"MA{period}", line=dict(color=color, width=1.5, dash="dot")))

    fig.update_layout(title=title, template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", height=400, margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)


# ---------------- PORTFOLIO DB & DEEP ANALYSIS ENGINE ----------------

def add_transaction(tx_date, ticker, total_invested, buy_price, notes=""):
    if buy_price <= 0:
        df = get_history(ticker, "5d")
        close = close_series(df)
        buy_price = float(close.iloc[-1]) if not close.empty else 100.0
        
    qty = total_invested / buy_price if buy_price > 0 else 0.0
    with connect_db() as con:
        con.execute("""
        INSERT INTO transactions (tx_date, ticker, total_invested, buy_price, quantity, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (str(tx_date), ticker.upper(), float(total_invested), float(buy_price), float(qty), str(notes)))

def update_transaction(tx_id, tx_date, ticker, total_invested, buy_price, notes=""):
    if buy_price <= 0:
        df = get_history(ticker, "5d")
        close = close_series(df)
        buy_price = float(close.iloc[-1]) if not close.empty else 100.0
    qty = total_invested / buy_price if buy_price > 0 else 0.0
    with connect_db() as con:
        con.execute("""
        UPDATE transactions 
        SET tx_date=?, ticker=?, total_invested=?, buy_price=?, quantity=?, notes=?
        WHERE id=?
        """, (str(tx_date), ticker.upper(), float(total_invested), float(buy_price), float(qty), str(notes), int(tx_id)))

def delete_transaction(tx_id):
    with connect_db() as con:
        con.execute("DELETE FROM transactions WHERE id=?", (int(tx_id),))

def load_transactions():
    with connect_db() as con:
        try:
            return pd.read_sql_query("SELECT * FROM transactions ORDER BY tx_date DESC, id DESC", con)
        except Exception:
            return pd.DataFrame()

def calculate_positions(tx):
    if tx.empty:
        return pd.DataFrame()

    vix_df = get_history("^VIX", "5d")
    vix_close = close_series(vix_df)
    vix_val = float(vix_close.iloc[-1]) if not vix_close.empty else 20.0

    results = []
    for _, row in tx.iterrows():
        tx_id = row["id"]
        ticker = row["ticker"]
        tx_date = row["tx_date"]
        cost = safe_float(row.get("total_invested", 0))
        buy_price = safe_float(row.get("buy_price", 0))
        units = safe_float(row.get("quantity", 0))
        notes = str(row.get("notes", ""))

        df = get_history(ticker, "6m")
        close = close_series(df)
        current = float(close.iloc[-1]) if not close.empty else np.nan
        
        # חישוב כמויות מדויק ואוטומטי בלייב
        if units <= 0:
            if buy_price > 0 and cost > 0:
                units = cost / buy_price
            elif current > 0 and cost > 0:
                units = cost / current
            else:
                units = 1.0

        tech = technical(df)
        info = get_info(ticker)
        pe_ratio = info.get("trailingPE", info.get("forwardPE", "N/A"))
        target_price = info.get("targetMeanPrice", "N/A")

        if np.isfinite(current) and units > 0:
            value = current * units
            pnl = value - cost
            pnl_pct = (pnl / cost) * 100 if cost > 0 else 0.0
        else:
            value = cost
            pnl = 0.0
            pnl_pct = 0.0
            current = buy_price if buy_price > 0 else 100.0

        rsi = tech.get("rsi", 50.0)
        ma200 = tech.get("ma200", current)
        
        # מנוע המלצות אקטיבי מבוסס נתונים
        if pnl_pct > 20 or (rsi > 72 and pnl_pct > 10):
            suggestion = "🔴 למכור ולמימוש רווחים: הנכס הגיע ליעד רווח גבוה או נמצא במצב קנוי-יתר (RSI > 72)."
        elif pnl_pct < -10 and (rsi < 45 or vix_val > 22):
            suggestion = "➕ להוסיף כסף (אסטרטגיית DCA): המחיר כרגע נמוך מעלות הקנייה בהנחה, והשוק בתמחור אטרקטיבי."
        elif current < ma200 and rsi < 40:
            suggestion = "🟡 להמתין בזהירות: הנכס מתחת לממוצע 200 עם מומנטום חלש, עקוב מקרוב לפני הגדלת חשיפה."
        else:
            suggestion = "🛡️ להשאיר ולהחזיק: המגמה הראשית יציבה ותקינה, אין צורך בשינוי מבני כרגע."

        results.append({
            "מזהה": int(tx_id),
            "תאריך": tx_date,
            "נכס/מדד": ticker,
            "סכום שהושקע ($)": round(cost, 2),
            "מחיר קנייה ($)": round(buy_price, 2) if buy_price > 0 else round(current, 2),
            "מחיר נוכחי בלייב ($)": round(current, 2) if np.isfinite(current) else 0.0,
            "שווי עדכני ($)": round(value, 2),
            "רווח/הפסד ($)": round(pnl, 2),
            "תשואה (%)": f"{pnl_pct:+.2f}%",
            "מכפיל רווח P/E": round(float(pe_ratio), 2) if isinstance(pe_ratio, (int, float)) else "לא זמין",
            "יעד אנליסטים ($)": f"${target_price:,.2f}" if isinstance(target_price, (int, float)) else "לא זמין",
            "המלצת מערכת עמוקה": suggestion,
            "הערות": notes
        })

    return pd.DataFrame(results)


# =====================================================
# SIDEBAR NAVIGATION (ALL 10 PAGES)
# =====================================================

st.sidebar.title("📊 MARKET RADAR PRO")
st.sidebar.caption("מערכת ניתוח וניהול השקעות בלייב ($)")

page = st.sidebar.radio(
    "ניווט במערכת",
    [
        "תיק השקעות והמלצות",
        "סקירת שוק חכמה",
        "המלצות Top 5 יומיות",
        "קרנות ממונפות",
        "ניתוח מדדים",
        "תמחור ומחירים",
        "מאקרו וכלכלה",
        "חדשות שוק",
        "ניהול סיכונים",
        "Backtesting"
    ]
)

if st.sidebar.button("🔄 רענון נתונים בלייב"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("הנתונים מתעדכנים ישירות משערי השוק החיים בדולרים ($).")


# =====================================================
# 1. PORTFOLIO MANAGEMENT
# =====================================================

if page == "תיק השקעות והמלצות":
    st.title("💼 ניהול תיק השקעות והמלצות חכמות מעמיקות")
    st.markdown("כאן תוכל לנהל את התיק שלך. השדות נקיים לחלוטין להזנה נוחה. המערכת שולפת את שערי השוק בלייב ומנתחת את התיק לעומק.")

    tab_add, tab_edit, tab_view = st.tabs(["➕ הוספת השקעה", "✏️ עריכה ומחיקה", "📋 צפייה וניתוח התיק"])

    with tab_add:
        with st.form("clean_add_form", clear_on_submit=True):
            st.subheader("הוספת השקעה חדשה לתיק")
            col1, col2 = st.columns(2)
            with col1:
                ticker = st.selectbox("בחר מדד / נכס", ["SPY", "QQQ", "DIA", "IWM", "VTI", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"])
                tx_date = st.date_input("תאריך השקעה", date.today())
            with col2:
                total_invested = st.number_input("סכום ההשקעה הכולל ($)", min_value=0.0, value=0.0, step=100.0, format="%.2f", placeholder="הכנס סכום...")
                buy_price = st.number_input("מחיר קנייה ליחידה ($) [השאר 0 לזיהוי אוטומטי]", min_value=0.0, value=0.0, step=1.0, format="%.2f", placeholder="הכנס מחיר קנייה...")
            notes = st.text_input("הערות (אופציונלי)")
            submit = st.form_submit_button("שמור השקעה בתיק")

            if submit:
                if total_invested <= 0:
                    st.warning("נא להזין סכום השקעה גדול מ-0.")
                else:
                    add_transaction(tx_date, ticker, total_invested, buy_price, notes)
                    st.success(f"השקעה ב-{ticker} על סך ${total_invested:,.2f} נשמרה בהצלחה!")
                    st.rerun()

    tx = load_transactions()

    with tab_edit:
        st.subheader("✏️ עריכה או מחיקה של השקעה קיימת")
        if not tx.empty and "id" in tx.columns:
            edit_id = st.selectbox("בחר מזהה (ID) של השקעה לעריכה/מחיקה", tx["id"].tolist())
            selected_row = tx[tx["id"] == edit_id].iloc[0]

            with st.form("edit_form"):
                all_tickers = ["SPY", "QQQ", "DIA", "IWM", "VTI", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
                curr_tick = str(selected_row.get("ticker", "SPY"))
                idx = all_tickers.index(curr_tick) if curr_tick in all_tickers else 0
                
                e_ticker = st.selectbox("נכס/מדד", all_tickers, index=idx)
                try:
                    default_date = pd.to_datetime(selected_row.get("tx_date", date.today())).date()
                except Exception:
                    default_date = date.today()
                
                e_date = st.date_input("תאריך", default_date)
                e_invested = st.number_input("סכום השקעה כולל ($)", min_value=0.0, value=float(selected_row.get("total_invested", 0.0)), format="%.2f")
                e_price = st.number_input("מחיר הקנייה ליחידה ($)", min_value=0.0, value=float(selected_row.get("buy_price", 0.0)), format="%.2f")
                e_notes = st.text_input("הערות", value=str(selected_row.get("notes", "")))

                col_e1, col_e2 = st.columns(2)
                update_btn = col_e1.form_submit_button("עדכן השקעה")
                delete_btn = col_e2.form_submit_button("מחק השקעה זו")

                if update_btn:
                    update_transaction(edit_id, e_date, e_ticker, e_invested, e_price, e_notes)
                    st.success(f"השקעה מס' {edit_id} עודכנה בהצלחה!")
                    st.rerun()
                if delete_btn:
                    delete_transaction(edit_id)
                    st.success(f"השקעה מס' {edit_id} נמחקה בהצלחה!")
                    st.rerun()
        else:
            st.info("אין עדיין השקעות בתיק לעריכה.")

    with tab_view:
        if not tx.empty:
            st.subheader("📋 היסטוריית עסקאות שמורות")
            st.dataframe(tx, use_container_width=True)

            st.download_button(
                "הורדת עסקאות כקובץ CSV",
                tx.to_csv(index=False).encode("utf-8-sig"),
                "my_portfolio_transactions.csv",
                "text/csv"
            )

            positions = calculate_positions(tx)

            st.subheader("📊 פוזיציות פתוחות, ניתוח מעמיק והמלצות מערכת")
            st.dataframe(positions, use_container_width=True)

            valid_vals = positions.dropna(subset=["שווי עדכני ($)"]) if "שווי עדכני ($)" in positions.columns else pd.DataFrame()
            if not valid_vals.empty:
                total_cost = positions["סכום שהושקע ($)"].sum()
                total_val = positions["שווי עדכני ($)"].sum()
                total_pnl = total_val - total_cost
                total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

                c1, c2, c3 = st.columns(3)
                c1.metric("סך הכל הושקע ($)", money(total_cost))
                c2.metric("שווי התיק כיום ($)", money(total_val))
                c3.metric("סך רווח / הפסד ($)", money(total_pnl), f"{total_pnl_pct:+.2f}%")

                fig = go.Figure(data=[go.Pie(labels=positions["נכס/מדד"], values=positions["שווי עדכני ($)"], hole=0.45)])
                fig.update_layout(title="פיזור נכסים בתיק ($)", template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("עדיין לא הוזנו השקעות לתיק. עבור ללשונית 'הוספת השקעה' כדי להתחיל.")


# =====================================================
# 2. SMART MARKET OVERVIEW
# =====================================================

elif page == "סקירת שוק חכמה":
    st.title("🌎 סקירת שוק ותזמון כניסה חכם")
    st.markdown("שקלול של מחירי המדדים, ממוצעים נעים, RSI ומדד הפחד להחלטה האם השוק אטרקטיבי כרגע.")

    assets = {
        "S&P 500 (SPY)": "SPY",
        "Nasdaq 100 (QQQ)": "QQQ",
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
    price_chart(sp_df, "גרף מחיר S&P 500 ($) מול ממוצעים נעים")


# =====================================================
# 3. DAILY TOP 5 RECOMMENDATIONS
# =====================================================

elif page == "המלצות Top 5 יומיות":
    st.title("⭐ המלצות Top 5 יומיות להשקעה")
    st.markdown("סריקה מקיפה של מדדים מובילים וקרנות סל מומלצות לבדיקה יומית.")

    mega_pool = [
        {"name": "S&P 500 ETF", "ticker": "SPY"},
        {"name": "Nasdaq 100 ETF", "ticker": "QQQ"},
        {"name": "Dow Jones ETF", "ticker": "DIA"},
        {"name": "Russell 2000 ETF", "ticker": "IWM"},
        {"name": "Apple", "ticker": "AAPL"},
        {"name": "Microsoft", "ticker": "MSFT"},
        {"name": "Nvidia", "ticker": "NVDA"}
    ]

    analyzed_list = []
    with st.spinner("סורק ומנתח את השוק בלייב..."):
        for item in mega_pool:
            ticker = item["ticker"]
            df = get_history(ticker, "6m")
            tech = technical(df)
            if tech and "price" in tech:
                price = tech["price"]
                rsi = tech["rsi"]
                analyzed_list.append({
                    "נכס / מדד": f"{item['name']} ({ticker})",
                    "מחיר נוכחי ($)": round(price, 2),
                    "RSI (מומנטום)": round(rsi, 1),
                    "המלצת המערכת": "🟢 מומלץ לבדיקה וניתוח"
                })

    if analyzed_list:
        st.dataframe(pd.DataFrame(analyzed_list), use_container_width=True)
    else:
        st.warning("לא התקבלו נתונים כרגע.")


# =====================================================
# 4. LEVERAGED FUNDS
# =====================================================

elif page == "קרנות ממונפות":
    st.title("⚡ ניתוח והמלצות על קרנות ממונפות")
    st.warning("⚠️ קרנות ממונפות (2x/3x) מיועדות למשקיעים המודעים לסיכון השחיקה בתקופות תנודתיות.")

    lev_tickers = {
        "TQQQ (3x Nasdaq - טכנולוגיה ממונפת)": "TQQQ",
        "UPRO (3x S&P 500 - מדד רחב ממונף)": "UPRO",
        "QLD (2x Nasdaq - ממונף מתון)": "QLD",
        "SSO (2x S&P 500 - ממונף מתון)": "SSO"
    }

    selected_lev = st.selectbox("בחר קרן ממונפת לבדיקה", list(lev_tickers.keys()))
    ticker_symbol = lev_tickers[selected_lev]

    df_lev = get_history(ticker_symbol, "1y")
    tech_lev = technical(df_lev)

    if not df_lev.empty and tech_lev:
        col1, col2, col3 = st.columns(3)
        col1.metric("מחיר נוכחי", f"${tech_lev['price']:,.2f}")
        col2.metric("תנודתיות שנתית", f"{tech_lev['volatility']:.1f}%")
        col3.metric("ירידה מהשיא", f"{tech_lev['drawdown']:.1f}%")

        st.divider()
        st.subheader("🤖 המלצת המערכת לקרן ממונפת זו:")
        if tech_lev["price"] > tech_lev.get("ma200", 0) and tech_lev.get("rsi", 50) < 62:
            st.success("**המלצה: כניסה זהירה אפשרית.** המגמה מעל ממוצע 200 וה-RSI אינו קנוי יתר.")
        elif tech_lev.get("rsi", 50) > 68:
            st.warning("**המלצה: לא להיכנס כעת.** RSI גבוה מאוד (סיכון לתיקון חד).")
        else:
            st.error("**המלצה: סיכון מוגבר.** מומלץ להמתין להתייצבות השוק.")

        price_chart(df_lev, f"ביצועי {ticker_symbol} בדולרים ($)")
    else:
        st.warning("אין מספיק נתונים להצגת הקרן הממונפות.")


# =====================================================
# 5. INDEX ANALYSIS
# =====================================================

elif page == "ניתוח מדדים":
    st.title("📈 ניתוח מדדים מובילים")
    choices = {"S&P 500 (SPY)": "SPY", "Nasdaq 100 (QQQ)": "QQQ"}
    selected = st.selectbox("בחר מדד", list(choices))
    df = get_history(choices[selected], "5y")

    if not df.empty:
        price_chart(df, selected)
        t = technical(df)
        if t:
            cols = st.columns(3)
            cols[0].metric("RSI (מומנטום)", money(t["rsi"], ""))
            cols[1].metric("תנודתיות שנתית", f"{t['volatility']:.2f}%")
            cols[2].metric("ירידה מהשיא", f"{t['drawdown']:.1f}%")
    else:
        st.error("לא התקבלו נתונים עבור המדד הנבחר.")


# =====================================================
# 6. VALUATION
# =====================================================

elif page == "תמחור ומחירים":
    st.title("💰 תמחור נכסים מובילים")
    ticker = st.selectbox("בחר נכס", ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"])
    info = get_info(ticker)

    fields = {
        "מכפיל רווח נוכחי (Trailing P/E)": "trailingPE",
        "מכפיל רווח עתידי (Forward P/E)": "forwardPE",
        "יחס מחיר להון (Price to Book)": "priceToBook",
        "תחזית מחיר ממוצעת מאנליסטים": "targetMeanPrice"
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


# =====================================================
# 7. MACRO
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
        fig.add_trace(go.Scatter(x=df["date"], y=df["value"], mode="lines", name=selected, line=dict(color="#2563eb")))
        fig.update_layout(template="plotly_white", height=400, paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("הנתון אינו זמין כרגע.")


# =====================================================
# 8. NEWS
# =====================================================

elif page == "חדשות שוק":
    st.title("📰 חדשות שוק ההון")
    topic = st.selectbox("בחר נושא", ["US stock market economy", "Federal Reserve inflation", "technology AI stocks"])
    
    try:
        response = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": topic, "mode": "ArtList", "format": "json", "maxrecords": 10, "sort": "DateDesc"},
            timeout=10
        )
        articles = response.json().get("articles", []) if response.status_code == 200 else []
    except Exception:
        articles = []

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
# 9. RISK ANALYSIS
# =====================================================

elif page == "ניהול סיכונים":
    st.title("⚠️ ניהול סיכונים ותרחישי ירידה")
    capital = st.number_input("שווי תיק היפותטי ($)", min_value=0.0, value=10000.0, step=1000.0)

    scenarios = [-5, -10, -20, -30, -40]
    scenario_df = pd.DataFrame({
        "תרחיש ירידה": [f"ירידה של {abs(x)}%" for x in scenarios],
        "הפסד מוערך ($)": [round(capital * abs(x) / 100, 2) for x in scenarios],
        "שווי התיק לאחר ירידה ($)": [round(capital * (1 + x / 100), 2) for x in scenarios]
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
        fig.add_trace(go.Scatter(x=close_bt.index, y=buy_hold, name="Buy & Hold", line=dict(color="#2563eb")))
        fig.add_trace(go.Scatter(x=close_bt.index, y=model, name="אסטרטגיית ממוצעים", line=dict(color="#059669")))
        fig.update_layout(template="plotly_white", height=450, paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("אין מספיק נתונים היסטוריים לביצוע הבדיקה.")
