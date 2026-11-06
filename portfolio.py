"""Portfolio arithmetic: all amounts are CAD market values, not purchase costs."""
import math
from collections import defaultdict
import pandas as pd
from fund_data import ORIGINAL

def seed():
    return [dict(entered=t,ticker=t if t not in ['CSP','XULU','CLUC'] else None,amount=1000.) for t in ORIGINAL]

def validate(rows, funds):
    if not isinstance(rows,list) or not rows or not all(isinstance(r,dict) for r in rows):
        raise ValueError('Import a nonempty list of portfolio records.')
    seen=set(); clean=[]
    for r in rows:
        key=str(r['entered']).strip()
        if not key:raise ValueError('Each entry needs a ticker label.')
        if key in seen:raise ValueError('Duplicate portfolio entry: '+key)
        seen.add(key)
        amount=float(r['amount'])
        if not math.isfinite(amount) or amount<0:raise ValueError('Amounts must be finite and nonnegative.')
        ticker=r.get('ticker') or None
        if ticker and ticker not in funds:raise ValueError('Unsupported ticker: '+ticker)
        clean.append(dict(entered=key,ticker=ticker,amount=amount))
    return clean

def total(rows):return sum(r['amount'] for r in rows)

def is_security(h):
    return h['weight']>0 and (h['isin'] not in ['','-'] or h.get('asset_class') == 'Equity') and h['sector'] not in ['Cash and/or Derivatives','Cash','Other'] and not any(x in h['name'].upper() for x in ['ISHARES','ISHRS','ISHS '])

def security_key(h):return h['isin'] if h['isin'] not in ['','-'] else '|'.join([h['ticker'], h['exchange'], h['country']])

def exposures(rows,funds,dimension):
    values=defaultdict(float)
    for r in rows:
        amount=r['amount'];f=funds.get(r['ticker'])
        if not f:
            values['Unresolved ticker']+=amount;continue
        breakdown=f['breakdowns'].get(dimension)
        if not breakdown:
            breakdown=defaultdict(float)
            for h in f['holdings']:
                if dimension=='Asset class':
                    cat='Equity' if is_security(h) and f.get('asset_class')=='Equity' else 'Cash / derivatives / unclassified'
                else:
                    cat=h['sector'] if dimension=='Sector' else h['country']
                    if not is_security(h):cat='Cash / derivatives / unclassified'
                breakdown[cat]+=h['weight']
        mapped={'Equity (EQ)':'Equity','Fixed Income (FI)':'Fixed income'}
        for label,weight in breakdown.items():values[mapped.get(label,label)]+=amount*weight/100
        remainder=100-sum(breakdown.values())
        if abs(remainder)>0.001:values['Rounding / unclassified']+=amount*remainder/100
    base=total(rows)
    return pd.DataFrame([{'Exposure':k,'Amount (CAD)':v,'Portfolio (%)':v/base*100 if base else 0} for k,v in values.items()]).sort_values('Amount (CAD)',ascending=False)

def underlying(rows,funds):
    result={}
    for r in rows:
        f=funds.get(r['ticker'])
        if not f or not r['amount']:continue
        for h in f['holdings']:
            if not is_security(h):continue
            key=security_key(h)
            record=result.setdefault(key,dict(Security=h['name'],ISIN=h['isin'],Sector=h['sector'],Country=h['country'],amount=0.,via=set()))
            record['amount']+=r['amount']*h['weight']/100
            record['via'].add(r['ticker'])
    base=total(rows)
    records=[{'Security':v['Security'],'ISIN':v['ISIN'],'Sector':v['Sector'],'Country':v['Country'],
              'Amount (CAD)':v['amount'],'Portfolio (%)':v['amount']/base*100 if base else 0,
              'Held through':', '.join(sorted(v['via'])),'Fund count':len(v['via'])} for v in result.values()]
    return pd.DataFrame(records,columns=['Security','ISIN','Sector','Country','Amount (CAD)','Portfolio (%)','Held through','Fund count']).sort_values('Amount (CAD)',ascending=False)

def costs(rows,funds):
    base=total(rows);covered=0.;cost=0.
    for r in rows:
        f=funds.get(r['ticker'])
        if f and f.get('mer') is not None:
            covered+=r['amount'];cost+=r['amount']*f['mer']/100
    return dict(annual=cost,coverage=covered/base if base else 0,mer=cost/covered*100 if covered else None)

def overlap(rows,funds):
    # Sum of minimum security weights for each pair, on each fund's NAV basis.
    held=sorted({r['ticker'] for r in rows if r['amount']>0 and r['ticker'] in funds})
    parts={}
    for t in held:
        part=defaultdict(float)
        for h in funds[t]['holdings']:
            if is_security(h):part[security_key(h)]+=h['weight']
        parts[t]=part
    output=[]
    for i,a in enumerate(held):
        for b in held[i+1:]:
            common=parts[a].keys()&parts[b].keys()
            pct=sum(min(parts[a][k],parts[b][k]) for k in common)
            output.append({'Fund A':a,'Fund B':b,'Shared securities':len(common),'Overlap (%)':pct})
    return pd.DataFrame(output,columns=['Fund A','Fund B','Shared securities','Overlap (%)']).sort_values('Overlap (%)',ascending=False)
