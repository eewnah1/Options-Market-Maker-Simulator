(() => {
  const BASE = '';
  let es;
  let lastState = null;
  const els = {};
  ['spot','atm-vol','skew','days','step','pnl','mode','status','fut-price','ws-theo','options-table','combo-select','combo-legs','saved-spreads'].forEach(id => els[id] = document.getElementById(id));
  const fmt = (n, d=2) => n === undefined || n === null ? '--' : Number(n).toFixed(d);
  const fmtInt = n => n === undefined || n === null ? '--' : Math.round(n).toString();

  function connect() {
    if (es) { try { es.close(); } catch(e){} }
    es = new EventSource(`${BASE}/api/v1/sse`);
    es.onopen = () => setStatus('Connected');
    es.onmessage = e => {
      try { handleState(JSON.parse(e.data)); } catch(err) { console.error(err); }
    };
    es.onerror = () => setStatus('Reconnecting...');
  }

  function setStatus(s) { if (els.status) els.status.textContent = s; }

  function handleState(state) {
    lastState = state;
    renderHeader(state);
    renderPortfolio(state);
    renderOptions(state);
    renderRisk(state);
    renderFutures(state);
    renderTrades(state);
    renderVolCurve(state);
    renderSpotVol(state);
    renderCombos(state);
    computeWholesaleTheo();
    renderSaved();
    updateWarning(state);
  }

  function renderHeader(s) {
    const m = s.market || {};
    els.spot.textContent = fmt(m.spot, 2);
    els['atm-vol'].textContent = fmt(m.atm_vol, 2);
    els.skew.textContent = fmt(m.skew, 3);
    els.days.textContent = fmt(m.days_to_expiry, 1);
    els.step.textContent = `${m.simulation?.step || 0} / ${m.simulation?.total_steps || 0}`;
    const pnl = (s.portfolio?.total_pnl || 0);
    els.pnl.textContent = (pnl >= 0 ? '+' : '') + fmt(pnl, 0);
    els.pnl.style.color = pnl >= 0 ? 'var(--up)' : 'var(--down)';
    els.mode.textContent = m.increment_mode === 'eighth' ? 'Eighth' : 'Penny';
  }

  function renderPortfolio(s) {
    const g = s.portfolio?.total_greeks || {};
    const grid = document.getElementById('portfolio-grid');
    if (!grid) return;
    const cards = [
      {label:'Delta', value: g.delta}, {label:'Gamma', value: g.gamma},
      {label:'Vega', value: g.vega}, {label:'Theta', value: g.theta},
      {label:'Rho', value: g.rho}, {label:'Vanna', value: g.vanna},
      {label:'Volga', value: g.volga}, {label:'Cash', value: s.portfolio?.cash}
    ];
    grid.innerHTML = cards.map(c => `<div class="greek-card"><div class="label">${c.label}</div><div class="value" style="color:${c.value < 0 ? 'var(--down)' : 'var(--text)'}">${fmt(c.value, c.label==='Cash'?0:3)}</div></div>`).join('');
  }

  function renderOptions(s) {
    const tbody = els['options-table'].querySelector('tbody');
    if (!tbody) return;
    const opts = (s.options || []);
    const byStrike = {};
    opts.forEach(o => {
      byStrike[o.strike] = byStrike[o.strike] || {call:null, put:null};
      if (o.option_type === 'CALL') byStrike[o.strike].call = o;
      else byStrike[o.strike].put = o;
    });
    const strikes = Object.keys(byStrike).map(Number).sort((a,b)=>a-b);
    tbody.innerHTML = strikes.map(k => {
      const c = byStrike[k].call || {};
      const p = byStrike[k].put || {};
      const cg = c.greeks || {};
      const pg = p.greeks || {};
      return `<tr>
        <td class="call">${fmt(cg.delta, 3)}</td>
        <td class="call">${fmt(cg.gamma, 3)}</td>
        <td class="call">${fmt(cg.theta, 2)}</td>
        <td class="call">${fmt(cg.vega, 2)}</td>
        <td class="call">${fmt(c.implied_vol, 2)}</td>
        <td class="call pos">${fmtInt(c.position)}</td>
        <td class="call user-quote">${fmtInt(c.user_bid_qty || c.market_bid_qty)}</td>
        <td class="call user-quote">${fmt(c.user_bid || c.market_bid, 2)}</td>
        <td class="call theo">${fmt(c.theoretical, 2)}</td>
        <td class="call user-quote">${fmt(c.user_ask || c.market_ask, 2)}</td>
        <td class="call user-quote">${fmtInt(c.user_ask_qty || c.market_ask_qty)}</td>
        <td class="strike">${k.toFixed(1)}</td>
        <td class="put user-quote">${fmtInt(p.user_bid_qty || p.market_bid_qty)}</td>
        <td class="put user-quote">${fmt(p.user_bid || p.market_bid, 2)}</td>
        <td class="put theo">${fmt(p.theoretical, 2)}</td>
        <td class="put user-quote">${fmt(p.user_ask || p.market_ask, 2)}</td>
        <td class="put user-quote">${fmtInt(p.user_ask_qty || p.market_ask_qty)}</td>
        <td class="put pos">${fmtInt(p.position)}</td>
        <td class="put">${fmt(p.implied_vol, 2)}</td>
        <td class="put">${fmt(pg.vega, 2)}</td>
        <td class="put">${fmt(pg.theta, 2)}</td>
        <td class="put">${fmt(pg.gamma, 3)}</td>
        <td class="put">${fmt(pg.delta, 3)}</td>
      </tr>`;
    }).join('');
  }

  function renderRisk(s) {
    const tbody = document.querySelector('#risk-table tbody');
    if (!tbody) return;
    const risk = s.risk || [];
    tbody.innerHTML = risk.map(r => `<tr>
      <td>${(r.shock_pct * 100).toFixed(1)}%</td>
      <td>${fmt(r.spot, 2)}</td>
      <td style="color:${r.pnl>=0?'var(--up)':'var(--down)'}">${fmt(r.pnl, 0)}</td>
      <td>${fmt(r.delta, 0)}</td>
      <td>${fmt(r.gamma, 1)}</td>
      <td>${fmt(r.vega, 0)}</td>
      <td>${fmt(r.theta, 0)}</td>
    </tr>`).join('');
  }

  function renderFutures(s) {
    if (els['fut-price']) els['fut-price'].textContent = fmt(s.market?.spot, 2);
    const rows = document.getElementById('fut-ladder-rows');
    if (!rows) return;
    const spot = s.market?.spot || 0;
    let html = '';
    for (let i = 5; i >= 1; i--) {
      const p = spot + i * 0.25;
      html += `<div class="ladder-row"><span style="color:var(--up)">+${i*5}</span><b>${p.toFixed(2)}</b></div>`;
    }
    html += `<div class="ladder-row" style="background:var(--accent);color:#000"><span>Spot</span><b>${spot.toFixed(2)}</b></div>`;
    for (let i = 1; i <= 5; i++) {
      const p = spot - i * 0.25;
      html += `<div class="ladder-row"><span style="color:var(--down)">-${i*5}</span><b>${p.toFixed(2)}</b></div>`;
    }
    rows.innerHTML = html;
  }

  function renderTrades(s) {
    const el = document.getElementById('market-trades').querySelector('tbody');
    if (!el) return;
    const trades = (s.portfolio?.trades || []).slice(-30).reverse();
    el.innerHTML = trades.map(t => `<tr>
      <td>${new Date(t.timestamp).toLocaleTimeString()}</td>
      <td>${t.instrument_id.split('-').slice(-2).join('-')}</td>
      <td style="color:${t.side==='BUY'?'var(--up)':'var(--down)'}">${t.side}</td>
      <td>${t.qty}</td>
      <td>${fmt(t.price, 2)}</td>
    </tr>`).join('') || '<tr><td colspan="5" style="text-align:center">No trades</td></tr>';
  }

  let volChart, spotChart;
  function renderVolCurve(s) {
    const ctx = document.getElementById('vol-chart');
    if (!ctx) return;
    const vc = s.vol_curve || [];
    const data = { labels: vc.map(v => v.strike.toFixed(1)), datasets: [{ label: 'Implied Vol', data: vc.map(v => v.implied_vol), borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.15)', fill: true, tension: 0.3, pointRadius: 2 }] };
    if (volChart) { volChart.data = data; volChart.update(); }
    else {
      volChart = new Chart(ctx, { type: 'line', data, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#94a3b8', maxTicksLimit: 7 }, grid: { color: '#1f2937' } }, y: { ticks: { color: '#94a3b8' }, grid: { color: '#1f2937' }, title: { display: true, text: 'Implied Vol', color: '#64748b' } } } } });
    }
  }

  function renderSpotVol(s) {
    const ctx = document.getElementById('spot-chart');
    if (!ctx) return;
    const spotHist = (s.spot_history || []);
    const volHist = (s.vol_history || []);
    const labels = spotHist.map((p, i) => i.toString());
    if (spotChart) {
      spotChart.data.labels = labels;
      spotChart.data.datasets[0].data = spotHist.map(p => p[1]);
      spotChart.data.datasets[1].data = volHist.map(p => p[1]);
      spotChart.update();
    } else {
      spotChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [
          { label: 'Spot', data: spotHist.map(p => p[1]), borderColor: '#22d3ee', yAxisID: 'y', tension: 0.2, pointRadius: 1 },
          { label: 'ATM Vol', data: volHist.map(p => p[1]), borderColor: '#f59e0b', yAxisID: 'y1', tension: 0.2, pointRadius: 1 }
        ]},
        options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { labels: { color: '#94a3b8' } } }, scales: { x: { ticks: { color: '#94a3b8', maxTicksLimit: 8 }, grid: { color: '#1f2937' } }, y: { position: 'left', ticks: { color: '#94a3b8' }, grid: { color: '#1f2937' } }, y1: { position: 'right', ticks: { color: '#94a3b8' }, grid: { drawOnChartArea: false }, title: { display: true, text: 'Vol', color: '#64748b' } } } }
      });
    }
  }

  function renderCombos(s) {
    const sel = els['combo-select'];
    if (!sel) return;
    if (!sel.options.length && (s.combos || []).length) {
      sel.innerHTML = (s.combos || []).map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    }
    const active = sel.value;
    const combo = (s.combos || []).find(c => c.id === active) || (s.combos || [])[0];
    if (combo) {
      const legs = (combo.legs || []).map(l => `${l.ratio > 0 ? '+' : ''}${l.ratio}× ${l.instrument_id}`).join(', ');
      els['combo-legs'].innerHTML = `<b>${combo.name}</b><br/><span style="color:var(--muted);font-size:10px">${legs}</span>`;
    }
  }

  function updateWarning(s) {
    const m = s.market?.simulation || {};
    const left = (m.total_steps || 0) - (m.step || 0);
    const banner = document.getElementById('warning-banner');
    if (left <= 10 && left > 0 && !m.paused && m.running) banner.style.display = 'block';
    else banner.style.display = 'none';
  }

  // Actions
  async function post(path, body) {
    return fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  }

  document.getElementById('btn-start').onclick = () => post('/api/v1/start');
  document.getElementById('btn-pause').onclick = () => post('/api/v1/pause');
  document.getElementById('btn-step').onclick = () => post('/api/v1/step');
  document.getElementById('btn-reset').onclick = () => post('/api/v1/reset');
  document.getElementById('btn-increment').onclick = () => post('/api/v1/increment/toggle');
  document.getElementById('btn-vol-up').onclick = () => post('/api/v1/vol', { delta: 0.01 });
  document.getElementById('btn-vol-down').onclick = () => post('/api/v1/vol', { delta: -0.01 });
  document.getElementById('btn-skew-up').onclick = () => post('/api/v1/skew', { delta: 0.005 });
  document.getElementById('btn-skew-down').onclick = () => post('/api/v1/skew', { delta: -0.005 });

  document.getElementById('btn-fut-plus').onclick = () => {
    const qty = parseInt(prompt('Futures lots to buy (+5 per click buys 5):', '5'), 10) || 5;
    post('/api/v1/futures/hedge', { qty });
  };
  document.getElementById('btn-fut-minus').onclick = () => {
    const qty = parseInt(prompt('Futures lots to sell (negative qty):', '-5'), 10) || -5;
    post('/api/v1/futures/hedge', { qty });
  };

  document.getElementById('btn-combo-trade').onclick = () => {
    const combo_id = els['combo-select'].value;
    const side = document.getElementById('combo-side').value;
    const qty = parseInt(document.getElementById('combo-qty').value, 10) || 1;
    post('/api/v1/combo/trade', { combo_id, side, qty });
  };

  // Wholesale / combo builder
  let savedSpreads = [];
  function computeWholesaleTheo() {
    if (!lastState) return;
    const type = document.getElementById('ws-type').value;
    const k1 = parseFloat(document.getElementById('ws-k1').value);
    const k2 = parseFloat(document.getElementById('ws-k2').value);
    const k3 = parseFloat(document.getElementById('ws-k3').value);
    const opts = lastState.options || [];
    const get = (strike, kind) => opts.find(o => Math.abs(o.strike - strike) < 0.01 && o.option_type === kind);
    let theo = 0;
    if (type === 'call_spread') {
      const c1 = get(k1, 'CALL'); const c2 = get(k2, 'CALL');
      if (c1 && c2) theo = c1.theoretical - c2.theoretical;
    } else if (type === 'put_spread') {
      const p1 = get(k2, 'PUT'); const p2 = get(k1, 'PUT');
      if (p1 && p2) theo = p1.theoretical - p2.theoretical;
    } else if (type === 'straddle') {
      const c = get(k1, 'CALL'); const p = get(k1, 'PUT');
      if (c && p) theo = c.theoretical + p.theoretical;
    } else if (type === 'strangle') {
      const c = get(k2, 'CALL'); const p = get(k1, 'PUT');
      if (c && p) theo = c.theoretical + p.theoretical;
    } else if (type === 'risk_reversal') {
      const c = get(k2, 'CALL'); const p = get(k1, 'PUT');
      if (c && p) theo = c.theoretical - p.theoretical;
    } else if (type === 'butterfly') {
      const l = get(k1, 'CALL'); const m = get(k2, 'CALL'); const h = get(k3, 'CALL');
      if (l && m && h) theo = l.theoretical - 2 * m.theoretical + h.theoretical;
    }
    els['ws-theo'].value = theo.toFixed(2);
  }

  ['ws-type','ws-k1','ws-k2','ws-k3'].forEach(id => document.getElementById(id).addEventListener('input', computeWholesaleTheo));

  document.getElementById('btn-ws-trade').onclick = async () => {
    const type = document.getElementById('ws-type').value;
    const side = document.getElementById('ws-side').value;
    const qty = parseInt(document.getElementById('ws-qty').value, 10) || 1;
    const k1 = parseFloat(document.getElementById('ws-k1').value);
    const k2 = parseFloat(document.getElementById('ws-k2').value);
    const k3 = parseFloat(document.getElementById('ws-k3').value);
    const legs = buildCustomLegs(type, k1, k2, k3);
    if (!legs.length) return alert('Invalid strikes for chosen combo');
    for (const l of legs) {
      const tside = side === 'BUY' ? (l.ratio > 0 ? 'BUY' : 'SELL') : (l.ratio > 0 ? 'SELL' : 'BUY');
      await post('/api/v1/market/order', { instrument_id: l.instrument_id, side: tside, qty: Math.abs(l.ratio) * qty });
    }
  };

  document.getElementById('btn-ws-save').onclick = () => {
    const type = document.getElementById('ws-type').value;
    const k1 = document.getElementById('ws-k1').value;
    const k2 = document.getElementById('ws-k2').value;
    const k3 = document.getElementById('ws-k3').value;
    savedSpreads.unshift(`${type} ${k1}/${k2}/${k3}`);
    if (savedSpreads.length > 7) savedSpreads.pop();
    localStorage.setItem('omm_saved_spreads', JSON.stringify(savedSpreads));
    renderSaved();
  };

  function renderSaved() {
    if (!savedSpreads.length) {
      try { savedSpreads = JSON.parse(localStorage.getItem('omm_saved_spreads') || '[]'); } catch(e){}
    }
    const el = document.getElementById('saved-spreads');
    if (el) el.innerHTML = savedSpreads.map(s => `<div class="pill" style="margin-bottom:0.25rem">${s}</div>`).join('');
  }

  function buildCustomLegs(type, k1, k2, k3) {
    if (!lastState) return [];
    const opts = lastState.options || [];
    const get = (strike, kind) => opts.find(o => Math.abs(o.strike - strike) < 0.01 && o.option_type === kind);
    if (type === 'call_spread') {
      const c1 = get(k1, 'CALL'); const c2 = get(k2, 'CALL');
      if (c1 && c2) return [{instrument_id:c1.id, ratio:1}, {instrument_id:c2.id, ratio:-1}];
    } else if (type === 'put_spread') {
      const p1 = get(k2, 'PUT'); const p2 = get(k1, 'PUT');
      if (p1 && p2) return [{instrument_id:p1.id, ratio:1}, {instrument_id:p2.id, ratio:-1}];
    } else if (type === 'straddle') {
      const c = get(k1, 'CALL'); const p = get(k1, 'PUT');
      if (c && p) return [{instrument_id:c.id, ratio:1}, {instrument_id:p.id, ratio:1}];
    } else if (type === 'strangle') {
      const c = get(k2, 'CALL'); const p = get(k1, 'PUT');
      if (c && p) return [{instrument_id:c.id, ratio:1}, {instrument_id:p.id, ratio:1}];
    } else if (type === 'risk_reversal') {
      const c = get(k2, 'CALL'); const p = get(k1, 'PUT');
      if (c && p) return [{instrument_id:c.id, ratio:1}, {instrument_id:p.id, ratio:-1}];
    } else if (type === 'butterfly') {
      const l = get(k1, 'CALL'); const m = get(k2, 'CALL'); const h = get(k3, 'CALL');
      if (l && m && h) return [{instrument_id:l.id, ratio:1}, {instrument_id:m.id, ratio:-2}, {instrument_id:h.id, ratio:1}];
    }
    return [];
  }

  // Tabs
  document.querySelectorAll('.tab').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
      document.getElementById('tab-' + btn.dataset.tab).style.display = 'block';
    };
  });

  connect();
  renderSaved();
})();
