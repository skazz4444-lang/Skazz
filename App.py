
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
# MARKET RADAR - FULL STREAMLIT APP
# =====================================================

st.set_page_config(
    page_title="Market Radar",
    page_icon="📊",
    layout="wide"
)

DB = "market_radar.db"

# ---------------- DESIGN ----------------

st.markdown("""
<style>
.stApp {
    background: #0b1220;
    color: #e8eef7;
}
[data-testid="stSidebar"] {
    background: #111c2e;
}
[data-testid="stMetric"] {
    background: #172338;
    border: 1px solid #30415a;
    padding: 14px;
    border-radius: 12px;
}
h1,h2,h3,h4 {
    color: #e8eef7;
}
.stCaption {
    color: #9aacc3;
}
</style>
""", unsafe_allow_html=True)


# ---------------- DATABASE ----------------

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


# ---------------- DATA SOURCES ----------------

@st.cache_data(ttl=60)
def get_history(ticker, period="2y"):
    try:
        df = yf.download(
            ticker,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=False
        )
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
        url = (
            "https://fred.stlouisfed.org/graph/"
            f"fredgraph.csv?id={series}"
        )
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))
        if len(df.columns) < 2:
            return pd.DataFrame()

        df = df.iloc[:, :2]
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(
            df["value"], errors="coerce"
        )
        return df.dropna().sort_values("date")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900)
def get_news(query):
    try:
        response = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": query,
                "mode": "ArtList",
                "format": "json",
                "maxrecords": 20,
                "sort": "DateDesc"
            },
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
        "month": safe_float(
            (close.iloc[-1] / close.iloc[-22] - 1) * 100
        ) if len(close) >= 22 else None,
        "quarter": safe_float(
            (close.iloc[-1] / close.iloc[-64] - 1) * 100
        ) if len(close) >= 64 else None,
        "ma20": safe_float(close.rolling(20).mean().iloc[-1]),
        "ma50": safe_float(close.rolling(50).mean().iloc[-1]),
        "ma200": safe_float(close.rolling(200).mean().iloc[-1]),
        "rsi": safe_float(rsi.iloc[-1]),
        "volatility": safe_float(
            returns.std() * np.sqrt(252) * 100
        ),
        "drawdown": safe_float(drawdown.iloc[-1] * 100),
        "max_drawdown": safe_float(drawdown.min() * 100)
    }


def price_chart(df, title):
    if df.empty:
        st.warning("אין נתונים להצגה.")
        return

    close = close_series(df)
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=close.index,
        y=close,
        name="מחיר"
    ))

    for period in [20, 50, 200]:
        if len(close) >= period:
            fig.add_trace(go.Scatter(
                x=close.index,
                y=close.rolling(period).mean(),
                name=f"MA{period}"
            ))

    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor="#0b1220",
        plot_bgcolor="#0b1220",
        height=420,
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)


# ---------------- MARKET SCORE ----------------

def calculate_market_score(sp_df, vix_value):
    """
    Educational market-conditions indicator.
    Not an investment recommendation.
    """
    tech = technical(sp_df)
    factors = {}

    if not tech:
        return None, factors

    if tech["ma200"] is not None:
        factors["מגמה ארוכה"] = (
            100 if tech["price"] > tech["ma200"] else 0
        )

    if tech["ma50"] is not None:
        factors["מגמה בינונית"] = (
            100 if tech["price"] > tech["ma50"] else 0
        )

    if tech["rsi"] is not None:
        rsi = tech["rsi"]
        if 45 <= rsi <= 65:
            factors["מומנטום"] = 75
        elif 35 <= rsi < 45:
            factors["מומנטום"] = 45
        elif 65 < rsi <= 75:
            factors["מומנטום"] = 55
        else:
            factors["מומנטום"] = 25

    if vix_value is not None:
        if vix_value < 15:
            factors["תנודתיות"] = 90
        elif vix_value < 20:
            factors["תנודתיות"] = 70
        elif vix_value < 30:
            factors["תנודתיות"] = 45
        else:
            factors["תנודתיות"] = 20

    if len(factors) < 3:
        return None, factors

    return round(float(np.mean(list(factors.values()))), 1), factors


