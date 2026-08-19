"""五種結果與六個退出碼。這兩組是整個底盤的共用詞彙，其餘模組一律引用這裡。"""
from enum import Enum


class Level(str, Enum):
    """檢查的五種結果。

    PASS / WARN / FAIL 是常見的三級。另外兩種各解一個舊系統的病：

    SKIPPED — 檢查跑不了（缺欄位、前置不成立）。**不是 PASS。**
              「否定訊號要具名」：沒查到、解析失敗、不適用，不可以退化成同一個
              falsy 值，更不可以退化成通過。它的數量本身就是訊號。

    ENV     — 環境狀態（上游還沒更新、端點暫時不通），不是資料故障。
              不計數、不影響退出碼。分出去之後 WARN 才重新有意義——
              「會固定響的警報就是雜訊，而雜訊訓練人忽略警報」。
    """

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    ENV = "ENV"


class Exit:
    """統一退出碼。舊系統三支腳本的碼會撞，規格得寫「一定要連著腳本名讀」。"""

    OK = 0           # 成功
    CONTENT = 1      # 內容不合格（有 FAIL，或 SKIPPED 超過閾值）→ 改草稿重跑
    IMMUTABLE = 2    # 不可改寫守衛拒絕 → 改草稿沒有用，掛 errata
    BAD_INPUT = 3    # 輸入壞掉（JSON 解析失敗、缺必要頂層欄位）
    EMPTY_ROUND = 4  # 空輪次 —— **不是失敗，是設計**
    ENVIRONMENT = 5  # 環境／網路失敗 → 重跑可能會好
