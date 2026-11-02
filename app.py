"""Casey&Co portfolio workspace. streamlit run app.py"""
import copy
import html
import json
from datetime import date
import pandas as pd
import altair as alt
import streamlit as st
from fund_data import load_snapshot, refresh_snapshot, ORIGINAL, SUGGESTIONS
from portfolio import seed, validate, total, costs, exposures, underlying, overlap

st.set_page_config(page_title='Casey&Co | Portfolio Studio',page_icon='◒',layout='wide')
st.markdown('''<style>
.stApp{background:#f5f8f8;color:#153943} [data-testid="stHeader"]{background:#f5f8f8}
[data-testid="stAppViewBlockContainer"]{padding-top:2rem;max-width:1480px}
h1,h2,h3{color:#143c49;letter-spacing:-.035em} h1{font-weight:600}
[data-testid="stSidebar"]{background:#e9f1f1;border-right:1px solid #d4e3e3}
.brand{font-size:30px;font-weight:650;color:#153e49;letter-spacing:-1.5px}.brand span{color:#16858a}
.eyebrow{font-size:11px;letter-spacing:.16em;color:#26868b;font-weight:700;text-transform:uppercase}
.hero{padding:30px 34px;border-radius:20px;background:linear-gradient(115deg,#123e4b,#146e79);color:#fff;margin:20px 0 24px;position:relative;overflow:hidden}
.hero h1{font-size:36px;color:white;margin:3px 0 10px;padding:0}.hero p{color:#d5eaec;max-width:760px;margin:0;line-height:1.65}.hero .eyebrow{color:#a8e0dc;margin-bottom:9px}
[data-testid="stMetric"]{background:white;border:1px solid #dce7e7;border-radius:14px;padding:18px 20px;min-height:123px}
[data-testid="stMetricLabel"]{color:#54717a}[data-testid="stMetricValue"]{color:#126b74;font-size:30px}
[data-testid="stDataFrame"]{border:1px solid #dce7e7;border-radius:12px;overflow:hidden}
[data-testid="stExpander"]{background:white;border-radius:12px}
.insight{background:white;border:1px solid #dce7e7;border-left:4px solid #33939a;border-radius:10px;padding:17px 20px;margin-bottom:12px}.insight b{color:#174c59}.insight p{margin:5px 0 0;color:#526f77;font-size:14px}
.foot{border-top:1px solid #dce7e7;padding-top:18px;margin-top:30px;color:#637f85;font-size:12px}
button:focus-visible,input:focus-visible{outline:3px solid #188e9a!important;outline-offset:2px}
@media(max-width:700px){.hero{padding:23px}.hero h1{font-size:28px}}
</style>''',unsafe_allow_html=True)
if 'snapshot' not in st.session_state:st.session_state.snapshot=load_snapshot()
if 'portfolio' not in st.session_state:st.session_state.portfolio=seed()
if 'baseline' not in st.session_state:st.session_state.baseline=seed()
if 'watchlist' not in st.session_state:st.session_state.watchlist=[]
funds=st.session_state.snapshot['funds']
rows=st.session_state.portfolio

def money(n):return f'${n:,.0f}'
def pct(n):return 'Unavailable' if n is None else f'{n:.2f}%'
def insight(title,body):st.markdown(f'<div class="insight"><b>{html.escape(title)}</b><p>{html.escape(body)}</p></div>',unsafe_allow_html=True)
def show_table(df,height='auto'):
    config={c:st.column_config.NumberColumn(c,format='%.2f') for c in df.columns if '(%)' in c}
    config.update({c:st.column_config.NumberColumn(c,format='$%.2f') for c in df.columns if '(CAD)' in c})
    st.dataframe(df,hide_index=True,width='stretch',height=height,column_config=config)
