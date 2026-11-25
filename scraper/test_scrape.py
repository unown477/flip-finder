"""Offline tests: python3 -m unittest scraper/test_scrape.py -v

Fixtures below mirror the real page markup captured from Pickles and Manheim on
25 Nov 2026 (trimmed). No network access is used.
"""
import importlib
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def pickles_card(n, stock, href, title, variant, km, wovr, loc, img):
    return f'''<main class="x" id="ps-ccg-grid-card-main-{stock}"><div>
<a id="ps-ccg-product-card-link-{n}" class="l" href="{href}"><h2 class="t">{title}</h2></a><h2 class="v">{variant}</h2>
<section class="loc" id="ps-cu-location-wrapper-{n}"><span>{loc}</span></section>
<span>{km}</span><span>4 cyl</span><span>{wovr}</span><span>Stock {stock}</span>
<input type="hidden" id="ps-hid-startdatetime-{n}" value="2026-11-30T02:00:00Z"/>
<input type="hidden" id="ps-hid-enddatetime-{n}" value="2026-12-01T02:00:00Z"/>
<input type="hidden" id="ps-hid-buymethod-{n}" value="Pickles Online"/>
<img alt="" src="{img}"/><pds-button-standard label="Proposed"></pds-button-standard></div></main>'''


PICKLES_SEARCH = '<html><body>' + ''.join([
    pickles_card(0, '62488655', '/used/details/cars/2007-mazda-2/62488655', '2007 Mazda 2', 'DE10Y1 Neo Hatchback 5dr Man 5sp 1.5i', '163,631 km', 'WOVR N/A', 'Acacia Ridge, QLD', 'https://www.pickles.com.au/images/transform/w_search/a/b.jpeg'),
    pickles_card(1, '62476142', '/used/details/cars/2013-mitsubishi-outlander/62476142', '2013 Mitsubishi Outlander', 'ZJ MY14 LS Wagon', '257,059 km', 'Repairable Write-Off', 'Archerfield, QLD', '/images/transform/w_search/c/d.jpeg'),
    pickles_card(2, '62459239', '/used/details/cars/2012-mitsubishi-lancer/62459239', '2012 Mitsubishi Lancer', 'CJ MY12 ES Sedan', '144,651 km', 'Statutory Write-Off', 'Acacia Ridge, QLD', '/images/transform/w_search/e/f.jpeg'),
    pickles_card(3, '62383416', '/used/details/trucks/2005-volvo-fm/62383416', '2005 Volvo FM 12', 'Cab Chassis', '', 'WOVR N/A', 'Archerfield, QLD', '/x.jpeg'),
]) + '<a href="?limit=120&amp;page=1">1</a></body></html>'

DETAIL_ITEM = {"x": {"y": [{"wovrStatus": "WOVR N/A", "incidentTypes": ["Hail"], "doesEngineStarts": True, "driveable": True,
               "hasKeys": True, "burntStatus": None,
               "conditions": [{"componentDescription": "Damaged Entire Vehicle", "conditionDescription": "Hail Damaged Vehicle", "isVisibleToPublic": True}],
               "longDescription": "CP: 12/2007,Mazda,2,Manual,Colour: Yellow,Rego. No: "}]}}
PICKLES_DETAIL = '<html><script>self.__next_f.push(' + json.dumps([1, '5:' + json.dumps(DETAIL_ITEM) + '\n']) + ')</script></html>'

BID_JSON = json.dumps({"data": {"item": {"itemBidEndTimestamp": 1796090400000, "buyNowAmount": 0},
                                "bidding": {"currentActualBid": 450, "bidHistoryBidsCount": 6}}, "status": 200})


def manheim_card(stock, section, slug, title, loc, km, wovr, bids, bidtxt, price, timing):
    w = f'<div class="WOVR col-xs-6"> <div class="heading hidden-xs">WOVR</div> <div class="value"> {wovr} </div> </div>' if wovr else ''
    return f'''<li class="vehicle-item vehicle-item-newStyles"> <div class="check"> <div class="status"><a href="/{section}/{stock}/{slug}?referringPage=AuctionListing">BidNow</a></div>
<div class="timing"> <span id="stEnd-0000000000{stock}"> <span>{timing.split(':')[0]}: </span> {timing.split(': ',1)[1]} </span> </div> </div>
<div class=bidDetials><span id=nrbids-{stock} class=bids>{bids} <span>Bids</span></span> <span id=bidtxt-{stock} class=current-status>{bidtxt}</span> <span id=stprice-{stock} class=price>${price}</span></div>
<div class="item"><img src="https://img.manheim.com.au/FP1300/AUB01MANF/item/1/{stock}F.JPG" style="min-width: 25px" alt="" /></div>
<a href="/{section}/0000000000{stock}/{slug}?referringPage=AuctionListing&amp;saleid=X"> <h2 class="heading vehicle">{title}</h2> </a>
<div class="location-container"> <span class="location"> <span> Item Location: {loc} </span> </span> </div>
<div class="odometer col-xs-6"> <div class="heading hidden-xs">Odometer</div> <div class="value"> {km} KM Showing </div> </div>
<div class="bodydesc col-xs-6"> <div class="heading hidden-xs">Body</div> <div class="value"> Hatch </div> </div>
{w}<div class="stock col-xs-6"> <div class="heading hidden-xs">Stock No</div> <div class="value"> {stock} </div> </div></li>'''


