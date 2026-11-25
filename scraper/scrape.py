#!/usr/bin/env python3
"""Salvage Flip Dashboard - listing collector.

Reads public listing pages from Pickles (Brisbane salvage) and Manheim (Queensland
salvage + Brisbane clearing cars), keeps a small history so the dashboard can show
alerts (new listings, bid surges, Buy Now), and writes JSON into docs/data/.

Designed to run on GitHub Actions every hour with the Python standard library only.
Polite by design:
  * full listing scans at most every FULL_EVERY_HOURS (default 3)
  * hourly runs only refresh live bids for clean-title Pickles cars
  * pauses between requests, honest user agent, no logins, no bot-check bypassing
  * only pages allowed by the sites' robots.txt are requested
"""
import argparse
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import value  # noqa: E402  (profit estimates, fees, yard locations)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get('SALVAGE_DATA_DIR', os.path.join(ROOT, 'docs', 'data'))
VERSION = 2

UA = 'Mozilla/5.0 (compatible; SalvageFlipDashboard/2.0; personal low-frequency use)'
PICKLES = 'https://www.pickles.com.au'
MANHEIM = 'https://www.manheim.com.au'

# ---- settings (override with environment variables in the workflow) --------------
PICKLES_AREAS = [a.strip() for a in os.environ.get('PICKLES_AREAS', 'qld').split(',') if a.strip()]
SITE_URL = os.environ.get('SITE_URL', '').rstrip('/')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '').strip()
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '').strip()
NOTIFY_MIN_PROFIT = int(os.environ.get('NOTIFY_MIN_PROFIT', '1000'))
MANHEIM_ON = os.environ.get('MANHEIM', '1') != '0'
MANHEIM_CLEARING_ON = os.environ.get('MANHEIM_CLEARING', '1') != '0'
MANHEIM_LOCATION = re.compile(os.environ.get('MANHEIM_LOCATION', r'Queensland|\bQLD\b'), re.I)
FULL_EVERY_HOURS = float(os.environ.get('FULL_EVERY_HOURS', '0.9'))
MAX_PAGES = int(os.environ.get('MAX_PAGES', '12'))
MAX_DETAILS_PER_RUN = int(os.environ.get('MAX_DETAILS_PER_RUN', '60'))
MAX_BIDS_PER_RUN = int(os.environ.get('MAX_BIDS_PER_RUN', '260'))
PAGE_DELAY = float(os.environ.get('PAGE_DELAY', '1.5'))
API_DELAY = float(os.environ.get('API_DELAY', '0.5'))
KEEP_EVENTS_DAYS = 7
FORGET_AFTER_DAYS = 21

FIXTURES = os.environ.get('SALVAGE_FIXTURES')  # offline testing: directory of saved pages


# ---------------------------------------------------------------- helpers
def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z') if dt else None


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def clean(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', value or '')).split())


def first(pattern, value, default=''):
    m = re.search(pattern, value or '', re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else default


def to_int(value):
    digits = re.sub(r'[^\d]', '', str(value or ''))
    return int(digits) if digits else None


def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}', flush=True)


class BlockedError(RuntimeError):
    pass


def _fixture_for(url):
    """Map a URL to a saved file for offline tests."""
    key = re.sub(r'^https?://', '', url)
    name = re.sub(r'[^A-Za-z0-9]+', '_', key).strip('_')[:180]
    for cand in (name + '.html', name + '.json', name):
        path = os.path.join(FIXTURES, cand)
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return f.read()
    raise RuntimeError(f'no fixture for {url} ({name})')


def fetch(url, accept='text/html', delay=PAGE_DELAY, retries=2):
    if FIXTURES:
        return _fixture_for(url)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept': accept, 'Accept-Encoding': 'gzip',
                'Accept-Language': 'en-AU,en;q=0.8'})
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
            body = raw.decode('utf-8', errors='replace')
            head = body[:30000].lower()
            if any(s in head for s in ('verify you are human', 'captcha-container', 'cf-challenge', 'access denied</title')):
                raise BlockedError('The site asked for a human check. Nothing was bypassed.')
            time.sleep(delay)
            return body
        except BlockedError:
            raise
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 429):
                raise BlockedError(f'HTTP {e.code} from {url.split("/")[2]} - the site refused automated access.')
        except Exception as e:  # network hiccup: back off and retry
            last = e
        time.sleep(4 * (attempt + 1))
    raise RuntimeError(f'Could not read {url}: {last}')