# ---------------- PORTFOLIO ----------------

def add_transaction(
    tx_date, ticker, action, quantity,
    price, fee, currency, notes
):
    with connect_db() as con:
        con.execute("""
        INSERT INTO transactions
        (tx_date,ticker,action,quantity,price,fee,currency,notes)
        VALUES (?,?,?,?,?,?,?,?)
        """, (
            str(tx_date), ticker.upper(), action,
            quantity, price, fee, currency, notes
        ))


def load_transactions():
    with connect_db() as con:
        return pd.read_sql_query(
            "SELECT * FROM transactions ORDER BY tx_date,id",
            con
        )


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
            current = (
                float(close.iloc[-1]) if not close.empty else np.nan
            )

            value = current * units if np.isfinite(current) else np.nan
            pnl = value - cost if np.isfinite(value) else np.nan

            results.append({
                "סימול": ticker,
                "כמות": units,
                "עלות": cost,
                "מחיר אחרון": current,
                "שווי": value,
                "רווח/הפסד לא ממומש": pnl,
                "רווח/הפסד ממומש": realized
            })

    return pd.DataFrame(results)


# ---------------- BACKTEST ----------------

def backtest(ticker):
    df = get_history(ticker, "5y")
    close = close_series(df)

    if len(close) < 220:
        return pd.DataFrame()

    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    signal = (ma50 > ma200).astype(int)
    daily_returns = close.pct_change().fillna(0)

    model_returns = (
        signal.shift(1).fillna(0) * daily_returns
    )

    buy_hold = 10000 * (1 + daily_returns).cumprod()
    model = 10000 * (1 + model_returns).cumprod()

    return pd.DataFrame({
        "Buy & Hold": buy_hold,
        "Moving Average Model": model
    })


# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.title("📊 MARKET RADAR")

page = st.sidebar.radio(
    "ניווט",
    [
        "סקירת שוק",
        "ניתוח מדדים",
        "תמחור",
        "מאקרו",
        "חדשות",
        "תיק השקעות",
        "ניהול סיכונים",
        "Backtesting"
    ]
)

