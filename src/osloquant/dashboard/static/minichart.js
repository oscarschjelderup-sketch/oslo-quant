/* Small line charts for the macro page (D65), drawn with TradingView Lightweight Charts like the price chart.
   Every element with class "mc" and a data-key gets the series of that key from the JSON block #mc-data.
   One period applies to all charts on the page: MiniCharts.period('3m' | '1a' | '3a'). Our own code. */
(function () {
  'use strict';
  var LC = window.LightweightCharts, holder = document.getElementById('mc-data');
  if (!LC || !holder) return;
  var DATA = JSON.parse(holder.textContent || '{}');
  var UP = '#0b7a4b', DOWN = '#b3261e', FLAT = '#5c6770', GRID = '#eef1f3', TEXT = '#4a5560';
  var MONTHS = ['jan.', 'feb.', 'mars', 'april', 'mai', 'juni', 'juli', 'aug.', 'sep.', 'okt.', 'nov.', 'des.'];
  var MONTHS_BACK = { '3m': 3, '1a': 12, '3a': 36 };
  var charts = [], current = '1a';

  function fill(hex, a) { var n = parseInt(hex.slice(1), 16); return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')'; }
  function nf(d) { return new Intl.NumberFormat('nb-NO', { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function dato(s) { var p = s.split('-'); return parseInt(p[2], 10) + '. ' + MONTHS[parseInt(p[1], 10) - 1] + ' ' + p[0]; }
  function ymd(t) { return typeof t === 'string' ? t : (t && t.year ? t.year + '-' + String(t.month).padStart(2, '0') + '-' + String(t.day).padStart(2, '0') : ''); }
  function tick(t, type) { var s = ymd(t); if (!s) return ''; var p = s.split('-'); return type === 0 ? p[0] : type === 1 ? MONTHS[parseInt(p[1], 10) - 1] : parseInt(p[2], 10) + '. ' + MONTHS[parseInt(p[1], 10) - 1]; }

  function firstIndex(t, months) {
    var last = new Date(t[t.length - 1] + 'T00:00:00Z');
    var back = new Date(Date.UTC(last.getUTCFullYear(), last.getUTCMonth() - months, last.getUTCDate())).toISOString().slice(0, 10);
    for (var i = 0; i < t.length; i++) if (t[i] >= back) return i;
    return 0;
  }

  function build(el) {
    var d = DATA[el.dataset.key];
    if (!d || d.t.length < 2) return null;
    var fmt = nf(d.d), suffix = d.pct ? ' %' : '';
    var chart = LC.createChart(el, {
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: TEXT, fontSize: 10.5, fontFamily: '"Segoe UI",Arial,Helvetica,sans-serif', attributionLogo: false },   // the page carries the notice and the link once, under the charts
      grid: { vertLines: { visible: false }, horzLines: { color: GRID } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true, tickMarkFormatter: tick, rightOffset: 0 },
      crosshair: { mode: LC.CrosshairMode.Magnet, vertLine: { color: '#9aa6ae', style: LC.LineStyle.Dashed, width: 1, labelVisible: false },
        horzLine: { color: '#9aa6ae', style: LC.LineStyle.Dashed, width: 1, labelBackgroundColor: '#4a5560' } },
      handleScroll: false, handleScale: false,
      localization: { locale: 'nb-NO', timeFormatter: function (t) { var s = ymd(t); return s ? dato(s) : ''; } }
    });
    var series = chart.addSeries(LC.AreaSeries, { lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
      priceFormat: { type: 'custom', minMove: Math.pow(10, -d.d), formatter: function (v) { return fmt.format(v) + suffix; } } });
    series.setData(d.t.map(function (t, i) { return { time: t, value: d.v[i] }; }));
    var tip = document.createElement('div');
    tip.className = 'mc-tip';
    el.appendChild(tip);
    chart.subscribeCrosshairMove(function (p) {
      var pt = p && p.time && p.seriesData ? p.seriesData.get(series) : null;
      if (!pt) { tip.style.display = 'none'; return; }
      tip.textContent = dato(ymd(p.time)) + ': ' + fmt.format(pt.value) + suffix;
      tip.style.display = 'block';
    });
    var c = { el: el, chart: chart, series: series, d: d };
    show(c, current);
    return c;
  }

  function show(c, key) {
    var t = c.d.t, i0 = firstIndex(t, MONTHS_BACK[key] || 12), last = t.length - 1;
    var colour = c.d.v[last] > c.d.v[i0] ? UP : c.d.v[last] < c.d.v[i0] ? DOWN : FLAT;
    c.series.applyOptions({ lineColor: colour, topColor: fill(colour, 0.14), bottomColor: fill(colour, 0.01) });
    c.chart.timeScale().setVisibleLogicalRange({ from: i0 - 0.5, to: last + 0.5 });
  }

  function period(key) {
    current = key;
    charts.forEach(function (c) { show(c, key); });
    document.querySelectorAll('#mc-periods [data-mp]').forEach(function (b) { b.classList.toggle('on', b.dataset.mp === key); });
  }

  document.querySelectorAll('.mc[data-key]').forEach(function (el) { var c = build(el); if (c) charts.push(c); });
  document.querySelectorAll('#mc-periods [data-mp]').forEach(function (b) { b.addEventListener('click', function () { period(b.dataset.mp); }); });
  new ResizeObserver(function () { charts.forEach(function (c) { show(c, current); }); }).observe(document.body);
  window.MiniCharts = { period: period, state: function () { return { period: current, charts: charts.length, keys: charts.map(function (c) { return c.el.dataset.key; }) }; } };
})();
