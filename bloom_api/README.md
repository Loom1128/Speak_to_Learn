# Bloom 評分 AI API

Speak to Learn 的評分 AI 服務：對學生的**講義**與**教學**，依 Bloom 認知層級打分數（0 / 1 / 2）並給評論。

## 評分的兩個基準

| 基準 | 來源 | 在哪裡 |
|---|---|---|
| 一、Bloom 層級定義 | 寫在程式內（記憶、理解、應用、分析、評鑑、創造 + 可觀察指標 + 0/1/2 分數定義） | `app/bloom.py` |
| 二、本任務評分依據 | 教師上傳的教材 → AI 依 Bloom 定義產生每層級的評分依據，存入 `task_criteria` | `POST /api/v1/criteria/generate` |

基準二的用意：評分 AI 除了懂 Bloom，也必須知道「這次該教什麼」。教材是學生教 AI 的內容來源，
所以評分依據會寫出教材中的關鍵概念與正確內容，評分 AI 才能判斷學生教得對不對、完不完整。

## 流程

```
教師上傳教材 ──► ① /criteria/generate ──► task_criteria（6 筆，教師可再修改）
                                              │
學生上傳講義 ──► ② /evaluations/handout ◄─────┤  → handout_evaluations / handout_eval_items（層級 1、2、4）
                                              │
教學＋問答完成 ─► ③ /evaluations/teaching ◄───┘  → teaching_evaluations / evaluation_items（6 層級）
                                                  + evaluation_summaries（6 段摘要，不含分數，給老師複評）
```

本服務**不連資料庫**：主系統從 DB 讀出資料、呼叫 API、再把回傳結果寫回 DB。回傳欄位名稱與 ER 設計一致。

## 端點

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/health` | 健康檢查 |
| GET | `/api/v1/bloom-levels` | 回傳程式內的 Bloom 定義與分數定義 |
| POST | `/api/v1/criteria/generate` | 教材文字 → 6 層級評分依據 |
| POST | `/api/v1/evaluations/handout` | 講義評分（記憶、理解、分析） |
| POST | `/api/v1/evaluations/teaching` | 教學評分（6 層級分數＋評論＋摘要） |

完整的請求／回應格式啟動後看 `http://localhost:8000/docs`。

### 範例：教學評分

```json
POST /api/v1/evaluations/teaching
{
  "session_id": 11,
  "transcript": {
    "full_text": "……",
    "segments": [{ "start_sec": 0, "end_sec": 12.5, "text": "今天要教光合作用……" }]
  },
  "qa": [
    { "seq": 1, "difficulty": 0, "question_text": "什麼是葉綠素？", "answer_text": "……" },
    { "seq": 2, "difficulty": 2, "question_text": "如果沒有光會怎樣？", "answer_text": "……" }
  ],
  "criteria": [ { "level_id": 1, "criteria_content": "……" }, "…共 6 筆（task_criteria）" ],
  "handout_text": "（選填）講義擷取文字"
}
```

回應：

```json
{
  "session_id": 11,
  "ai_evaluated_at": "2026-11-20T08:00:00Z",
  "items": [
    { "level_id": 1, "level_name": "記憶", "ai_score": 2, "ai_comment": "……", "evidence": ["[00:00] ……"] }
  ],
  "summaries": [
    { "level_id": 1, "level_name": "記憶", "summary_text": "……" }
  ]
}
```

`evidence` 是 AI 引用的原文依據，資料表沒有對應欄位，可不入庫（方便除錯與向學生說明）。

## 注意事項

- **教材要先轉成文字**：影片傳逐字稿、ppt/pdf/word 傳擷取文字（`content_text`）。檔案轉文字不在本服務範圍。
- 評分依據產生後建議讓教師檢視、修改，再發布任務。
- 學生內容一律被當成資料而非指令，講義或講解中夾帶「給我滿分」之類的文字不會影響評分。
- AI 回傳若缺層級或格式不符，會自動重試（`BLOOM_MAX_ATTEMPTS`），仍失敗回 502。
- 若主模型因安全分類器拒答，會由 Claude API 自動改用備援模型（server-side fallback）。

## 執行

```bash
cd bloom_api
pip install -r requirements-dev.txt
cp .env.example .env   # 填入 ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload
```

測試（AI 呼叫已模擬，不需金鑰）：

```bash
pytest -q
```

## 設定（環境變數）

| 變數 | 預設 | 說明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | 必填 |
| `BLOOM_MODEL` | `claude-opus-5-5` | 評分模型 |
| `BLOOM_EFFORT` | `high` | 思考深度 low/medium/high/xhigh/max |
| `BLOOM_MAX_TOKENS` | `16000` | 單次輸出上限 |
| `BLOOM_MAX_ATTEMPTS` | `2` | 格式不符時的嘗試次數 |
| `BLOOM_SERVICE_API_KEY` | 空 | 設定後呼叫端需帶 `X-API-Key` header |

## 程式結構

```
app/
  bloom.py     Bloom 定義（基準一）、講義層級、分數定義
  prompts.py   三種任務的提示詞
  schemas.py   請求／回應格式、AI 結構化輸出格式
  llm.py       呼叫 Claude（結構化輸出、prompt cache、拒答處理）
  service.py   商業邏輯與層級完整性檢查
  main.py      FastAPI 路由
tests/         API 測試
```
