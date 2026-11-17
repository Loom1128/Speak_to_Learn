"""AI 教學評量系統 · 管理後台（Flask）

頁面 1  /accounts：管理帳號、設定帳號角色、設定角色的資料存取權限
頁面 2  /ai      ：管理兩個 AI 功能、監測兩個 AI 功能、紀錄 AI 異常
"""
import os
import secrets
from functools import wraps

from flask import Flask, jsonify, redirect, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import audit, get_conn, init_db, now
from monitor import run_checks, start_background_monitor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    JSON_AS_ASCII=False,
)

ROLE_IDS = {"admin", "teacher", "student"}
LEVELS = {"none", "own", "read", "write"}


# ---------- 共用 ----------

def error(message, code=400):
    return jsonify({"error": message}), code


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    conn = get_conn()
    u = conn.execute(
        "SELECT id, name, username, role_id, active FROM users WHERE id = ?", (uid,)
    ).fetchone()
    conn.close()
    if not u or not u["active"] or u["role_id"] != "admin":
        return None
    return dict(u)


def admin_required(view):
    """API 需管理者登入；頁面未登入時導向登入頁。"""
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            if request.path.startswith("/api/"):
                return error("請先以管理者帳號登入", 401)
            return redirect("/login")
        request.admin = user
        return view(*args, **kwargs)
    return wrapper


@app.before_request
def require_json_for_writes():
    # 寫入類 API 必須是 JSON，搭配 SameSite cookie 降低跨站請求偽造風險
    if request.path.startswith("/api/") and request.method in ("POST", "PUT", "DELETE"):
        if request.method != "DELETE" and not request.is_json:
            return error("請以 JSON 格式送出", 415)


def body():
    return request.get_json(silent=True) or {}


# ---------- 頁面 ----------

@app.get("/")
def index():
    return redirect("/accounts" if current_user() else "/login")


@app.get("/login")
def login_page():
    return send_from_directory(STATIC_DIR, "login.html")


@app.get("/accounts")
@admin_required
def accounts_page():
    return send_from_directory(STATIC_DIR, "accounts.html")


@app.get("/ai")
@admin_required
def ai_page():
    return send_from_directory(STATIC_DIR, "ai.html")


# ---------- 登入 ----------

@app.post("/api/login")
def api_login():
    data = body()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not u or not check_password_hash(u["password_hash"], password):
        audit(conn, username or "-", "登入失敗", "管理後台")
        conn.commit()
        conn.close()
        return error("帳號或密碼錯誤", 401)
    if u["role_id"] != "admin" or not u["active"]:
        audit(conn, username, "登入遭拒（非管理者或已停用）", "管理後台")
        conn.commit()
        conn.close()
        return error("此帳號沒有管理後台權限", 403)
    conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now(), u["id"]))
    audit(conn, username, "管理者登入", "管理後台")
    conn.commit()
    conn.close()
    session.clear()
    session["uid"] = u["id"]
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
@admin_required
def api_me():
    return jsonify(request.admin)


# =====================================================================
# 頁面 1：帳號、角色、資料存取權限
# =====================================================================

@app.get("/api/users")
@admin_required
def list_users():
    role = request.args.get("role")
    q = (request.args.get("q") or "").strip()
    active = request.args.get("active")
    sql = ("SELECT u.id, u.name, u.username, u.email, u.role_id, r.name AS role_name, u.active, "
           "u.created_at, u.last_login FROM users u JOIN roles r ON r.id = u.role_id WHERE 1=1")
    args = []
    if role in ROLE_IDS:
        sql += " AND u.role_id = ?"
        args.append(role)
    if active in ("0", "1"):
        sql += " AND u.active = ?"
        args.append(int(active))
    if q:
        sql += " AND (u.name LIKE ? OR u.username LIKE ? OR u.email LIKE ?)"
        args += [f"%{q}%"] * 3
    sql += " ORDER BY CASE u.role_id WHEN 'admin' THEN 0 WHEN 'teacher' THEN 1 ELSE 2 END, u.username"
    conn = get_conn()
    data = rows(conn.execute(sql, args))
    conn.close()
    return jsonify(data)


