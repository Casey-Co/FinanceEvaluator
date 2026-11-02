# Casey&Co Portfolio Studio

A portfolio-first Streamlit workspace for Canadian ETFs. The hypothetical starting portfolio holds $1,000 CAD of each of the user's 14 entries. Amounts are assumed current values, not actual account balances or purchase amounts.

## Open / deploy

The existing Streamlit Community Cloud app can continue using `Casey-Co/FinanceEvaluator`, `main`, `app.py`. Open https://share.streamlit.io/ to locate the deployed app. This repository does not contain its exact public app URL.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Included

- Casey&Co teal and blue theme.
- Executive summary, sector/country/asset-class exposures, underlying security rankings, and pairwise overlap.
- Dollar allocation editor, import/export, session watchlist, and proposed allocation comparisons.
- Official issuer YTD/1Y/3Y/5Y/since-inception returns, MER, inception dates, objectives, holdings and source links.
- Bundled issuer snapshot with holdings principally dated October 30, 2026 and performance dated September 30, 2026. Source-specific dates remain visible.
- Manual issuer refresh with per-fund fallback to prior data on failure. Refresh does not update GitHub or persist beyond the session.
- Original mutual-fund benchmark application preserved as `legacy_app.py` (`streamlit run legacy_app.py`).

## Tickers

The entered symbols CSP, XULU and CLUC are initially unresolved. Sidebar controls explicitly confirm suggested matches XSP, XVLU and CLU.C. Their $3,000 remains in the full portfolio denominator before confirmation. No silent ticker substitution occurs.

Supported researched funds: XSP, XQQ, XVLU, XUS, XMTM, CLU.C, XEQT, XWD, CEW, GGRO, XDNA, XEF, CIF and XDU. Further funds require verified catalog data; arbitrary unsupported tickers cannot be imported.

## Calculation and data boundaries

Exposure dollars equal current entered fund value times the issuer's published weight. Published breakdowns are preferred; detailed underlying holdings fill gaps. Unresolved amounts and rounding/unclassified residuals remain visible. Positions are not rescaled to make incomplete data look complete. Country means the issuer's geography classification, not revenue geography. Reporting currency is not currency risk exposure.

Underlying rankings consolidate identified positive securities by ISIN. Separate share classes remain separate. Cash, derivatives, unresolved ETF wrappers and unclassified positions are excluded; coverage is disclosed. Pairwise overlap sums minimum security weights and is descriptive rather than a trade recommendation. Weights/dates across holdings and breakdowns can differ. Sector-level classifications are available, not a complete industry taxonomy.

MER estimates use published top-level MERs without adding underlying ETF MERs again. Weighted MER covers only known MER values; coverage and annual dollar costs are disclosed. MER does not include every trading, investor, FX or tax cost.

Fund performance is NAV total return after expenses and with distributions reinvested. YTD/1Y are cumulative; 3Y/5Y and since inception are annualized for these funds. Missing history stays blank. No personal return or hypothetical historical portfolio backtest is inferred from current dollar balances.

The issuer's public pages/holdings endpoints can change. `fund_data.py` validates expected catalog rows and retains previous fund snapshots if refreshes fail. This is not a licensed real-time market feed or an unattended refresh service.

## Persistence and access

Changes are isolated to the current Streamlit session. Export your allocation before leaving; import it next session. Watchlist choices last for the session. The repo contains a hypothetical sample and issuer publications, not private account records. App viewer access is configured separately in Streamlit settings; this code does not add authentication.

## Verification

```bash
python -m unittest test_portfolio.py
```

Tests check conservation of portfolio value with unresolved entries, scale invariance, top-level fee treatment, underlying overlap, missing history, invalid inputs, ticker confirmation, all six screens, and recovery from a zero-value portfolio. Browser visual QA depends on the host preview environment.
