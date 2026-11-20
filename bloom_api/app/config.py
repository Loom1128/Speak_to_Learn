import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Claude 模型與思考深度。評分需要穩定、仔細，預設 effort=high。
    model: str = os.getenv("BLOOM_MODEL", "claude-opus-5-5")
    effort: str = os.getenv("BLOOM_EFFORT", "high")  # low | medium | high | xhigh | max
    max_tokens: int = int(os.getenv("BLOOM_MAX_TOKENS", "16000"))
    # 若設定，呼叫本 API 時需帶 header：X-API-Key
    service_api_key: str | None = os.getenv("BLOOM_SERVICE_API_KEY") or None
    # AI 輸出缺層級或格式不符時的重試次數
    max_attempts: int = int(os.getenv("BLOOM_MAX_ATTEMPTS", "2"))


settings = Settings()
