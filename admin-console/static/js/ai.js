// 頁面 2：管理兩個 AI 功能、監測兩個 AI 功能、紀錄 AI 異常
const STATUS_INFO = {
  ok: ['ok', '正常'], slow: ['warn', '回應偏慢'], down: ['bad', '無法連線'], disabled: ['', '已停用'],
};
const ANOMALY_STATUS = { open: ['bad', '待處理'], investigating: ['warn', '處理中'], resolved: ['ok', '已排除'] };
const LEVEL_INFO = { critical: ['bad', '嚴重'], warning: ['warn', '警告'] };

let anomalies = [];
let currentSection = 'manage';
let refreshTimer = null;

// ---------- 1. 管理 AI 功能 ----------
async function loadServices() {
  const services = await api('/api/ai/services');
  document.getElementById('service-forms').innerHTML = services.map((s) => `
    <form class="card stack" data-sid="${s.id}">
      <div class="row" style="justify-content:space-between">
        <div><h2>${esc(s.name)}</h2><p class="muted small">${esc(s.description)}</p></div>
        <label class="switch" title="啟用／停用">
          <input type="checkbox" name="enabled" ${s.enabled ? 'checked' : ''} aria-label="啟用${esc(s.name)}">
          <span></span>
        </label>
      </div>
      <label class="field">服務端點（健康檢查網址）
        <input name="endpoint" value="${esc(s.endpoint)}" class="mono" required>
      </label>
      <label class="field">模型／版本<input name="model" value="${esc(s.model)}"></label>
      <div class="grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
        <label class="field">回應逾時（秒）<input name="timeout_sec" type="number" min="1" max="300" value="${s.timeout_sec}"></label>
        <label class="field">延遲警示門檻（ms）<input name="latency_threshold_ms" type="number" min="100" step="100" value="${s.latency_threshold_ms}"></label>
      </div>
      <div class="row" style="justify-content:space-between">
        <span class="muted small">最後更新 ${esc(s.updated_at)}</span>
        <button class="primary" type="submit">儲存設定</button>
      </div>
    </form>`).join('');
}

document.getElementById('service-forms').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  if (!f.enabled.checked && !confirm('停用後學生將無法使用此 AI 功能，確定停用？')) return;
  try {
    await api(`/api/ai/services/${f.dataset.sid}`, {
      method: 'PUT',
      body: {
        enabled: f.enabled.checked,
        endpoint: f.endpoint.value,
        model: f.model.value,
        timeout_sec: Number(f.timeout_sec.value),
        latency_threshold_ms: Number(f.latency_threshold_ms.value),
      },
    });
    toast('AI 服務設定已儲存');
    loadServices();
  } catch (ex) { toast(ex.message, true); }
});

async function loadPolicies() {
  const policies = await api('/api/ai/policies');
  const ok = policies.every((p) => !p.value);
  const badge = document.getElementById('policy-badge');
  badge.className = 'badge ' + (ok ? 'ok' : 'bad');
  badge.textContent = ok ? `${policies.length} / ${policies.length} 項已落實` : '有政策未落實';
  document.getElementById('policy-rows').innerHTML = policies.map((p) => `
    <div class="policy-row">
      <div><b>${esc(p.label)}</b><div class="muted small">${esc(p.note)}</div></div>
      <div class="row">
        <span class="badge ${p.value ? 'bad' : 'ok'}">${p.value ? '已開啟 · 違規' : '已停用'}</span>
        <label class="switch"><input type="checkbox" disabled ${p.value ? 'checked' : ''} aria-label="${esc(p.label)}（系統鎖定）"><span></span></label>
      </div>
    </div>`).join('');
}

