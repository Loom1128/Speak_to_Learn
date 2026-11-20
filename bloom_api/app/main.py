"""Speak to Learn｜Bloom 評分 AI API

啟動：uvicorn app.main:app --reload
文件：http://localhost:8000/docs
"""

import logging

import anthropic
from fastapi import Depends, FastAPI, Header, HTTPException

from . import service
from .bloom import BLOOM_LEVELS, HANDOUT_LEVEL_IDS, SCORE_RUBRIC
from .config import settings
from .llm import LLMError
from .schemas import (
    GenerateCriteriaRequest,
    GenerateCriteriaResponse,
    HandoutEvaluationRequest,
    HandoutEvaluationResponse,
    TeachingEvaluationRequest,
    TeachingEvaluationResponse,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Speak to Learn｜Bloom 評分 AI API",
    version="1.0.0",
    description=(
        "依「程式內的 Bloom 層級定義」與「由教師教材產生的評分依據（task_criteria）」，"
        "對學生的講義與教學進行 Bloom 層級評分。"
    ),
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.service_api_key and x_api_key != settings.service_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key 錯誤或未提供")


async def _run(coro):
    try:
        return await coro
    except service.InputError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 服務繁忙，請稍後再試")
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        logging.exception("Claude API error")
        raise HTTPException(status_code=503, detail=f"AI 服務暫時無法使用：{type(e).__name__}")


@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.model}


@app.get("/api/v1/bloom-levels")
async def bloom_levels():
    """回傳程式內的 Bloom 定義（基準一），前端可直接顯示。"""
    return {
        "levels": [
            {
                "level_id": lv.level_id,
                "level_name": lv.level_name,
                "english": lv.english,
                "definition": lv.definition,
                "indicators": list(lv.indicators),
                "used_for_handout": lv.level_id in HANDOUT_LEVEL_IDS,
            }
            for lv in BLOOM_LEVELS.values()
        ],
        "score_rubric": SCORE_RUBRIC,
    }


@app.post(
    "/api/v1/criteria/generate",
    response_model=GenerateCriteriaResponse,
    dependencies=[Depends(require_api_key)],
    summary="教材 → 評分依據（基準二），結果寫入 task_criteria",
)
async def generate_criteria(req: GenerateCriteriaRequest):
    return await _run(service.generate_criteria(req))


@app.post(
    "/api/v1/evaluations/handout",
    response_model=HandoutEvaluationResponse,
    dependencies=[Depends(require_api_key)],
    summary="講義評分（記憶、理解、分析），結果寫入 handout_evaluations / handout_eval_items",
)
async def evaluate_handout(req: HandoutEvaluationRequest):
    return await _run(service.evaluate_handout(req))


@app.post(
    "/api/v1/evaluations/teaching",
    response_model=TeachingEvaluationResponse,
    dependencies=[Depends(require_api_key)],
    summary="教學評分（Bloom 六層級＋分段摘要），結果寫入 teaching_evaluations / evaluation_items / evaluation_summaries",
)
async def evaluate_teaching(req: TeachingEvaluationRequest):
    return await _run(service.evaluate_teaching(req))
