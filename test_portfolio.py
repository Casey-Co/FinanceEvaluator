import unittest
from streamlit.testing.v1 import AppTest
from fund_data import load_snapshot, SUGGESTIONS
from portfolio import seed, total, costs, exposures, underlying, overlap, validate

class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.funds=load_snapshot()['funds']
    def test_unconfirmed_money_stays_in_denominator(self):
        rows=seed()
        self.assertEqual(total(rows),14000)
        self.assertAlmostEqual(costs(rows,self.funds)['coverage'],11/14)
        for dim in ['Country','Sector','Asset class']:
            out=exposures(rows,self.funds,dim)
            self.assertAlmostEqual(out['Amount (CAD)'].sum(),14000,places=2)
            self.assertAlmostEqual(out.loc[out.Exposure=='Unresolved ticker','Portfolio (%)'].iloc[0],3000/14000*100)
    def test_scale_does_not_change_exposure_weights(self):
        rows=seed();scaled=[dict(r,amount=r['amount']*17) for r in rows]
        first=exposures(rows,self.funds,'Country').set_index('Exposure')
        second=exposures(scaled,self.funds,'Country').set_index('Exposure')
        self.assertTrue((abs(first['Portfolio (%)']-second['Portfolio (%)'])<1e-9).all())
    def test_fees_do_not_add_underlying_mer(self):
        rows=[dict(ticker='XEQT',entered='XEQT',amount=10000)]
        self.assertAlmostEqual(costs(rows,self.funds)['annual'],19)
    def test_underlying_overlap_and_no_wrappers(self):
        rows=[dict(ticker=t,entered=t,amount=1000) for t in ['XUS','XSP']]
        stocks=underlying(rows,self.funds)
        apple=stocks[stocks.ISIN=='US0378331005'].iloc[0]
        self.assertEqual(apple['Fund count'],2)
        self.assertNotIn('IVV',stocks.Security.values)
        self.assertGreater(overlap(rows,self.funds).iloc[0]['Overlap (%)'],90)
    def test_confirmed_snapshot_and_missing_history(self):
        rows=seed()
        for r in rows:r['ticker']=SUGGESTIONS.get(r['entered'],r['ticker'])
        self.assertEqual(costs(rows,self.funds)['coverage'],1)
        self.assertIsNone(self.funds['XDNA']['returns']['5Y'])
        self.assertTrue(all(f['holdings_as_of'] for f in self.funds.values()))
    def test_invalid_inputs(self):
        for value in [-1,float('nan'),float('inf')]:
            rows=seed();rows[0]['amount']=value
            with self.assertRaises(ValueError):validate(rows,self.funds)
        for rows in [[],{},[None]]:
            with self.assertRaises(ValueError):validate(rows,self.funds)
    def test_app_with_confirmed_sample_tickers(self):
        at=AppTest.from_file('app.py',default_timeout=30).run()
        self.assertFalse(at.exception)
        self.assertFalse(any('has unresolved tickers' in warning.value for warning in at.warning))
        self.assertTrue(all(row['ticker'] for row in at.session_state['portfolio']))
        self.assertEqual(at.metric[2].value,'100.0%')
        for page in ['Exposure & overlap','My portfolio','Performance','Fund research','Compare a scenario']:
            at.radio[0].set_value(page).run()
            self.assertFalse(at.exception,page)
        at.session_state['portfolio']=[dict(r,amount=0) for r in seed()]
        at.radio[0].set_value('My portfolio').run()
        self.assertFalse(at.exception)
        self.assertTrue(any(b.label=='Update portfolio' for b in at.button))

if __name__=='__main__':unittest.main()