// ---------- 2. 監測 AI 功能 ----------
function sparkBars(recent, threshold) {
  if (!recent.length) return '<p class="muted small">尚無檢查紀錄</p>';
  const max = Math.max(threshold * 1.5, ...recent.map((c) => c.latency_ms || 0));
  return `<div class="spark" role="img" aria-label="最近 ${recent.length} 次檢查的回應時間">
    ${recent.map((c) => {
      const h = c.latency_ms ? Math.max(6, Math.round((c.latency_ms / max) * 100)) : 100;
      const label = `${c.ts}｜${STATUS_INFO[c.status][1]}${c.latency_ms ? `｜${c.latency_ms} ms` : ''}`;
      return `<i class="${c.status}" style="height:${h}%" title="${esc(label)}"></i>`;
    }).join('')}
  </div>`;
}

function fmt(v, unit) { return v === null || v === undefined ? '—' : `${v}${unit}`; }

async function loadStatus() {
  const data = await api('/api/ai/status');
  const openTotal = data.services.reduce((n, s) => n + s.open_anomalies, 0);
  document.getElementById('live-text').textContent = `持續監控中 · 每 ${data.interval_sec} 秒檢查`;
  document.getElementById('monitor-meta').textContent =
    '最後檢查：' + (data.services.map((s) => s.latest?.ts).filter(Boolean).sort().pop() || '尚未檢查');

  const banner = document.getElementById('monitor-banner');
  if (openTotal || !data.policies_ok) {
    banner.innerHTML = `<div class="banner bad" role="alert">
      <div><b>偵測到 ${openTotal} 筆未排除的 AI 異常${data.policies_ok ? '' : '，且有治理政策未落實'}</b>
      <div class="small">異常已自動寫入異常紀錄，請前往處理並通報。</div></div>
      <button type="button" class="primary" id="goto-anomalies">前往異常紀錄 →</button></div>`;
    document.getElementById('goto-anomalies').onclick = () => document.querySelector('[data-section="anomalies"]').click();
  } else {
    banner.innerHTML = '<div class="banner ok"><b>兩個 AI 功能運作正常</b><span class="small">AI 禁止自動化學習政策已落實</span></div>';
  }

  document.getElementById('status-cards').innerHTML = data.services.map((s) => {
    const st = s.latest ? s.latest.status : null;
    const [cls, label] = st ? STATUS_INFO[st] : ['', '尚未檢查'];
    return `<div class="card stack status-card ${st === 'down' ? 'is-down' : ''}">
      <div class="row" style="justify-content:space-between">
        <h2>${esc(s.name)}</h2>
        <span class="badge ${cls}"><span class="dot"></span>${label}</span>
      </div>
      <div class="grid cols-4" style="grid-template-columns:repeat(4,minmax(0,1fr))">
        <div class="stat"><b>${fmt(s.latest?.latency_ms, '')}</b><span>目前延遲 ms</span></div>
        <div class="stat"><b>${fmt(s.avg_latency_24h, '')}</b><span>24h 平均 ms</span></div>
        <div class="stat"><b>${fmt(s.uptime_24h, '%')}</b><span>24h 可用率</span></div>
        <div class="stat"><b>${fmt(s.error_rate_24h, '%')}</b><span>24h 錯誤率</span></div>
      </div>
      ${sparkBars(s.recent, s.latency_threshold_ms)}
      <div class="row small muted" style="justify-content:space-between">
        <span>延遲門檻 ${s.latency_threshold_ms} ms · 24h 共 ${s.checks_24h} 次檢查</span>
        <span>${s.open_anomalies ? `<span class="badge bad">${s.open_anomalies} 筆未排除</span>` : '無未排除異常'}</span>
      </div>
      ${s.latest?.message ? `<p class="small mono muted">${esc(s.latest.message)}</p>` : ''}
    </div>`;
  }).join('');

  const oc = document.getElementById('open-count');
  oc.textContent = openTotal;
  oc.classList.toggle('hidden', !openTotal);
}

document.getElementById('btn-check').addEventListener('click', async (e) => {
  e.target.disabled = true;
  try {
    await api('/api/ai/check', { method: 'POST', body: {} });
    toast('檢查完成');
    await loadStatus();
  } catch (ex) { toast(ex.message, true); }
  e.target.disabled = false;
});

