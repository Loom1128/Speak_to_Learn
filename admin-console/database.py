"""SQLite 資料庫：建表與初始資料。"""
import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get("ADMIN_DB_PATH", os.path.join(os.path.dirname(__file__), "admin.db"))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    id          TEXT PRIMARY KEY,           -- admin / teacher / student
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL DEFAULT '',
    role_id       TEXT NOT NULL REFERENCES roles(id),
    active        INTEGER NOT NULL DEFAULT 1,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);

-- 可被授權的系統資源
CREATE TABLE IF NOT EXISTS resources (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,
    note     TEXT NOT NULL DEFAULT '',
    sort     INTEGER NOT NULL DEFAULT 0
);

-- 角色 × 資源 的存取等級；locked = 1 代表由系統固定，管理者不可修改
CREATE TABLE IF NOT EXISTS permissions (
    role_id     TEXT NOT NULL REFERENCES roles(id),
    resource_id TEXT NOT NULL REFERENCES resources(id),
    level       TEXT NOT NULL CHECK (level IN ('none', 'own', 'read', 'write')),
    locked      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (role_id, resource_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    actor  TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);

-- 兩個 AI 功能：聽眾 AI、評分 AI
CREATE TABLE IF NOT EXISTS ai_services (
    id                   TEXT PRIMARY KEY,   -- listener / scoring
    name                 TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    enabled              INTEGER NOT NULL DEFAULT 1,
    endpoint             TEXT NOT NULL,
    model                TEXT NOT NULL DEFAULT '',
    timeout_sec          INTEGER NOT NULL DEFAULT 15,
    latency_threshold_ms INTEGER NOT NULL DEFAULT 3000,
    updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_checks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id TEXT NOT NULL REFERENCES ai_services(id),
    ts         TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('ok', 'slow', 'down', 'disabled')),
    latency_ms INTEGER,
    message    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_checks_service_ts ON ai_checks(service_id, ts);

CREATE TABLE IF NOT EXISTS ai_anomalies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id      TEXT REFERENCES ai_services(id),
    ts              TEXT NOT NULL,
    level           TEXT NOT NULL CHECK (level IN ('warning', 'critical')),
    type            TEXT NOT NULL,          -- slow / down / policy / manual
    message         TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'monitor',
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved')),
    resolution_note TEXT NOT NULL DEFAULT '',
    resolved_by     TEXT,
    resolved_at     TEXT,
    notified        INTEGER NOT NULL DEFAULT 0
);

