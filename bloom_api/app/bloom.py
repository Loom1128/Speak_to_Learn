"""Bloom 認知層級定義（寫在程式內，對應資料表 bloom_levels）。

採用 Anderson & Krathwohl (2001) 修訂版 Bloom 認知歷程向度。
這份定義是評分 AI 的「基準 1」，所有評分都以此為共同語言；
「基準 2」則是由教師教材 + 本定義產生的 task_criteria（每個任務各自一份）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BloomLevel:
    level_id: int
    level_name: str
    english: str
    definition: str
    indicators: tuple[str, ...]  # 學生在「教 AI」時，此層級可觀察到的行為
    verbs: tuple[str, ...]


BLOOM_LEVELS: dict[int, BloomLevel] = {
    1: BloomLevel(
        1, "記憶", "Remember",
        "能從長期記憶中正確提取相關知識，包括名詞、事實、定義、步驟。",
        (
            "正確說出教材中的關鍵名詞、定義、公式或事實",
            "內容與教材一致，沒有事實性錯誤",
            "涵蓋教材中的主要知識點，沒有重大遺漏",
        ),
        ("列出", "說出", "定義", "辨認", "回想"),
    ),
    2: BloomLevel(
        2, "理解", "Understand",
        "能從教學訊息中建構意義，用自己的話解釋、舉例、分類、摘要、比較或推論。",
        (
            "用自己的話（而非照念教材）解釋概念",
            "能舉出恰當的例子或反例",
            "能說明概念之間的關係、做摘要或比較異同",
        ),
        ("解釋", "舉例", "摘要", "比較", "分類", "推論"),
    ),
    3: BloomLevel(
        3, "應用", "Apply",
        "能在特定情境中執行或運用所學的程序、方法或概念。",
        (
            "示範如何用概念或方法解決具體問題或情境",
            "面對聽眾提出的新情境時，能正確套用所學",
            "步驟正確、能說明每一步為何這樣做",
        ),
        ("執行", "運用", "實作", "計算", "示範"),
    ),
    4: BloomLevel(
        4, "分析", "Analyze",
        "能將材料拆解成組成部分，判斷各部分之間以及與整體結構或目的的關係。",
        (
            "將主題拆解成要素，並說明要素之間的結構或因果關係",
            "能區分重點與次要、相關與無關的資訊",
            "能指出概念背後的假設、條件或成立前提",
        ),
        ("區辨", "組織", "歸因", "拆解", "比較結構"),
    ),
    5: BloomLevel(
        5, "評鑑", "Evaluate",
        "能依據標準或準則做出判斷，例如檢核、批判、評估優劣。",
        (
            "依明確的標準比較不同方法或觀點的優缺點",
            "能指出論點或做法的限制、錯誤或適用範圍",
            "面對質疑時，能提出有根據的理由為判斷辯護",
        ),
        ("評估", "判斷", "批判", "檢核", "辯護"),
    ),
    6: BloomLevel(
        6, "創造", "Create",
        "能將元素組合成一個連貫或具功能性的新整體，或重組成新的模式或結構。",
        (
            "提出教材以外、但合理的新例子、新應用或新方案",
            "能整合多個概念形成新的觀點、模型或設計",
            "能針對假設性的新問題規劃解決方法",
        ),
        ("設計", "建構", "規劃", "產出", "提出新方案"),
    ),
}

# 講義只評這三個層級（對應 handout_eval_items CHECK IN (1, 2, 4)）
HANDOUT_LEVEL_IDS: tuple[int, ...] = (1, 2, 4)
TEACHING_LEVEL_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)

# 分數定義（evaluation_items / handout_eval_items 皆為 0 / 1 / 2）
SCORE_RUBRIC: dict[int, str] = {
    0: "未達成：沒有展現此層級的表現，或內容有明顯錯誤。",
    1: "部分達成：有展現此層級的表現，但不完整、不夠精確，或只涵蓋部分評分依據。",
    2: "達成：清楚且正確地展現此層級的表現，符合本任務評分依據的主要要求。",
}


def level_name(level_id: int) -> str:
    return BLOOM_LEVELS[level_id].level_name


def render_bloom_definitions(level_ids: tuple[int, ...] = TEACHING_LEVEL_IDS) -> str:
    """把 Bloom 定義轉成給 AI 讀的文字。"""
    parts = []
    for lid in level_ids:
        lv = BLOOM_LEVELS[lid]
        indicators = "\n".join(f"    - {i}" for i in lv.indicators)
        parts.append(
            f"  <level id=\"{lv.level_id}\" name=\"{lv.level_name}\" en=\"{lv.english}\">\n"
            f"    定義：{lv.definition}\n"
            f"    常見動詞：{'、'.join(lv.verbs)}\n"
            f"    可觀察指標：\n{indicators}\n"
            f"  </level>"
        )
    return "<bloom_levels>\n" + "\n".join(parts) + "\n</bloom_levels>"


def render_score_rubric() -> str:
    return "<score_rubric>\n" + "\n".join(
        f"  {score} 分 = {desc}" for score, desc in SCORE_RUBRIC.items()
    ) + "\n</score_rubric>"
