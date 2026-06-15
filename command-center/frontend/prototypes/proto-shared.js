/* Shared synthetic data + canvas chart engine for the layout prototypes.
   Zero dependencies so the files open straight from disk. */
(function (global) {
  'use strict';

  const T = {
    green: '#34d399', red: '#f87171', accent: '#2dd4bf',
    grid: 'rgba(148,163,184,0.07)', axis: 'rgba(148,163,184,0.18)',
    text3: '#5d6b7e', text2: '#9aa7b8',
  };

  // deterministic RNG so both prototypes render identically every reload
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---------- synthetic dataset ----------
  const DATA = (function build() {
    const rnd = mulberry32(7);
    const start = Date.UTC(2021, 5, 14), end = Date.UTC(2026, 5, 14);

    // equity: steady riser with two visible drawdown valleys
    const N = 280, equity = [];
    let v = 5000;
    for (let i = 0; i < N; i++) {
      let drift = 2.45;
      if (i > 118 && i < 138) drift = -3.2;     // mid-2023 valley
      if (i > 228 && i < 246) drift = -4.0;      // mid-2025 valley
      v += drift + (rnd() - 0.5) * 30;
      equity.push({ t: start + (end - start) * i / (N - 1), v });
    }

    // drawdown from peak (%)
    let peak = -Infinity;
    const dd = equity.map(p => {
      peak = Math.max(peak, p.v);
      return { t: p.t, v: (p.v - peak) / peak * 100 };
    });

    // daily P&L: 64 bars, ~60% green, a few tall ones
    const daily = [];
    for (let i = 0; i < 64; i++) {
      let val = (rnd() - 0.4) * 900;
      if (rnd() > 0.86) val *= 1.9;
      daily.push({ i, v: val });
    }

    // candles: early sharp dip then a long grind up
    const C = 130, candles = [];
    let px = 214.7;
    for (let i = 0; i < C; i++) {
      let drift = 0.012;
      if (i > 4 && i < 11) drift = -0.62;        // the dip to ~210.7
      if (i >= 11 && i < 16) drift = 0.5;        // snap back
      const o = px;
      const move = drift + (rnd() - 0.5) * 0.55;
      const c = o + move;
      const hi = Math.max(o, c) + rnd() * 0.35;
      const lo = Math.min(o, c) - rnd() * 0.35;
      candles.push({ i, o, h: hi, l: lo, c });
      px = c;
    }

    return {
      equity, dd, daily, candles,
      dir: {
        long:  { win: 25, trades: 64, pnl: 118, won: 16, lost: 48 },
        short: { win: 36, trades: 41, pnl: 502, won: 23, lost: 18 },
      },
      // ties out to headline: net +$628, 64 trades
      regimes: [
        { name: 'TRENDING',        color: '#06b6d4', pnl:  420, win: 68, trades: 22 },
        { name: 'HIGH_VOLATILITY', color: '#ef4444', pnl:  240, win: 62, trades:  9 },
        { name: 'TRANSITIONING',   color: '#8b5cf6', pnl:   60, win: 55, trades: 11 },
        { name: 'RANGING',         color: '#f59e0b', pnl:  -45, win: 48, trades: 14 },
        { name: 'LOW_VOLATILITY',  color: '#64748b', pnl:  -47, win: 50, trades:  8 },
      ],
    };
  })();

  // ---------- helpers ----------
  function setup(canvas) {
    const dpr = global.devicePixelRatio || 1;
    const r = canvas.getBoundingClientRect();
    const w = Math.max(1, r.width), h = Math.max(1, r.height);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }
  const fmtK = v => Math.abs(v) >= 1000 ? '$' + (v / 1000).toFixed(1) + 'k' : '$' + v.toFixed(0);
  function fmtDate(t) {
    const d = new Date(t);
    const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()];
    return m + " '" + String(d.getUTCFullYear()).slice(2);
  }
  function gridY(ctx, w, padL, padT, plotH, ticks, fmt, vmin, vmax) {
    ctx.font = '10px ui-sans-serif, system-ui';
    ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    for (let k = 0; k <= ticks; k++) {
      const yy = padT + plotH * k / ticks;
      const val = vmax - (vmax - vmin) * k / ticks;
      ctx.strokeStyle = T.grid; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(w - 8, yy); ctx.stroke();
      ctx.fillStyle = T.text3;
      ctx.fillText(fmt(val), padL - 6, yy);
    }
  }
  function xLabels(ctx, pts, padT, plotH, count) {
    ctx.fillStyle = T.text3; ctx.font = '10px ui-sans-serif, system-ui';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let k = 0; k <= count; k++) {
      const idx = Math.round((pts.length - 1) * k / count);
      const p = pts[idx];
      ctx.fillText(fmtDate(p.t), p.px, padT + plotH + 6);
    }
  }

  // ---------- chart drawers ----------
  function drawEquity(canvas, opts) {
    opts = opts || {};
    const { ctx, w, h } = setup(canvas);
    const padL = 46, padT = 10, padB = 22, padR = 8;
    const plotW = w - padL - padR, plotH = h - padT - padB;
    const data = DATA.equity;
    let vmin = Infinity, vmax = -Infinity;
    data.forEach(p => { vmin = Math.min(vmin, p.v); vmax = Math.max(vmax, p.v); });
    const pad = (vmax - vmin) * 0.08; vmin -= pad; vmax += pad;
    const X = i => padL + plotW * i / (data.length - 1);
    const Y = v => padT + plotH * (1 - (v - vmin) / (vmax - vmin));

    if (opts.regime) {
      const bands = [[0,0.30,'rgba(6,182,212,0.07)'],[0.30,0.44,'rgba(239,68,68,0.07)'],
        [0.44,0.60,'rgba(139,92,246,0.07)'],[0.60,0.82,'rgba(245,158,11,0.07)'],
        [0.82,1,'rgba(100,116,139,0.08)']];
      bands.forEach(b => { ctx.fillStyle = b[2];
        ctx.fillRect(padL + plotW*b[0], padT, plotW*(b[1]-b[0]), plotH); });
    }

    gridY(ctx, w, padL, padT, plotH, 4, fmtK, vmin, vmax);

    const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
    grad.addColorStop(0, 'rgba(52,211,153,0.28)');
    grad.addColorStop(1, 'rgba(52,211,153,0)');
    ctx.beginPath();
    data.forEach((p, i) => { const x = X(i), y = Y(p.v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.lineTo(X(data.length - 1), padT + plotH); ctx.lineTo(X(0), padT + plotH); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();

    ctx.beginPath();
    data.forEach((p, i) => { const x = X(i), y = Y(p.v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.strokeStyle = T.green; ctx.lineWidth = 1.8; ctx.stroke();

    const pts = data.map((p, i) => ({ px: X(i), py: Y(p.v), t: p.t, v: p.v }));
    xLabels(ctx, pts, padT, plotH, 6);
    canvas._hover = { pts, draw: () => drawEquity(canvas, opts),
      label: p => `<span class="t-k">${fmtDate(p.t)}</span>  <b>${fmtK(p.v)}</b>`, color: T.green };
  }

  function drawDrawdown(canvas) {
    const { ctx, w, h } = setup(canvas);
    const padL = 40, padT = 8, padB = 16, padR = 8;
    const plotW = w - padL - padR, plotH = h - padT - padB;
    const data = DATA.dd;
    let vmin = 0; data.forEach(p => vmin = Math.min(vmin, p.v));
    vmin *= 1.15;
    const X = i => padL + plotW * i / (data.length - 1);
    const Y = v => padT + plotH * (v / vmin);          // 0 at top, vmin at bottom

    gridY(ctx, w, padL, padT, plotH, 3, v => v.toFixed(1) + '%', vmin, 0);

    const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
    grad.addColorStop(0, 'rgba(248,113,113,0)');
    grad.addColorStop(1, 'rgba(248,113,113,0.30)');
    ctx.beginPath(); ctx.moveTo(X(0), padT);
    data.forEach((p, i) => ctx.lineTo(X(i), Y(p.v)));
    ctx.lineTo(X(data.length - 1), padT); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();

    ctx.beginPath();
    data.forEach((p, i) => { const x = X(i), y = Y(p.v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.strokeStyle = T.red; ctx.lineWidth = 1.3; ctx.stroke();
  }

  function drawDaily(canvas) {
    const { ctx, w, h } = setup(canvas);
    const padL = 44, padT = 10, padB = 16, padR = 8;
    const plotW = w - padL - padR, plotH = h - padT - padB;
    const data = DATA.daily;
    let m = 0; data.forEach(p => m = Math.max(m, Math.abs(p.v))); m *= 1.1;
    const zero = padT + plotH / 2;
    const bw = plotW / data.length * 0.62;

    gridY(ctx, w, padL, padT, plotH, 4, fmtK, -m, m);
    data.forEach((p, i) => {
      const x = padL + plotW * (i + 0.5) / data.length;
      const hgt = Math.abs(p.v) / m * (plotH / 2);
      ctx.fillStyle = p.v >= 0 ? T.green : T.red;
      ctx.globalAlpha = 0.9;
      ctx.fillRect(x - bw / 2, p.v >= 0 ? zero - hgt : zero, bw, hgt);
      ctx.globalAlpha = 1;
    });
    ctx.strokeStyle = T.axis; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, zero); ctx.lineTo(w - padR, zero); ctx.stroke();
  }

  function drawCandles(canvas, opts) {
    opts = opts || {};
    const { ctx, w, h } = setup(canvas);
    const padL = 8, padT = 10, padB = 22, padR = 52;
    const plotW = w - padL - padR, plotH = h - padT - padB;
    const data = DATA.candles;
    let lo = Infinity, hi = -Infinity;
    data.forEach(c => { lo = Math.min(lo, c.l); hi = Math.max(hi, c.h); });
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const X = i => padL + plotW * (i + 0.5) / data.length;
    const Y = v => padT + plotH * (1 - (v - lo) / (hi - lo));
    const cw = plotW / data.length * 0.62;

    // y axis on the right
    ctx.font = '10px ui-sans-serif, system-ui'; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
    for (let k = 0; k <= 4; k++) {
      const yy = padT + plotH * k / 4, val = hi - (hi - lo) * k / 4;
      ctx.strokeStyle = T.grid; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(w - padR, yy); ctx.stroke();
      ctx.fillStyle = T.text3; ctx.fillText(val.toFixed(2), w - padR + 6, yy);
    }

    data.forEach(c => {
      const x = X(c.i), up = c.c >= c.o, col = up ? T.green : T.red;
      ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, Y(c.h)); ctx.lineTo(x, Y(c.l)); ctx.stroke();
      const yo = Y(c.o), yc = Y(c.c);
      ctx.fillRect(x - cw / 2, Math.min(yo, yc), cw, Math.max(1, Math.abs(yc - yo)));
    });

    const pts = data.map(c => ({ px: X(c.i), py: Y(c.c), t: DATA.equity[0].t, c }));
    ctx.fillStyle = T.text3; ctx.font = '10px ui-sans-serif, system-ui';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let k = 0; k <= 5; k++) {
      const idx = Math.round((data.length - 1) * k / 5);
      ctx.fillText('bar ' + idx, X(idx), padT + plotH + 6);
    }
    canvas._hover = { pts, draw: () => drawCandles(canvas, opts),
      label: p => `O <b>${p.c.o.toFixed(2)}</b>  H <b>${p.c.h.toFixed(2)}</b>  L <b>${p.c.l.toFixed(2)}</b>  C <b>${p.c.c.toFixed(2)}</b>`,
      color: T.accent };
  }

  function drawDonut(canvas) {
    const { ctx, w, h } = setup(canvas);
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 6, r = R - 13;
    const pct = parseFloat(canvas.dataset.win) / 100;
    ctx.lineWidth = R - r;
    ctx.lineCap = 'butt';
    // loss remainder
    ctx.strokeStyle = 'rgba(248,113,113,0.55)';
    ctx.beginPath(); ctx.arc(cx, cy, (R + r) / 2, -Math.PI / 2 + pct * 2 * Math.PI, -Math.PI / 2 + 2 * Math.PI); ctx.stroke();
    // win
    ctx.strokeStyle = T.green;
    ctx.beginPath(); ctx.arc(cx, cy, (R + r) / 2, -Math.PI / 2, -Math.PI / 2 + pct * 2 * Math.PI); ctx.stroke();
    // center label
    ctx.fillStyle = '#e6eaf0'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '700 ' + Math.round(R * 0.42) + 'px ui-sans-serif, system-ui';
    ctx.fillText(canvas.dataset.win + '%', cx, cy);
  }

  function draw(canvas) {
    if (!canvas || canvas.offsetParent === null || canvas.offsetWidth === 0) return;
    const type = canvas.dataset.chart;
    const regime = canvas.dataset.regime === '1';
    if (type === 'equity') drawEquity(canvas, { regime });
    else if (type === 'drawdown') drawDrawdown(canvas);
    else if (type === 'daily') drawDaily(canvas);
    else if (type === 'candles') drawCandles(canvas);
    else if (type === 'donut') drawDonut(canvas);
  }
  function drawAll(root) {
    (root || document).querySelectorAll('canvas.chart').forEach(draw);
  }

  // performance-by-regime breakdown (DOM table, not canvas)
  function renderRegime(el) {
    if (!el) return;
    const rows = DATA.regimes;
    const maxAbs = Math.max.apply(null, rows.map(r => Math.abs(r.pnl)));
    let html = '<div class="rg-head"><span>Market Regime</span><span>P&amp;L contribution</span>' +
      '<span class="rg-num">Win</span><span class="rg-num">Trades</span><span class="rg-num">Net</span></div>';
    rows.forEach(r => {
      const pos = r.pnl >= 0, w = Math.abs(r.pnl) / maxAbs * 50;
      const bar = pos
        ? `<span class="rg-bar pos" style="left:50%;width:${w}%"></span>`
        : `<span class="rg-bar neg" style="left:${50 - w}%;width:${w}%"></span>`;
      html += `<div class="rg-row">
        <span class="rg-name"><i style="background:${r.color}"></i>${r.name}</span>
        <span class="rg-track"><span class="rg-zero"></span>${bar}</span>
        <span class="rg-num">${r.win}%</span>
        <span class="rg-num">${r.trades}</span>
        <span class="rg-num ${pos ? 'pos' : 'neg'}">${pos ? '+' : '−'}$${Math.abs(r.pnl)}</span>
      </div>`;
    });
    el.innerHTML = html;
  }

  // ---------- crosshair tooltip ----------
  let tip;
  function ensureTip() {
    if (!tip) { tip = document.createElement('div'); tip.className = 'proto-tip'; document.body.appendChild(tip); }
    return tip;
  }
  function attachHover(canvas) {
    ensureTip();
    canvas.addEventListener('mousemove', e => {
      const hv = canvas._hover; if (!hv) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      let best = 0, bd = Infinity;
      hv.pts.forEach((p, i) => { const d = Math.abs(p.px - mx); if (d < bd) { bd = d; best = i; } });
      const p = hv.pts[best];
      hv.draw();
      const ctx = canvas.getContext('2d');
      ctx.strokeStyle = 'rgba(148,163,184,0.4)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(p.px, 6); ctx.lineTo(p.px, canvas.getBoundingClientRect().height - 18); ctx.stroke();
      ctx.fillStyle = hv.color; ctx.beginPath(); ctx.arc(p.px, p.py, 3.2, 0, 2 * Math.PI); ctx.fill();
      tip.innerHTML = hv.label(p);
      tip.style.display = 'block';
      tip.style.left = Math.min(e.clientX + 14, global.innerWidth - tip.offsetWidth - 10) + 'px';
      tip.style.top = (e.clientY - 36) + 'px';
    });
    canvas.addEventListener('mouseleave', () => {
      if (tip) tip.style.display = 'none';
      if (canvas._hover) canvas._hover.draw();
    });
  }

  // redraw visible charts on resize (debounced)
  let rt;
  global.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => drawAll(), 120); });

  global.Proto = { DATA, draw, drawAll, attachHover, renderRegime };
})(window);