def bars(frame,title):
    st.subheader(title)
    data=frame.copy()
    if len(data)>12:
        data=pd.concat([data.head(11),pd.DataFrame([{'Exposure':'Other exposures','Amount (CAD)':data.iloc[11:]['Amount (CAD)'].sum(),'Portfolio (%)':data.iloc[11:]['Portfolio (%)'].sum()}])],ignore_index=True)
    chart=alt.Chart(data).mark_bar(cornerRadiusEnd=5,color='#218b96').encode(
        x=alt.X('Portfolio (%):Q',title='Share of the entire portfolio (%)'),
        y=alt.Y('Exposure:N',sort='-x',title=None),
        tooltip=['Exposure',alt.Tooltip('Portfolio (%):Q',format='.2f'),alt.Tooltip('Amount (CAD):Q',format=',.2f')]
    ).properties(height=max(180,len(data)*30)).configure_view(strokeWidth=0)
    st.altair_chart(chart,width='stretch')

with st.sidebar:
    st.markdown('<div class="brand">casey<span>&</span>co</div><p class="eyebrow">Portfolio Studio</p>',unsafe_allow_html=True)
    page=st.radio('Workspace',['Overview','Exposure & overlap','My portfolio','Performance','Fund research','Compare a scenario'],label_visibility='collapsed')
    st.divider()
    st.caption('SAMPLE PORTFOLIO · CAD')
    st.write('Your $1,000-per-fund starting point.')
    st.caption('Amounts represent assumed current market values. They are not actual account balances.')
    with st.expander('Confirm three ticker matches',expanded=any(r['ticker'] is None and r['amount']>0 for r in rows)):
        st.caption('Confirm these suggestions before they contribute fund data.')
        confirmed={}
        for entered,suggested in SUGGESTIONS.items():
            current=next((r['ticker'] for r in rows if r['entered']==entered),None)
            confirmed[entered]=st.selectbox(entered,['Unresolved',suggested],index=1 if current==suggested else 0,key='map_'+entered)
            st.caption(funds[suggested]['name'])
        if st.button('Apply ticker matches',width='stretch'):
            for r in rows + st.session_state.baseline:
                if r['entered'] in confirmed:r['ticker']=None if confirmed[r['entered']]=='Unresolved' else confirmed[r['entered']]
            st.rerun()
    if st.button('Refresh issuer data',width='stretch'):
        with st.spinner('Reading issuer publications…'):
            try:
                snapshot,errors=refresh_snapshot(st.session_state.snapshot)
                st.session_state.snapshot=snapshot
                st.session_state.refresh_errors=errors
                st.rerun()
            except Exception as e:st.error('Refresh unavailable. Previous dated data retained. '+str(e))
    st.caption('Issuer snapshot retrieved '+st.session_state.snapshot['retrieved_at'][:10]+'. Effective dates appear with each dataset.')
    st.download_button('Export portfolio',json.dumps(rows,indent=2),'caseyco_portfolio.json','application/json',width='stretch')
    st.caption('Edits last for this session. Export to keep your portfolio.')

st.markdown('<div class="eyebrow">CASEY&CO / INVESTMENT INSIGHTS</div>',unsafe_allow_html=True)
st.markdown(f'<div class="hero"><div class="eyebrow">Your portfolio. A clearer perspective.</div><h1>{page}</h1><p>Understand what you own, where your exposure sits, and how your funds have performed.</p></div>',unsafe_allow_html=True)
base=total(rows); held=[r for r in rows if r['amount']>0];resolved=sum(r['amount'] for r in held if r['ticker'] in funds)
unknown=base-resolved;cost=costs(rows,funds)
if st.session_state.get('refresh_errors'):st.warning('Some fund refreshes failed; previous snapshots retained: '+', '.join(st.session_state.refresh_errors))
if unknown:st.warning(f'{money(unknown)} ({unknown/base:.1%}) has unresolved tickers. Confirm the suggested matches in the sidebar. That amount remains visible in exposure totals; its fees, returns, and holdings are unavailable.')
if base==0 and page not in ['My portfolio','Compare a scenario']:
    st.info('Add an amount to at least one fund in My portfolio.');st.stop()