// ---------- 3. AI 異常紀錄 ----------
async function loadAnomalies() {
  const params = new URLSearchParams();
  const st = document.getElementById('a-status').value;
  const sv = document.getElementById('a-service').value;
  if (st) params.set('status', st);
  if (sv) params.set('service', sv);
  anomalies = await api('/api/ai/anomalies?' + params);
  const tbody = document.getElementById('anomaly-rows');
  if (!anomalies.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty">沒有符合條件的異常紀錄</td></tr>';
    return;
  }
  tbody.innerHTML = anomalies.map((a) => {
    const [lc, ll] = LEVEL_INFO[a.level];
    const [sc, sl] = ANOMALY_STATUS[a.status];
    return `<tr>
      <td class="mono">#${a.id}</td>
      <td class="muted small" style="white-space:nowrap">${esc(a.ts)}</td>
      <td>${esc(a.service_name || '治理政策')}</td>
      <td><span class="badge ${lc}">${ll}</span></td>
      <td>${esc(a.message)}${a.resolution_note ? `<div class="muted small">處理：${esc(a.resolution_note)}</div>` : ''}</td>
      <td class="muted small">${a.source === 'monitor' ? '自動監測' : esc(a.source)}</td>
      <td><span class="badge ${sc}">${sl}</span>${a.notified ? ' <span class="badge info">已通報</span>' : ''}</td>
      <td class="actions"><button class="sm" data-aid="${a.id}">${a.status === 'resolved' ? '檢視' : '處理'}</button></td>
    </tr>`;
  }).join('');
}

document.getElementById('anomaly-rows').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-aid]');
  if (!btn) return;
  const a = anomalies.find((x) => x.id === Number(btn.dataset.aid));
  const f = document.getElementById('handle-form');
  f.dataset.aid = a.id;
  document.getElementById('handle-meta').textContent = `#${a.id} · ${a.ts} · ${a.service_name || '治理政策'}`;
  document.getElementById('handle-message').textContent = a.message;
  f.status.value = a.status === 'open' ? 'investigating' : a.status;
  f.note.value = a.resolution_note || '';
  f.notify.checked = false;
  document.getElementById('handle-dialog').showModal();
});

document.getElementById('handle-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api(`/api/ai/anomalies/${f.dataset.aid}`, {
      method: 'PUT',
      body: { status: f.status.value, resolution_note: f.note.value, notify: f.notify.checked },
    });
    document.getElementById('handle-dialog').close();
    toast(f.status.value === 'resolved' ? '已標記排除，系統回到持續監控' : '異常狀態已更新');
    loadAnomalies();
    loadStatus();
  } catch (ex) { toast(ex.message, true); }
});

document.getElementById('btn-new-anomaly').addEventListener('click', () => {
  document.getElementById('new-anomaly-form').reset();
  document.getElementById('new-anomaly-dialog').showModal();
});
document.getElementById('new-anomaly-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api('/api/ai/anomalies', {
      method: 'POST', body: { service_id: f.service_id.value, level: f.level.value, message: f.message.value },
    });
    document.getElementById('new-anomaly-dialog').close();
    toast('異常已記錄');
    loadAnomalies();
    loadStatus();
  } catch (ex) { toast(ex.message, true); }
});
document.querySelectorAll('.dialog-cancel').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
document.getElementById('a-status').addEventListener('change', loadAnomalies);
document.getElementById('a-service').addEventListener('change', loadAnomalies);

// ---------- 初始化與自動更新 ----------
function loadSection(id) {
  currentSection = id;
  if (id === 'manage') { loadServices(); loadPolicies(); }
  if (id === 'monitor') loadStatus();
  if (id === 'anomalies') loadAnomalies();
}

setupTopbar();
setupSections(loadSection);
loadStatus();  // 讓分頁上的未排除數量一開始就顯示

clearInterval(refreshTimer);
refreshTimer = setInterval(() => {
  if (document.hidden) return;
  loadStatus().catch(() => {});
  if (currentSection === 'anomalies' && !document.querySelector('dialog[open]')) loadAnomalies().catch(() => {});
}, 15000);