@app.post("/api/users")
@admin_required
def create_user():
    d = body()
    name = (d.get("name") or "").strip()
    username = (d.get("username") or "").strip()
    email = (d.get("email") or "").strip()
    role_id = d.get("role_id")
    password = d.get("password") or ""
    if not name or not username:
        return error("姓名與帳號為必填")
    if role_id not in ROLE_IDS:
        return error("角色不正確")
    generated = False
    if not password:
        password = secrets.token_urlsafe(8)
        generated = True
    if len(password) < 8:
        return error("密碼至少 8 個字元")
    conn = get_conn()
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        return error("帳號已存在", 409)
    cur = conn.execute(
        "INSERT INTO users (name, username, email, role_id, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, username, email, role_id, generate_password_hash(password), now()),
    )
    audit(conn, request.admin["username"], "新增帳號", username, f"角色：{role_id}")
    conn.commit()
    conn.close()
    resp = {"id": cur.lastrowid}
    if generated:
        resp["temp_password"] = password
    return jsonify(resp), 201


def _active_admin_count(conn):
    return conn.execute("SELECT COUNT(*) FROM users WHERE role_id = 'admin' AND active = 1").fetchone()[0]


@app.put("/api/users/<int:uid>")
@admin_required
def update_user(uid):
    d = body()
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not u:
        conn.close()
        return error("找不到帳號", 404)
    name = (d.get("name", u["name"]) or "").strip()
    email = (d.get("email", u["email"]) or "").strip()
    active = int(bool(d.get("active", u["active"])))
    if not name:
        conn.close()
        return error("姓名不可空白")
    if not active and u["active"]:
        if uid == request.admin["id"]:
            conn.close()
            return error("不能停用自己的帳號")
        if u["role_id"] == "admin" and _active_admin_count(conn) <= 1:
            conn.close()
            return error("至少需保留一位啟用中的管理者")
    conn.execute("UPDATE users SET name = ?, email = ?, active = ? WHERE id = ?", (name, email, active, uid))
    changes = []
    if name != u["name"]:
        changes.append(f"姓名 → {name}")
    if email != u["email"]:
        changes.append("Email 已更新")
    if active != u["active"]:
        changes.append("啟用" if active else "停用")
    audit(conn, request.admin["username"], "編輯帳號", u["username"], "、".join(changes))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.post("/api/users/<int:uid>/reset-password")
@admin_required
def reset_password(uid):
    conn = get_conn()
    u = conn.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
    if not u:
        conn.close()
        return error("找不到帳號", 404)
    temp = secrets.token_urlsafe(8)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(temp), uid))
    audit(conn, request.admin["username"], "重設密碼", u["username"])
    conn.commit()
    conn.close()
    return jsonify({"temp_password": temp})


@app.delete("/api/users/<int:uid>")
@admin_required
def delete_user(uid):
    if uid == request.admin["id"]:
        return error("不能刪除自己的帳號")
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not u:
        conn.close()
        return error("找不到帳號", 404)
    if u["role_id"] == "admin" and u["active"] and _active_admin_count(conn) <= 1:
        conn.close()
        return error("至少需保留一位啟用中的管理者")
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    audit(conn, request.admin["username"], "刪除帳號", u["username"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.put("/api/users/<int:uid>/role")
@admin_required
def set_role(uid):
    role_id = body().get("role_id")
    if role_id not in ROLE_IDS:
        return error("角色不正確")
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not u:
        conn.close()
        return error("找不到帳號", 404)
    if u["role_id"] == role_id:
        conn.close()
        return jsonify({"ok": True})
    if u["role_id"] == "admin":
        if uid == request.admin["id"]:
            conn.close()
            return error("不能變更自己的管理者角色")
        if u["active"] and _active_admin_count(conn) <= 1:
            conn.close()
            return error("至少需保留一位啟用中的管理者")
    conn.execute("UPDATE users SET role_id = ? WHERE id = ?", (role_id, uid))
    audit(conn, request.admin["username"], "變更角色", u["username"], f"{u['role_id']} → {role_id}")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/roles")
@admin_required
def list_roles():
    conn = get_conn()
    data = rows(conn.execute(
        "SELECT r.id, r.name, r.description, "
        "(SELECT COUNT(*) FROM users u WHERE u.role_id = r.id) AS user_count, "
        "(SELECT COUNT(*) FROM users u WHERE u.role_id = r.id AND u.active = 1) AS active_count "
        "FROM roles r ORDER BY CASE r.id WHEN 'admin' THEN 0 WHEN 'teacher' THEN 1 ELSE 2 END"
    ))
    conn.close()
    return jsonify(data)


@app.get("/api/permissions")
@admin_required
def get_permissions():
    conn = get_conn()
    resources = rows(conn.execute("SELECT id, name, category, note FROM resources ORDER BY sort"))
    perms = rows(conn.execute("SELECT role_id, resource_id, level, locked FROM permissions"))
    conn.close()
    matrix = {}
    for p in perms:
        matrix.setdefault(p["resource_id"], {})[p["role_id"]] = {"level": p["level"], "locked": bool(p["locked"])}
    return jsonify({"resources": resources, "matrix": matrix})


@app.put("/api/permissions")
@admin_required
def set_permission():
    d = body()
    role_id, resource_id, level = d.get("role_id"), d.get("resource_id"), d.get("level")
    if role_id not in ROLE_IDS or level not in LEVELS:
        return error("參數不正確")
    if level == "own" and role_id != "student":
        return error("「僅本人」只適用於學生角色")
    conn = get_conn()
    p = conn.execute(
        "SELECT level, locked FROM permissions WHERE role_id = ? AND resource_id = ?", (role_id, resource_id)
    ).fetchone()
    if not p:
        conn.close()
        return error("找不到此權限項目", 404)
    if p["locked"]:
        conn.close()
        return error("此項目由系統鎖定，無法修改", 403)
    conn.execute(
        "UPDATE permissions SET level = ? WHERE role_id = ? AND resource_id = ?", (level, role_id, resource_id)
    )
    audit(conn, request.admin["username"], "變更資料存取權限", f"{role_id}/{resource_id}", f"{p['level']} → {level}")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/audit")
@admin_required
def get_audit():
    limit = min(int(request.args.get("limit", 30)), 200)
    conn = get_conn()
    data = rows(conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)))
    conn.close()
    return jsonify(data)