if page=='Overview':
    a,b,c,d=st.columns(4)
    a.metric('Assumed portfolio value',money(base));b.metric('Funds held',len(held))
    c.metric('Fund identity coverage',f'{resolved/base:.1%}')
    d.metric('Weighted MER · known funds',pct(cost['mer']))
    st.caption(f"MER coverage: {cost['coverage']:.1%} of portfolio value. Estimated annual fund expenses on covered holdings: ${cost['annual']:,.2f}. Underlying ETF MERs are not added again.")
    st.subheader('Your executive summary')
    countries=exposures(rows,funds,'Country');sectors=exposures(rows,funds,'Sector');stocks=underlying(rows,funds)
    real=countries[~countries.Exposure.str.contains('Unresolved|unclassified|Rounding|Cash',case=False)]
    if not real.empty:
        leader=real.iloc[0];insight('Where your exposure is largest',f"{leader['Exposure']} represents {leader['Portfolio (%)']:.1f}% of the full portfolio, using the available issuer data.")
    pairs=overlap(rows,funds)
    if not pairs.empty and pairs.iloc[0]['Overlap (%)']>0:
        p=pairs.iloc[0];insight('Different funds can hold the same securities',f"{p['Fund A']} and {p['Fund B']} have {p['Overlap (%)']:.1f}% measured security overlap. Review whether that repeated exposure is intentional.")
    if not stocks.empty:
        s=stocks.iloc[0];insight('Your largest identified underlying security',f"{s['Security']} accounts for {s['Portfolio (%)']:.2f}% of the portfolio, held through {s['Fund count']} funds. Separate share classes remain separate securities.")
    left,right=st.columns(2)
    with left:bars(countries,'Where you invest')
    with right:bars(sectors,'Sector exposure')
    st.caption('Charts use the entire portfolio as their denominator. Published breakdowns are preferred; holdings-derived breakdowns fill gaps. Dates may differ. Geography is issuer location/risk classification, not company revenue exposure.')
    st.subheader('Largest underlying securities')
    show_table(stocks.head(10).drop(columns=['ISIN']))
    st.caption(f"Identified positive securities represent {stocks['Portfolio (%)'].sum():.1f}% of the full portfolio. This coverage includes any identified bond securities, and excludes unresolved tickers, cash, derivatives, and unclassified positions.")
    st.caption('Positive identified securities only; cash, derivatives, unresolved ETF wrappers, and unclassified positions are excluded from this ranking. It is not a complete measure of company-level economic risk.')

elif page=='Exposure & overlap':
    group=st.selectbox('Explore exposure',['Sector','Country','Asset class'])
    frame=exposures(rows,funds,group);bars(frame,group+' breakdown');show_table(frame)
    st.caption('Signed published weights are retained. Rounding and unclassified residuals remain visible; negative derivative or residual exposures can occur. Sector is available; more detailed industry classifications are not yet supplied.')
    st.subheader('Fund overlap')
    st.caption('For each pair, sum the smaller weight in each shared identified security. This is an exposure comparison, not a fee or a percentage to add across pairs. Mixed snapshot dates can affect results.')
    show_table(overlap(rows,funds).head(25))
    st.subheader('Follow the underlying holdings')
    stocks=underlying(rows,funds)
    search=st.text_input('Search a security, sector, or country')
    if search:stocks=stocks[stocks[['Security','Sector','Country','Held through']].apply(lambda col:col.str.contains(search,case=False,regex=False)).any(axis=1)]
    show_table(stocks,height=440)
    st.download_button('Download underlying exposure CSV',stocks.to_csv(index=False),'underlying_exposure.csv','text/csv')