def split_title(title):
    """'2007 Mazda 2' -> (2007, 'Mazda', '2')"""
    m = re.match(r'\s*((?:19|20)\d\d)\s+(.*)', title or '')
    year, rest = (int(m.group(1)), m.group(2)) if m else (None, (title or '').strip())
    parts = rest.split(' ', 1)
    make = parts[0] if parts else ''
    model = parts[1] if len(parts) > 1 else ''
    # two-word makes
    for two in ('Land Rover', 'Mercedes-Benz', 'Alfa Romeo', 'Great Wall', 'Aston Martin'):
        if rest.lower().startswith(two.lower()):
            make, model = two, rest[len(two):].strip()
    return year, make.title() if make.isupper() and len(make) > 3 else make, model


def title_status(wovr, source_kind='salvage'):
    w = (wovr or '').lower()
    if source_kind == 'clearing':
        return 'clearing'
    if 'statutory' in w:
        return 'statutory'
    if 'inspect' in w:
        return 'inspected'          # passed/needs inspection; still on the write-off register
    if 'repairable' in w:
        return 'repairable'
    if 'n/a' in w or 'no wovr' in w or 'exempt' in w:
        return 'clean'
    return 'unknown'


# ---------------------------------------------------------------- Pickles
def parse_pickles_search(body, base=PICKLES):
    rows = []
    for stock, card in re.findall(r'<main\b[^>]*id="ps-ccg-grid-card-main-(\d+)"[^>]*>(.*?)</main>', body, re.S):
        url = first(r'<a[^>]*id="ps-ccg-product-card-link-\d+"[^>]*href="([^"]+)"', card)
        if not url.startswith('/used/details/cars/'):
            continue  # cars only (skips trucks, bikes, caravans, trailers)
        heads = [clean(t) for t in re.findall(r'<h2[^>]*>(.*?)</h2>', card, re.S)]
        if not heads:
            continue
        text = clean(card)
        km = first(r'([\d,]+)\s*km\b', text)
        wovr = first(r'(Inspection Passed Repairable Writeoff|Statutory Write-Off|Repairable Write-Off|WOVR N/A)', text, 'Unknown')
        price, price_kind = None, None
        for label in re.findall(r'<pds-button-standard\b[^>]*label="([^"]*)"', card):
            m = re.search(r'(Current bid|Buy now|Minimum bid)\s*:?\s*\$([\d,]+)', html.unescape(label), re.I)
            if m:
                price, price_kind = float(m.group(2).replace(',', '')), m.group(1).lower()
                break
        year, make, model = split_title(heads[0])
        img = first(r'<img[^>]*src="([^"]+)"', card)
        rows.append({
            'key': 'P' + stock, 'src': 'Pickles', 'kind': 'salvage', 'id': stock,
            'title': heads[0], 'variant': heads[1] if len(heads) > 1 else '',
            'year': year, 'make': make, 'model': model,
            'km': to_int(km), 'wovr': wovr, 'status': title_status(wovr),
            'location': clean(first(r'<section[^>]*id="ps-cu-location-wrapper-\d+"[^>]*>(.*?)</section>', card)),
            'start': first(r'id="ps-hid-startdatetime-\d+"[^>]*value="([^"]*)"', card) or None,
            'end': first(r'id="ps-hid-enddatetime-\d+"[^>]*value="([^"]*)"', card) or None,
            'method': first(r'id="ps-hid-buymethod-\d+"[^>]*value="([^"]*)"', card),
            'url': urljoin(base, url), 'image': urljoin(base, img) if img else '',
            'bid': price if price_kind == 'current bid' else None,
            'buyNow': price if price_kind == 'buy now' else None,
            'bids': None,
        })
    pages = [int(p) for p in re.findall(r'[?&](?:amp;)?page=(\d+)', body)]
    return rows, max(pages or [1])