if st.sidebar.button("🔄 רענון נתונים"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("חלק מהנתונים מתעדכנים כל 60 שניות.")
st.sidebar.caption("מקורות חיצוניים עשויים להיות מושהים.")


# =====================================================
# 1. MARKET OVERVIEW
# =====================================================

if page == "סקירת שוק":

    st.title("🌎 סקירת שוק")

    assets = {
        "S&P 500": "^GSPC",
        "Nasdaq 100": "^NDX",
        "Dow Jones": "^DJI",
        "Russell 2000": "^RUT",
        "VIX": "^VIX",
        "זהב": "GC=F",
        "נפט": "CL=F",
        "דולר/שקל": "ILS=X",
        "אגח ארוך": "TLT"
    }

    cols = st.columns(3)

    for i, (name, ticker) in enumerate(assets.items()):
        df = get_history(ticker, "5d")
        close = close_series(df)

        with cols[i % 3]:
            if len(close) >= 2:
                change = (
                    close.iloc[-1] / close.iloc[-2] - 1
                ) * 100
                st.metric(
                    name,
                    f"{close.iloc[-1]:,.2f}",
                    f"{change:+.2f}%"
                )
            elif len(close) == 1:
                st.metric(name, f"{close.iloc[-1]:,.2f}")
            else:
                st.metric(name, "לא זמין")

    st.divider()

    sp = get_history("^GSPC", "2y")
    vix_df = get_history("^VIX", "5d")
    vix_close = close_series(vix_df)

    vix_value = (
        float(vix_close.iloc[-1])
        if not vix_close.empty else None
    )

    score, factors = calculate_market_score(sp, vix_value)

    st.subheader("מדד תנאי שוק משולב")

    if score is not None:
        st.metric("ציון אינדיקטיבי", f"{score}/100")
        st.progress(int(score))

        st.dataframe(
            pd.DataFrame([
                {"גורם": k, "ציון": v}
                for k, v in factors.items()
            ]),
            use_container_width=True
        )

        st.caption(
            f"כיסוי: {len(factors)} גורמים מתוך 4. "
            "המשקולות שוות והציון אינו המלצת השקעה."
        )
    else:
        st.warning("אין מספיק נתונים לחישוב ציון.")

    price_chart(sp, "S&P 500")


# =====================================================
# 2. INDEX ANALYSIS
# =====================================================

elif page == "ניתוח מדדים":

    st.title("📈 ניתוח מדדים")

    choices = {
        "S&P 500": "^GSPC",
        "Nasdaq 100": "^NDX",
        "Dow Jones": "^DJI",
        "Russell 2000": "^RUT"
    }

    selected = st.selectbox("בחר מדד", list(choices))
    df = get_history(choices[selected], "5y")

    if not df.empty:
        price_chart(df, selected)
        t = technical(df)

        if t:
            cols = st.columns(3)
            cols[0].metric("RSI", money(t["rsi"], ""))
            cols[1].metric(
                "תנודתיות שנתית",
                f"{t['volatility']:.2f}%"
            )
            cols[2].metric(
                "ירידה מהשיא",
                f"{t['drawdown']:.2f}%"
            )

            cols = st.columns(3)
            cols[0].metric(
                "שינוי יומי",
                f"{t['change']:.2f}%"
            )
            cols[1].metric(
                "תשואה חודשית",
                f"{t['month']:.2f}%"
                if t["month"] is not None else "לא זמין"
            )
            cols[2].metric(
                "תשואה רבעונית",
                f"{t['quarter']:.2f}%"
                if t["quarter"] is not None else "לא זמין"
            )

            st.write("ממוצעים נעים")
            st.json({
                "MA20": t["ma20"],
                "MA50": t["ma50"],
                "MA200": t["ma200"]
            })
    else:
        st.error("לא התקבלו נתונים.")


# =====================================================
# 3. VALUATION
# =====================================================

elif page == "תמחור":

    st.title("💰 תמחור ותחזיות")

    ticker = st.selectbox(
        "בחר נכס",
        ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
    )

    info = get_info(ticker)

    fields = {
        "Trailing P/E": "trailingPE",
        "Forward P/E": "forwardPE",
        "Price to Book": "priceToBook",
        "Price to Sales": "priceToSalesTrailing12Months",
        "Profit Margin": "profitMargins",
        "Revenue Growth": "revenueGrowth",
        "Earnings Growth": "earningsGrowth",
        "Analyst Target Mean": "targetMeanPrice",
        "Analyst Target High": "targetHighPrice",
        "Analyst Target Low": "targetLowPrice",
        "Analyst Opinions": "numberOfAnalystOpinions"
    }

    rows = []

    for label, key in fields.items():
        value = info.get(key)

        if value is None:
            value = "לא זמין"
        elif isinstance(value, (float, int, np.number)):
            value = round(float(value), 4)

        rows.append({"נתון": label, "ערך": value})

    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.info(
        "נתוני Yahoo Finance עשויים להיות חסרים או מושהים. "
        "מכפיל ETF אינו בהכרח מכפיל המדד עצמו."
    )

    st.subheader("CAPE ו-Buffett Indicator")
    st.warning(
        "מדדים אלה אינם מחושבים כאן, כי אין חיבור למקור "
        "נתונים מאומת עבורם. הם אינם אפס ואינם זמינים כרגע."
    )


# =====================================================
# 4. MACRO
# =====================================================

elif page == "מאקרו":

    st.title("🏦 מאקרו וכלכלה")

    series = {
        "ריבית הפד": "FEDFUNDS",
        "תשואת אגח 10 שנים": "DGS10",
        "תשואת אגח 2 שנים": "DGS2",
        "אינפלציה CPI": "CPIAUCSL",
        "אבטלה": "UNRATE",
        "מרווח אשראי High Yield": "BAMLH0A0HYM2",
        "תשואה ריאלית 10 שנים": "DFII10",
        "מדד תנאים פיננסיים": "NFCI"
    }

    selected = st.selectbox("בחר נתון", list(series))
    df = get_fred(series[selected])

    if not df.empty:
        latest = df.iloc[-1]

        st.metric(
            selected,
            f"{latest['value']:.3f}",
            str(latest["date"].date())
        )

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["value"],
            mode="lines",
            name=selected
        ))

        fig.update_layout(
            template="plotly_dark",
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df.tail(30), use_container_width=True)
    else:
        st.warning("הנתון אינו זמין כרגע.")


