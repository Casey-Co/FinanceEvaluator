"""Read issuer publications; snapshots work offline and refreshes never invent data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import gzip
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from lxml import html

CATALOG_URL = 'https://www.blackrock.com/ca/investors/en/products/product-list'
TICKERS = (
    'XSP XQQ XVLU XUS XMTM CLU.C XEQT XWD CEW GGRO XDNA XEF CIF XDU '
    'XFN XDV XCV FIE XST CUD XMW XEC.U XEI XSEM CWO XEC XEG XUSR'
).split()
ACWV_URL = 'https://www.ishares.com/us/products/239605/ishares-msci-global-min-vol-factor-etf'
ORIGINAL = 'CSP XQQ XULU XUS XMTM CLUC XEQT XWD CEW GGRO XDNA XEF CIF XDU'.split()
SUGGESTIONS = {'CSP':'XSP', 'XULU':'XVLU', 'CLUC':'CLU.C'}
SNAPSHOT = Path(__file__).with_name('issuer_snapshot.json.gz')

def download(url):
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=30) as r:
        return r.read().decode('utf-8-sig')

def text(node):
    return ' '.join(node.text_content().split())

def number(value):
    try:
        return float(str(value).replace(',',''))
    except (ValueError, TypeError):
        return None

def catalog_from_html(raw):
    output = {}
    for tr in html.fromstring(raw).xpath('//tr'):
        cells = tr.xpath('./th|./td')
        vals = [text(c) for c in cells]
        if len(vals) != 11 or vals[0] not in TICKERS:
            continue
        output[vals[0]] = dict(ticker=vals[0], name=vals[1],
            returns=dict(zip(['YTD','1Y','3Y','5Y','SI'],map(number,vals[2:7]))),
            performance_as_of=vals[7], mer=number(vals[8]), inception=vals[9],
            url='https://www.blackrock.com'+cells[0].xpath('.//a/@href')[0],
            returns_currency='USD' if vals[0].endswith('.U') else 'CAD')
    if len(output) != len(TICKERS):
        missing = ', '.join(sorted(set(TICKERS) - output.keys()))
        raise ValueError(f'Issuer catalog is missing {missing}; keeping previous snapshot.')
    return output

def dated(element):
    if element is None:
        return None
    selected=element.xpath('.//div[contains(@class,"component-date-list")]//option[@selected]')
    if selected:
        return text(selected[0])
    nodes=element.xpath('.//div[contains(@class,"component-date-list")]')
    return text(nodes[0]).replace('as of','').strip() if nodes else None

def parse_holdings(raw, *, sector_column=True):
    output=[]
    for row in json.loads(raw).get('aaData',[]):
        if len(row) < 8:
            continue
        weight_index = 3 if sector_column else 2
        if not isinstance(row[weight_index], dict):
            continue
        weight = number(row[weight_index].get('raw'))
        if weight is None:
            continue
        output.append(dict(ticker=row[0], name=row[1], weight=weight,
                           sector=row[2] if sector_column else 'Unclassified sector',
                           isin=row[weight_index+2], country=row[weight_index+3],
                           exchange=row[weight_index+4]))
    return output

def parse_profile(fund, raw, loader=download):
    p=html.fromstring(raw)
    result=dict(fund)
    # The issuer embeds its published exposure breakdowns as JSON-like arrays.
    result['breakdowns']={}
    result['breakdown_dates']={}
    for code,label in [('tabsSector','Sector'),('subTabsCountries','Country'),('tabsAssetclass','Asset class')]:
        match=re.search(r'var '+code+r'DataTable\s*=\s*(\[.*?\]);',raw,re.S)
        if match:
            clean=re.sub(r',\s*([}\]])',r'\1',match.group(1))
            result['breakdowns'][label]={v['name']:float(v['value']) for v in json.loads(clean)}
            parent=p.xpath('//*[@id="'+code+'"]')
            result['breakdown_dates'][label]=dated(parent[0]) if parent else None
    objective=p.xpath('//*[self::h2 or self::h3][contains(translate(normalize-space(.),"abcdefghijklmnopqrstuvwxyz","ABCDEFGHIJKLMNOPQRSTUVWXYZ"),"INVESTMENT OBJECTIVE")]/following-sibling::*[1]')
    result['objective']=text(objective[0]) if objective else ''
    for cls,key in [('col-benchmark','benchmark'),('col-assetClass','asset_class')]:
        nodes=p.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," '+cls+' ")]//*[contains(@class,"data")]')
        if nodes:result[key]=text(nodes[-1])
    result['hedging']='CAD-hedged' if 'Hedged' in fund['name'] else 'See fund strategy'
    result['holdings']=[]
    look=p.xpath('//*[@id="allLookthrusTab"]')
    direct=p.xpath('//*[@id="allHoldingsTab"]')
    element=(look or direct or [None])[0]
    if element is not None:
        endpoint='https://www.blackrock.com'+element.get('data-ajaxuri')
        columns = [text(th) for th in element.xpath('.//thead//th')]
        result['holdings'] = parse_holdings(loader(endpoint), sector_column='Sector' in columns)
        result['holdings_url']=endpoint
        result['holdings_as_of']=dated(element)
        result['holdings_basis']='Aggregate underlying holdings' if look else 'Direct holdings'
    if not result['holdings']:
        raise ValueError(f"No usable holdings for {fund['ticker']}")
    if fund['ticker'] == 'FIE':
        classes = {'CPD': 'Preferred shares', 'XCB': 'Fixed income',
                   'CAD': 'Cash', 'USD': 'Cash'}
        asset_mix = {}
        for holding in result['holdings']:
            label = classes.get(holding['ticker'], 'Equity')
            asset_mix[label] = asset_mix.get(label, 0) + holding['weight']
        result['breakdowns']['Asset class'] = asset_mix
        result['breakdown_dates']['Asset class'] = result['holdings_as_of']
    result['retrieved_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    return result

def holding_identity(ticker, name, country):
    return tuple(value.strip().casefold() for value in (ticker, name, country))


def parse_acwv(raw, reference_holdings, loader=download):
    """Read US issuer data and use XMW holdings to resolve shared security IDs."""
    page = html.fromstring(raw)
    components = [json.loads(value) for value in page.xpath('//@componentprops')]
    performance = next(c for c in components if c.get('componentId') == 'performance'
                       and 'selectedView' in c)
    tables = performance['containersByNameMap']['returns']['subContainersByNameMap']
    average = tables['average']['dataPointsByNameMap']
    cumulative = tables['cumulative']['dataPointsByNameMap']
    avg_row = average['returnTypes']['formattedValue'].index('Total Return (%)')
    cum_row = cumulative['returnTypes']['formattedValue'].index('Total Return (%)')
    as_of = average['asOfDate']['formattedValue']
    returns = {
        period: number(average[field]['formattedValue'][avg_row])
        for period, field in [('1Y', 'oneYearAnnualized'), ('3Y', 'threeYearAnnualized'),
                              ('5Y', 'fiveYearAnnualized'), ('SI', 'sinceInceptionAnnualized')]
    }
    returns['YTD'] = (number(cumulative['yearToDate']['formattedValue'][cum_row])
                      if cumulative['asOfDate']['formattedValue'] == as_of else None)
    facts = next(c['dataPoints'] for c in components if c.get('componentId') == 'keyFundFacts')
    fee = next(c['feeDataPoints']['expr']['formattedValue'] for c in components
               if c.get('componentId') == 'feeTable')
    objective = next(c['content']['fund-description'][0]['text'] for c in components
                     if 'fund-description' in c.get('content', {}))
    endpoint = urljoin(ACWV_URL, page.xpath('//a[@data-id="holdings-csv-link"]/@href')[0])
    lines = loader(endpoint).splitlines()
    rows = list(csv.reader(lines))
    holdings_as_of = next(row[1] for row in rows if row and row[0] == 'Fund Holdings as of')
    start = next(i for i, row in enumerate(rows) if row and row[0] == 'Ticker')
    ids = {}
    for h in reference_holdings:
        if h['isin'] not in ('', '-'):
            key = holding_identity(h['ticker'], h['name'], h['country'])
            ids.setdefault(key, set()).add(h['isin'])
    holdings = []
    asset_mix = {}
    for row in csv.DictReader(lines[start:]):
        weight = number(row.get('Weight (%)'))
        if weight is None:
            continue
        ticker, name, country = row['Ticker'], row['Name'], row['Location']
        matches = ids.get(holding_identity(ticker, name, country), set())
        holdings.append(dict(ticker=ticker, name=name, country=country,
                             sector=row['Sector'], exchange=row['Exchange'], weight=weight,
                             isin=next(iter(matches)) if len(matches) == 1 else '',
                             asset_class=row['Asset Class']))
        label = row['Asset Class']
        asset_mix[label] = asset_mix.get(label, 0) + weight
    if not holdings:
        raise ValueError('No usable holdings for ACWV')
    return dict(ticker='ACWV', name='iShares MSCI Global Min Vol Factor ETF', objective=objective,
                returns=returns, performance_as_of=as_of, returns_currency='USD',
                mer=number(fee.rstrip('%')), inception=facts['launchDate']['formattedValue'],
                asset_class=facts['assetClass']['formattedValue'], url=ACWV_URL,
                holdings=holdings, holdings_url=endpoint, holdings_as_of=holdings_as_of,
                holdings_basis='Direct holdings; shared security IDs matched to issuer XMW holdings',
                breakdowns={'Asset class': asset_mix}, breakdown_dates={'Asset class': holdings_as_of},
                retrieved_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))


def refresh_snapshot(previous):
    catalog=catalog_from_html(download(CATALOG_URL))
    errors={}
    def get(t):
        try:return t,parse_profile(catalog[t],download(catalog[t]['url'])),None
        except Exception as e:return t,previous['funds'].get(t),f'{type(e).__name__}: {e}'
    funds={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for ticker,data,error in pool.map(get,TICKERS):
            if data:funds[ticker]=data
            if error:errors[ticker]=error
    try:
        funds['ACWV'] = parse_acwv(download(ACWV_URL), funds['XMW']['holdings'])
    except Exception as error:
        if 'ACWV' in previous['funds']:
            funds['ACWV'] = previous['funds']['ACWV']
        errors['ACWV'] = f'{type(error).__name__}: {error}'
    return dict(funds=funds, retrieved_at=datetime.now(timezone.utc).isoformat(timespec='seconds')), errors

def load_snapshot():
    return json.loads(gzip.decompress(SNAPSHOT.read_bytes()))
