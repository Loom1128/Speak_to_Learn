// 共用：API 呼叫、提示訊息、跳脫、分頁切換
async function api(path, options = {}) {
  const opts = { method: options.method || 'GET', headers: {}, credentials: 'same-origin' };
  if (options.body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, opts);
  if (res.status === 401 && !path.endsWith('/login')) {
    location.href = '/login';
    throw new Error('未登入');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `請求失敗（${res.status}）`);
  return data;
}

function toast(message, isError = false) {
  document.querySelectorAll('.toast').forEach((t) => t.remove());
  const el = document.createElement('div');
  el.className = 'toast' + (isError ? ' error' : '');
  el.setAttribute('role', 'status');
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// 頁內三個功能的切換（同步到網址 #hash，方便重新整理後回到同一區）
function setupSections(onChange) {
  const buttons = [...document.querySelectorAll('.segmented button[data-section]')];
  const show = (id) => {
    buttons.forEach((b) => {
      const on = b.dataset.section === id;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on);
    });
    document.querySelectorAll('section[data-section]').forEach((s) => s.classList.toggle('hidden', s.dataset.section !== id));
    history.replaceState(null, '', '#' + id);
    onChange && onChange(id);
  };
  buttons.forEach((b) => b.addEventListener('click', () => show(b.dataset.section)));
  const initial = location.hash.slice(1);
  show(buttons.some((b) => b.dataset.section === initial) ? initial : buttons[0].dataset.section);
}

async function setupTopbar() {
  try {
    const me = await api('/api/me');
    const el = document.getElementById('me');
    if (el) el.textContent = `${me.name}（${me.username}）`;
  } catch (e) { /* 401 已導向登入頁 */ }
  const logout = document.getElementById('logout');
  if (logout) {
    logout.addEventListener('click', async () => {
      await api('/api/logout', { method: 'POST', body: {} });
      location.href = '/login';
    });
  }
}

const ROLE_LABEL = { admin: '管理者', teacher: '教師', student: '學生' };
const ROLE_BADGE = { admin: 'dark', teacher: 'info', student: '' };