# =====================================================
# 5. NEWS
# =====================================================

elif page == "חדשות":

    st.title("📰 חדשות וגיאופוליטיקה")

    topics = {
        "כלכלה אמריקאית": "US economy",
        "שוק המניות": "US stock market",
        "ריבית ואינפלציה": "Federal Reserve inflation",
        "המזרח התיכון": "Middle East geopolitics",
        "סנקציות": "international sanctions",
        "אנרגיה": "oil energy markets"
    }

    topic = st.selectbox("בחר נושא", list(topics))
    articles = get_news(topics[topic])

    if articles:
        for article in articles:
            with st.container(border=True):
                st.markdown(
                    f"**{article.get('title', 'ללא כותרת')}**"
                )
                st.caption(
                    str(article.get("domain", "")) +
                    " | " + str(article.get("seendate", ""))
                )

                url = article.get("url")
                if url:
                    st.link_button("לקריאת הכתבה", url)
    else:
        st.warning("לא התקבלו כתבות.")

    st.caption(
        "חדשות אינן מדד כמותי מאומת לסיכון גיאופוליטי."
    )


# =====================================================
# 6. PORTFOLIO
# =====================================================

elif page == "תיק השקעות":

    st.title("💼 ניהול תיק השקעות")

    st.warning(
        "מעקב לימודי בלבד. בדוק את המטבע של כל עסקה. "
        "אין כאן חישוב המרה אוטומטי בין מטבעות."
    )

    with st.form("add_transaction"):

        ticker = st.text_input("סימול", "SPY").upper()

        action = st.selectbox(
            "פעולה",
            ["קנייה", "מכירה"]
        )

        quantity = st.number_input(
            "כמות",
            min_value=0.000001,
            value=1.0
        )

        price = st.number_input(
            "מחיר ליחידה",
            min_value=0.0,
            value=100.0
        )

        fee = st.number_input(
            "עמלה",
            min_value=0.0,
            value=0.0
        )

        currency = st.selectbox(
            "מטבע",
            ["USD", "ILS", "EUR"]
        )

        tx_date = st.date_input(
            "תאריך עסקה",
            date.today()
        )

        notes = st.text_input("הערות")

        submit = st.form_submit_button("שמור עסקה")

        if submit:
            if ticker and quantity > 0 and price > 0:
                add_transaction(
                    tx_date,
                    ticker,
                    action,
                    quantity,
                    price,
                    fee,
                    currency,
                    notes
                )
                st.success("העסקה נשמרה.")
                st.rerun()

    tx = load_transactions()

    if not tx.empty:

        st.subheader("היסטוריית עסקאות")
        st.dataframe(tx, use_container_width=True)

        st.download_button(
            "הורדת עסקאות CSV",
            tx.to_csv(index=False).encode("utf-8-sig"),
            "transactions.csv",
            "text/csv"
        )

        positions = calculate_positions(tx)

        st.subheader("פוזיציות פתוחות")

        if not positions.empty:
            st.dataframe(
                positions,
                use_container_width=True
            )

            st.metric(
                "רווח/הפסד לא ממומש",
                money(
                    positions["רווח/הפסד לא ממומש"].sum()
                )
            )

            valid = positions.dropna(subset=["שווי"])

            if not valid.empty:
                fig = go.Figure(
                    data=[go.Pie(
                        labels=valid["סימול"],
                        values=valid["שווי"],
                        hole=0.45
                    )]
                )

                fig.update_layout(
                    title="פיזור תיק",
                    template="plotly_dark"
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True
                )

        st.subheader("מחיקת עסקה")

        delete_id = st.number_input(
            "מספר עסקה למחיקה",
            min_value=0,
            step=1
        )

        if st.button("מחק עסקה"):
            if delete_id:
                with connect_db() as con:
                    con.execute(
                        "DELETE FROM transactions WHERE id=?",
                        (int(delete_id),)
                    )
                st.success("העסקה נמחקה.")
                st.rerun()

    else:
        st.info("עדיין לא הוזנו עסקאות.")


