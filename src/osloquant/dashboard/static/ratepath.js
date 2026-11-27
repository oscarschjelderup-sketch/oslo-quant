/* The policy rate against Norges Bank's rate paths on the macro page (D73), drawn with TradingView Lightweight Charts
   like the price chart. Data: the JSON block #rp-data – {actual: {t, v}, paths: [{name, published, rank, strong, t, v}]}.
   The actual rate is a step line; each path is a line through its quarters' middles, the newest darkest. Our own code. */
(function () {
  'use strict';
  var LC = window.LightweightCharts, holder = document.getElementById('rp-data'), el = document.getElementById('rp-chart');
  if (!LC || !holder || !el) return;
  var D = JSON.parse(holder.textContent || '{}');
  var GRID = '#eef1f3', TEXT = '#4a5560', ACTUAL = '#1d2a33';
  var SHADES = ['#0b5cad', '#4f8fd0', '#93b9e2'], OLD = '#c9d2d9';
  var MONTHS = ['jan.', 'feb.', 'mars', 'april', 'mai', 'juni', 'juli', 'aug.', 'sep.', 'okt.', 'nov.', 'des.'];
  var nf = new Intl.NumberFormat('nb-NO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function ymd(t) { return typeof t === 'string' ? t : (t && t.year ? t.year + '-' + String(t.month).padStart(2, '0') + '-' + String(t.day).padStart(2, '0') : ''); }
  function dato(s) { var p = s.split('-'); return parseInt(p[2], 10) + '. ' + MONTHS[parseInt(p[1], 10) - 1] + ' ' + p[0]; }
  function kvartal(s) { var p = s.split('-'); return (Math.floor((parseInt(p[1], 10) - 1) / 3) + 1) + '. kv. ' + p[0]; }
  function tick(t, type) { var s = ymd(t); if (!s) return ''; var p = s.split('-'); return type === 0 ? p[0] : MONTHS[parseInt(p[1], 10) - 1]; }

  var chart = LC.createChart(el, {
    autoSize: true,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: TEXT, fontSize: 11, fontFamily: '"Segoe UI",Arial,Helvetica,sans-serif', attributionLogo: false },
    grid: { vertLines: { visible: false }, horzLines: { color: GRID } },
    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.08 } },
    timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true, tickMarkFormatter: tick },
    crosshair: { mode: LC.CrosshairMode.Normal, vertLine: { color: '#9aa6ae', style: LC.LineStyle.Dashed, width: 1, labelVisible: false },
      horzLine: { color: '#9aa6ae', style: LC.LineStyle.Dashed, width: 1, labelBackgroundColor: '#4a5560' } },
    handleScroll: false, handleScale: false,
    localization: { locale: 'nb-NO', priceFormatter: function (v) { return nf.format(v) + ' %'; }, timeFormatter: function (t) { var s = ymd(t); return s ? dato(s) : ''; } }
  });
  var fmt = { type: 'custom', minMove: 0.01, formatter: function (v) { return nf.format(v) + ' %'; } };
  var lines = [];
  // every Friday of the window as whitespace, so the time axis is even: the library spaces points by count, not by date
  if (D.grid && D.grid.length) chart.addSeries(LC.LineSeries, { visible: false, priceLineVisible: false, lastValueVisible: false })
    .setData(D.grid.map(function (t) { return { time: t }; }));
  // oldest first, so the newest paths are drawn on top
  (D.paths || []).slice().sort(function (a, b) { return b.rank - a.rank; }).forEach(function (p) {
    var colour = p.rank < SHADES.length ? SHADES[p.rank] : OLD;
    var s = chart.addSeries(LC.LineSeries, { color: colour, lineWidth: p.rank === 0 ? 3 : 2, priceLineVisible: false, lastValueVisible: false,
      crosshairMarkerVisible: p.rank < SHADES.length, pointMarkersVisible: p.rank === 0, priceFormat: fmt });
    s.setData(p.t.map(function (t, i) { return { time: t, value: p.v[i] }; }));
    var byq = {}; p.q.forEach(function (q, i) { byq[q] = p.v[i]; });     // a path is a quarterly average: hovering any week of the quarter shows it
    lines.push({ s: s, name: p.name, path: true, rank: p.rank, byq: byq });
  });
  if (D.actual && D.actual.t.length) {
    var a = chart.addSeries(LC.LineSeries, { color: ACTUAL, lineWidth: 3, lineType: LC.LineType.WithSteps, priceLineVisible: false, lastValueVisible: true, priceFormat: fmt });
    a.setData(D.actual.t.map(function (t, i) { return { time: t, value: D.actual.v[i] }; }));
    lines.push({ s: a, name: 'Faktisk styringsrente', path: false });
  }
  chart.timeScale().fitContent();

  var tip = document.createElement('div');
  tip.className = 'mc-tip';
  el.appendChild(tip);
  chart.subscribeCrosshairMove(function (p) {
    if (!p || !p.time || !p.seriesData) { tip.style.display = 'none'; return; }
    var s = ymd(p.time), q = kvartal(s), out = [];
    lines.slice().reverse().forEach(function (l) {
      if (l.path) {
        if (l.rank < SHADES.length && l.byq[q] !== undefined) out.push(l.name + ' for ' + q + ': ' + nf.format(l.byq[q]) + ' %');
      } else {
        var pt = p.seriesData.get(l.s);
        if (pt) out.push('Faktisk, uken til ' + dato(s) + ': ' + nf.format(pt.value) + ' %');
      }
    });
    if (!out.length) { tip.style.display = 'none'; return; }
    tip.textContent = out.join(' · ');
    tip.style.display = 'block';
  });
  window.RatePath = { state: function () { return { lines: lines.length, paths: (D.paths || []).length, actual: (D.actual && D.actual.t.length) || 0 }; } };
})();
