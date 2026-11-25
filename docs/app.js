/* Flip Finder - shows the salvage cars near you that should make the most money.
   Data comes from data/*.json, refreshed hourly by the GitHub Action. */
(function () {
  'use strict';
  const CITIES = [
    ['Brisbane', -27.47, 153.02], ['Gold Coast', -28.0, 153.4], ['Sunshine Coast', -26.65, 153.07],
    ['Ipswich', -27.61, 152.76], ['Logan', -27.64, 153.11], ['Toowoomba', -27.56, 151.95],
    ['Bundaberg', -24.87, 152.35], ['Hervey Bay', -25.29, 152.84], ['Rockhampton', -23.38, 150.51],
    ['Mackay', -21.14, 149.19], ['Townsville', -19.26, 146.82], ['Cairns', -16.92, 145.77]];
  const SORTS = [['profit', '💰 Most profit'], ['ending', '⏳ Ending soon'], ['new', '🆕 Newest'], ['near', '📍 Closest']];
  const PAGE = 24;
  const KEY = 'flipfinder.v1';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (n) => (n == null || isNaN(n)) ? '—' : (n < 0 ? '-$' : '$') + Math.abs(Math.round(n)).toLocaleString('en-AU');

  let S = load();
  let DATA = { items: [], meta: null, alerts: { events: [] } };
  let shown = PAGE, alertFilter = null;

  function load() {
    let s = {};
    try { s = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { /* private mode */ }
    return Object.assign({ loc: null, radius: 100, sort: 'profit', cleanOnly: true, clearing: true, maxSpend: 10000, view: 'picks', saved: [], savedOnly: false, lastVisit: null, prevVisit: null }, s);
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* ignore */ } }

  // ---------- data
  async function getJSON(name) {
    const r = await fetch('data/' + name + '?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(name + ' ' + r.status);
    return r.json();
  }
  async function refresh() {
    try {
      if (window.__DATA__) { DATA = window.__DATA__; }
      else {
        const [l, m, a] = await Promise.all([getJSON('listings.json'), getJSON('meta.json'), getJSON('alerts.json').catch(() => ({ events: [] }))]);
        DATA = { items: l.items || [], meta: m, alerts: a };
      }
    } catch (e) {
      $('updated').innerHTML = '<span class="bad">Could not load data - check your connection</span>';
    }
    render();
  }

  // ---------- helpers
  function dist(it) {
    if (!S.loc || it.lat == null) return null;
    const R = 6371, rad = Math.PI / 180;
    const dLat = (it.lat - S.loc.lat) * rad, dLon = (it.lon - S.loc.lon) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(S.loc.lat * rad) * Math.cos(it.lat * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  function ago(iso) {
    const t = Date.parse(iso); if (!t) return '';
    const m = Math.round((Date.now() - t) / 60000);
    if (m < 1) return 'just now'; if (m < 60) return m + ' min ago';
    const h = Math.round(m / 60); if (h < 36) return h + ' h ago';
    return Math.round(h / 24) + ' days ago';
  }
  function when(it) {
    const end = Date.parse(it.end), start = Date.parse(it.start), now = Date.now();
    const fmt = (ms) => { const h = ms / 3600000; return h < 1 ? Math.max(1, Math.round(ms / 60000)) + ' min' : h < 48 ? Math.round(h) + ' h' : Math.round(h / 24) + ' days'; };
    if (end && end > now) {
      if (start && start > now) return { txt: 'Bidding opens in ' + fmt(start - now), soon: false, ms: end - now };
      return { txt: 'Ends in ' + fmt(end - now), soon: end - now < 6 * 3600000, ms: end - now };
    }
    if (start && start > now) return { txt: 'Auction in ' + fmt(start - now), soon: start - now < 6 * 3600000, ms: start - now + 3600000 };
    return { txt: 'Check auction time', soon: false, ms: 9e15 };
  }
  const isClean = (it) => it.status === 'clean' || it.status === 'clearing';
  const isNew = (it) => {
    const f = Date.parse(it.firstSeen); if (!f) return false;
    const base = DATA.alerts && DATA.alerts.baselineAt ? Date.parse(DATA.alerts.baselineAt) : 0;
    if (f <= base + 60000) return false;                       // came from the very first scan
    const since = S.prevVisit ? Date.parse(S.prevVisit) : Date.now() - 24 * 3600000;
    return f > since;
  };
  const hotKeys = () => new Set((DATA.alerts.events || []).filter((e) => e.type === 'hot' && Date.now() - Date.parse(e.at) < 24 * 3600000).map((e) => e.key));

  function visible() {
    const now = Date.now();
    return DATA.items.filter((it) => {
      if (Date.parse(it.end) && Date.parse(it.end) < now) return false;
      if (S.cleanOnly && !isClean(it)) return false;
      if (!S.clearing && it.status === 'clearing') return false;
      const d = dist(it);
      if (S.loc && Number(S.radius) > 0 && (d == null || d > Number(S.radius))) return false;
      if (S.savedOnly && !S.saved.includes(it.key)) return false;
      return true;
    });
  }

  // ---------- render
  function render() {
    const meta = DATA.meta;
    $('updated').innerHTML = meta && meta.generatedAt
      ? 'Updated ' + esc(ago(meta.generatedAt)) + ' · ' + DATA.items.length + ' cars checked' + (Object.values(meta.sources || {}).some((s) => !s.ok) ? ' · <span class="bad">a source had trouble</span>' : '')
      : 'Waiting for the first scan…';
    $('locLabel').textContent = S.loc ? S.loc.label : 'Set area';
    $('setup').hidden = !!S.loc && !setupOpen;
    $('cleanOnly').checked = S.cleanOnly; $('clearing').checked = S.clearing; $('maxSpend').value = String(S.maxSpend);
    $('radius').value = String(S.radius);
    $('savedOnly').setAttribute('aria-pressed', S.savedOnly ? 'true' : 'false');
    $('savedOnly').textContent = (S.savedOnly ? '★' : '☆') + ' Saved' + (S.saved.length ? ' (' + S.saved.length + ')' : '');
    $('sortChips').innerHTML = SORTS.map(([k, l]) => `<button class="chip${S.sort === k ? ' on' : ''}" data-sort="${k}">${l}</button>`).join('');
    $('cities').innerHTML = CITIES.map(([n]) => `<button data-city="${esc(n)}" class="${S.loc && S.loc.label === n ? 'on' : ''}">${esc(n)}</button>`).join('');

    const hot = hotKeys();
    const base = visible();
    const priced = base.filter((it) => it.est && it.est.ok && (!Number(S.maxSpend) || it.est.total <= Number(S.maxSpend)));
    const unpriced = base.filter((it) => !(it.est && it.est.ok));

    // alerts strip
    const newOnes = priced.filter(isNew).filter((it) => it.est.profit > 0);
    const soonOnes = priced.filter((it) => when(it).soon && it.est.profit > 500);
    const hotOnes = priced.filter((it) => hot.has(it.key));
    const savedSoon = DATA.items.filter((it) => S.saved.includes(it.key) && when(it).soon);
    const al = [];
    if (newOnes.length) al.push(['new', '🆕', newOnes.length, 'new money-makers since your last visit']);
    if (soonOnes.length) al.push(['soon', '⏳', soonOnes.length, 'good cars ending in the next 6 h']);
    if (hotOnes.length) al.push(['hot', '🔥', hotOnes.length, 'bid surges today']);
    if (savedSoon.length) al.push(['saved', '★', savedSoon.length, 'of your saved cars ending soon']);
    $('alerts').innerHTML = al.length ? al.map(([k, i, n, t]) => `<div class="alert ${k}${alertFilter === k ? ' on' : ''}" data-alert="${k}">${i} <b>${n}</b> ${t}</div>`).join('')
      + (alertFilter ? '<div class="alert" data-alert="">✕ Show all</div>' : '') : '';

    let list = S.view === 'picks' ? priced : base;
    if (alertFilter === 'new') list = newOnes;
    else if (alertFilter === 'soon') list = soonOnes;
    else if (alertFilter === 'hot') list = hotOnes;
    else if (alertFilter === 'saved') list = savedSoon.filter((it) => it.est && it.est.ok);
    const sorter = {
      profit: (a, b) => ((b.est && b.est.ok ? b.est.score : -1e9) - (a.est && a.est.ok ? a.est.score : -1e9)) || (when(a).ms - when(b).ms),
      ending: (a, b) => when(a).ms - when(b).ms,
      new: (a, b) => (Date.parse(b.firstSeen) || 0) - (Date.parse(a.firstSeen) || 0),
      near: (a, b) => (dist(a) ?? 1e9) - (dist(b) ?? 1e9),
    }[S.sort];
    list = list.slice().sort(sorter);

    document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.view === S.view));
    $('otherWrap').hidden = true;
    if (S.view === 'hunt' && DATA.items.length && !alertFilter) {
      renderHunt(list, hot);
      $('sources').innerHTML = srcLine(meta);
      return;
    }
    if (!DATA.items.length) {
      $('grid').innerHTML = '';
      $('empty').hidden = false;
      $('empty').innerHTML = '<b>First scan is on its way.</b><br>The site checks Pickles and Manheim every 30 minutes. If this stays empty, open the GitHub repo → Actions → “Update car listings” → Run workflow.';
    } else if (!list.length) {
      $('grid').innerHTML = '';
      $('empty').hidden = false;
      $('empty').innerHTML = '<b>No cars match right now.</b><br>Try a bigger distance, a higher max spend, or turn off “No write-offs”.';
    } else {
      $('empty').hidden = true;
      $('grid').innerHTML = list.slice(0, shown).map((it, i) => card(it, i + 1, hot)).join('');
    }
    $('count').textContent = list.length ? `${list.length} car${list.length > 1 ? 's' : ''}${S.view === 'all' ? ' listed' : ''}${S.loc ? ' near ' + S.loc.label : ''} · ranked by ${SORTS.find((s) => s[0] === S.sort)[1].slice(2).toLowerCase()}` : '';
    $('more').hidden = list.length <= shown;
    if (S.view === 'picks') {
      $('otherSummary').textContent = `Other cars nearby without a price guide (${unpriced.length})`;
      $('otherWrap').hidden = !unpriced.length;
      $('otherGrid').innerHTML = $('otherWrap').open ? unpriced.slice(0, 60).map((it) => card(it, 0, hot)).join('') : '';
    }
    $('sources').innerHTML = srcLine(meta);
  }

  function srcLine(meta) {
    return meta && meta.sources ? Object.entries(meta.sources).map(([n, s]) => `<span class="${s.ok ? 'src-ok' : 'src-bad'}">${s.ok ? '●' : '▲'} ${esc(n)}: ${s.ok ? (s.count || 0) + ' cars, ' + esc(ago(s.checkedAt)) : 'not reachable (' + esc(ago(s.failedAt)) + ') - showing last good data'}</span>`).join(' &nbsp; ') : '';
  }

  // ---------- Auction hunt: every car on sale now or coming up, grouped by when you can buy it
  const groupOpen = {};
  function huntGroup(it) {
    const now = Date.now(), st = Date.parse(it.start), en = Date.parse(it.end);
    if (it.buyNow || /buy ?now/i.test(it.method || '')) return 0;
    const day = (t) => { const d = new Date(t); d.setHours(0, 0, 0, 0); return d.getTime(); };
    const today = day(now), DAY = 86400000;
    if ((!st || st <= now) && en && en > now) return en - now < DAY ? 1 : 2;
    const t = st || en;
    if (!t) return 7;
    if (day(t) === today) return 3;
    if (day(t) === today + DAY) return 4;
    if (t - now < 7 * DAY) return 5;
    return 6;
  }
  const GROUPS = [
    ['⚡ Buy now', 'Fixed price - can be bought straight away'],
    ['🔴 Bidding open - ends within 24 h', 'Last chance: check photos and set your max bid'],
    ['🟢 Bidding open now', 'Live online auctions you can bid on today'],
    ['📅 Auctions opening today', 'Get your research done before bidding starts'],
    ['📅 Opening tomorrow', ''],
    ['🗓 Coming up this week', 'Plenty of time to inspect and plan repairs'],
    ['🗓 Later', ''],
    ['❓ Time not listed', 'Open the listing to check the sale date']];
  function renderHunt(list, hot) {
    const groups = GROUPS.map(() => []);
    list.forEach((it) => groups[huntGroup(it)].push(it));
    $('empty').hidden = list.length > 0;
    $('empty').innerHTML = '<b>No cars match right now.</b><br>Try a bigger distance or turn off “No write-offs”.';
    $('more').hidden = true;
    $('count').textContent = `${list.length} car${list.length === 1 ? '' : 's'} for sale or coming up${S.loc ? ' near ' + S.loc.label : ''} · best money-makers first in each group`;
    $('grid').innerHTML = groups.map((g, i) => {
      if (!g.length) return '';
      const n = groupOpen[i] || 12;
      return `<section class="group" style="grid-column:1/-1"><h2>${GROUPS[i][0]} <small>${g.length} car${g.length === 1 ? '' : 's'}</small></h2>${GROUPS[i][1] ? `<p class="gsub">${GROUPS[i][1]}</p>` : ''}
        <div class="grid">${g.slice(0, n).map((it, k) => card(it, 0, hot)).join('')}</div>
        ${g.length > n ? `<button class="more" data-group="${i}">Show ${Math.min(24, g.length - n)} more of ${g.length}</button>` : ''}</section>`;
    }).join('');
  }

  function card(it, rank, hot) {
    const e = it.est || {}, w = when(it), d = dist(it), saved = S.saved.includes(it.key), det = it.details || {};
    const status = it.status === 'clean' ? '<span class="b clean">No write-off</span>'
      : it.status === 'clearing' ? '<span class="b clean">Clearing car</span>'
      : `<span class="b wo">${esc(it.wovr)}</span>`;
    const badges = [isNew(it) ? '<span class="b new">NEW</span>' : '', status,
      (hot.has(it.key) || (it.bids || 0) >= 10) ? `<span class="b hot">🔥 ${it.bids || ''} bids</span>` : '',
      `<span class="b ${w.soon ? 'soon' : 'time'}">${esc(w.txt)}</span>`].join('');
    const flags = [];
    (e.flags || []).forEach((f) => flags.push(`<span class="flag ${/no |doesn/.test(f) ? 'bad' : 'good'}">${esc(f)}</span>`));
    if (det.incident) flags.push(`<span class="flag">${esc(det.incident)}</span>`);
    if (e.repairNote) flags.push(`<span class="flag">${esc(e.repairNote)}</span>`);
    const bidLine = it.bid ? `<div class="v">${money(it.bid)}</div><div class="s">${it.bids || 0} bid${it.bids === 1 ? '' : 's'}</div>`
      : it.bids === 0 ? '<div class="v">No bids yet</div><div class="s">get in early</div>'
      : '<div class="v">Bid: see listing</div><div class="s">' + esc(it.src) + '</div>';
    const over = e.ok && it.bid && it.bid > e.maxBid;
    const metaLine = [it.year && it.km ? (it.km.toLocaleString('en-AU') + ' km') : (it.km ? it.km.toLocaleString('en-AU') + ' km' : ''), esc(it.location || ''), d != null ? Math.round(d) + ' km away' : '', esc(it.src)].filter(Boolean).join(' · ');
    const money1 = e.ok ? `<div class="money"><div class="profit"><div class="l">Est. profit</div><div class="v${e.profit < 1000 ? ' low' : ''}">${money(e.profit)}</div></div><div class="bidbox"><div class="l">Current bid</div>${bidLine}</div></div>
      <div class="maxbid"><span>Bid up to <b>${money(e.maxBid)}</b> for ${money((DATA.meta && DATA.meta.targetProfit) || 1500)}+ profit</span>${over ? '<span class="over">over max</span>' : ''}</div>
      <details class="how"><summary>How this is worked out</summary><table>
        <tr><td>Resale guide (repaired)</td><td>${money(e.resaleLow)}–${money(e.resaleHigh)}</td></tr>
        <tr><td>Likely buy price (${esc(e.buyBasis)})</td><td>−${money(e.buy)}</td></tr>
        <tr><td>Auction fee</td><td>−${money(e.fee)}</td></tr>
        <tr><td>Repair allowance</td><td>−${money(e.repairs)}</td></tr>
        <tr><td>Safety cert, transport, rego</td><td>−${money(e.other)}</td></tr>
        <tr><td><b>Est. profit (mid resale)</b></td><td><b>${money(e.profit)}</b></td></tr></table></details>`
      : `<div class="maxbid"><span>${esc(e.why || 'No price guide for this model')} - check comparable sales</span></div>`;
    const comps = `https://www.facebook.com/marketplace/brisbane/search?query=${encodeURIComponent((it.year || '') + ' ' + (it.make || '') + ' ' + (it.model || '').split(' ')[0])}`;
    return `<article class="card">
      <a class="ph" href="${esc(it.url)}" target="_blank" rel="noopener">
        ${it.image ? `<img loading="lazy" referrerpolicy="no-referrer" src="${esc(it.image)}" alt="${esc(it.title)}" onerror="this.remove()">` : ''}<span class="noimg">${it.image ? '' : 'no photo'}</span>
        <div class="badges">${badges}</div>${rank && S.sort === 'profit' ? `<span class="rank">#${rank}</span>` : ''}
      </a>
      <button class="save${saved ? ' on' : ''}" data-save="${esc(it.key)}" aria-label="Save">${saved ? '★' : '☆'}</button>
      <div class="body">
        <div class="ttl">${esc(it.title)}</div>
        <div class="meta">${metaLine}${it.variant ? '<br>' + esc(it.variant) : ''}</div>
        ${money1}
        ${flags.length ? `<div class="flags">${flags.join('')}</div>` : ''}
        <a class="cta" href="${esc(it.url)}" target="_blank" rel="noopener">View on ${esc(it.src)} ↗</a>
        <a class="meta" href="${comps}" target="_blank" rel="noopener" style="text-align:center">Compare prices on Marketplace ↗</a>
      </div>
    </article>`;
  }

  // ---------- events
  let setupOpen = false;
  document.addEventListener('click', (ev) => {
    const t = ev.target.closest('[data-sort],[data-city],[data-save],[data-alert],[data-view],[data-group]');
    if (!t) return;
    if (t.dataset.sort) { S.sort = t.dataset.sort; shown = PAGE; }
    if (t.dataset.view) { S.view = t.dataset.view; shown = PAGE; alertFilter = null; window.scrollTo({ top: 0 }); }
    if (t.dataset.group) { groupOpen[t.dataset.group] = (groupOpen[t.dataset.group] || 12) + 24; }
    if (t.dataset.city) { const c = CITIES.find((x) => x[0] === t.dataset.city); S.loc = { label: c[0], lat: c[1], lon: c[2] }; setupOpen = false; shown = PAGE; }
    if (t.dataset.save) { const k = t.dataset.save; S.saved = S.saved.includes(k) ? S.saved.filter((x) => x !== k) : S.saved.concat(k); }
    if (t.dataset.alert !== undefined) { alertFilter = t.dataset.alert && alertFilter !== t.dataset.alert ? t.dataset.alert : null; shown = PAGE; window.scrollTo({ top: 0, behavior: 'smooth' }); }
    save(); render();
  });
  $('locBtn').addEventListener('click', () => { setupOpen = !setupOpen; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  $('useGps').addEventListener('click', () => {
    if (!navigator.geolocation) { $('gpsNote').textContent = 'Location is not available on this device - pick a city instead.'; return; }
    $('gpsNote').textContent = 'Finding you…';
    navigator.geolocation.getCurrentPosition((p) => {
      const near = CITIES.slice().sort((a, b) => Math.hypot(a[1] - p.coords.latitude, a[2] - p.coords.longitude) - Math.hypot(b[1] - p.coords.latitude, b[2] - p.coords.longitude))[0];
      S.loc = { label: 'near ' + near[0], lat: p.coords.latitude, lon: p.coords.longitude };
      setupOpen = false; $('gpsNote').textContent = ''; save(); render();
    }, () => { $('gpsNote').textContent = 'Could not get your location - pick a city instead.'; }, { timeout: 10000, maximumAge: 3600000 });
  });
  $('radius').addEventListener('change', (e) => { S.radius = Number(e.target.value); save(); render(); });
  $('cleanOnly').addEventListener('change', (e) => { S.cleanOnly = e.target.checked; save(); render(); });
  $('clearing').addEventListener('change', (e) => { S.clearing = e.target.checked; save(); render(); });
  $('maxSpend').addEventListener('change', (e) => { S.maxSpend = Number(e.target.value); save(); render(); });
  $('savedOnly').addEventListener('click', () => { S.savedOnly = !S.savedOnly; save(); render(); });
  $('more').addEventListener('click', () => { shown += PAGE; render(); });
  $('otherWrap').addEventListener('toggle', render);

  // "new since your last visit": remember the previous visit, then mark this one after a minute.
  if (!S.lastVisit || Date.now() - Date.parse(S.lastVisit) > 30 * 60000) { S.prevVisit = S.lastVisit; }
  save();
  setTimeout(() => { S.lastVisit = new Date().toISOString(); save(); }, 60000);
  refresh();
  setInterval(refresh, 5 * 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
