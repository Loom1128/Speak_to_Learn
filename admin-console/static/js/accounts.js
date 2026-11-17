// 頁面 1：管理帳號、設定帳號角色、設定角色的資料存取權限
const LEVEL_LABEL = { none: '無權限', own: '僅本人', read: '檢視', write: '編輯' };
const LOCK_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>';

let users = [];
let editingId = null;

function roleBadge(role) {
  return `<span class="badge ${ROLE_BADGE[role]}">${ROLE_LABEL[role] || role}</span>`;
}

// ---------- 1. 管理帳號 ----------
async function loadUsers() {
  const params = new URLSearchParams();
  const role = document.getElementById('f-role').value;
  const active = document.getElementById('f-active').value;
  const q = document.getElementById('f-q').value.trim();
  if (role) params.set('role', role);
  if (active) params.set('active', active);
  if (q) params.set('q', q);
  users = await api('/api/users?' + params);
  const tbody = document.getElementById('user-rows');
  document.getElementById('user-count').textContent = `共 ${users.length} 個帳號`;
  if (!users.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">沒有符合條件的帳號</td></tr>';
    return;
  }
  tbody.innerHTML = users.map((u) => `
    <tr>
      <td><b>${esc(u.name)}</b></td>
      <td class="mono">${esc(u.username)}</td>
      <td class="muted">${esc(u.email) || '—'}</td>
      <td>${roleBadge(u.role_id)}</td>
      <td>${u.active ? '<span class="badge ok">啟用</span>' : '<span class="badge">停用</span>'}</td>
      <td class="muted small">${esc(u.last_login) || '尚未登入'}</td>
      <td class="actions">
        <button class="sm ghost" data-act="edit" data-id="${u.id}">編輯</button>
        <button class="sm ghost" data-act="reset" data-id="${u.id}">重設密碼</button>
        <button class="sm ghost" data-act="toggle" data-id="${u.id}">${u.active ? '停用' : '啟用'}</button>
        <button class="sm danger" data-act="delete" data-id="${u.id}">刪除</button>
      </td>
    </tr>`).join('');
}

function openUserDialog(user) {
  editingId = user ? user.id : null;
  const form = document.getElementById('user-form');
  form.reset();
  document.getElementById('user-dialog-title').textContent = user ? '編輯帳號' : '新增帳號';
  form.querySelectorAll('[data-only="new"]').forEach((el) => el.classList.toggle('hidden', !!user));
  form.username.disabled = !!user;
  if (user) {
    form.name.value = user.name;
    form.username.value = user.username;
    form.email.value = user.email;
  }
  document.getElementById('user-dialog').showModal();
}

document.getElementById('user-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    if (editingId) {
      await api(`/api/users/${editingId}`, { method: 'PUT', body: { name: f.name.value, email: f.email.value } });
      toast('帳號已更新');
    } else {
      const res = await api('/api/users', {
        method: 'POST',
        body: { name: f.name.value, username: f.username.value, email: f.email.value, role_id: f.role_id.value, password: f.password.value },
      });
      toast(res.temp_password ? `帳號已建立，初始密碼：${res.temp_password}` : '帳號已建立');
    }
    document.getElementById('user-dialog').close();
    refreshAll();
  } catch (ex) { toast(ex.message, true); }
});
document.getElementById('user-cancel').addEventListener('click', () => document.getElementById('user-dialog').close());
document.getElementById('btn-new').addEventListener('click', () => openUserDialog(null));

document.getElementById('user-rows').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const u = users.find((x) => x.id === Number(btn.dataset.id));
  try {
    if (btn.dataset.act === 'edit') return openUserDialog(u);
    if (btn.dataset.act === 'reset') {
      if (!confirm(`要重設「${u.name}」的密碼嗎？`)) return;
      const res = await api(`/api/users/${u.id}/reset-password`, { method: 'POST', body: {} });
      prompt('臨時密碼（請轉交使用者並要求登入後更改）', res.temp_password);
    }
    if (btn.dataset.act === 'toggle') {
      await api(`/api/users/${u.id}`, { method: 'PUT', body: { active: !u.active } });
      toast(u.active ? '帳號已停用' : '帳號已啟用');
    }
    if (btn.dataset.act === 'delete') {
      if (!confirm(`確定要刪除「${u.name}（${u.username}）」？此動作無法復原，建議改用「停用」。`)) return;
      await api(`/api/users/${u.id}`, { method: 'DELETE' });
      toast('帳號已刪除');
    }
    refreshAll();
  } catch (ex) { toast(ex.message, true); }
});

let searchTimer;
document.getElementById('f-q').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadUsers, 250); });
document.getElementById('f-role').addEventListener('change', loadUsers);
document.getElementById('f-active').addEventListener('change', loadUsers);