-- AI 治理政策：全部固定為停用（value = 0），locked = 1
CREATE TABLE IF NOT EXISTS ai_policies (
    key    TEXT PRIMARY KEY,
    label  TEXT NOT NULL,
    note   TEXT NOT NULL DEFAULT '',
    value  INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 1
);
"""

ROLES = [
    ("admin", "管理者", "帳號權限、平台與 AI 服務維運"),
    ("teacher", "教師", "建立教學任務、檢視學習資料、人工評分與匯出"),
    ("student", "學生", "觀看教學影片、對聽眾 AI 進行語音教學"),
]

RESOURCES = [
    # id, name, category, note
    ("accounts", "帳號管理", "帳號與平台", ""),
    ("roles_permissions", "角色與權限設定", "帳號與平台", ""),
    ("ai_services", "AI 服務設定與監控", "帳號與平台", ""),
    ("ai_anomalies", "AI 異常紀錄", "帳號與平台", ""),
    ("teaching_tasks", "教學任務（含聽眾 AI 提問難度）", "教學與評量", "淺・中・深題數由教師設定"),
    ("teaching_videos", "教學影片", "教學與評量", ""),
    ("learning_records", "學生學習資料（錄音、AI 摘要）", "教學與評量", "own = 僅本人"),
    ("grading", "人工評分", "教學與評量", ""),
    ("export", "學習資料匯出", "教學與評量", ""),
    ("bloom_rubric", "Bloom 評分規準", "系統鎖定", "寫死於程式碼，任何角色皆不可修改"),
]

# (role, resource): (level, locked)
DEFAULT_PERMISSIONS = {
    ("admin", "accounts"): ("write", 1),
    ("admin", "roles_permissions"): ("write", 1),
    ("admin", "ai_services"): ("write", 0),
    ("admin", "ai_anomalies"): ("write", 0),
    ("admin", "teaching_tasks"): ("none", 0),
    ("admin", "teaching_videos"): ("read", 0),
    ("admin", "learning_records"): ("none", 1),
    ("admin", "grading"): ("none", 1),
    ("admin", "export"): ("none", 1),
    ("admin", "bloom_rubric"): ("read", 1),

    ("teacher", "accounts"): ("none", 0),
    ("teacher", "roles_permissions"): ("none", 1),
    ("teacher", "ai_services"): ("none", 0),
    ("teacher", "ai_anomalies"): ("read", 0),
    ("teacher", "teaching_tasks"): ("write", 0),
    ("teacher", "teaching_videos"): ("write", 0),
    ("teacher", "learning_records"): ("read", 0),
    ("teacher", "grading"): ("write", 0),
    ("teacher", "export"): ("write", 0),
    ("teacher", "bloom_rubric"): ("read", 1),

    ("student", "accounts"): ("none", 1),
    ("student", "roles_permissions"): ("none", 1),
    ("student", "ai_services"): ("none", 1),
    ("student", "ai_anomalies"): ("none", 0),
    ("student", "teaching_tasks"): ("read", 0),
    ("student", "teaching_videos"): ("read", 0),
    ("student", "learning_records"): ("own", 0),
    ("student", "grading"): ("none", 1),
    ("student", "export"): ("none", 0),
    ("student", "bloom_rubric"): ("none", 1),
}

AI_SERVICES = [
    # mock:// 開頭的端點由內建模擬器回應，正式環境請改成 AI 服務的健康檢查網址
    ("listener", "聽眾 AI", "接收學生語音教學並依任務難度提問", "mock://listener", "listener-v1", 15, 3000),
    ("scoring", "評分 AI", "依 Bloom 六層級評分並產生各層級摘要，交由教師複核", "mock://scoring", "scoring-v1", 60, 8000),
]

AI_POLICIES = [
    ("auto_training", "依學生資料自動訓練模型", "聽眾 AI、評分 AI 皆不以學生錄音或回答進行訓練"),
    ("kb_auto_update", "依評量結果自動更新知識庫", "知識庫僅能由人工維護"),
    ("auto_adjust_scale", "依資料自動調整評分尺度", "評分 AI 一律依固定規準評分"),
    ("modify_rubric", "AI 修改 Bloom 評分規準", "規準寫死於程式碼"),
]


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    t = now()
    conn.executemany("INSERT OR IGNORE INTO roles (id, name, description) VALUES (?, ?, ?)", ROLES)
    conn.executemany(
        "INSERT OR IGNORE INTO resources (id, name, category, note, sort) VALUES (?, ?, ?, ?, ?)",
        [(r[0], r[1], r[2], r[3], i) for i, r in enumerate(RESOURCES)],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO permissions (role_id, resource_id, level, locked) VALUES (?, ?, ?, ?)",
        [(k[0], k[1], v[0], v[1]) for k, v in DEFAULT_PERMISSIONS.items()],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO ai_services (id, name, description, endpoint, model, timeout_sec, "
        "latency_threshold_ms, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [s + (t,) for s in AI_SERVICES],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO ai_policies (key, label, note) VALUES (?, ?, ?)", AI_POLICIES
    )

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        admin_pw = os.environ.get("ADMIN_PASSWORD", "admin1234")
        seed_users = [
            ("系統管理者", "admin", "", "admin", admin_pw),
            ("王老師", "t1001", "", "teacher", "changeme123"),
            ("陳老師", "t1002", "", "teacher", "changeme123"),
            ("學生 A", "s2026001", "", "student", "changeme123"),
            ("學生 B", "s2026002", "", "student", "changeme123"),
        ]
        conn.executemany(
            "INSERT INTO users (name, username, email, role_id, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(n, u, e, r, generate_password_hash(p), t) for n, u, e, r, p in seed_users],
        )
    conn.commit()
    conn.close()


def audit(conn, actor, action, target="", detail=""):
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
        (now(), actor, action, target, detail),
    )
