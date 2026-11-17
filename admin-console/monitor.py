"""AI 服務監控：定期健康檢查、寫入檢查紀錄、偵測到異常時自動寫入異常紀錄。"""
import os
import random
import threading
import time
import urllib.error
import urllib.request

from database import audit, get_conn, now

INTERVAL_SEC = int(os.environ.get("MONITOR_INTERVAL", "60"))
_lock = threading.Lock()


def _probe(service):
    """回傳 (status, latency_ms, message)。"""
    if not service["enabled"]:
        return "disabled", None, "服務已停用"

    endpoint = service["endpoint"]
    threshold = service["latency_threshold_ms"]

    if endpoint.startswith("mock://"):
        # 內建模擬器：方便在沒有真實 AI 服務時展示監控與異常流程
        base = 900 if service["id"] == "listener" else 3500
        latency = int(random.gauss(base, base * 0.35))
        roll = random.random()
        if roll < 0.04:
            return "down", None, "模擬：連線逾時"
        if roll < 0.12:
            latency = int(threshold * random.uniform(1.1, 1.8))
        latency = max(latency, 80)
    else:
        start = time.perf_counter()
        try:
            req = urllib.request.Request(endpoint, method="GET")
            with urllib.request.urlopen(req, timeout=service["timeout_sec"]) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            return "down", None, f"HTTP {e.code}"
        except Exception as e:  # 逾時、DNS、連線拒絕等
            return "down", None, f"{type(e).__name__}: {e}"[:200]
        latency = int((time.perf_counter() - start) * 1000)
        if not 200 <= code < 300:
            return "down", latency, f"HTTP {code}"

    if latency > threshold:
        return "slow", latency, f"回應 {latency} ms，超過門檻 {threshold} ms"
    return "ok", latency, ""


def _open_anomaly(conn, service_id, type_, level, message):
    """同一服務、同一類型若已有未排除的異常，就不重複開立。"""
    exists = conn.execute(
        "SELECT id FROM ai_anomalies WHERE service_id IS ? AND type = ? AND status != 'resolved'",
        (service_id, type_),
    ).fetchone()
    if exists:
        return None
    cur = conn.execute(
        "INSERT INTO ai_anomalies (service_id, ts, level, type, message, source) "
        "VALUES (?, ?, ?, ?, ?, 'monitor')",
        (service_id, now(), level, type_, message),
    )
    audit(conn, "monitor", "自動寫入異常紀錄", f"{service_id or 'policy'}#{cur.lastrowid}", message)
    return cur.lastrowid


def run_checks():
    """檢查兩個 AI 服務與治理政策。回傳本次各服務的檢查結果。"""
    with _lock:
        conn = get_conn()
        results = []
        services = conn.execute("SELECT * FROM ai_services ORDER BY rowid").fetchall()
        for s in services:
            status, latency, message = _probe(s)
            conn.execute(
                "INSERT INTO ai_checks (service_id, ts, status, latency_ms, message) VALUES (?, ?, ?, ?, ?)",
                (s["id"], now(), status, latency, message),
            )
            if status == "down":
                _open_anomaly(conn, s["id"], "down", "critical", f"{s['name']} 無法連線：{message}")
            elif status == "slow":
                _open_anomaly(conn, s["id"], "slow", "warning", f"{s['name']} 回應偏慢：{message}")
            results.append({"service_id": s["id"], "status": status, "latency_ms": latency, "message": message})

        # 確認 AI 禁止自動化學習政策落實
        violated = conn.execute("SELECT key, label FROM ai_policies WHERE value != 0").fetchall()
        for p in violated:
            _open_anomaly(conn, None, f"policy:{p['key']}", "critical", f"治理政策未落實：{p['label']} 被開啟")

        # 只保留最近 7 天的檢查紀錄
        conn.execute("DELETE FROM ai_checks WHERE ts < datetime('now', 'localtime', '-7 days')")
        conn.commit()
        conn.close()
        return results


def _loop(stop_event):
    while not stop_event.is_set():
        try:
            run_checks()
        except Exception as e:  # 監控本身不能因單次錯誤而停止
            print(f"[monitor] 檢查失敗：{e}")
        stop_event.wait(INTERVAL_SEC)


def start_background_monitor():
    stop_event = threading.Event()
    t = threading.Thread(target=_loop, args=(stop_event,), daemon=True, name="ai-monitor")
    t.start()
    return stop_event