// ---------- 2. 設定帳號角色 ----------
async function loadRoles() {
  const [roles, all] = await Promise.all([api('/api/roles'), api('/api/users')]);
  document.getElementById('role-cards').innerHTML = roles.map((r) => `
    <div class="card role-card">
      <div class="row" style="justify-content:space-between">${roleBadge(r.id)}<span class="muted small">啟用 ${r.active_count}</span></div>
      <div class="count">${r.user_count}<span class="muted small" style="font-weight:400"> 個帳號</span></div>
      <p class="muted small">${esc(r.description)}</p>
    </div>`).join('');
  document.getElementById('role-rows').innerHTML = all.map((u) => `
    <tr>
      <td><b>${esc(u.name)}</b>${u.active ? '' : ' <span class="badge">停用</span>'}</td>
      <td class="mono">${esc(u.username)}</td>
      <td>${roleBadge(u.role_id)}</td>
      <td>
        <select class="inline" data-uid="${u.id}" data-current="${u.role_id}" aria-label="變更 ${esc(u.name)} 的角色">
          ${['admin', 'teacher', 'student'].map((r) => `<option value="${r}" ${r === u.role_id ? 'selected' : ''}>${ROLE_LABEL[r]}</option>`).join('')}
        </select>
      </td>
    </tr>`).join('');
}

document.getElementById('role-rows').addEventListener('change', async (e) => {
  const sel = e.target.closest('select[data-uid]');
  if (!sel) return;
  const to = sel.value;
  if (to === 'admin' && !confirm('確定要授予管理者角色？此帳號將可管理所有帳號與 AI 服務。')) {
    sel.value = sel.dataset.current;
    return;
  }
  try {
    await api(`/api/users/${sel.dataset.uid}/role`, { method: 'PUT', body: { role_id: to } });
    toast(`角色已變更為「${ROLE_LABEL[to]}」`);
    refreshAll();
  } catch (ex) {
    sel.value = sel.dataset.current;
    toast(ex.message, true);
  }
});

// ---------- 3. 角色資料存取權限 ----------
async function loadPerms() {
  const { resources, matrix } = await api('/api/permissions');
  let lastCat = '';
  const html = [];
  for (const r of resources) {
    if (r.category !== lastCat) {
      html.push(`<tr><th class="group" colspan="4" scope="rowgroup">${esc(r.category)}</th></tr>`);
      lastCat = r.category;
    }
    const cells = ['admin', 'teacher', 'student'].map((role) => {
      const p = matrix[r.id]?.[role];
      if (!p) return '<td>—</td>';
      if (p.locked) {
        const cls = { write: 'ok', read: 'info', own: 'warn', none: '' }[p.level];
        return `<td><span class="badge ${cls}">${LEVEL_LABEL[p.level]}</span> <span class="lock" title="系統鎖定">${LOCK_SVG}</span></td>`;
      }
      const levels = role === 'student' ? ['none', 'own', 'read', 'write'] : ['none', 'read', 'write'];
      return `<td><select class="perm-select lv-${p.level}" data-role="${role}" data-res="${r.id}" data-current="${p.level}"
        aria-label="${ROLE_LABEL[role]}對「${esc(r.name)}」的權限">
        ${levels.map((lv) => `<option value="${lv}" ${lv === p.level ? 'selected' : ''}>${LEVEL_LABEL[lv]}</option>`).join('')}
      </select></td>`;
    }).join('');
    html.push(`<tr><td><b>${esc(r.name)}</b>${r.note ? `<div class="muted small">${esc(r.note)}</div>` : ''}</td>${cells}</tr>`);
  }
  document.getElementById('perm-rows').innerHTML = html.join('');
}

document.getElementById('perm-rows').addEventListener('change', async (e) => {
  const sel = e.target.closest('select[data-res]');
  if (!sel) return;
  try {
    await api('/api/permissions', { method: 'PUT', body: { role_id: sel.dataset.role, resource_id: sel.dataset.res, level: sel.value } });
    sel.dataset.current = sel.value;
    sel.className = `perm-select lv-${sel.value}`;
    toast('權限已更新');
    loadAudit();
  } catch (ex) {
    sel.value = sel.dataset.current;
    toast(ex.message, true);
  }
});

async function loadAudit() {
  const logs = await api('/api/audit?limit=15');
  document.getElementById('audit-rows').innerHTML = logs.length ? logs.map((l) => `
    <tr><td class="muted small">${esc(l.ts)}</td><td class="mono">${esc(l.actor)}</td><td>${esc(l.action)}</td>
    <td class="mono">${esc(l.target)}</td><td class="muted small">${esc(l.detail)}</td></tr>`).join('')
    : '<tr><td colspan="5" class="empty">尚無紀錄</td></tr>';
}

function refreshAll() {
  loadUsers();
  loadRoles();
  loadAudit();
}

setupTopbar();
setupSections((id) => {
  if (id === 'users') loadUsers();
  if (id === 'roles') loadRoles();
  if (id === 'perms') { loadPerms(); loadAudit(); }
});