MANHEIM_HOME = '<a href="/damaged-vehicles/auctions/REP053/page1?franchiseID=REP">Salvage</a><a href="/damaged-vehicles/auctions/STAT053/page1?franchiseID=STAT">Stat</a>'
MANHEIM_REP = 'Showing 1-3 of 3 ' + ''.join([
    manheim_card('7482100', 'damaged-vehicles', '2013-ford-fiesta-wz-trend-hatch', '2013 Ford Fiesta WZ Trend Hatch', 'Pinkenba, Queensland', '109,850', 'No WOVR Record', 3, 'Current Bid', '650', 'Start: Fri 27/11/26 | 01:00 PM AEDT'),
    manheim_card('7482155', 'damaged-vehicles', '2012-bmw-3-series', '2012 BMW 3 Series F30 328i Sedan', 'Altona North, Melbourne, Victoria', '200,868', 'Repairable Write-off', 0, 'Starting Bid', '0', 'Start: Fri 27/11/26 | 01:00 PM AEDT'),
    manheim_card('7306742', 'damaged-vehicles', '2016-mazda-3-sp25', '2016 Mazda 3 SP25 GT Hatch', 'Eagle Farm, Brisbane, Queensland | Lot 4002', '109,557', 'Repairable Write-off', 15, 'Current Bid', '1,700', 'End: Mon 30/11/26 | 02:00 PM AEST'),
])
MANHEIM_GPC = 'Showing 1-1 of 1 ' + manheim_card('7487628', 'passenger-vehicles', '2016-ford-focus-lz-trend-5d-hatch', '2016 Ford Focus LZ Trend 5D Hatch', 'Eagle Farm, Brisbane, Queensland | Lot 401', '117,614', '', 0, '', '0', 'Start: Thu 26/11/26 | 09:00 AM AEST')


def fname(url):
    key = re.sub(r'^https?://', '', url)
    return re.sub(r'[^A-Za-z0-9]+', '_', key).strip('_')[:180]


class ScraperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.fix = os.path.join(cls.tmp, 'fix')
        cls.data = os.path.join(cls.tmp, 'data')
        os.makedirs(cls.fix)
        files = {
            'https://www.pickles.com.au/used/search/lob/salvage/items/state/qld?limit=120': PICKLES_SEARCH,
            'https://www.pickles.com.au/used/details/cars/2007-mazda-2/62488655': PICKLES_DETAIL,
            'https://www.pickles.com.au/api-website/buyer/ms-bidding-controller/v2/api/bidding/62488655/lot-details/Tenant01:14661:62488655': BID_JSON,
            'https://www.manheim.com.au/': MANHEIM_HOME,
            'https://www.manheim.com.au/damaged-vehicles/auctions/REP053/page1/P?franchiseID=REP&rowsPerPage=120': MANHEIM_REP,
            'https://www.manheim.com.au/passenger-vehicles/auctions/GPC999/page1/P?franchiseID=GPC&rowsPerPage=120': MANHEIM_GPC,
        }
        for url, body in files.items():
            with open(os.path.join(cls.fix, fname(url) + '.html'), 'w') as f:
                f.write(body)
        os.environ.update({'SALVAGE_FIXTURES': cls.fix, 'SALVAGE_DATA_DIR': cls.data, 'PAGE_DELAY': '0', 'API_DELAY': '0'})
        import scrape
        cls.s = importlib.reload(scrape)

    def test_1_parsers(self):
        rows, pages = self.s.parse_pickles_search(PICKLES_SEARCH)
        self.assertEqual(len(rows), 3)          # truck skipped
        self.assertEqual(pages, 1)
        r = rows[0]
        self.assertEqual((r['year'], r['make'], r['model'], r['km'], r['status']), (2007, 'Mazda', '2', 163631, 'clean'))
        self.assertEqual(rows[1]['image'], 'https://www.pickles.com.au/images/transform/w_search/c/d.jpeg')
        self.assertEqual([x['status'] for x in rows], ['clean', 'repairable', 'statutory'])
        det = self.s.parse_pickles_detail(PICKLES_DETAIL)
        self.assertEqual(det['incident'], 'Hail')
        self.assertTrue(det['keys'] and det['starts'])
        self.assertEqual(det['colour'], 'Yellow')
        m, total = self.s.parse_manheim_event(MANHEIM_REP)
        self.assertEqual(total, 3)
        self.assertEqual(m[0]['status'], 'clean')
        self.assertEqual(m[0]['bid'], 650)
        self.assertEqual(m[0]['start'], '2026-11-27T02:00:00Z')   # 1pm AEDT
        self.assertEqual(m[2]['end'], '2026-11-30T04:00:00Z')     # 2pm AEST
        self.assertEqual(m[2]['location'], 'Eagle Farm, Brisbane, Queensland')
        self.assertEqual(m[2]['lot'], '4002')
        self.assertEqual(m[0]['url'], 'https://www.manheim.com.au/damaged-vehicles/7482100/2013-ford-fiesta-wz-trend-hatch')

    def test_2_fees_and_estimates(self):
        import value
        self.assertEqual(value.pickles_salvage_fee(50), 33)
        self.assertEqual(value.pickles_salvage_fee(999), 245)
        self.assertEqual(value.pickles_salvage_fee(2000), 460)
        self.assertEqual(value.manheim_salvage_fee(1000), 220)
        self.assertEqual(value.manheim_car_fee(3000), 695)
        item = value.estimate({'src': 'Pickles', 'kind': 'salvage', 'year': 2008, 'make': 'Toyota', 'model': 'Corolla',
                               'title': '2008 Toyota Corolla', 'km': 160000, 'details': {'incident': 'Hail', 'keys': True}})
        e = item['est']
        self.assertTrue(e['ok'])
        self.assertEqual(e['repairs'], 700)
        self.assertGreater(e['profit'], 1000)
        b = e['maxBid']   # max bid must leave the target profit at the LOW resale
        self.assertGreaterEqual(e['resaleLow'] - b - value.pickles_salvage_fee(b) - e['repairs'] - value.OTHER_COSTS, value.TARGET_PROFIT)
        self.assertFalse(value.estimate({'src': 'Pickles', 'year': 2010, 'make': 'Ferrari', 'model': 'X', 'title': 'Ferrari'})['est']['ok'])

    def test_3_full_run(self):
        code = self.s.run(force_full=True)
        self.assertEqual(code, 0)
        with open(os.path.join(self.data, 'listings.json')) as f:
            items = {i['key']: i for i in json.load(f)['items']}
        self.assertIn('P62488655', items)
        self.assertIn('M7482100', items)
        self.assertIn('M7487628', items)          # clearing car
        self.assertNotIn('M7482155', items)       # Victoria filtered out
        mz = items['P62488655']
        self.assertEqual((mz['bid'], mz['bids']), (450, 6))
        self.assertEqual(mz['details']['incident'], 'Hail')
        self.assertTrue(mz['est']['ok'])
        self.assertIsNotNone(mz['lat'])
        self.assertEqual(items['M7487628']['status'], 'clearing')
        with open(os.path.join(self.data, 'meta.json')) as f:
            meta = json.load(f)
        self.assertTrue(meta['sources']['Pickles Qld']['ok'])
        self.assertTrue(meta['sources']['Manheim QLD']['ok'])
        with open(os.path.join(self.data, 'alerts.json')) as f:
            self.assertEqual(json.load(f)['events'], [])   # first run = baseline, no alert flood

    def test_4_second_run_alerts(self):
        # A new Pickles car appears, and Manheim's Mazda 3 gets a bid surge.
        extra = pickles_card(9, '62499999', '/used/details/cars/2009-toyota-corolla/62499999', '2009 Toyota Corolla', 'Ascent Hatch', '150,000 km', 'WOVR N/A', 'Brendale, QLD', '/i.jpeg')
        path = os.path.join(self.fix, fname('https://www.pickles.com.au/used/search/lob/salvage/items/state/qld?limit=120') + '.html')
        with open(path, 'w') as f:
            f.write(PICKLES_SEARCH.replace('</body>', extra + '</body>'))
        rep = os.path.join(self.fix, fname('https://www.manheim.com.au/damaged-vehicles/auctions/REP053/page1/P?franchiseID=REP&rowsPerPage=120') + '.html')
        with open(rep, 'w') as f:
            f.write(MANHEIM_REP.replace('>15 <span>Bids', '>24 <span>Bids'))
        self.assertEqual(self.s.run(force_full=True), 0)
        with open(os.path.join(self.data, 'alerts.json')) as f:
            events = json.load(f)['events']
        kinds = {(e['type'], e['key']) for e in events}
        self.assertIn(('new', 'P62499999'), kinds)
        self.assertIn(('hot', 'M7306742'), kinds)

    def test_5_failed_source_keeps_last_data(self):
        os.remove(os.path.join(self.fix, fname('https://www.manheim.com.au/') + '.html'))
        self.assertEqual(self.s.run(force_full=True), 0)
        with open(os.path.join(self.data, 'listings.json')) as f:
            items = {i['key'] for i in json.load(f)['items']}
        self.assertIn('M7482100', items)          # previous Manheim data kept
        with open(os.path.join(self.data, 'meta.json')) as f:
            self.assertFalse(json.load(f)['sources']['Manheim QLD']['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
