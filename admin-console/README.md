# AI 教學評量系統 · 管理後台

前端：HTML + CSS（原生 JavaScript 呼叫 API）
後端：Python（Flask + SQLite）

## 頁面

| 頁面 | 網址 | 功能 |
|---|---|---|
| 登入 | `/login` | 僅限管理者帳號登入 |
| 頁面 1：帳號與權限 | `/accounts` | ① 管理帳號（新增、編輯、停用、重設密碼、刪除）② 設定帳號角色 ③ 設定角色的資料存取權限 |
| 頁面 2：AI 服務 | `/ai` | ① 管理兩個 AI 功能（聽眾 AI、評分 AI）② 監測兩個 AI 功能 ③ 紀錄並處理 AI 異常 |

## 執行

```bash
pip install -r requirements.txt
python app.py
```

開啟 http://127.0.0.1:5000 ，以預設管理者帳號 `admin` / `admin1234` 登入。
**第一次登入後請到「管理帳號」重設 admin 密碼**，或啟動前用環境變數指定：

```bash
ADMIN_PASSWORD='你的密碼' SECRET_KEY='一串隨機字串' python app.py
```

其他環境變數：

| 變數 | 預設 | 說明 |
|---|---|---|
| `MONITOR_INTERVAL` | `60` | AI 監測的檢查間隔（秒），展示時可設為 `10` |
| `ADMIN_DB_PATH` | `./admin.db` | SQLite 檔案位置 |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | 伺服器位址 |

## AI 監測如何運作

- `monitor.py` 在背景依 `MONITOR_INTERVAL` 定期檢查兩個 AI 服務，結果寫入 `ai_checks`。
- 端點以 `mock://` 開頭時，由內建模擬器回應（會隨機出現延遲或斷線，方便展示異常流程）。
  正式串接時，在「管理 AI 功能」把端點改成 AI 服務的健康檢查網址（`http(s)://...`），回應 2xx 即視為正常。
- 回應超過「延遲警示門檻」→ 開立「警告」異常；連線失敗或非 2xx → 開立「嚴重」異常。
  同一服務、同一類型若已有未排除的異常，不會重複開立。
- 每次檢查也會確認 AI 治理政策（禁止自動訓練、知識庫自動更新、自動調整評分尺度、修改評分規準）維持停用，若被開啟即開立嚴重異常。
- 異常排除時須填寫處理說明，可勾選「通報」；通報目前寫入操作紀錄並輸出到主控台，正式環境可改寫 `app.py` 的 `notify()` 寄信或推播。

## 權限設計

- 權限等級：`none` 無權限、`own` 僅本人（學生）、`read` 檢視、`write` 編輯。
- `locked = 1` 的權限由系統固定，前端顯示鎖頭，後端 API 也會拒絕修改。例如：
  - Bloom 評分規準：任何角色都不能修改。
  - 管理者不能存取學生學習資料、評分與匯出（屬於教師權限）。
- AI 治理政策的 API（`PUT /api/ai/policies/<key>`）一律回傳 403。
- 保護機制：不能停用／刪除自己、不能移除自己的管理者角色、系統至少保留一位啟用中的管理者。
- 所有帳號、角色、權限、AI 設定與異常處理都會寫入 `audit_log`。

## 檔案結構

```
app.py           Flask 路由與 API
database.py      資料表結構與初始資料
monitor.py       AI 健康檢查與異常偵測
static/
  login.html
  accounts.html  頁面 1
  ai.html        頁面 2
  css/style.css
  js/common.js   共用：API 呼叫、提示、分頁切換
  js/accounts.js
  js/ai.js
```

## API 一覽

```
POST /api/login · POST /api/logout · GET /api/me

GET    /api/users?role=&active=&q=
POST   /api/users
PUT    /api/users/<id>
POST   /api/users/<id>/reset-password
DELETE /api/users/<id>
PUT    /api/users/<id>/role
GET    /api/roles
GET    /api/permissions
PUT    /api/permissions          {role_id, resource_id, level}
GET    /api/audit?limit=

GET    /api/ai/services
PUT    /api/ai/services/<id>     {enabled, endpoint, model, timeout_sec, latency_threshold_ms}
GET    /api/ai/policies
GET    /api/ai/status
POST   /api/ai/check
GET    /api/ai/anomalies?status=&service=
POST   /api/ai/anomalies         {service_id, level, message}
PUT    /api/ai/anomalies/<id>    {status, resolution_note, notify}
```