# =====================================================
# 7. RISK ANALYSIS
# =====================================================

elif page == "ניהול סיכונים":

    st.title("⚠️ ניהול סיכונים")

    tickers = st.multiselect(
        "בחר נכסים",
        ["SPY", "QQQ", "DIA", "IWM", "TLT", "GLD"],
        default=["SPY", "QQQ", "TLT", "GLD"]
    )

    if len(tickers) >= 2:

        returns = {}

        for ticker in tickers:
            df = get_history(ticker, "2y")
            close = close_series(df)

            if not close.empty:
                returns[ticker] = close.pct_change()

        if len(returns) >= 2:

            ret = pd.DataFrame(returns).dropna()
            corr = ret.corr()

            fig = go.Figure(
                data=go.Heatmap(
                    z=corr.values,
                    x=corr.columns,
                    y=corr.index,
                    zmin=-1,
                    zmax=1,
                    text=np.round(corr.values, 2),
                    texttemplate="%{text}"
                )
            )

            fig.update_layout(
                title="מטריצת קורלציה",
                template="plotly_dark",
                height=450
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

    st.subheader("תרחישי ירידה")

    capital = st.number_input(
        "שווי תיק היפותטי",
        min_value=0.0,
        value=10000.0,
        step=500.0
    )

    scenarios = [-5, -10, -20, -30, -40]

    scenario_df = pd.DataFrame({
        "תרחיש ירידה": [f"{abs(x)}%" for x in scenarios],
        "הפסד היפותטי": [
            capital * abs(x) / 100 for x in scenarios
        ],
        "שווי לאחר ירידה": [
            capital * (1 + x / 100) for x in scenarios
        ]
    })

    st.dataframe(
        scenario_df,
        use_container_width=True
    )


# =====================================================
# 8. BACKTESTING
# =====================================================

elif page == "Backtesting":

    st.title("🧪 Backtesting")

    ticker = st.selectbox(
        "בחר נכס",
        ["SPY", "QQQ", "DIA", "IWM"]
    )

    result = backtest(ticker)

    if not result.empty:

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=result.index,
            y=result["Buy & Hold"],
            name="Buy & Hold"
        ))

        fig.add_trace(go.Scatter(
            x=result.index,
            y=result["Moving Average Model"],
            name="מודל ממוצעים נעים"
        ))

        fig.update_layout(
            title="השוואת ביצועים היסטוריים",
            template="plotly_dark",
            height=450
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        final_hold = result["Buy & Hold"].iloc[-1]
        final_model = result["Moving Average Model"].iloc[-1]

        c1, c2 = st.columns(2)

        c1.metric(
            "Buy & Hold",
            f"${final_hold:,.2f}"
        )

        c2.metric(
            "מודל ממוצעים נעים",
            f"${final_model:,.2f}"
        )

        st.caption(
            "בדיקת עבר היפותטית לפני מס, עמלות והחלקה. "
            "אינה תחזית לביצועים עתידיים."
        )

    else:
        st.warning("אין מספיק נתונים לבדיקה.")


# =====================================================
# FOOTER
# =====================================================

st.divider()

st.caption(
    "Market Radar | כלי מידע וניתוח לימודי. "
    "אין לראות בתוכן ייעוץ השקעות או המלצה לפעולה. "
    "נתוני ספקים חיצוניים עשויים להיות מושהים, חלקיים "
    "או להשתנות בהתאם לתנאי השירות שלהם."
)
