"""Private fund dashboard. Run: streamlit run app.py

requirements.txt: streamlit>=1.45,<2; pandas>=2.2,<3; yfinance>=0.2.65,<1
Use one requirement per line. Configure Cloud access as private before use.
All percentages use percentage points: enter 8.5 for 8.5%, not 0.085.
Optional funds.json is a JSON array using the same fields as SEED below.
Cloud edits live in this browser session: export JSON to retain changes.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import math
import re

import pandas as pd
import streamlit as st
import yfinance as yf

HORIZONS = ("YTD", "1Y", "3Y", "5Y")
HOLD = "🟢 HOLD (Outperforming)"
REPLACE = "🔴 REPLACE (Fee Drag)"
PENDING = "⚪ AWAITING DATA"
SEED = [
    {"code": "RBF678", "name": "RBC QUBE Canadian Equity", "asset_class": "Canadian Large Cap", "mer": 0.77, "benchmark": "XIC.TO"},
    {"code": "RBF3314", "name": "RBC Canadian Mid-Cap Equity", "asset_class": "Canadian Mid Cap", "mer": 0.93, "benchmark": "XMD.TO"},
    {"code": "RBF611", "name": "RBC North American Growth F", "asset_class": "US/CAD Large Cap", "mer": 0.77, "benchmark": "VFV.TO"},
    {"code": "RBF639", "name": "RBC QUBE International Equity", "asset_class": "International Equity", "mer": 1.02, "benchmark": "ZEA.TO"},
]
FIELDS = ["code", "name", "asset_class", "mer", "benchmark", "as_of", *HORIZONS]


def normalize(records):
    """Validate edits/imports atomically; never silently coerce bad returns."""
    if not isinstance(records, list) or not records:
        raise ValueError("Provide a nonempty JSON array of fund records.")
    clean, seen = [], set()
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    for i, item in enumerate(records, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Row {i}: expected an object.")
        row = {}
        for key in ("code", "name", "asset_class", "benchmark"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Row {i}: {key} is required.")
            row[key] = value.strip()
        row["code"] = row["code"].upper()
        row["benchmark"] = row["benchmark"].upper()
        if row["code"] in seen:
            raise ValueError(f"Duplicate fund code: {row['code']}")
        seen.add(row["code"])
        if not re.fullmatch(r"[A-Z0-9.^=\-]{1,30}", row["benchmark"]):
            raise ValueError(f"Row {i}: invalid benchmark ticker.")
        for key in ("mer", *HORIZONS):
            value = item.get(key)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                if key == "mer":
                    raise ValueError(f"Row {i}: MER is required.")
                row[key] = None
                continue
            if isinstance(value, bool):
                raise ValueError(f"Row {i}: {key} must be numeric.")
            value = float(value)
            if not math.isfinite(value) or (key == "mer" and not 0 <= value <= 100) or (key != "mer" and value < -100):
                raise ValueError(f"Row {i}: invalid {key}.")
            row[key] = value
        raw_date = item.get("as_of")
        as_of = None if raw_date is None or pd.isna(raw_date) or raw_date == "" else pd.Timestamp(raw_date).date()
        if as_of and as_of > yesterday:
            raise ValueError(f"Row {i}: choose a completed date (yesterday or earlier).")
        if any(row[h] is not None for h in HORIZONS) and not as_of:
            raise ValueError(f"Row {i}: reporting date is required with stated returns.")
        row["as_of"] = as_of.isoformat() if as_of else None
        clean.append(row)
    return clean


@st.cache_data(ttl=900, max_entries=256, show_spinner=False)
def fetch_history(ticker, start, end):
    """Exceptions are not cached. Each unique ETF is fetched once, not per fund."""
    history = yf.Ticker(ticker).history(
        start=start, end=end, interval="1d", auto_adjust=True,
        actions=False, repair=True, timeout=20,
    )
    if history.empty or "Close" not in history:
        raise ValueError("No price history returned; retry later or verify ticker.")
    prices = pd.to_numeric(history["Close"], errors="coerce").dropna()
    prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
    prices = prices[~prices.index.duplicated(keep="last")].sort_index()
    if prices.empty or not all(math.isfinite(v) and v > 0 for v in prices):
        raise ValueError("Invalid adjusted prices returned.")
    return prices, datetime.now(timezone.utc).isoformat(timespec="seconds")


def price_on(prices, target):
    """Use prior close on weekends/holidays; reject gaps over four days."""
    target = pd.Timestamp(target)
    eligible = prices.loc[:target]
    if eligible.empty or (target - eligible.index[-1]).days > 4:
        raise ValueError(f"Missing close near {target.date()}.")
    return float(eligible.iloc[-1]), eligible.index[-1]


def benchmark_returns(prices, as_of):
    end_value, end_date = price_on(prices, as_of)
    values, notes = {}, []
    for horizon in HORIZONS:
        years = 0 if horizon == "YTD" else int(horizon[0])
        start_date = pd.Timestamp(end_date.year - 1, 12, 31) if years == 0 else end_date - pd.DateOffset(years=years)
        try:
            start_value, _ = price_on(prices, start_date)
            # Standard trailing-year convention; YTD/1Y cumulative, 3Y/5Y CAGR.
            values[horizon] = ((end_value / start_value) ** (1 / max(years, 1)) - 1) * 100
        except ValueError as exc:
            values[horizon] = None
            notes.append(f"{horizon}: {exc}")
    return values, end_date.date().isoformat(), "; ".join(notes)


def action_for(alpha):
    return PENDING if alpha is None or pd.isna(alpha) else HOLD if alpha > 0 else REPLACE


def build_grid(funds, histories, errors):
    rows = []
    for fund in funds:
        ticker = fund["benchmark"]
        row = {"Fund Code": fund["code"], "Fund Name": fund["name"],
               "Asset Class": fund["asset_class"], "MER (%)": fund["mer"],
               "Benchmark": ticker, "Fund As Of": fund["as_of"],
               "ETF As Of": None, "Fetched (UTC)": None}
        values = dict.fromkeys(HORIZONS)
        note = errors.get(ticker, "")
        if ticker in histories:
            prices, fetched = histories[ticker]
            row["Fetched (UTC)"] = fetched
            if fund["as_of"]:
                try:
                    values, row["ETF As Of"], note = benchmark_returns(prices, fund["as_of"])
                    if row["ETF As Of"] != fund["as_of"]:
                        note = f"Prior market close {row['ETF As Of']}. {note}".strip()
                except ValueError as exc:
                    note = str(exc)
            else:
                note = "Enter dated fund returns to compare."
        for horizon in HORIZONS:
            stated, benchmark = fund[horizon], values[horizon]
            row[f"Fund {horizon} (%)"] = stated
            row[f"ETF {horizon} (%)"] = benchmark
            row[f"Alpha {horizon} (pp)"] = None if stated is None or benchmark is None else stated - benchmark
        row["Action"] = action_for(row["Alpha 3Y (pp)"])
        row["Data Status"] = note or "Ready"
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    st.set_page_config(page_title="Fund Performance | Destiny Benefits", page_icon="📈", layout="wide")
    st.markdown("""<style>
    :root { --destiny-navy:#1B365D; --destiny-blue:#2563AB;
      --destiny-ink:#243750; --destiny-line:#DDE5EE; }
    .stApp { background:#F7F8FA; color:var(--destiny-ink); }
    [data-testid="stAppViewBlockContainer"] { padding-top:2rem; padding-bottom:2rem; }
    [data-testid="stHeader"] { background:#F7F8FA; }
    h1,h2,h3 { color:var(--destiny-navy); letter-spacing:-.025em; }
    [data-testid="stSidebar"] { background:#EDF2F8; border-right:1px solid #DDE5EE; }
    [data-testid="stSidebar"] h2 { font-size:1.25rem; }
    .destiny-sidebar { padding:8px 0 22px; margin-bottom:18px;
      border-bottom:1px solid #CFDBE9; }
    .destiny-sidebar p { margin:0; font-size:.7rem; letter-spacing:.15em;
      color:#2563AB; font-weight:700; }
    .destiny-sidebar strong { display:block; margin-top:7px;
      color:#1B365D; font-size:1.15rem; letter-spacing:-.02em; }
    .destiny-hero { position:relative; overflow:hidden; background:#1B365D;
      border-radius:18px; padding:34px 38px; margin:0 0 24px; color:white;
      border:1px solid #294971; box-shadow:0 8px 28px #1B365D12; }
    .destiny-hero:after { content:""; position:absolute; right:-70px; top:-130px;
      width:370px; height:370px; border:52px solid #345984;
      border-radius:50%; opacity:.35; pointer-events:none; }
    .destiny-hero .eyebrow { position:relative; z-index:1; color:#D7E7FA;
      font-size:.7rem; font-weight:700; letter-spacing:.17em; margin:0 0 12px; }
    .destiny-hero h1 { position:relative; z-index:1; color:#FFFFFF !important;
      font-size:clamp(1.8rem,4vw,2.7rem); font-weight:650; line-height:1.15;
      letter-spacing:-.035em; padding:0; margin:0 0 12px; }
    .destiny-hero .intro { position:relative; z-index:1; color:#E0E9F5;
      max-width:680px; font-size:1rem; line-height:1.65; margin:0; }
    .destiny-hero .hero-note { position:relative; z-index:1; display:inline-block;
      margin-top:22px; padding-top:14px; border-top:1px solid #597391;
      color:#C8D9EE; font-size:.75rem; letter-spacing:.035em; }
    [data-testid="stMetric"] { background:#FFFFFF; border:1px solid #DDE5EE;
      border-top:3px solid #2563AB; border-radius:14px; padding:20px 22px;
      min-height:128px; box-shadow:0 3px 12px #1B365D05; }
    [data-testid="stMetricLabel"] { color:#53667D; font-size:.8rem; }
    [data-testid="stMetricValue"] { color:#1B365D; font-weight:650; }
    [data-testid="stDataFrame"] { border:1px solid #DDE5EE;
      border-radius:12px; overflow:hidden; }
    [data-testid="stExpander"] { background:#FFFFFF; border:1px solid #DDE5EE;
      border-radius:12px; }
    .stButton>button, .stFormSubmitButton>button {
      background:#1B365D; color:#FFFFFF; border:1px solid #1B365D;
      border-radius:9px; font-weight:600; min-height:42px; }
    .stButton>button:hover, .stFormSubmitButton>button:hover {
      background:#274C79; color:#FFFFFF; border-color:#274C79; }
    .stButton>button:disabled { background:#E9EEF5; color:#65758A; border-color:#DDE5EE; }
    .stDownloadButton>button { background:#FFFFFF; color:#1B365D;
      border:1px solid #BACBE0; border-radius:9px; font-weight:600; }
    .stDownloadButton>button:hover { background:#EDF3FB; color:#1B365D; border-color:#2563AB; }
    button:focus-visible, input:focus-visible { outline:3px solid #80ACDF !important;
      outline-offset:2px; }
    .destiny-section { margin:26px 0 5px; color:#1B365D;
      font-size:1.25rem; font-weight:650; letter-spacing:-.02em; }
    .destiny-footer { margin-top:30px; border-top:1px solid #DDE5EE;
      padding-top:18px; color:#5A6C83; font-size:.75rem; }
    @media(max-width:640px) {
      .destiny-hero { padding:26px 22px; border-radius:12px; }
      [data-testid="stMetric"] { padding:16px; min-height:110px; }
    }
    </style>""", unsafe_allow_html=True)
    st.markdown("""<section class="destiny-hero" aria-label="Destiny Benefits fund performance">
      <p class="eyebrow">DESTINY BENEFITS · RETIREMENT INSIGHTS</p>
      <h1>A clearer view of fund performance.</h1>
      <p class="intro">Compare your funds. Understand the difference.
      Bring clarity to your next investment review.</p>
      <span class="hero-note">ACTIVE FUNDS &nbsp; / &nbsp; INDEX BENCHMARKS &nbsp; / &nbsp; INFORMED DECISIONS</span>
    </section>""", unsafe_allow_html=True)
    if "funds" not in st.session_state:
        config = Path(__file__).with_name("funds.json")
        try:
            st.session_state.funds = normalize(json.loads(config.read_text()) if config.exists() else SEED)
        except (ValueError, OSError, TypeError) as exc:
            st.error(f"Cannot load funds.json: {exc}")
            st.stop()
        st.session_state.editor_version = 0

    with st.expander("Manage fund database / enter stated returns"):
        st.caption("Enter 8.5 for 8.5%. Use fund total returns after MER, in CAD, with distributions reinvested. 3Y/5Y must be annualized. All returns on a row share one reporting date. Add or paste 100+ rows.")
        upload = st.file_uploader("Import fund database (JSON)", type="json")
        if st.button("Load uploaded JSON", disabled=upload is None):
            try:
                st.session_state.funds = normalize(json.loads(upload.getvalue()))
                st.session_state.editor_version += 1
                st.rerun()
            except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
                st.error(f"Import rejected: {exc}")
        source = pd.DataFrame(st.session_state.funds, columns=FIELDS)
        source["as_of"] = pd.to_datetime(source["as_of"])
        for key in ("mer", *HORIZONS):
            source[key] = pd.to_numeric(source[key], errors="coerce").astype(float)
        with st.form("fund_editor"):
            edited = st.data_editor(source, num_rows="dynamic", hide_index=True, width="stretch",
                key=f"editor_{st.session_state.editor_version}",
                column_config={"as_of": st.column_config.DateColumn("Reporting date", format="YYYY-MM-DD"),
                               "mer": st.column_config.NumberColumn("MER (%)", min_value=0, max_value=100, format="%.2f"),
                               **{h: st.column_config.NumberColumn(f"{h} (%)", min_value=-100, format="%.4f") for h in HORIZONS}})
            save = st.form_submit_button("Apply fund changes")
        if save:
            try:
                st.session_state.funds = normalize(edited.to_dict("records"))
                st.session_state.editor_version += 1
                st.rerun()
            except (ValueError, TypeError, OverflowError) as exc:
                st.error(f"Changes rejected: {exc}")
        st.download_button("Export funds.json", json.dumps(st.session_state.funds, indent=2, allow_nan=False),
                           file_name="funds.json", mime="application/json")
        st.info("Applied changes last for this session. Export JSON to keep them; import it next time or add funds.json beside app.py in your private repository. Cloud local files are not durable storage.")

    with st.sidebar:
        st.markdown('<div class="destiny-sidebar"><p>RETIREMENT INSIGHTS</p><strong>Your fund workspace</strong></div>', unsafe_allow_html=True)
        st.header("Refine your view")
        classes = st.multiselect("Asset Class", sorted({f["asset_class"] for f in st.session_state.funds}))
        statuses = st.multiselect("Strategic Action Status", [HOLD, REPLACE, PENDING])
        search = st.text_input("Search Fund Code", placeholder="e.g. RBF678").strip()
        refresh = st.button("Refresh benchmarks")
        st.caption("Empty filters show all funds. Automatic refresh every 15 minutes while open; completed daily prices only.")
    if refresh:
        fetch_history.clear()

    @st.fragment(run_every="15m")
    def dashboard():
        funds = st.session_state.funds
        today = datetime.now(timezone.utc).date()
        oldest = min([pd.Timestamp(f["as_of"]).date() for f in funds if f["as_of"]] or [today])
        start = (pd.Timestamp(oldest) - pd.DateOffset(years=5) - pd.Timedelta(days=10)).date().isoformat()
        histories, errors = {}, {}
        tickers = sorted({f["benchmark"] for f in funds})
        with st.spinner("Updating benchmark history…"):
            # Background workers perform network I/O only; Streamlit stays on main thread.
            with ThreadPoolExecutor(max_workers=min(4, len(tickers))) as pool:
                jobs = {pool.submit(fetch_history, t, start, today.isoformat()): t for t in tickers}
                for job in as_completed(jobs):
                    ticker = jobs[job]
                    try:
                        histories[ticker] = job.result()
                    except Exception as exc:
                        errors[ticker] = f"Benchmark unavailable ({type(exc).__name__}). Verify ticker or refresh later."
        grid = build_grid(funds, histories, errors)
        a, b, c, d = st.columns(4)
        a.metric("Total funds tracked", len(grid))
        b.metric("Positive alpha · 3Y", int((grid["Action"] == HOLD).sum()))
        c.metric("Negative / zero alpha · 3Y", int((grid["Action"] == REPLACE).sum()))
        d.metric("Awaiting comparable data", int((grid["Action"] == PENDING).sum()))
        if errors:
            st.warning("Some benchmarks are unavailable. Affected rows remain unclassified; refresh to retry.")
        visible = grid.copy()
        if classes:
            visible = visible[visible["Asset Class"].isin(classes)]
        if statuses:
            visible = visible[visible["Action"].isin(statuses)]
        if search:
            visible = visible[visible["Fund Code"].str.contains(search, case=False, regex=False)]
        st.markdown('<div class="destiny-section">Your fund comparison</div>', unsafe_allow_html=True)
        st.caption(f"Showing {len(visible)} of {len(grid)} funds · cards summarize the entire database · alpha in percentage points")
        leading = ["Fund Code", "Fund Name", "Action", "Alpha 3Y (pp)", "Asset Class", "MER (%)", "Benchmark", "Fund As Of", "ETF As Of"]
        visible = visible[leading + [col for col in visible if col not in leading]]
        formats = {col: st.column_config.NumberColumn(col, format="%.2f") for col in visible if "(%)" in col or "(pp)" in col}
        st.dataframe(visible, hide_index=True, width="stretch", height=550, column_config=formats)
        if visible.empty:
            st.info("No funds match these filters.")
        st.download_button("Download filtered results (CSV)", visible.to_csv(index=False),
                           "fund_comparison.csv", "text/csv")
        with st.expander("Live benchmark reference / methodology"):
            reference = []
            for ticker, (prices, fetched) in histories.items():
                values, as_of, note = benchmark_returns(prices, prices.index[-1])
                reference.append({"ETF": ticker, "As Of": as_of, **values, "Fetched UTC": fetched, "Notes": note})
            st.dataframe(pd.DataFrame(reference), hide_index=True, width="stretch")
            st.markdown("YTD and 1Y are cumulative; 3Y and 5Y use `(end / start) ** (1 / years) - 1`. ETF returns use Yahoo adjusted closing prices as a distribution-reinvested total-return proxy. Reporting-date comparisons use the prior market close on non-trading dates (maximum gap: four calendar days). Inspect both as-of columns; missing history is never replaced with zero.")
            st.markdown("Alpha = stated fund return − ETF return. Fund returns must already be net of MER; ETF prices already reflect fund expenses, so neither MER is subtracted again. HOLD means 3Y alpha > 0; REPLACE means ≤ 0, including ties. ‘Fee Drag’ is the requested screening label, not proof that fees caused the result. The supplied ETF mappings are retained; review whether each benchmark fits the fund mandate, currency and hedging policy.")
            st.caption("Yahoo data can be delayed, revised or rate-limited. Refreshes run only while the app session is active; there is no always-on scheduler. Restrict app access in your hosting settings.")
    dashboard()
    st.markdown('<div class="destiny-footer">DESTINY BENEFITS &nbsp; · &nbsp; Group retirement for real life.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
