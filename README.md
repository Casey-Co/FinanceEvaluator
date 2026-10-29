# FinanceEvaluator

A Streamlit dashboard comparing active mutual fund total returns with passive ETF benchmarks.

## Deploy on Streamlit Community Cloud

1. Sign in at https://share.streamlit.io and connect your GitHub account.
2. Select **Create app**, choose **Casey-Co/FinanceEvaluator**, branch **main**, and entry point **app.py**. Choose Python **3.12** in Advanced settings, then deploy.
3. Before entering private data, open **App settings → Sharing** and select **Only specific people can view this app**.

**Repository visibility and app visibility are separate settings.** This repository was public when initialized. A public repository produces a public app by default. Make the repository private in GitHub if you want to keep its code/configuration private as well. Never commit confidential data or secrets to a public repository. There is no custom login in the Python script; private viewer authentication is handled by Streamlit Community Cloud.

## Run locally

Use Python 3.12:

```bash
python -m venv .venv
# Activate the environment for your operating system.
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Use the dashboard

- The database begins with RBF678, RBF3314, RBF611 and RBF639 and their specified MERs, asset classes and benchmark mappings.
- Open **Manage fund database / enter stated returns** to add, delete or paste rows. There is no hard-coded 100-row limit.
- Enter **8.5 for 8.5%**, not 0.085. Enter CAD total returns after fund expenses, with distributions reinvested. Three- and five-year fund returns must be annualized.
- Add one reporting date per row, shared by all returns on that row. The date must be yesterday or earlier in UTC.
- Apply changes. The app retrieves the matching ETF history and calculates alpha in percentage points.
- Filter by asset class, action status or fund code. Metric cards summarize the full database.
- Use **Export funds.json** to keep changes. Import the file next session.
- Download filtered comparisons as CSV.

Fund returns are deliberately blank initially because verified stated returns were not supplied. Missing returns or missing benchmark history are classified as **AWAITING DATA**, never as zero.

## Storage

The baseline fund configuration is embedded in `app.py`. An optional local `funds.json` beside the script overrides the baseline on startup. It contains a JSON array with the fields below:

```json
[
  {
    "code": "RBF678",
    "name": "RBC QUBE Canadian Equity",
    "asset_class": "Canadian Large Cap",
    "mer": 0.77,
    "benchmark": "XIC.TO",
    "as_of": null,
    "YTD": null,
    "1Y": null,
    "3Y": null,
    "5Y": null
  }
]
```

Applied edits are isolated to the current Streamlit session; they are not shared across users and do not write back to GitHub. Export JSON before leaving. Community Cloud's local filesystem is not durable storage. Local fund files and secrets are excluded by `.gitignore`.

## Returns and screening rules

- yfinance retrieves daily adjusted closes for each unique benchmark. Network requests run in a bounded worker pool; repeated ETF tickers share cached history.
- Downloads are cached for 15 minutes. The dashboard refreshes every 15 minutes while its session is active. It is not an always-on background job; sleeping apps do not refresh.
- Today is excluded from the daily history request to avoid partial daily prices.
- Adjusted prices are a distribution-reinvested total-return proxy sourced from Yahoo. Verify material figures against official fund/ETF publications.
- ETF return uses the fund's reporting date. On non-trading dates, the app uses the prior close and displays its actual date. Gaps over four calendar days are rejected.
- YTD uses the prior year-end close. One-year return is cumulative. Three- and five-year returns use CAGR: `(end / start) ** (1 / years) - 1`.
- Alpha = stated fund return minus ETF return. Do not subtract either MER again: input fund returns must already be net of MER, and ETF prices already reflect fund expenses.
- Three-year alpha **> 0** gives **HOLD (Outperforming)**. Three-year alpha **≤ 0**, including ties, gives **REPLACE (Fee Drag)**.
- “Fee Drag” is the requested screening label, not evidence that fees caused underperformance or an automatic recommendation to trade.
- The requested benchmark mappings are retained. Check mandate, currency, hedging and asset mix before relying on comparisons.
- Data can be delayed, revised, incomplete or rate-limited. Errors leave affected comparisons unavailable; refresh to retry.

## Validation

The original implementation passed offline checks of return calculations, missing data, date gaps, duplicate validation, zero-alpha ties, a 125-fund database, Streamlit rendering and fund-code search. Live downloads succeeded for XIC.TO, XMD.TO, VFV.TO and ZEA.TO in the build environment. These checks do not guarantee future Yahoo availability.

## Official references

- Deployment: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app
- Private sharing: https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app
- yfinance: https://ranaroussi.github.io/yfinance/