elif page=='My portfolio':
    st.subheader('Build your portfolio')
    st.caption('Edit current dollar amounts. Set a holding to zero to remove it from calculations. Ticker matches are confirmed in the sidebar.')
    table=pd.DataFrame([{'Entered ticker':r['entered'],'Matched fund':r['ticker'] or 'Unresolved','Amount (CAD)':r['amount']} for r in rows])
    with st.form('amounts'):
        edited=st.data_editor(table,hide_index=True,width='stretch',disabled=['Entered ticker','Matched fund'],column_config={'Amount (CAD)':st.column_config.NumberColumn(min_value=0.,format='$%.2f')})
        if st.form_submit_button('Update portfolio'):
            try:
                st.session_state.portfolio=validate([dict(r,amount=float(edited.iloc[i]['Amount (CAD)'])) for i,r in enumerate(rows)],funds);st.rerun()
            except (ValueError,TypeError) as e:st.error(str(e))
    show_table(pd.DataFrame([{'Fund':r['ticker'] or r['entered'],'Portfolio (%)':r['amount']/base*100 if base else 0,'Amount (CAD)':r['amount']} for r in rows]))
    with st.expander('Import an exported portfolio'):
        uploaded=st.file_uploader('Portfolio JSON',type=['json'])
        if st.button('Import portfolio',disabled=uploaded is None):
            try:st.session_state.portfolio=validate(json.loads(uploaded.getvalue()),funds);st.rerun()
            except (ValueError,KeyError,TypeError) as e:st.error(str(e))
    st.subheader('Watchlist')
    st.session_state.watchlist=st.multiselect('Funds to research without adding portfolio exposure',list(funds),default=st.session_state.watchlist,format_func=lambda t:t+' · '+funds[t]['name'])
    st.caption('Watchlist choices last for this session and are excluded from portfolio calculations.')

elif page=='Performance':
    st.subheader('Published fund performance')
    st.caption('Issuer NAV total returns in CAD, after fund expenses and with distributions reinvested. YTD and 1Y are cumulative; 3Y/5Y are annualized. Since inception is annualized for these funds and spans different start dates.')
    data=[]
    for r in rows:
        f=funds.get(r['ticker'])
        data.append({'Ticker':r['ticker'] or r['entered'],'Fund name':f['name'] if f else 'Unresolved ticker',
                     **{('Since inception' if h=='SI' else h)+' (%)':f['returns'][h] if f else None for h in ['YTD','1Y','3Y','5Y','SI']},
                     'Performance as of':f['performance_as_of'] if f else None,'MER (%)':f['mer'] if f else None,'Inception':f['inception'] if f else None})
    show_table(pd.DataFrame(data),height=560)
    st.download_button('Download performance CSV',pd.DataFrame(data).to_csv(index=False),'fund_performance.csv','text/csv')
    st.info('These are fund returns, not your personal portfolio return. The $1,000 entries have no purchase dates or transaction history. A portfolio return or historical growth chart is not inferred from them.')
    horizon=st.selectbox('Compare a common published period',['3Y','5Y','1Y','YTD'])
    chartdata=pd.DataFrame([{'Fund':x['Ticker'],'Return (%)':x[horizon+' (%)']} for x in data]).dropna()
    st.altair_chart(alt.Chart(chartdata).mark_bar(color='#218b96',cornerRadiusEnd=4).encode(x=alt.X('Return (%):Q',title=horizon+' return (%)'),y=alt.Y('Fund:N',sort='-x'),tooltip=['Fund',alt.Tooltip('Return (%):Q',format='.2f')]).properties(height=400),width='stretch')
    st.caption('Different mandates and risks make this a descriptive comparison, not a ranking of suitability. Missing history stays blank.')

elif page=='Fund research':
    ticker=st.selectbox('Choose a fund',list(funds),format_func=lambda t:t+' · '+funds[t]['name'])
    f=funds[ticker];st.subheader(f['name']);st.write(f['objective'])
    a,b,c=st.columns(3);a.metric('Published MER',pct(f['mer']));b.metric('Inception',f['inception']);c.metric('5Y annualized return',pct(f['returns']['5Y']))
    st.caption('Returns as of '+f['performance_as_of']+' · CAD. MER is the published snapshot figure; no second layer of underlying MER is added.')
    st.link_button('Open official fund page ↗',f['url'])
    st.caption('The official page contains the governing fund documents, benchmark, hedging policy, distribution history, and additional risks.')
    st.subheader('Top 10 identified underlying securities')
    one=underlying([dict(ticker=ticker,amount=1000.,entered=ticker)],funds)
    show_table(one.head(10).rename(columns={'Portfolio (%)':'Fund (%)'}).drop(columns=['Amount (CAD)','Held through','Fund count','ISIN']))
    st.caption(f"{f['holdings_basis']} · holdings as of {f['holdings_as_of']}. Separate share classes shown separately.")
    l,r=st.columns(2)
    with l:bars(exposures([dict(ticker=ticker,amount=1000.)],funds,'Sector'),'Sectors')
    with r:bars(exposures([dict(ticker=ticker,amount=1000.)],funds,'Country'),'Countries')

