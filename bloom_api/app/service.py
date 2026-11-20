"""三個功能的商業邏輯：產生評分依據、講義評分、教學評分。"""

from datetime import datetime, timezone

from pydantic import BaseModel

from . import prompts
from .bloom import HANDOUT_LEVEL_IDS, TEACHING_LEVEL_IDS, level_name
from .config import settings
from .llm import LLMError, structured_call
from .schemas import (
    CriterionOut,
    EvaluationItemOut,
    EvaluationSummaryOut,
    GenerateCriteriaRequest,
    GenerateCriteriaResponse,
    HandoutEvalItemOut,
    HandoutEvaluationRequest,
    HandoutEvaluationResponse,
    LLMCriteriaOutput,
    LLMHandoutOutput,
    LLMTeachingOutput,
    TeachingEvaluationRequest,
    TeachingEvaluationResponse,
)


class InputError(ValueError):
    """呼叫端傳入的資料不完整。"""


def _check_levels(items: list[BaseModel], expected: tuple[int, ...], what: str) -> None:
    got = sorted(i.level_id for i in items)
    if got != sorted(expected):
        raise LLMError(f"AI 的{what}層級不正確：預期 {list(expected)}，實際 {got}")


async def _call_with_retry(system, user, model, validate):
    last_err: LLMError | None = None
    for _ in range(max(1, settings.max_attempts)):
        try:
            out = await structured_call(system, user, model)
            validate(out)
            return out
        except LLMError as e:
            last_err = e
    assert last_err is not None
    raise last_err


def _require_criteria(criteria, level_ids: tuple[int, ...]) -> None:
    have = {c.level_id for c in criteria}
    missing = [lid for lid in level_ids if lid not in have]
    if missing:
        raise InputError(f"criteria 缺少 level_id {missing}")
    if len(have) != len(criteria):
        raise InputError("criteria 中有重複的 level_id")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- 1. 教材 → 評分依據 ----------

async def generate_criteria(req: GenerateCriteriaRequest) -> GenerateCriteriaResponse:
    out: LLMCriteriaOutput = await _call_with_retry(
        prompts.CRITERIA_SYSTEM,
        prompts.build_criteria_user(req),
        LLMCriteriaOutput,
        lambda o: _check_levels(o.criteria, TEACHING_LEVEL_IDS, "評分依據"),
    )
    return GenerateCriteriaResponse(
        task_id=req.task_id,
        criteria=[
            CriterionOut(level_id=c.level_id, level_name=level_name(c.level_id),
                         criteria_content=c.criteria_content.strip())
            for c in sorted(out.criteria, key=lambda c: c.level_id)
        ],
    )


# ---------- 2. 講義評分 ----------

async def evaluate_handout(req: HandoutEvaluationRequest) -> HandoutEvaluationResponse:
    _require_criteria(req.criteria, HANDOUT_LEVEL_IDS)
    out: LLMHandoutOutput = await _call_with_retry(
        prompts.HANDOUT_SYSTEM,
        prompts.build_handout_user(req),
        LLMHandoutOutput,
        lambda o: _check_levels(o.items, HANDOUT_LEVEL_IDS, "評分"),
    )
    return HandoutEvaluationResponse(
        handout_id=req.handout_id,
        handout_evaluated_at=_now(),
        items=[
            HandoutEvalItemOut(level_id=i.level_id, level_name=level_name(i.level_id),
                               handout_score=i.score, handout_comment=i.comment.strip(),
                               evidence=i.evidence)
            for i in sorted(out.items, key=lambda i: i.level_id)
        ],
    )


# ---------- 3. 教學評分 ----------

async def evaluate_teaching(req: TeachingEvaluationRequest) -> TeachingEvaluationResponse:
    _require_criteria(req.criteria, TEACHING_LEVEL_IDS)

    def validate(o: LLMTeachingOutput) -> None:
        _check_levels(o.items, TEACHING_LEVEL_IDS, "評分")
        _check_levels(o.summaries, TEACHING_LEVEL_IDS, "摘要")

    out: LLMTeachingOutput = await _call_with_retry(
        prompts.TEACHING_SYSTEM, prompts.build_teaching_user(req), LLMTeachingOutput, validate
    )
    return TeachingEvaluationResponse(
        session_id=req.session_id,
        ai_evaluated_at=_now(),
        items=[
            EvaluationItemOut(level_id=i.level_id, level_name=level_name(i.level_id),
                              ai_score=i.score, ai_comment=i.comment.strip(), evidence=i.evidence)
            for i in sorted(out.items, key=lambda i: i.level_id)
        ],
        summaries=[
            EvaluationSummaryOut(level_id=s.level_id, level_name=level_name(s.level_id),
                                 summary_text=s.summary_text.strip())
            for s in sorted(out.summaries, key=lambda s: s.level_id)
        ],
    )
