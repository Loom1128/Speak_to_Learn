"""API 的請求／回應格式，以及要求 AI 輸出的結構。

欄位命名盡量沿用 ER 設計（ER_資料表.xlsx），方便呼叫端直接寫入資料庫。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Score = Literal[0, 1, 2]
LevelId = Literal[1, 2, 3, 4, 5, 6]


# ---------- 共用 ----------

class Criterion(BaseModel):
    """task_criteria 的一列。"""
    level_id: LevelId
    criteria_content: str = Field(min_length=1)


# ---------- 1. 產生評分依據（教材 → task_criteria） ----------

class MaterialInput(BaseModel):
    material_id: int
    material_title: str
    material_type: Literal["影片", "ppt", "pdf", "word"]
    content_text: str = Field(
        min_length=1,
        description="教材的文字內容。影片請傳逐字稿；ppt/pdf/word 請傳擷取出的文字。",
    )


class GenerateCriteriaRequest(BaseModel):
    task_id: int
    task_title: str
    description: str | None = None
    materials: list[MaterialInput] = Field(min_length=1)


class CriterionOut(BaseModel):
    level_id: LevelId
    level_name: str
    criteria_content: str


class GenerateCriteriaResponse(BaseModel):
    task_id: int
    criteria: list[CriterionOut]  # 6 筆，可直接寫入 task_criteria


# ---------- 2. 講義評分（handout_evaluations / handout_eval_items） ----------

class HandoutEvaluationRequest(BaseModel):
    handout_id: int
    handout_title: str
    extracted_text: str = Field(min_length=1, description="handouts.extracted_text")
    criteria: list[Criterion] = Field(
        min_length=1, description="本任務的 task_criteria，至少需含 level 1、2、4"
    )


class HandoutEvalItemOut(BaseModel):
    level_id: LevelId
    level_name: str
    handout_score: Score
    handout_comment: str
    evidence: list[str] = Field(default_factory=list, description="講義中的引用依據（不入庫，可供除錯）")


class HandoutEvaluationResponse(BaseModel):
    handout_id: int
    handout_evaluated_at: datetime
    items: list[HandoutEvalItemOut]  # level 1、2、4


# ---------- 3. 教學評分（teaching_evaluations / evaluation_items / evaluation_summaries） ----------

class TranscriptSegment(BaseModel):
    start_sec: float
    end_sec: float
    text: str


class TranscriptInput(BaseModel):
    full_text: str = Field(min_length=1)
    segments: list[TranscriptSegment] = Field(default_factory=list)


class QAInput(BaseModel):
    seq: int
    difficulty: Literal[0, 1, 2] = Field(description="0 淺 / 1 中 / 2 深")
    question_text: str
    answer_text: str


class TeachingEvaluationRequest(BaseModel):
    session_id: int
    transcript: TranscriptInput
    qa: list[QAInput] = Field(default_factory=list)
    criteria: list[Criterion] = Field(min_length=6, max_length=6)
    handout_text: str | None = Field(default=None, description="選填：本場次使用的講義擷取文字，作為背景參考")


class EvaluationItemOut(BaseModel):
    level_id: LevelId
    level_name: str
    ai_score: Score
    ai_comment: str
    evidence: list[str] = Field(default_factory=list)


class EvaluationSummaryOut(BaseModel):
    level_id: LevelId
    level_name: str
    summary_text: str  # 不含分數，給教師評分時參考


class TeachingEvaluationResponse(BaseModel):
    session_id: int
    ai_evaluated_at: datetime
    items: list[EvaluationItemOut]          # 6 筆 → evaluation_items
    summaries: list[EvaluationSummaryOut]   # 6 筆 → evaluation_summaries


# ---------- AI 結構化輸出（Claude structured outputs 用） ----------

class _LLMCriterion(BaseModel):
    level_id: LevelId
    criteria_content: str


class LLMCriteriaOutput(BaseModel):
    criteria: list[_LLMCriterion]


class _LLMScoredItem(BaseModel):
    level_id: LevelId
    evidence: list[str]
    comment: str
    score: Score


class LLMHandoutOutput(BaseModel):
    items: list[_LLMScoredItem]


class _LLMSummary(BaseModel):
    level_id: LevelId
    summary_text: str


class LLMTeachingOutput(BaseModel):
    items: list[_LLMScoredItem]
    summaries: list[_LLMSummary]
