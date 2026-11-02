"""Read issuer publications; snapshots work offline and refreshes never invent data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import gzip
import re
from urllib.request import Request, urlopen
from lxml import html

CATALOG_URL = 'https://www.blackrock.com/ca/investors/en/products/product-list'
TICKERS = 'XSP XQQ XVLU XUS XMTM CLU.C XEQT XWD CEW GGRO XDNA XEF CIF XDU'.split()
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
            returns_currency='CAD')
    if len(output) != len(TICKERS):
        raise ValueError('Issuer catalog did not return all 14 expected funds; keeping previous snapshot.')
    return output

def dated(element):
    if element is None:
        return None
    selected=element.xpath('.//div[contains(@class,"component-date-list")]//option[@selected]')
    if selected:
        return text(selected[0])
    nodes=element.xpath('.//div[contains(@class,"component-date-list")]')
    return text(nodes[0]).replace('as of','').strip() if nodes else None

def parse_holdings(raw):
    output=[]
    for row in json.loads(raw).get('aaData',[]):
        # Lookthrough and ordinary holdings have sector in column 3;
        # multiasset direct holdings omit that column.
        if len(row)<9 or not isinstance(row[2],str) or not isinstance(row[3],dict):
            continue
        weight=number(row[3].get('raw'))
        if weight is None:
            continue
        output.append(dict(ticker=row[0],name=row[1],sector=row[2],weight=weight,
                           isin=row[5],country=row[6],exchange=row[7]))
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
        result['holdings']=parse_holdings(loader(endpoint))
        result['holdings_url']=endpoint
        result['holdings_as_of']=dated(element)
        result['holdings_basis']='Aggregate underlying holdings' if look else 'Direct holdings'
    if not result['holdings']:
        raise ValueError(f"No usable holdings for {fund['ticker']}")
    result['retrieved_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    return result

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
    return dict(funds=funds, retrieved_at=datetime.now(timezone.utc).isoformat(timespec='seconds')), errors

def load_snapshot():
    return json.loads(gzip.decompress(SNAPSHOT.read_bytes()))