# =====================================================================
# 頁面 2：AI 功能管理、監測、異常紀錄
# =====================================================================

@app.get("/api/ai/services")
@admin_required
def ai_services():
    conn = get_conn()
    data = rows(conn.execute("SELECT * FROM ai_services ORDER BY rowid"))
    conn.close()
    return jsonify(data)


@app.put("/api/ai/services/<sid>")
@admin_required
def update_ai_service(sid):
    d = body()
    conn = get_conn()
    s = conn.execute("SELECT * FROM ai_services WHERE id = ?", (sid,)).fetchone()
    if not s:
        conn.close()
        return error("找不到 AI 服務", 404)
    try:
        enabled = int(bool(d.get("enabled", s["enabled"])))
        endpoint = (d.get("endpoint", s["endpoint"]) or "").strip()
        model = (d.get("model", s["model"]) or "").strip()
        timeout = int(d.get("timeout_sec", s["timeout_sec"]))
        threshold = int(d.get("latency_threshold_ms", s["latency_threshold_ms"]))
    except (TypeError, ValueError):
        conn.close()
        return error("數值格式不正確")
    if not (endpoint.startswith("mock://") or endpoint.startswith("http://") or endpoint.startswith("https://")):
        conn.close()
        return error("端點需以 http://、https:// 或 mock:// 開頭")
    if not 1 <= timeout <= 300:
        conn.close()
        return error("逾時需介於 1–300 秒")
    if not 100 <= threshold <= 120000:
        conn.close()
        return error("延遲門檻需介於 100–120000 ms")
    conn.execute(
        "UPDATE ai_services SET enabled = ?, endpoint = ?, model = ?, timeout_sec = ?, "
        "latency_threshold_ms = ?, updated_at = ? WHERE id = ?",
        (enabled, endpoint, model, timeout, threshold, now(), sid),
    )
    audit(conn, request.admin["username"], "更新 AI 服務設定", s["name"],
          f"{'啟用' if enabled else '停用'}、逾時 {timeout}s、門檻 {threshold}ms")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/ai/policies")
@admin_required
def ai_policies():
    conn = get_conn()
    data = rows(conn.execute("SELECT * FROM ai_policies ORDER BY rowid"))
    conn.close()
    return jsonify(data)


@app.put("/api/ai/policies/<key>")
@admin_required
def update_ai_policy(key):
    # AI 治理政策固定停用，管理者只能檢核、不能開啟
    return error("AI 治理政策由系統鎖定，管理者無法變更", 403)