def scan_pickles(area):
    path = f'/used/search/lob/salvage/items/state/{area}?limit=120'
    log(f'Pickles {area}: page 1')
    rows, pages = parse_pickles_search(fetch(PICKLES + path))
    if not rows:
        raise RuntimeError('No car listings found - Pickles may have changed its page layout.')
    cap = min(pages, MAX_PAGES)
    for page in range(2, cap + 1):
        log(f'Pickles {area}: page {page}/{cap}')
        more, _ = parse_pickles_search(fetch(f'{PICKLES}{path}&page={page}'))
        rows.extend(more)
    area_name = area.split('/')[-1].replace('-', ' ').title()
    for r in rows:
        r['area'] = area_name
    return {r['key']: r for r in rows}, {'pages': cap, 'pagesAvailable': pages, 'complete': cap >= pages}


def parse_pickles_detail(body):
    chunks = []
    for raw in re.findall(r'self\.__next_f\.push\((\[.*?\])\)</script>', body, re.S):
        try:
            val = json.loads(raw)
            if len(val) > 1 and isinstance(val[1], str):
                chunks.append(val[1])
        except (ValueError, TypeError):
            pass

    def walk(obj):
        if isinstance(obj, dict):
            if 'incidentTypes' in obj and 'wovrStatus' in obj:
                return obj
            for v in obj.values():
                found = walk(v)
                if found:
                    return found
        elif isinstance(obj, list):
            for v in obj:
                found = walk(v)
                if found:
                    return found
        return None

    item = None
    for line in ''.join(chunks).splitlines():
        try:
            item = walk(json.loads(line.split(':', 1)[1]))
        except (ValueError, IndexError):
            continue
        if item:
            break
    if not item:
        raise RuntimeError('vehicle details not found')
    damage = []
    for c in item.get('conditions') or []:
        if c.get('isVisibleToPublic', True):
            txt = ' - '.join(str(c.get(k) or '').strip() for k in ('componentDescription', 'conditionDescription')).strip(' -')
            if txt:
                damage.append(txt)
    desc = item.get('longDescription') or ''
    colour = first(r'Colour:\s*([^,]+)', desc)
    trans = 'Manual' if re.search(r'\bManual\b', desc) else ('Automatic' if re.search(r'\bAuto', desc) else '')
    return {
        'incident': ', '.join(item.get('incidentTypes') or []),
        'damage': damage[:8],
        'starts': item.get('doesEngineStarts'),
        'drives': item.get('driveable'),
        'keys': item.get('hasKeys'),
        'burnt': item.get('burntStatus'),
        'colour': colour,
        'trans': trans,
        'wovr': item.get('wovrStatus'),
    }


def fetch_pickles_bid(stock):
    url = f'{PICKLES}/api-website/buyer/ms-bidding-controller/v2/api/bidding/{stock}/lot-details/Tenant01:14661:{stock}'
    data = json.loads(fetch(url, accept='application/json', delay=API_DELAY)).get('data') or {}
    bidding, item = data.get('bidding') or {}, data.get('item') or {}
    end_ms = item.get('itemBidEndTimestamp')
    return {
        'bid': bidding.get('currentActualBid'),
        'bids': bidding.get('bidHistoryBidsCount') or 0,
        'buyNow': item.get('buyNowAmount') or None,
        'end': iso(datetime.fromtimestamp(end_ms / 1000, timezone.utc)) if end_ms else None,
        'result': item.get('bidResult'),
    }


# ---------------------------------------------------------------- Manheim
TZ_OFFSETS = {'AEDT': 11, 'AEST': 10, 'ACDT': 10.5, 'ACST': 9.5, 'AWST': 8, 'AWDT': 9}


