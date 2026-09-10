"""序列的頻率判準 —— **這是它唯一的家**。

## 為什麼要有這一份

「這條序列是月頻還是日頻」原本有兩份實作，而**它們對同一條序列會給出不同答案**：

| 在哪 | 怎麼判 | 對 `DCOILBRENTEU`（末日 2026-09-01）的答案 |
|---|---|---|
| `scripts/chart/build_series._is_monthly()` | 整條序列**每一筆**都以 `-01` 結尾 | 日頻 ✓ |
| `scripts/chart/prep_chart._stale()` | **末日那一筆**以 `-01` 結尾 | 月頻 ✗ |
| `checks/chart.py` 的 `series_freshness` | 同上 | 月頻 ✗ |

2026-09-10 那一輪撞上了：布蘭特末日停在 **2026-09-01**，以交易日計落後 7 個、
已過 `anchors.freshness.daily_fail_days=5` 的硬失敗門檻，
**而它在 `prep_chart` 的硬失敗與警示兩堆裡都沒有出現** ——
9 個日曆日被當成月頻的 `9 // 30 = 0` 期。

**它藏住的方式值得記**：這個洞早就寫在 `chart.series_freshness` 的 `blind_to` 裡
（「日頻資料剛好落在 1 號會被誤判成月頻」），登錄了、也預期到了，
**但沒有人把它接回實作** —— 於是它以「已知限制」的身分活著，
每個月 1 號都有一次機會發作，而發作的樣子是**檢查全綠、資料落後七個交易日**。
`prep_chart.selftest_offline()` 的案例裡剛好有兩筆 `last` 是 `-01` 結尾
（`2026-06-01`、`2026-08-01`），所以連自檢都在這個歧義裡跑。

一條被登錄成 `blind_to` 的缺陷仍然是缺陷 —— **登錄讓它不再意外，不讓它不再發生。**

## 判準

**月頻的標記約定是「整條序列每一筆都落在每月 1 號」**
（`anchors.freshness.monthly_detection`）。只看末日那一筆答不出這個問題：
任何日頻序列每個月都會有一天剛好落在 1 號。

點數太少時一律回 `False`：兩三個點分不出頻率，
而**判錯成月頻的代價（門檻鬆 30 倍）遠大於判錯成日頻**。
"""
from __future__ import annotations

MIN_POINTS = 3


def is_monthly(dates) -> bool:
    """整條序列是不是月頻標記（每一筆都落在每月 1 號）。

    `dates` 收字串序列；非字串或長度不足 10 的元素一律讓它回 `False`，
    **不要跳過** —— 「這一筆看不懂」與「這一筆是 1 號」是兩件事。
    """
    if not isinstance(dates, (list, tuple)) or len(dates) < MIN_POINTS:
        return False
    for d in dates:
        if not isinstance(d, str) or len(d) < 10 or not d[:10].endswith("-01"):
            return False
    return True
