"""Profit estimates, yard locations and auction fees for the Salvage Flip Dashboard.

Everything here is a rough guide for ranking cars, not a valuation. Users should check
photos, damage and real comparable sales before bidding.
"""
import math
import re

# ---- auction fees (GST incl.) -----------------------------------------------------
def pickles_salvage_fee(bid):
    """pickles.com.au/fees/salvage (checked 25 Nov 2026)."""
    if bid < 100:
        return 33.0
    if bid < 500:
        return 140.0
    if bid < 1000:
        return 245.0
    return round(bid * 0.15 + 160, 2)


def manheim_salvage_fee(bid):
    """Manheim Buyer Auction Fees, effective 1 June 2026 - salvage vehicles."""
    if bid <= 200:
        return 121.0
    if bid <= 500:
        return 148.0
    if bid <= 1000:
        return 220.0
    return round(120 + bid * 0.15, 2)


def manheim_car_fee(bid):
    """Manheim Buyer Auction Fees, effective 1 June 2026 - cars & light commercial (clearing sales)."""
    if bid <= 2000:
        return 500.0
    return round(650 + bid * 0.015, 2)


def fee_for(item, bid):
    if item.get('src') == 'Manheim':
        return manheim_car_fee(bid) if item.get('kind') == 'clearing' else manheim_salvage_fee(bid)
    return pickles_salvage_fee(bid)


# ---- rough private-sale guide (repaired, roadworthy, Brisbane) -------------------
# (pattern, reference year, low, high) at ~150-200k km. Adjusted for age and km below.
GUIDE = [
    (r'landcruiser|land cruiser', 2008, 16000, 24000), (r'prado', 2008, 15000, 21000),
    (r'hilux', 2008, 10000, 15000), (r'ranger', 2012, 13000, 18000), (r'navara', 2010, 9000, 13000),
    (r'triton', 2010, 8000, 11500), (r'd-?max', 2013, 13000, 17500), (r'bt-?50', 2012, 10000, 14000),
    (r'colorado', 2012, 9000, 13000), (r'amarok', 2013, 12000, 16000), (r'patrol', 2008, 12000, 19000),
    (r'pajero', 2009, 8500, 12000), (r'kluger', 2010, 9000, 12500), (r'rav4', 2008, 6500, 9000),
    (r'x-?trail', 2010, 6500, 9000), (r'outlander', 2010, 6500, 8500), (r'forester', 2009, 6000, 8500),
    (r'outback', 2009, 6500, 9000), (r'cx-?5', 2013, 11000, 14500), (r'cx-?3', 2016, 12000, 15000),
    (r'cx-?7', 2009, 5000, 7000), (r'tucson', 2016, 12000, 15500), (r'ix35', 2012, 8000, 10500),
    (r'santa ?fe', 2010, 7500, 10500), (r'sportage', 2012, 8500, 11000), (r'sorento', 2011, 8500, 11500),
    (r'carnival', 2012, 8000, 11000), (r'territory', 2009, 5500, 8000), (r'asx', 2012, 7500, 10000),
    (r'dualis|qashqai', 2012, 6500, 9000), (r'juke', 2014, 8000, 10500), (r'kona', 2019, 15000, 19000),
    (r'xv', 2013, 9000, 12000), (r'grand vitara', 2008, 6000, 8500), (r'odyssey', 2009, 5500, 8000),
    (r'tarago', 2008, 5500, 8000), (r'hiace', 2010, 16000, 22000),
    (r'corolla', 2008, 5500, 7500), (r'camry', 2008, 5000, 7000), (r'aurion', 2009, 5000, 7000),
    (r'yaris', 2008, 4800, 7000), (r'echo', 2004, 3500, 5000), (r'prius', 2010, 7000, 9500),
    (r'mazda ?2\b|^2\b', 2008, 4800, 7000), (r'mazda ?3\b|^3\b', 2008, 5000, 7000), (r'mazda ?6\b|^6\b', 2008, 4800, 6500),
    (r'civic', 2008, 5000, 7000), (r'jazz|fit\b', 2010, 5500, 7500), (r'accord', 2008, 4800, 6800),
    (r'cr-?v', 2008, 6000, 8500), (r'getz', 2009, 3500, 5000), (r'i30', 2010, 5000, 6800),
    (r'accent', 2012, 5000, 6800), (r'elantra', 2010, 4500, 6000), (r'rio\b', 2012, 5000, 6800),
    (r'cerato', 2012, 6500, 8500), (r'tiida|pulsar', 2009, 4000, 5800), (r'lancer', 2009, 4800, 6300),
    (r'impreza', 2009, 5000, 7000), (r'swift', 2010, 5000, 6800), (r'baleno', 2018, 9000, 11500),
    (r'falcon', 2008, 4800, 7000), (r'focus', 2010, 4500, 6000), (r'fiesta', 2010, 4000, 5500),
    (r'commodore', 2008, 5000, 7000), (r'cruze', 2011, 4800, 6300), (r'barina', 2008, 3200, 4500),
    (r'astra', 2008, 4000, 5500), (r'captiva', 2010, 4800, 6500), (r'golf', 2010, 6000, 8000),
    (r'polo', 2012, 5000, 6800), (r'mg ?zs', 2020, 12000, 15000), (r'mg ?3', 2020, 9000, 11500),
    (r'jolion|haval', 2021, 16000, 20000),
]
POPULAR = re.compile(r'toyota|mazda|honda|hyundai|kia|nissan|mitsubishi|subaru|suzuki|ford|holden|isuzu|volkswagen|mg\b|haval|gwm', re.I)