elif page=='Compare a scenario':
    st.subheader('What changes if you adjust the mix?')
    st.caption('Your current portfolio stays unchanged while you explore a proposed allocation.')
    if st.button('Use current portfolio as comparison baseline'):
        st.session_state.baseline=copy.deepcopy(rows);st.rerun()
    baseline=st.session_state.baseline
    proposal=st.data_editor(pd.DataFrame([{'Ticker':r['ticker'] or r['entered'],'Amount (CAD)':r['amount']} for r in rows]),disabled=['Ticker'],hide_index=True,width='stretch',key='scenario_editor',column_config={'Amount (CAD)':st.column_config.NumberColumn(min_value=0.,format='$%.2f')})
    try:
        scenario=validate([dict(r,amount=float(proposal.iloc[i]['Amount (CAD)'])) for i,r in enumerate(rows)],funds)
        if total(scenario)==0:st.info('Enter at least one positive amount.');st.stop()
        a,b=st.columns(2);a.metric('Baseline value',money(total(baseline)));b.metric('Proposed value',money(total(scenario)))
        group=st.selectbox('Compare exposure',['Country','Sector','Asset class'])
        left=exposures(baseline,funds,group)[['Exposure','Portfolio (%)']].rename(columns={'Portfolio (%)':'Baseline (%)'})
        right=exposures(scenario,funds,group)[['Exposure','Portfolio (%)']].rename(columns={'Portfolio (%)':'Proposed (%)'})
        changes=left.merge(right,on='Exposure',how='outer').fillna(0);changes['Change (pp)']=changes['Proposed (%)']-changes['Baseline (%)']
        show_table(changes.sort_values('Proposed (%)',ascending=False))
        sc=costs(scenario,funds)
        st.write(f"Proposed weighted MER on known funds: {pct(sc['mer'])}. Fee coverage: {sc['coverage']:.1%}. Estimated annual fund expenses on covered holdings: ${sc['annual']:,.2f}.")
        if st.button('Apply proposed allocation to My portfolio'):
            st.session_state.portfolio=scenario;st.rerun()
    except (ValueError,TypeError) as e:st.error(str(e))

with st.expander('Sources, effective dates & calculation notes'):
    st.write('Source: BlackRock Canada/iShares product catalog, fund pages, and downloadable holdings. This is a dated issuer snapshot, not a live quote feed. Refresh retrieves new data for this session and retains prior fund data if a refresh fails.')
    show_table(pd.DataFrame([{'Fund':t,'Returns as of':f['performance_as_of'],'Holdings as of':f['holdings_as_of'],'Retrieved UTC':f['retrieved_at'],'Sector date':f['breakdown_dates'].get('Sector'),'Country date':f['breakdown_dates'].get('Country'),'Official source':f['url']} for t,f in funds.items()]))
    st.write('Exposure dollars = assumed current holding value × published fund exposure weight. Portfolio percentage = exposure dollars ÷ total entered portfolio value. Underlying securities are consolidated by ISIN, not company name; different share classes remain separate. Geography is not sales geography; quoted/reporting currency is not underlying currency risk. Detailed currency exposure requires additional data and is not inferred.')
    st.write('MER cost estimate = current amount × published MER. Weighted MER is weighted only across holdings with available MERs, and coverage is stated. MERs are not added across ETF layers. Trading costs, investor commissions, spreads, foreign exchange costs, and applicable taxes are outside this estimate. Snapshot data may have different effective dates.')
    st.caption('This workspace describes the selected portfolio. It does not issue automatic buy/sell instructions or predict future returns. The original mutual-fund comparison tool is retained in legacy_app.py.')
st.markdown('<div class="foot">casey&co · Portfolio Studio &nbsp; / &nbsp; Understand your investments. Make informed decisions.</div>',unsafe_allow_html=True)
