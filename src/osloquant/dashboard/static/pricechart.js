/* The stock page's price chart (oslo-quant, night session 10 Nov 2026 – docs/natt/endringer.md K1–K3).
 *
 * Draws one payload (<script type="application/json" id="pc-data">) with TradingView Lightweight Charts™ 5.2.1
 * (Apache-2.0, served from /static with its LICENSE and NOTICE; the attribution logo stays on). The data are the
 * store's own adjusted daily bars – nothing is fetched from TradingView. All series share the stock's sessions, so the
 * time scale has no weekend or holiday gaps and a logical index is an index into the payload's arrays.
 *
 * window.PriceChart exposes period(key), set(option, value) and state() for the page script and the browser tests.
 */
(function () {
  'use strict';
  var holder = document.getElementById('pc-data');
  var box = document.getElementById('chart-price');
  if (!holder || !box || !window.LightweightCharts) return;
  var LC = window.LightweightCharts;
  var D = JSON.parse(holder.textContent);
  var n = D.t.length;
  if (n < 2) return;

  // ------------------------------------------------------------------------------------------ formats (nb-NO)
  var NF = {
    p0: new Intl.NumberFormat('nb-NO', { maximumFractionDigits: 0 }),
    p2: new Intl.NumberFormat('nb-NO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    p4: new Intl.NumberFormat('nb-NO', { minimumFractionDigits: 3, maximumFractionDigits: 4 }),
    pct: new Intl.NumberFormat('nb-NO', { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: 'exceptZero' })
  };
  var COMPACT = new Intl.NumberFormat('nb-NO', { notation: 'compact', maximumFractionDigits: 1 });
  // one formatter for every axis (the library applies it to all panes): prices, and volume from a million up as «40 mill.»
  function price(p) { var a = Math.abs(p); return (a >= 1e6 ? COMPACT : a >= 1000 ? NF.p0 : a >= 1 ? NF.p2 : NF.p4).format(p); }
  function pct(x) { return NF.pct.format(x * 100) + ' %'; }
  function pctPoints(v) { return NF.pct.format(v) + ' %'; }
  function pad(x) { return (x < 10 ? '0' : '') + x; }
  function ymd(t) {
    if (typeof t === 'string') return t;
    if (typeof t === 'number') return new Date(t * 1000).toISOString().slice(0, 10);
    if (t && t.year) return t.year + '-' + pad(t.month) + '-' + pad(t.day);
    return '';
  }
  function dato(s, weekday) {
    var y = +s.slice(0, 4), m = +s.slice(5, 7), d = +s.slice(8, 10);
    var wd = weekday ? D.days[(new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7] + ' ' : '';
    return wd + d + '. ' + D.months[m - 1] + ' ' + y;
  }
  function tick(t, type) {
    var s = ymd(t); if (!s) return '';
    var y = s.slice(0, 4), m = +s.slice(5, 7), d = +s.slice(8, 10);
    if (type === 0) return y;                    // year
    if (type === 1) return D.months[m - 1];      // month
    if (type === 2) return d + '.';              // day of month
    return '';
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  var UP = '#0b7a4b', DOWN = '#b3261e', GRID = '#eef1f3', TEXT = '#4a5560', MUTED = '#8a96a0';
  var EV = {
    rapport: { position: 'aboveBar', shape: 'square', color: '#5c6770', text: 'R' },
    utbytte: { position: 'belowBar', shape: 'circle', color: '#0f7c7c', text: 'U' },
    vurdering: { position: 'aboveBar', shape: 'circle', color: '#c98500', text: 'V' },
    innside_buy: { position: 'belowBar', shape: 'arrowUp', color: UP, text: 'I' },
    innside_sell: { position: 'aboveBar', shape: 'arrowDown', color: DOWN, text: 'I' },
    innside: { position: 'inBar', shape: 'circle', color: MUTED, text: 'I' }
  };

  // ------------------------------------------------------------------------------------------ state
  var S = {
    type: 'area', period: D.default, log: false, cmp: { osebx: false, sector: false }, sma: { 50: false, 200: false },
    ev: { rapport: true, utbytte: true, innside: false, vurdering: true }, base: 0, color: UP, ret: null, i0: 0, i1: n - 1
  };
  var index = {}; D.t.forEach(function (t, i) { index[t] = i; });
  var byDay = {}; (D.events || []).forEach(function (e) { (byDay[e.t] = byDay[e.t] || []).push(e); });
  function sma(len) {
    var out = new Array(n), sum = 0;
    for (var i = 0; i < n; i++) { sum += D.c[i]; if (i >= len) sum -= D.c[i - len]; out[i] = i >= len - 1 ? sum / len : null; }
    return out;
  }
  var SMA = { 50: sma(50), 200: sma(200) };
  function comparing() { return S.cmp.osebx || S.cmp.sector; }
  function tf(v) { return comparing() ? (v / D.c[S.base] - 1) * 100 : v; }   // price, or % since the base session

  // ------------------------------------------------------------------------------------------ the chart
  var chart = LC.createChart(box, {
    autoSize: true,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: TEXT, fontSize: 11,
      fontFamily: 'Segoe UI, Arial, sans-serif', attributionLogo: true,
      panes: { separatorColor: GRID, separatorHoverColor: 'rgba(15,124,124,0.12)', enableResize: false } },
    grid: { vertLines: { visible: false }, horzLines: { color: GRID } },
    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.06 } },
    timeScale: { borderVisible: false, minBarSpacing: 0.01, rightOffset: 0, tickMarkFormatter: tick },
    crosshair: { mode: LC.CrosshairMode.Normal,
      vertLine: { color: '#9aa6ae', style: LC.LineStyle.Dashed, width: 1, labelBackgroundColor: '#4a5560' },
      horzLine: { color: '#9aa6ae', style: LC.LineStyle.Dashed, width: 1, labelBackgroundColor: '#4a5560' } },
    localization: { locale: 'nb-NO', timeFormatter: function (t) { var s = ymd(t); return s ? dato(s, true) : ''; } },
    handleScale: { axisPressedMouseMove: { time: true, price: false } }
  });
  // volume in its own pane under the prices: the price axis never runs below zero into the volume bars
  // (the pane keeps its axis: a pane without one breaks the library's layout; it reads «1,2 mill.»)
  var vol = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: 'custom', formatter: function (v) { return COMPACT.format(v); }, minMove: 1 },
    lastValueVisible: false, priceLineVisible: false }, 1);
  chart.priceScale('right', 1).applyOptions({ scaleMargins: { top: 0.15, bottom: 0 }, borderVisible: false });
  var panes = chart.panes();
  if (panes.length > 1) { panes[0].setStretchFactor(4); panes[1].setStretchFactor(1); }
  vol.setData(D.t.map(function (t, i) {
    var v = D.v[i]; if (v == null) return { time: t };
    return { time: t, value: v, color: i && D.c[i] < D.c[i - 1] ? 'rgba(179,38,30,0.28)' : 'rgba(11,122,75,0.26)' };
  }));
  var main = null, markers = null, plines = [], smaS = {}, cmpS = {};

  function autoscale(original) {           // keep the target and kill lines on screen in price mode
    var r = original();
    if (!r || comparing() || !D.lines || !D.lines.length) return r;
    D.lines.forEach(function (l) {
      r.priceRange.minValue = Math.min(r.priceRange.minValue, l.p);
      r.priceRange.maxValue = Math.max(r.priceRange.maxValue, l.p);
    });
    return r;
  }
  // Each series formats its own axis. A formatter on the whole chart would also write the volume pane's counts as per
  // cent when the price pane compares returns.
  var AXIS = { type: 'custom', minMove: 0.001, formatter: function (v) { return comparing() ? pctPoints(v) : price(v); } };
  function buildMain() {
    // the new series is added before the old one goes: the library drops a pane that becomes empty, and the volume
    // pane would then move up into the prices' place
    if (markers) { markers.detach(); markers = null; }
    var old = main;
    var common = { priceLineVisible: false, lastValueVisible: true, autoscaleInfoProvider: autoscale, priceFormat: AXIS };
    if (S.type === 'candles') {
      main = chart.addSeries(LC.CandlestickSeries, Object.assign({ upColor: UP, downColor: DOWN, borderUpColor: UP, borderDownColor: DOWN,
        wickUpColor: UP, wickDownColor: DOWN }, common), 0);
      main.setData(D.t.map(function (t, i) { return { time: t, open: tf(D.o[i]), high: tf(D.h[i]), low: tf(D.l[i]), close: tf(D.c[i]) }; }));
    } else {
      main = chart.addSeries(LC.AreaSeries, Object.assign({ lineWidth: 2, lineColor: S.color, topColor: fill(S.color, 0.16), bottomColor: fill(S.color, 0.01) }, common), 0);
      main.setData(D.t.map(function (t, i) { return { time: t, value: tf(D.c[i]) }; }));
    }
    if (old) chart.removeSeries(old);
    plines = [];
    markers = LC.createSeriesMarkers(main, []);
    drawMarkers(); drawLines();
  }
  function fill(hex, a) { var v = parseInt(hex.slice(1), 16); return 'rgba(' + (v >> 16) + ',' + ((v >> 8) & 255) + ',' + (v & 255) + ',' + a + ')'; }
  function drawMarkers() {
    var list = [];
    (D.events || []).forEach(function (e) {
      if (!S.ev[e.k]) return;
      var st = EV[e.k === 'innside' && e.side ? 'innside_' + e.side : e.k] || EV[e.k];
      list.push({ time: e.t, position: st.position, shape: st.shape, color: st.color, text: st.text, size: 0.9 });
    });
    list.sort(function (a, b) { return a.time < b.time ? -1 : a.time > b.time ? 1 : 0; });
    markers.setMarkers(list);
    S.markers = list.length;
  }
  function drawLines() {
    plines.forEach(function (l) { try { main.removePriceLine(l); } catch (e) { /* the line went with its old series */ } }); plines = [];
    var add = function (p, color, title, width) {
      plines.push(main.createPriceLine({ price: tf(p), color: color, lineWidth: width || 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true, title: title }));
    };
    add(D.prev, '#9aa6ae', 'Forrige slutt');
    (D.lines || []).forEach(function (l) {
      add(l.p, l.k === 'kill' ? DOWN : '#0f7c7c', l.title + ' ' + price(l.p) + ' (' + pct(l.p / D.last - 1) + ')', 1);
    });
    S.lines = plines.length;
  }
  function drawSma() {
    [50, 200].forEach(function (len) {
      if (S.sma[len] && !smaS[len]) {
        smaS[len] = chart.addSeries(LC.LineSeries, { color: len === 50 ? '#c98500' : '#6a5acd', lineWidth: 1, priceLineVisible: false,
          lastValueVisible: false, crosshairMarkerVisible: false, title: 'SMA ' + len, priceFormat: AXIS }, 0);
      }
      if (!S.sma[len] && smaS[len]) { chart.removeSeries(smaS[len]); delete smaS[len]; }
      if (smaS[len]) smaS[len].setData(D.t.map(function (t, i) { var v = SMA[len][i]; return v == null ? { time: t } : { time: t, value: tf(v) }; }));
    });
  }
  function drawCmp() {
    Object.keys(S.cmp).forEach(function (k) {
      var c = D.cmp && D.cmp[k];
      if (S.cmp[k] && c && !cmpS[k]) {
        cmpS[k] = chart.addSeries(LC.LineSeries, { color: k === 'osebx' ? '#3b6fb6' : '#8a6d3b', lineWidth: 1.5, priceLineVisible: false,
          lastValueVisible: true, crosshairMarkerVisible: false, title: c.short, priceFormat: AXIS }, 0);
      }
      if (!S.cmp[k] && cmpS[k]) { chart.removeSeries(cmpS[k]); delete cmpS[k]; }
      if (cmpS[k]) {
        var b = c.v[S.base];
        cmpS[k].setData(D.t.map(function (t, i) { var v = c.v[i]; return v == null || b == null ? { time: t } : { time: t, value: (v / b - 1) * 100 }; }));
      }
    });
  }
  function baseFor(i0) {                    // the first session from i0 where the stock and every active comparison have a value
    for (var i = i0; i < n; i++) {
      var ok = true;
      Object.keys(S.cmp).forEach(function (k) { if (S.cmp[k] && (!D.cmp[k] || D.cmp[k].v[i] == null)) ok = false; });
      if (ok) return i;
    }
    return i0;
  }
  function redraw() {
    if (comparing()) S.base = baseFor(S.i0);
    buildMain(); drawSma(); drawCmp();
    chart.priceScale('right').applyOptions({ mode: S.log && !comparing() ? LC.PriceScaleMode.Logarithmic : LC.PriceScaleMode.Normal });
  }

  // ------------------------------------------------------------------------------------------ range, colour, return
  var head = document.querySelector('.pc-ret');
  function show(i0, i1) {
    chart.timeScale().setVisibleLogicalRange({ from: i0 - 0.5, to: i1 + 0.5 });
    paint(i0, i1);
  }
  function paint(i0, i1) {
    S.i0 = i0; S.i1 = i1;
    S.ret = D.c[i1] / D.c[i0] - 1;
    var color = S.ret >= 0 ? UP : DOWN;
    if (color !== S.color) {
      S.color = color;
      if (main && S.type === 'area') main.applyOptions({ lineColor: color, topColor: fill(color, 0.16), bottomColor: fill(color, 0.01) });
    }
    var p = periodByKey(S.period);
    var lbl = p ? p.label : 'Synlig';
    if (!head) return;
    if (comparing()) {                       // every line from the same base session, so the numbers match the chart
      var b = S.base, parts = [esc(D.code) + ' <b class="' + (D.c[i1] >= D.c[b] ? 'up' : 'down') + '">' + pct(D.c[i1] / D.c[b] - 1) + '</b>'];
      Object.keys(S.cmp).forEach(function (k) {
        var c = D.cmp[k]; if (!S.cmp[k] || !c || c.v[b] == null || c.v[i1] == null) return;
        parts.push(esc(c.short) + ' <b class="' + (c.v[i1] >= c.v[b] ? 'up' : 'down') + '">' + pct(c.v[i1] / c.v[b] - 1) + '</b>');
      });
      head.innerHTML = esc(lbl) + ': ' + parts.join(' · ') + ' <span class="src">' + esc(dato(D.t[b]) + ' – ' + dato(D.t[i1])) + ', rebasert til ' + esc(dato(D.t[b])) + '</span>';
      head.title = 'Prosent siden sluttkursen ' + dato(D.t[b]) + ' – første dag i perioden der alle linjene har kurs. ' + D.src;
      return;
    }
    head.innerHTML = esc(lbl) + ' <b class="' + (S.ret >= 0 ? 'up' : 'down') + '">' + pct(S.ret) + '</b> <span class="src">' + esc(dato(D.t[i0]) + ' – ' + dato(D.t[i1])) + '</span>';
    head.title = 'Sluttkurs ' + dato(D.t[i1]) + ' mot sluttkurs ' + dato(D.t[i0]) + ', justert for utbytte og splitt (' + D.src + ')';
  }
  function periodByKey(k) { return (D.periods || []).filter(function (p) { return p.key === k; })[0]; }
  // a range change counts as the reader's own zoom or drag only right after they touched the chart – a resize or the
  // page's own period buttons never clear the active period
  var touched = 0;
  ['wheel', 'pointerdown', 'touchstart', 'keydown'].forEach(function (ev) { box.addEventListener(ev, function () { touched = Date.now(); }, { passive: true }); });
  box.addEventListener('pointermove', function (e) { if (e.buttons) touched = Date.now(); }, { passive: true });
  chart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
    if (!r || Date.now() - touched > 1500) return;
    var i0 = Math.max(0, Math.ceil(r.from - 1e-6)), i1 = Math.min(n - 1, Math.floor(r.to + 1e-6));
    if (i1 <= i0 || (i0 === S.i0 && i1 === S.i1)) return;
    S.period = null;
    document.querySelectorAll('button.per[data-p]').forEach(function (b) { b.classList.remove('on'); });
    paint(i0, i1); toolState();
  });
  function period(key) {
    var p = periodByKey(key);
    if (!p || !p.enough) return false;
    S.period = key;
    var i0 = index[p.x0] != null ? index[p.x0] : 0, i1 = index[p.x1] != null ? index[p.x1] : n - 1;
    if (key !== '5a' && key !== 'maks') S.log = false;
    S.i0 = i0;
    redraw(); show(i0, i1); toolState();
    document.querySelectorAll('button.per[data-p]').forEach(function (b) { b.classList.toggle('on', b.dataset.p === key); });
    return true;
  }

  // ------------------------------------------------------------------------------------------ hover box
  var tip = document.querySelector('.pc-tip');
  chart.subscribeCrosshairMove(function (param) {
    if (!tip) return;
    if (!param.point || param.logical == null || param.point.x < 0 || param.point.y < 0) { tip.hidden = true; return; }
    var i = Math.round(param.logical);
    if (i < 0 || i >= n) { tip.hidden = true; return; }
    var rows = ['<div class="d">' + esc(dato(D.t[i], true)) + '</div>'];
    var ch = i ? D.c[i] / D.c[i - 1] - 1 : null;
    rows.push('<div><span>Sluttkurs</span><b>' + price(D.c[i]) + '</b></div>');
    if (ch != null) rows.push('<div><span>Endring</span><b class="' + (ch >= 0 ? 'up' : 'down') + '">' + pct(ch) + '</b></div>');
    if (S.type === 'candles') rows.push('<div><span>Åpning · høy · lav</span><b>' + price(D.o[i]) + ' · ' + price(D.h[i]) + ' · ' + price(D.l[i]) + '</b></div>');
    if (D.v[i] != null) rows.push('<div><span>Volum</span><b>' + NF.p0.format(D.v[i]) + '</b></div>');
    [50, 200].forEach(function (len) { if (S.sma[len] && SMA[len][i] != null) rows.push('<div><span>SMA ' + len + '</span><b>' + price(SMA[len][i]) + '</b></div>'); });
    if (comparing()) {
      rows.push('<div><span>' + esc(D.code) + ' siden ' + esc(dato(D.t[S.base])) + '</span><b>' + pct(D.c[i] / D.c[S.base] - 1) + '</b></div>');
      Object.keys(S.cmp).forEach(function (k) {
        var c = D.cmp[k]; if (!S.cmp[k] || !c || c.v[i] == null || c.v[S.base] == null) return;
        rows.push('<div><span>' + esc(c.short) + '</span><b>' + pct(c.v[i] / c.v[S.base] - 1) + '</b></div>');
      });
    }
    (byDay[D.t[i]] || []).forEach(function (e) { if (S.ev[e.k]) rows.push('<div class="ev ' + e.k + '">' + esc(e.txt) + '<small>' + esc(e.src) + '</small></div>'); });
    tip.innerHTML = rows.join('');
    tip.hidden = false;
    var W = box.clientWidth, H = box.clientHeight, w = tip.offsetWidth, h = tip.offsetHeight, gap = 18;
    var px = param.point.x, py = param.point.y;
    if (param.paneIndex) {                   // the point is relative to its pane: add the panes above it
      var ps = chart.panes();
      for (var k = 0; k < param.paneIndex && k < ps.length; k++) py += ps[k].getHeight() + 1;
    }
    var x = px + gap + w <= W - 64 ? px + gap : px - gap - w;                 // beside the point, never on it
    x = Math.max(4, x);
    if (x <= px && x + w >= px) x = px + gap;                                  // a very wide box still clears it
    var y = Math.min(Math.max(4, py - h / 2), Math.max(4, H - h - 4));
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
    S.tip = { x: x, y: y, w: w, h: h, px: px, py: py, pane: param.paneIndex || 0 };
  });
  box.addEventListener('mouseleave', function () { if (tip) tip.hidden = true; });

  // ------------------------------------------------------------------------------------------ the toolbar
  var tools = document.querySelector('.pc-tools');
  function toolState() {
    if (!tools) return;
    tools.querySelectorAll('[data-type]').forEach(function (b) { b.classList.toggle('on', b.dataset.type === S.type); b.setAttribute('aria-pressed', b.dataset.type === S.type); });
    var logOk = (S.period === '5a' || S.period === 'maks') && !comparing();
    tools.querySelectorAll('[data-opt="log"]').forEach(function (b) {
      b.disabled = !logOk; b.classList.toggle('on', S.log && logOk); b.setAttribute('aria-pressed', S.log && logOk);
      b.title = logOk ? 'Log-skala: like prosentendringer får lik høyde. For lange perioder.' : (comparing() ? 'Log-skala er av mens du sammenligner (aksen viser prosent).' : 'Log-skala er bare for 5Å og Maks.');
    });
    tools.querySelectorAll('[data-cmp]').forEach(function (b) { b.classList.toggle('on', !!S.cmp[b.dataset.cmp]); b.setAttribute('aria-pressed', !!S.cmp[b.dataset.cmp]); });
    tools.querySelectorAll('[data-sma]').forEach(function (b) { b.classList.toggle('on', !!S.sma[b.dataset.sma]); b.setAttribute('aria-pressed', !!S.sma[b.dataset.sma]); });
    tools.querySelectorAll('[data-ev]').forEach(function (b) { b.classList.toggle('on', !!S.ev[b.dataset.ev]); b.setAttribute('aria-pressed', !!S.ev[b.dataset.ev]); });
  }
  function set(opt, value) {
    if (opt === 'type') { S.type = value === 'candles' ? 'candles' : 'area'; redraw(); paint(S.i0, S.i1); }
    else if (opt === 'log') { S.log = !!value && (S.period === '5a' || S.period === 'maks') && !comparing(); redraw(); }
    else if (opt === 'osebx' || opt === 'sector') {
      if (value && !(D.cmp && D.cmp[opt])) return false;
      S.cmp[opt] = !!value; if (comparing()) S.log = false; redraw(); paint(S.i0, S.i1);
    }
    else if (opt === 'sma50' || opt === 'sma200') { S.sma[opt.slice(3)] = !!value; drawSma(); }
    else if (opt in S.ev) { S.ev[opt] = !!value; drawMarkers(); }
    else return false;
    toolState();
    return true;
  }
  if (tools) {
    tools.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b || b.disabled) return;
      if (b.dataset.type) set('type', b.dataset.type);
      else if (b.dataset.opt === 'log') set('log', !S.log);
      else if (b.dataset.cmp) set(b.dataset.cmp, !S.cmp[b.dataset.cmp]);
      else if (b.dataset.sma) set('sma' + b.dataset.sma, !S.sma[b.dataset.sma]);
      else if (b.dataset.ev) set(b.dataset.ev, !S.ev[b.dataset.ev]);
    });
  }

  // a chart drawn inside a hidden tab has no width, and a resize moves the window: show the same sessions again
  S.w = box.clientWidth;
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      var W = box.clientWidth;
      if (W > 0 && W !== S.w) { S.w = W; setTimeout(function () { show(S.i0, S.i1); }, 0); }
    }).observe(box);
  }

  window.PriceChart = {
    period: period, set: set,
    state: function () {
      var r = chart.timeScale().getVisibleLogicalRange();
      return { type: S.type, period: S.period, log: S.log, cmp: Object.assign({}, S.cmp), sma: Object.assign({}, S.sma), ev: Object.assign({}, S.ev),
        markers: S.markers, lines: S.lines, color: S.color, ret: S.ret, from: D.t[S.i0], to: D.t[S.i1], base: D.t[S.base], n: n,
        logical: r ? { from: r.from, to: r.to } : null, scaleMode: chart.priceScale('right').options().mode, tip: S.tip || null, width: box.clientWidth,
        panes: chart.panes().length, mainPane: main.getPane().paneIndex(), volPane: vol.getPane().paneIndex() };
    },
    chart: chart
  };
  if (!period(S.period)) { S.period = null; redraw(); show(0, n - 1); }
  toolState();
})();
