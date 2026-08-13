const API = window.location.origin;
let sseSource = null;
let volChart = null;
let riskChart = null;
let lastState = null;

function fmt(n) {
  return n === undefined || n === null ? '--' : Number(n).toFixed(2);
}

function fmt4(n) {
  return n === undefined || n === null ? '--' : Number(n).toFixed(4);
}

function post(path, body = {}) {
  return fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

function updateHeader(state) {
  const m = state.market;
  document.getElementById('spot').textContent = fmt(m.spot);
  document.getElementById('atm-vol').textContent = (m.atm_vol * 100).toFixed(1) + '%';
  document.getElementById('days').textContent = fmt(m.days_to_expiry);
  document.getElementById('step').textContent = `${m.simulation.step} / ${m.simulation.total_steps}`;
  document.getElementById('pnl').textContent = fmt(state.portfolio.total_pnl);
  document.getElementById('btn-increment').textContent = m.increment_mode === 'penny' ? 'Penny' : 'Eighth';
  const warn = document.getElementById('warning-banner');
  warn.style.display = m.simulation.remaining_warning ? 'block' : 'none';
  document.getElementById('status').textContent = m.simulation.running ? (m.simulation.paused ? 'Paused' : 'Live') : 'Idle';
  document.getElementById('fut-price').textContent = fmt(state.future.price);
}

function renderPortfolio(state) {
  const g = state.portfolio.total_greeks;
  const grid = document.getElementById('portfolio-grid');
  grid.innerHTML = `
    <div class="greek-card"><div class="label">Delta</div><div class="value ${g.delta >= 0 ? '' : 'down'}">${fmt(g.delta)}</div></div>
    <div class="greek-card"><div class="label">Gamma</div><div class="value">${fmt(g.gamma)}</div></div>
    <div class="greek-card"><div class="label">Vega</div><div class="value">${fmt(g.vega)}</div></div>
    <div class="greek-card"><div class="label">Theta</div><div class="value">${fmt(g.theta)}</div></div>
    <div class="greek-card"><div class="label">Rho</div><div class="value">${fmt(g.rho)}</div></div>
    <div class="greek-card"><div class="label">Cash</div><div class="value">${fmt(state.portfolio.cash)}</div></div>
  `;
}

function renderOptionBoard(state) {
  const tbody = document.querySelector('#options-table tbody');
  const byStrike = {};
  for (const o of state.options) {
    if (!byStrike[o.strike]) byStrike[o.strike] = {};
    byStrike[o.strike][o.option_type] = o;
  }
  const strikes = Object.keys(byStrike).map(Number).sort((a, b) => a - b);
  let html = '';
  for (const strike of strikes) {
    const c = byStrike[strike].CALL;
    const p = byStrike[strike].PUT;
    if (!c || !p) continue;
    html += `<tr>
      <td><input type="number" step="0.01" value="${fmt(c.quote.bid)}" id="cb-${c.id}"/></td>
      <td><input type="number" value="${c.quote.bid_qty}" id="cbq-${c.id}" style="width:38px"/></td>
      <td><input type="number" step="0.01" value="${fmt(c.quote.ask)}" id="ca-${c.id}"/></td>
      <td><input type="number" value="${c.quote.ask_qty}" id="caq-${c.id}" style="width:38px"/></td>
      <td class="strike">${fmt(strike)}</td>
      <td><input type="number" step="0.01" value="${fmt(p.quote.bid)}" id="pb-${p.id}"/></td>
      <td><input type="number" value="${p.quote.bid_qty}" id="pbq-${p.id}" style="width:38px"/></td>
      <td><input type="number" step="0.01" value="${fmt(p.quote.ask)}" id="pa-${p.id}"/></td>
      <td><input type="number" value="${p.quote.ask_qty}" id="paq-${p.id}" style="width:38px"/></td>
      <td>C:${fmt(c.theoretical)}<br/>P:${fmt(p.theoretical)}</td>
      <td style="font-size:10px">
        <button onclick="updateQuote('${c.id}')">Q</button>
        <button onclick="marketOrder('${c.id}','BUY',1)">B</button>
        <button onclick="marketOrder('${c.id}','SELL',1)">S</button>
      </td>
    </tr>`;
  }
  tbody.innerHTML = html;
}

function updateQuote(id) {
  const bid = parseFloat(document.getElementById('cb-' + id)?.value || 0) || parseFloat(document.getElementById('pb-' + id)?.value || 0);
  const ask = parseFloat(document.getElementById('ca-' + id)?.value || 0) || parseFloat(document.getElementById('pa-' + id)?.value || 0);
  const bidQty = parseInt(document.getElementById('cbq-' + id)?.value || document.getElementById('pbq-' + id)?.value || 0);
  const askQty = parseInt(document.getElementById('caq-' + id)?.value || document.getElementById('paq-' + id)?.value || 0);
  post('/api/v1/quote/' + encodeURIComponent(id), { bid, bid_qty: bidQty, ask, ask_qty: askQty });
}

function marketOrder(id, side, qty) {
  fetch(API + '/api/v1/market/' + encodeURIComponent(id) + '?side=' + side + '&qty=' + qty, { method: 'POST' });
}

function renderCombos(state) {
  const sel = document.getElementById('combo-select');
  sel.innerHTML = state.combos.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
  const legs = document.getElementById('combo-legs');
  const c = state.combos.find(x => x.id === sel.value) || state.combos[0];
  if (c) {
    legs.innerHTML = `<b>${c.name}</b><br/>` + c.legs.map(l => `${l.instrument_id} x${l.ratio}`).join('<br/>');
  }
}

function comboTrade() {
  const combo_id = document.getElementById('combo-select').value;
  const side = document.getElementById('combo-side').value;
  const qty = parseInt(document.getElementById('combo-qty').value) || 1;
  post('/api/v1/combo/trade', { combo_id, side, qty });
}

function renderTrades(state) {
  const tbody = document.querySelector('#trades tbody');
  const rows = state.portfolio.trades.slice(-20).reverse();
  tbody.innerHTML = rows.map(t => `<tr>
    <td>${new Date(t.timestamp).toLocaleTimeString()}</td>
    <td>${t.instrument_id.split('_').slice(-2).join(' ')}</td>
    <td class="${t.side === 'BUY' ? 'call' : 'put'}">${t.side}</td>
    <td>${t.qty}</td>
    <td>${fmt(t.price)}</td>
    <td>${t.counterparty}</td>
  </tr>`).join('');
}

function renderVolCurve(state) {
  const ctx = document.getElementById('vol-chart').getContext('2d');
  const points = state.vol_curve;
  const data = points.map(p => ({ x: p.delta * 100, y: p.vol * 100 }));
  if (volChart) { volChart.data.datasets[0].data = data; volChart.update('none'); return; }
  volChart = new Chart(ctx, {
    type: 'scatter',
    data: { datasets: [{ label: 'Call IV %', data, backgroundColor: '#22d3ee', pointRadius: 4 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { x: { title: { display: true, text: 'Delta' }, grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' } },
                y: { title: { display: true, text: 'Implied Vol %' }, grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' } } },
      plugins: { legend: { labels: { color: '#e5e7eb' } } }
    }
  });
}

function renderRisk(state) {
  const ctx = document.getElementById('risk-chart').getContext('2d');
  const labels = state.risk.map(r => (r.shock_pct * 100).toFixed(0) + '%');
  const data = state.risk.map(r => r.pnl);
  if (riskChart) { riskChart.data.labels = labels; riskChart.data.datasets[0].data = data; riskChart.update('none'); return; }
  riskChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ label: 'PnL', data, backgroundColor: data.map(v => v >= 0 ? '#10b981' : '#ef4444') }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { x: { grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' } },
                y: { grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' } } },
      plugins: { legend: { labels: { color: '#e5e7eb' } } }
    }
  });
}

function render(state) {
  lastState = state;
  updateHeader(state);
  renderPortfolio(state);
  renderOptionBoard(state);
  renderCombos(state);
  renderTrades(state);
  renderVolCurve(state);
  renderRisk(state);
}

function connectSSE() {
  if (sseSource) sseSource.close();
  sseSource = new EventSource(API + '/api/v1/sse');
  sseSource.onmessage = (ev) => {
    try { render(JSON.parse(ev.data)); } catch (e) { console.error(e); }
  };
  sseSource.onerror = () => { document.getElementById('status').textContent = 'Reconnecting...'; };
}

function fetchState() {
  fetch(API + '/api/v1/state').then(r => r.json()).then(render).catch(console.error);
}

function toggleTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.getElementById('tab-' + name).style.display = 'block';
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.querySelector('.tab[data-tab="' + name + '"]').classList.add('active');
  if (lastState) render(lastState);
}

function bind() {
  document.getElementById('btn-start').onclick = () => post('/api/v1/start');
  document.getElementById('btn-pause').onclick = () => post('/api/v1/pause');
  document.getElementById('btn-step').onclick = () => post('/api/v1/step');
  document.getElementById('btn-reset').onclick = () => post('/api/v1/reset');
  document.getElementById('btn-increment').onclick = () => post('/api/v1/increment/toggle');
  document.getElementById('btn-fut-plus').onclick = () => post('/api/v1/futures/hedge', { qty: 5 });
  document.getElementById('btn-fut-minus').onclick = () => post('/api/v1/futures/hedge', { qty: -5 });
  document.getElementById('btn-combo-trade').onclick = comboTrade;
  document.getElementById('combo-select').onchange = () => { if (lastState) renderCombos(lastState); };
  document.getElementById('btn-vol-up').onclick = () => post('/api/v1/vol', { delta: 0.01 });
  document.getElementById('btn-vol-down').onclick = () => post('/api/v1/vol', { delta: -0.01 });
  document.getElementById('btn-skew-up').onclick = () => post('/api/v1/skew', { delta: 0.01 });
  document.getElementById('btn-skew-down').onclick = () => post('/api/v1/skew', { delta: -0.01 });
  document.querySelectorAll('.tab').forEach(btn => btn.onclick = () => toggleTab(btn.dataset.tab));
  window.updateQuote = updateQuote;
  window.marketOrder = marketOrder;
}

bind();
fetchState();
connectSSE();