def resale_guide(item):
    name = f"{item.get('make', '')} {item.get('model', '')} {item.get('title', '')}"
    year = item.get('year')
    if not year:
        return None
    for pat, ref, lo, hi in GUIDE:
        if re.search(pat, name, re.I):
            yrs = year - ref
            factor = 1 + 0.07 * yrs if yrs >= 0 else (1 - 0.075) ** (-yrs)
            factor = max(0.35, min(factor, 1.8))
            km = item.get('km')
            if km:
                if km < 100000:
                    factor *= 1.08
                elif km > 200000:
                    factor *= max(0.7, 1 - 0.06 * ((km - 200000) / 50000 + 1))
            lo2, hi2 = lo * factor, hi * factor
            return int(round(lo2, -2)), int(round(hi2, -2))
    return None


# ---- repairs & extra costs ---------------------------------------------------------
def repair_estimate(item):
    """Very rough default repair allowance from the damage/incident text."""
    if item.get('kind') == 'clearing':
        return 400, 'clearing car: allow for service, tyres, safety items'
    det = item.get('details') or {}
    text = ' '.join([det.get('incident') or '', ' '.join(det.get('damage') or []), str(det.get('burnt') or '')]).lower()
    if re.search(r'fire|burn', text) and 'not burnt' not in text and str(det.get('burnt')).lower() not in ('none', 'false', 'no', 'not burnt', ''):
        return None, 'fire damage'
    if re.search(r'flood|water|submerg', text):
        return 3000, 'water damage - high risk'
    if re.search(r'hail', text):
        return 700, 'hail (mostly cosmetic)'
    if re.search(r'theft|stolen|recover', text):
        return 600, 'theft recovered'
    if re.search(r'mechanical|engine|gearbox|transmission', text):
        return 1500, 'mechanical'
    if re.search(r'impact|collision|accident', text):
        return 1400, 'impact damage'
    return 1300, 'damage unknown - check photos'


OTHER_COSTS = 450  # safety certificate, transport, rego permit, detailing (rough)
TARGET_PROFIT = 1500


def _max_bid(item, sell_low, repairs, target):
    budget = sell_low - repairs - OTHER_COSTS - target
    if budget <= 0:
        return 0
    lo, hi = 0, int(budget)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if mid + fee_for(item, mid) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo


def estimate(item):
    """Adds item['est'] with resale, likely buy price, costs, profit and max bid."""
    guide = resale_guide(item)
    repairs, repair_note = repair_estimate(item)
    if not guide or repairs is None:
        item['est'] = {'ok': False, 'why': 'no price guide for this model' if not guide else repair_note}
        return item
    lo, hi = guide
    mid = (lo + hi) / 2
    share = 0.55 if item.get('kind') == 'clearing' else 0.30   # rough typical hammer vs resale
    bid = item.get('bid') or 0
    buy = max(bid, round(lo * share, -1))
    fee = fee_for(item, buy)
    total = buy + fee + repairs + OTHER_COSTS
    profit = mid - total
    det = item.get('details') or {}
    adj, flags = 0, []
    if det.get('keys') is True:
        flags.append('keys')
    elif det.get('keys') is False:
        adj -= 300
        flags.append('no keys')
    if det.get('starts') is True:
        flags.append('starts')
        adj += 150
    elif det.get('starts') is False:
        adj -= 400
        flags.append("doesn't start")
    if det.get('drives') is True:
        flags.append('drives')
        adj += 150
    if (item.get('km') or 0) > 250000:
        adj -= 300
    if not POPULAR.search(item.get('make') or ''):
        adj -= 500
    bids = item.get('bids') or 0
    item['est'] = {
        'ok': True, 'resaleLow': lo, 'resaleHigh': hi, 'buy': int(buy), 'buyBasis': 'current bid' if bid and bid >= lo * share else 'typical price',
        'fee': round(fee), 'repairs': repairs, 'repairNote': repair_note, 'other': OTHER_COSTS,
        'total': int(total), 'profit': int(profit), 'maxBid': _max_bid(item, lo, repairs, TARGET_PROFIT),
        'score': int(profit + adj - (250 if bids >= 25 else 0)), 'flags': flags,
    }
    return item


# ---- yards (for "near me") --------------------------------------------------------
YARDS = [
    (r'acacia ridge', -27.585, 153.026), (r'archerfield', -27.570, 153.006), (r'brendale', -27.320, 152.985),
    (r'eagle farm', -27.430, 153.090), (r'pinkenba', -27.418, 153.119), (r'hamilton', -27.438, 153.070),
    (r'yatala', -27.740, 153.220), (r'steiglitz', -27.860, 153.330), (r'rocklea', -27.540, 153.000),
    (r'toowoomba', -27.560, 151.950), (r'ipswich', -27.615, 152.760), (r'gold coast|southport|molendinar', -27.970, 153.400),
    (r'sunshine coast|maroochydore|kunda park|caloundra', -26.660, 153.090), (r'kingaroy', -26.540, 151.840),
    (r'dundowran|hervey bay', -25.270, 152.790), (r'bundaberg', -24.870, 152.350), (r'callemondah|gladstone', -23.850, 151.240),
    (r'central queensland|rockhampton|parkhurst', -23.310, 150.520), (r'paget|mackay', -21.180, 149.170),
    (r'bohle|townsville', -19.280, 146.700), (r'cairns|portsmith', -16.930, 145.770), (r'mutchilba|mareeba', -17.130, 145.400),
    (r'brisbane', -27.470, 153.020),
]


def locate(item):
    text = (item.get('location') or '') + ' ' + (item.get('area') or '')
    for pat, lat, lon in YARDS:
        if re.search(pat, text, re.I):
            item['lat'], item['lon'] = lat, lon
            return item
    item['lat'] = item['lon'] = None
    return item


def distance_km(a_lat, a_lon, b_lat, b_lon):
    r = 6371
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