def parse_manheim_time(text):
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})\s*\|\s*(\d{1,2}):(\d{2})\s*([AP]M)\s*([A-Z]{4})?', text or '')
    if not m:
        return None
    d, mo, y, hh, mm, ap, tz = m.groups()
    y = int(y) + (2000 if len(y) == 2 else 0)
    hh = int(hh) % 12 + (12 if ap == 'PM' else 0)
    off = TZ_OFFSETS.get(tz or 'AEST', 10)
    local = datetime(y, int(mo), int(d), hh, int(mm), tzinfo=timezone(timedelta(hours=off)))
    return iso(local)


def manheim_events(home_html):
    """Find this week's salvage event (code changes weekly) plus Brisbane clearing events."""
    found = []
    for path, fr in re.findall(r'href="(/damaged-vehicles/auctions/[A-Z0-9]+)/page1\?franchiseID=([A-Z0-9]+)"', home_html):
        if fr == 'REP':
            found.append((path, fr, 'salvage'))
    if MANHEIM_CLEARING_ON:
        for path, fr in re.findall(r'href="(/passenger-vehicles/auctions/[A-Z0-9]+)/page1\?franchiseID=(GPC|MOTR)"', home_html):
            found.append((path, fr, 'clearing'))
        for fixed in (('/passenger-vehicles/auctions/GPC999', 'GPC'), ('/passenger-vehicles/auctions/MTR999', 'MOTR')):
            if not any(f[0] == fixed[0] for f in found):
                found.append((fixed[0], fixed[1], 'clearing'))
    seen, out = set(), []
    for f in found:
        if f[0] not in seen:
            seen.add(f[0])
            out.append(f)
    return out


def _detail(card, cls):
    return clean(first(r'<div class="' + cls + r'[^"]*">\s*<div class="heading[^"]*">[^<]*</div>\s*<div class="value">(.*?)</div>', card))


def parse_manheim_event(body, kind='salvage', base=MANHEIM):
    rows = []
    for card in re.split(r'<li class="vehicle-item', body)[1:]:
        link = re.search(r'href="/(damaged-vehicles|passenger-vehicles)/0*(\d+)/([a-z0-9-]+)', card)
        if not link:
            continue
        section, stock, slug = link.groups()
        title = clean(first(r'<h2 class="heading vehicle">(.*?)</h2>', card))
        location = clean(first(r'<span class="location">(.*?)</span>\s*</div>', card)).replace('Item Location:', '').strip()
        lot = first(r'\|\s*Lot\s*(\d+)', location)
        location = re.sub(r'\s*\|\s*Lot\s*\d+.*$', '', location)
        timing = clean(first(r'<span id="stEnd-[^"]*">(.*?)</span>\s*</div>', card))
        when = parse_manheim_time(timing)
        bids = to_int(first(r'class=bids>\s*(\d+)', card))
        status_txt = clean(first(r'class=current-status>([^<]*)<', card))
        price = to_int(first(r'class=price>\s*\$([\d,]+)', card))
        wovr = _detail(card, 'WOVR') or ('Not stated (clearing sale)' if kind == 'clearing' else 'Unknown')
        img = first(r'<img src="(https://img\.manheim\.com\.au/[^"]+)"', card)
        year, make, model = split_title(title)
        rows.append({
            'key': 'M' + stock, 'src': 'Manheim', 'kind': kind, 'id': stock,
            'title': title, 'variant': '', 'year': year, 'make': make, 'model': model,
            'km': to_int(_detail(card, 'odometer')), 'wovr': wovr, 'status': title_status(wovr, kind),
            'location': location, 'lot': lot or None,
            'start': when if timing.lower().startswith('start') else None,
            'end': when if not timing.lower().startswith('start') else None,
            'method': 'BidNow' if 'BidNow' in card else ('Simulcast' if 'Simulcast' in card else ''),
            'url': f'{base}/{section}/{stock}/{slug}', 'image': img,
            'bid': price if (status_txt.lower().startswith('current') and price) else None,
            'bids': bids, 'buyNow': None,
            'colour': _detail(card, 'colour'), 'trans': _detail(card, 'transmission'),
            'body': _detail(card, 'bodydesc'), 'fuel': _detail(card, 'fuel'),
            'seller': _detail(card, 'seller'),
        })
    total = to_int(first(r'Showing\s+\d+-\d+\s+of\s+(\d+)', body))
    return rows, total


