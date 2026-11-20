"""API 測試：以假的 AI 回應取代 Claude，不需要 API 金鑰。"""

import pytest
from fastapi.testclient import TestClient

from app import service
from app.llm import LLMError
from app.main import app
from app.schemas import LLMCriteriaOutput, LLMHandoutOutput, LLMTeachingOutput

client = TestClient(app)

CRITERIA = [{"level_id": i, "criteria_content": f"層級 {i} 的評分依據"} for i in range(1, 7)]


def fake(responses):
    """依序回傳 responses 中的物件（例外則丟出），並記錄收到的 prompt。"""
    calls = []

    async def _fake(system, user, model):
        calls.append({"system": system, "user": user, "model": model})
        r = responses[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return model.model_validate(r)

    return _fake, calls


def item(level_id, score=1):
    return {"level_id": level_id, "evidence": ["引用"], "comment": "評論", "score": score}


def test_bloom_levels():
    r = client.get("/api/v1/bloom-levels")
    assert r.status_code == 200
    assert [lv["level_name"] for lv in r.json()["levels"]] == ["記憶", "理解", "應用", "分析", "評鑑", "創造"]


def test_generate_criteria(monkeypatch):
    f, calls = fake([{"criteria": [{"level_id": i, "criteria_content": f" 依據{i} "} for i in (6, 5, 4, 3, 2, 1)]}])
    monkeypatch.setattr(service, "structured_call", f)
    r = client.post("/api/v1/criteria/generate", json={
        "task_id": 7, "task_title": "光合作用",
        "materials": [{"material_id": 1, "material_title": "講義", "material_type": "pdf",
                       "content_text": "光合作用是植物利用光能……"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["level_id"] for c in body["criteria"]] == [1, 2, 3, 4, 5, 6]
    assert body["criteria"][0] == {"level_id": 1, "level_name": "記憶", "criteria_content": "依據1"}
    assert calls[0]["model"] is LLMCriteriaOutput
    assert "光合作用是植物利用光能" in calls[0]["user"]


def test_handout_only_levels_1_2_4(monkeypatch):
    f, calls = fake([{"items": [item(1, 2), item(2, 1), item(4, 0)]}])
    monkeypatch.setattr(service, "structured_call", f)
    r = client.post("/api/v1/evaluations/handout", json={
        "handout_id": 3, "handout_title": "我的講義", "extracted_text": "講義內容", "criteria": CRITERIA,
    })
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(i["level_id"], i["handout_score"]) for i in items] == [(1, 2), (2, 1), (4, 0)]
    assert calls[0]["model"] is LLMHandoutOutput
    # 只把 1、2、4 的評分依據送給 AI
    assert 'level_id="3"' not in calls[0]["user"] and 'level_id="4"' in calls[0]["user"]


def test_handout_missing_criteria():
    r = client.post("/api/v1/evaluations/handout", json={
        "handout_id": 3, "handout_title": "t", "extracted_text": "x",
        "criteria": [{"level_id": 1, "criteria_content": "a"}],
    })
    assert r.status_code == 422
    assert "[2, 4]" in r.json()["detail"]


def teaching_payload():
    return {
        "session_id": 11,
        "transcript": {"full_text": "今天要教光合作用",
                       "segments": [{"start_sec": 75, "end_sec": 80, "text": "今天要教光合作用"}]},
        "qa": [{"seq": 2, "difficulty": 2, "question_text": "深題", "answer_text": "答2"},
               {"seq": 1, "difficulty": 0, "question_text": "淺題", "answer_text": "答1"}],
        "criteria": CRITERIA,
    }


def test_teaching(monkeypatch):
    out = {"items": [item(i, i % 3) for i in range(1, 7)],
           "summaries": [{"level_id": i, "summary_text": f"摘要{i}"} for i in range(1, 7)]}
    f, calls = fake([out])
    monkeypatch.setattr(service, "structured_call", f)
    r = client.post("/api/v1/evaluations/teaching", json=teaching_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert [i["ai_score"] for i in body["items"]] == [1, 2, 0, 1, 2, 0]
    assert len(body["summaries"]) == 6
    user = calls[0]["user"]
    assert "[01:15] 今天要教光合作用" in user
    assert user.index('seq="1"') < user.index('seq="2"')
    assert calls[0]["model"] is LLMTeachingOutput


def test_teaching_retries_when_level_missing(monkeypatch):
    bad = {"items": [item(i) for i in range(1, 6)],
           "summaries": [{"level_id": i, "summary_text": "s"} for i in range(1, 7)]}
    good = {"items": [item(i) for i in range(1, 7)],
            "summaries": [{"level_id": i, "summary_text": "s"} for i in range(1, 7)]}
    f, calls = fake([bad, good])
    monkeypatch.setattr(service, "structured_call", f)
    r = client.post("/api/v1/evaluations/teaching", json=teaching_payload())
    assert r.status_code == 200
    assert len(calls) == 2


def test_llm_error_maps_to_502(monkeypatch):
    f, _ = fake([LLMError("AI 拒絕處理"), LLMError("AI 拒絕處理")])
    monkeypatch.setattr(service, "structured_call", f)
    r = client.post("/api/v1/evaluations/teaching", json=teaching_payload())
    assert r.status_code == 502


@pytest.mark.parametrize("score", [3, -1])
def test_invalid_score_rejected(score):
    with pytest.raises(Exception):
        LLMHandoutOutput.model_validate({"items": [item(1, score)]})