@app.get("/api/ai/status")
@admin_required
def ai_status():
    conn = get_conn()
    services = rows(conn.execute("SELECT id, name, enabled, latency_threshold_ms FROM ai_services ORDER BY rowid"))
    for s in services:
        recent = rows(conn.execute(
            "SELECT ts, status, latency_ms, message FROM ai_checks WHERE service_id = ? ORDER BY id DESC LIMIT 40",
            (s["id"],),
        ))
        s["recent"] = list(reversed(recent))
        s["latest"] = recent[0] if recent else None
        day = conn.execute(
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN status IN ('ok','slow') THEN 1 ELSE 0 END) AS up, "
            "SUM(CASE WHEN status = 'down' THEN 1 ELSE 0 END) AS down, "
            "AVG(latency_ms) AS avg_latency "
            "FROM ai_checks WHERE service_id = ? AND status != 'disabled' "
            "AND ts >= datetime('now', 'localtime', '-1 day')",
            (s["id"],),
        ).fetchone()
        n = day["n"] or 0
        s["checks_24h"] = n
        s["uptime_24h"] = round(day["up"] * 100 / n, 1) if n else None
        s["error_rate_24h"] = round(day["down"] * 100 / n, 1) if n else None
        s["avg_latency_24h"] = round(day["avg_latency"]) if day["avg_latency"] is not None else None
        s["open_anomalies"] = conn.execute(
            "SELECT COUNT(*) FROM ai_anomalies WHERE service_id = ? AND status != 'resolved'", (s["id"],)
        ).fetchone()[0]
    policies_ok = conn.execute("SELECT COUNT(*) FROM ai_policies WHERE value != 0").fetchone()[0] == 0
    conn.close()
    from monitor import INTERVAL_SEC
    return jsonify({"services": services, "policies_ok": policies_ok, "interval_sec": INTERVAL_SEC})


@app.post("/api/ai/check")
@admin_required
def ai_check_now():
    results = run_checks()
    return jsonify({"results": results})


@app.get("/api/ai/anomalies")
@admin_required
def list_anomalies():
    status = request.args.get("status")
    service = request.args.get("service")
    sql = ("SELECT a.*, s.name AS service_name FROM ai_anomalies a "
           "LEFT JOIN ai_services s ON s.id = a.service_id WHERE 1=1")
    args = []
    if status in ("open", "investigating", "resolved"):
        sql += " AND a.status = ?"
        args.append(status)
    elif status == "unresolved":
        sql += " AND a.status != 'resolved'"
    if service:
        sql += " AND a.service_id = ?"
        args.append(service)
    sql += " ORDER BY CASE a.status WHEN 'open' THEN 0 WHEN 'investigating' THEN 1 ELSE 2 END, a.id DESC LIMIT 200"
    conn = get_conn()
    data = rows(conn.execute(sql, args))
    conn.close()
    return jsonify(data)


@app.post("/api/ai/anomalies")
@admin_required
def create_anomaly():
    d = body()
    service_id = d.get("service_id")
    level = d.get("level", "warning")
    message = (d.get("message") or "").strip()
    if level not in ("warning", "critical") or not message:
        return error("請填寫異常說明與等級")
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM ai_services WHERE id = ?", (service_id,)).fetchone():
        conn.close()
        return error("AI 服務不正確")
    cur = conn.execute(
        "INSERT INTO ai_anomalies (service_id, ts, level, type, message, source) VALUES (?, ?, ?, 'manual', ?, ?)",
        (service_id, now(), level, message, request.admin["username"]),
    )
    audit(conn, request.admin["username"], "手動新增異常紀錄", f"{service_id}#{cur.lastrowid}", message)
    conn.commit()
    conn.close()
    return jsonify({"id": cur.lastrowid}), 201


def notify(anomaly, note):
    """異常通報。此處先寫入稽核紀錄；正式環境可改為寄信或推送到通訊軟體。"""
    print(f"[notify] 異常 #{anomaly['id']}（{anomaly['service_id']}）已排除：{note}")


@app.put("/api/ai/anomalies/<int:aid>")
@admin_required
def update_anomaly(aid):
    d = body()
    status = d.get("status")
    note = (d.get("resolution_note") or "").strip()
    send_notice = bool(d.get("notify"))
    if status not in ("open", "investigating", "resolved"):
        return error("狀態不正確")
    if status == "resolved" and not note:
        return error("標記已排除前，請填寫處理說明")
    conn = get_conn()
    a = conn.execute("SELECT * FROM ai_anomalies WHERE id = ?", (aid,)).fetchone()
    if not a:
        conn.close()
        return error("找不到異常紀錄", 404)
    resolved = status == "resolved"
    conn.execute(
        "UPDATE ai_anomalies SET status = ?, resolution_note = ?, resolved_by = ?, resolved_at = ?, "
        "notified = ? WHERE id = ?",
        (status, note or a["resolution_note"],
         request.admin["username"] if resolved else None,
         now() if resolved else None,
         int(send_notice or a["notified"]), aid),
    )
    audit(conn, request.admin["username"], "更新異常狀態", f"#{aid}", f"{a['status']} → {status}")
    if send_notice:
        notify(dict(a), note)
        audit(conn, request.admin["username"], "異常通報", f"#{aid}", note)
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------- 啟動 ----------

init_db()

if __name__ == "__main__":
    start_background_monitor()
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