def scan_manheim():
    home = fetch(MANHEIM + '/')
    events = manheim_events(home)
    if not events:
        raise RuntimeError('No Manheim salvage event found on the homepage.')
    items, info = {}, []
    for path, fr, kind in events:
        page, total, got = 1, None, 0
        while page <= MAX_PAGES:
            log(f'Manheim {fr}: page {page}')
            try:
                rows, total = parse_manheim_event(fetch(f'{MANHEIM}{path}/page{page}/P?franchiseID={fr}&rowsPerPage=120'), kind)
            except RuntimeError as e:
                if kind == 'clearing' and page == 1:
                    log(f'  skipped {fr}: {e}')
                    break
                raise
            got += len(rows)
            for r in rows:
                if MANHEIM_LOCATION.search(r['location']):
                    items[r['key']] = r
            if not rows or not total or got >= total:
                break
            page += 1
        info.append({'event': path.rsplit('/', 1)[-1], 'kind': kind, 'total': total})
    return items, {'events': info}


# ---------------------------------------------------------------- state / alerts
def load_json(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(name, value):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def add_event(events, when, kind, item, detail=''):
    events.append({'at': iso(when), 'type': kind, 'key': item['key'], 'src': item['src'],
                   'title': item['title'], 'status': item.get('status'), 'detail': detail})


def track_changes(items, state, when, baseline):
    seen = state.setdefault('seen', {})
    events = state.setdefault('events', [])
    start_len = len(events)
    for key, it in items.items():
        prev = seen.get(key)
        if prev is None:
            it['firstSeen'] = iso(when)
            if not baseline:
                add_event(events, when, 'new', it, it.get('wovr') or '')
            seen[key] = {'first': iso(when)}
        else:
            it['firstSeen'] = prev.get('first')
            pb, nb = prev.get('bids') or 0, it.get('bids') or 0
            if it.get('bids') is not None and (nb - pb >= 5 or (pb < 10 <= nb)):
                add_event(events, when, 'hot', it, f'{pb} -> {nb} bids' + (f', now ${it["bid"]:,.0f}' if it.get('bid') else ''))
            if it.get('buyNow') and not prev.get('buyNow'):
                add_event(events, when, 'buynow', it, f'Buy Now ${it["buyNow"]:,.0f}')
        rec = seen[key]
        rec['last'] = iso(when)
        if it.get('bids') is not None:
            rec['bids'] = it.get('bids')
        if it.get('buyNow'):
            rec['buyNow'] = it['buyNow']
    cutoff = when - timedelta(days=FORGET_AFTER_DAYS)
    for key in [k for k, v in seen.items() if (parse_iso(v.get('last')) or when) < cutoff]:
        seen.pop(key, None)
        state.get('details', {}).pop(key, None)
    fresh = events[start_len:]
    keep_after = when - timedelta(days=KEEP_EVENTS_DAYS)
    state['events'] = [e for e in events if (parse_iso(e['at']) or when) >= keep_after][-500:]
    return fresh


# ---------------------------------------------------------------- optional push (webhook)
def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def notify(new_events, items):
    """Push new, clean-title, profitable cars as cards to Discord and/or any JSON webhook
    (Make/Zapier/n8n can forward these to WhatsApp, SMS, email...)."""
    if not (DISCORD_WEBHOOK_URL or WEBHOOK_URL) or FIXTURES:
        return 0
    cars = []
    for ev in new_events:
        it = items.get(ev['key'])
        est = (it or {}).get('est') or {}
        if it and it['status'] in ('clean', 'clearing') and est.get('ok') and est.get('profit', 0) >= NOTIFY_MIN_PROFIT:
            cars.append(it)
    cars.sort(key=lambda it: -it['est']['score'])
    cars = cars[:10]
    if not cars:
        return 0
    try:
        if DISCORD_WEBHOOK_URL:
            embeds = []
            for it in cars:
                e = it['est']
                ends = parse_iso(it.get('end') or it.get('start'))
                embeds.append({
                    'title': f"{it['title']} - est. profit ${e['profit']:,}"[:250], 'url': it['url'], 'color': 0x2EA043,
                    'description': f"{it.get('wovr')} | {(it.get('km') or 0):,} km | {it.get('location')}\n"
                                   f"Bid now: {'$' + format(int(it['bid']), ',') if it.get('bid') else 'no bids'} | Max bid: ${e['maxBid']:,}"
                                   + (f"\nAuction: <t:{int(ends.timestamp())}:R>" if ends else ''),
                    'image': {'url': it['image']} if it.get('image') else None,
                    'footer': {'text': f"{it['src']} | resale guide ${e['resaleLow']:,}-${e['resaleHigh']:,}"},
                })
            content = f'New money-makers found: {len(cars)}' + (f' - full list: {SITE_URL}' if SITE_URL else '')
            _post(DISCORD_WEBHOOK_URL, {'username': 'Salvage Flip', 'content': content,
                                        'embeds': [{k: v for k, v in e.items() if v} for e in embeds]})
        if WEBHOOK_URL:
            _post(WEBHOOK_URL, {'dashboard': SITE_URL, 'cars': [{
                'title': it['title'], 'url': it['url'], 'image': it.get('image'), 'source': it['src'],
                'titleStatus': it.get('wovr'), 'km': it.get('km'), 'location': it.get('location'),
                'currentBid': it.get('bid'), 'bids': it.get('bids'), 'auctionEnds': it.get('end'),
                'estProfit': it['est']['profit'], 'maxBid': it['est']['maxBid']} for it in cars]})
        log(f'Pushed {len(cars)} new cars to webhook')
    except Exception as e:  # never fail the run because of a webhook
        log(f'!! webhook failed: {e}')
    return len(cars)


# ---------------------------------------------------------------- main run
def run(force_full=False, light_only=False):
    started = now()
    state = load_json('state.json', {})
    previous = {i['key']: i for i in load_json('listings.json', {}).get('items', [])}
    meta = load_json('meta.json', {}).get('sources', {})
    last_full = parse_iso(state.get('lastFull'))
    full = not light_only and (force_full or not last_full or (started - last_full).total_seconds() >= FULL_EVERY_HOURS * 3600)
    baseline = not state.get('seen')
    items = dict(previous)
    log(f'{"FULL scan" if full else "Light refresh (bids)"} - {len(previous)} cars from last run')

    if full:
        fresh, ok_sources = {}, set()
        for area in PICKLES_AREAS:
            name = f'Pickles {area.split("/")[-1].replace("-", " ").title()}'
            try:
                got, info = scan_pickles(area)
                fresh.update(got)
                ok_sources.add(('Pickles', area.split('/')[-1].replace('-', ' ').title()))
                meta[name] = {'ok': True, 'count': len(got), 'checkedAt': iso(now()), **info}
            except Exception as e:
                log(f'!! {name} failed: {e}')
                meta[name] = {**meta.get(name, {}), 'ok': False, 'error': str(e)[:300], 'failedAt': iso(now())}
        if MANHEIM_ON:
            try:
                got, info = scan_manheim()
                fresh.update(got)
                ok_sources.add(('Manheim', None))
                meta['Manheim QLD'] = {'ok': True, 'count': len(got), 'checkedAt': iso(now()), **info}
            except Exception as e:
                log(f'!! Manheim failed: {e}')
                meta['Manheim QLD'] = {**meta.get('Manheim QLD', {}), 'ok': False, 'error': str(e)[:300], 'failedAt': iso(now())}
        # Replace data only for sources that scanned OK; keep last good data for the rest.
        items = {}
        for key, it in previous.items():
            src_ok = ('Manheim', None) in ok_sources if it['src'] == 'Manheim' else ('Pickles', it.get('area')) in ok_sources
            if not src_ok:
                items[key] = it
        for key, it in fresh.items():
            old = previous.get(key, {})
            for f in ('bids', 'bid', 'buyNow', 'details', 'bidCheckedAt'):
                if it.get(f) in (None, '') and old.get(f) not in (None, ''):
                    it[f] = old[f]
            items[key] = it
        if ok_sources:
            state['lastFull'] = iso(started)

    # Pickles enrichment: damage details (cached) and live bids for clean-title cars.
    details_cache = state.setdefault('details', {})
    pickles_clean = [it for it in items.values() if it['src'] == 'Pickles' and it['status'] == 'clean']
    soon_first = sorted(pickles_clean, key=lambda it: it.get('end') or '9999')
    fetched = 0
    for it in soon_first:
        cached = details_cache.get(it['key'])
        if cached:
            it['details'] = cached
            continue
        if fetched >= MAX_DETAILS_PER_RUN:
            continue
        try:
            path = it['url'].replace(PICKLES, '')
            det = parse_pickles_detail(fetch(PICKLES + path, delay=1.0))
            det['at'] = iso(now())
            details_cache[it['key']] = it['details'] = det
            fetched += 1
        except BlockedError as e:
            log(f'!! details stopped: {e}')
            break
        except Exception as e:
            log(f'   details {it["id"]}: {e}')
    horizon = started + timedelta(days=8)
    bid_targets = [it for it in soon_first if (parse_iso(it.get('end')) or horizon) <= horizon and (parse_iso(it.get('end')) or horizon) > started]
    bid_ok = 0
    for it in bid_targets[:MAX_BIDS_PER_RUN]:
        try:
            b = fetch_pickles_bid(it['id'])
            it['bid'] = b['bid']
            it['bids'] = b['bids']
            it['buyNow'] = b['buyNow'] or it.get('buyNow')
            it['end'] = b['end'] or it.get('end')
            it['bidCheckedAt'] = iso(now())
            bid_ok += 1
        except BlockedError as e:
            log(f'!! bids stopped: {e}')
            break
        except Exception as e:
            log(f'   bid {it["id"]}: {e}')
    log(f'Details fetched: {fetched}, bids refreshed: {bid_ok}/{len(bid_targets)}')

    # Drop auctions that ended more than a day ago (if they are still listed they reappear next scan).
    stale = started - timedelta(days=1)
    items = {k: v for k, v in items.items() if not (parse_iso(v.get('end')) and parse_iso(v.get('end')) < stale)}

    for it in items.values():
        value.locate(it)
        value.estimate(it)
    new_events = track_changes(items, state, started, baseline)
    if baseline:
        state['baselineAt'] = iso(started)
    pushed = notify(new_events, items)

    ordered = sorted(items.values(), key=lambda it: (it.get('end') or it.get('start') or '9999', it['key']))
    counts = {'total': len(ordered)}
    for it in ordered:
        counts[it['status']] = counts.get(it['status'], 0) + 1
        counts['src_' + it['src']] = counts.get('src_' + it['src'], 0) + 1
    finished = now()
    save_json('listings.json', {'generatedAt': iso(finished), 'items': ordered})
    save_json('alerts.json', {'generatedAt': iso(finished), 'baselineAt': state.get('baselineAt'),
                              'events': list(reversed(state.get('events', [])))[:400]})
    save_json('meta.json', {'version': VERSION, 'generatedAt': iso(finished), 'lastFull': state.get('lastFull'),
                            'lastRunType': 'full' if full else 'bids', 'runSeconds': round((finished - started).total_seconds()),
                            'pushed': pushed, 'targetProfit': value.TARGET_PROFIT, 'otherCosts': value.OTHER_COSTS,
                            'sources': meta, 'counts': counts,
                            'settings': {'picklesAreas': PICKLES_AREAS, 'manheim': MANHEIM_ON,
                                         'manheimClearing': MANHEIM_CLEARING_ON, 'fullEveryHours': FULL_EVERY_HOURS}})
    save_json('state.json', state)
    log(f'Saved {len(ordered)} cars - {counts}')
    ok_any = any(v.get('ok') for v in meta.values()) if meta else False
    return 0 if (ok_any or not full) else 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--full', action='store_true', help='force a full listing scan')
    ap.add_argument('--bids-only', action='store_true', help='only refresh live bids')
    args = ap.parse_args()
    sys.exit(run(force_full=args.full, light_only=args.bids_only))


if __name__ == '__main__':
    main()
