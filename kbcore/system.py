"""系統登記：一個系統 id 對應到「用哪一組檢查」與「payload 怎麼組」。

publish 跑在所有系統之上，但每一套系統的 payload 形狀不同——投顧的檢查要看前一版
與 anchors，tracer 的檢查直接吃草稿本身。**這是一道接縫，不是一串條件式。**

## 認不出來就大聲失敗

`get()` 找不到系統 id 時回 None，呼叫端必須當成錯誤中止。

**絕對不要退回預設的 suite。** 那會讓投顧的草稿被 demo 的四條檢查驗過然後全綠——
每一個訊號都說成功，而真正該擋的十二條一條都沒跑。這是本系統一路在抓的那種假成功，
只是換了個位置：守衛檢查的維度（有沒有跑完檢查）比它宣稱保護的東西（跑對檢查沒有）低一階。

## `.kb-data-repo` 的第二個職責

目的地守門用它確認「我站在對的 repo」。有了這份登記，同一個 id 還決定**跑哪一組檢查**。
一個檔案兩個職責是刻意的：它們要一起對，分開放就會有一天只對了一半。
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class System:
    id: str
    """與資料 repo 根目錄的 `.kb-data-repo` 內容逐字相同。"""

    suite: str
    """這套系統用哪一組檢查。空的 suite 會被 run_all 擋下來。"""

    build: Callable[[Any, Path], Any]
    """(草稿, 資料 repo 路徑) → payload。

    讀檔全部在這裡，因為**檢查本身不做 IO**——那樣每條檢查才能用純資料當 fixture。
    """

    index_meta: Callable[[dict], dict]
    """草稿 → `data/index.json` 的**頂層**欄位（不含 `days`）。

    2026-08-20 加的，跟 `index_entry` 同一個理由的第二次發作：
    `publish.py` 原本硬寫 `updated` 與 `count`，而 podcast 的站台還要一個
    `updatedLabel`（人看的時間字串）—— **沒人寫它，於是它停在兩天前的值**。

    這件事的嚴重性不在顯示：舊系統把「`updatedLabel` 是本次執行時間」列為
    上線驗證的判準之一，因為 `days[0].date` 早就是當天了（排程每天都會寫），
    **只看日期看不出推送鏈斷掉**。判準本身被靜靜地架空了。

    每套系統自己決定頂層要有什麼，publish 只負責 merge。
    """

    index_entry: Callable[[dict], dict]
    """草稿 → `data/index.json` 的當日 entry。

    2026-08-20 從 `publish.py` 搬過來的。原本它寫死投顧的欄位
    （weekday／stamp／headline／cards／thermo／threads／watch／pulse／snap），
    住在通用的 publish 裡——**登記那道接縫管到了「跑哪組檢查」與「payload 怎麼組」，
    卻漏掉了「index entry 長什麼樣」**，而那同樣是每套系統各不相同的東西。

    第二套系統一接上去就撞到：podcast 的 doc 沒有 `overview`，publish 會在
    組 entry 時 KeyError。**接縫漏一個維度，第二個使用者才會發現。**
    """


REGISTRY: "dict[str, System]" = {}


def register(s: System) -> System:
    if s.id in REGISTRY:
        raise ValueError(f"重複的系統 id：{s.id}")
    REGISTRY[s.id] = s
    return s


def get(system_id: str):
    return REGISTRY.get(system_id)
