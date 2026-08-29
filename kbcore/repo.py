"""資料 repo 的身分辨識——「我現在站在哪裡」。

2026-08-19 的事故教的：不可改寫守衛檢查的維度是**檔案**，它從設計上就看不見
「我站在哪個 repo」。所有破壞性動作都要問同一個問題——我驗證的是**物件**，
還是**我所在的位置**？前者永遠答不出後者。

這段刻意放在 kbcore 而不是 publish.py 裡：publish 要用它，哨兵的看門狗也要用。
守衛複製成兩份就是**雙軌漂移**的起點——改了一邊忘了另一邊，而且沒有任何訊號。
"""
import json
import os
from pathlib import Path

MARKER = ".kb-data-repo"


def day_json(doc) -> str:
    """日檔（`data/<日期>.json`）的**正規序列化**——這是它唯一的家。

    2026-08-29 的事故教的：`publish.py` 的不可改寫守衛比的是
    `target.read_text() != json.dumps(draft, ensure_ascii=False, indent=1)`，
    而 `render_day.py`／`build_series.py`／`rebuild_option.py` 三支全部寫
    `separators=(",", ":")`。**同一份文件因此有兩種寫法，而守衛比的是字串。**

    症狀是：任何一輪只要在同一台機器上先出圖再交草稿，
    第一次回執**必然**是 exit 11「已存在且內容不同」——
    而 exit 11 的字面意思是「已發布的一期就是已發布的樣子」，
    於是下一個人會被推去掛一份根本不需要的 errata。
    2026-08-29 那一輪就是這樣：`data/index.json` 當時根本沒有那一天、
    回執的 commit 是空字串，**那份日檔從來沒有被發布過**，
    逐行 diff 出來的差異只有一個 `window.to` 欄位。

    **`rebuild_option.py` 是更糟的那一個**：它是修既有封存的唯一合法工具，
    卻會把一份已發布的 `indent=1` 檔整份改寫成 compact ——
    資料一個位元都沒變，而 diff 是全檔重寫，**真正改了什麼因此看不見**。

    格式選 `indent=1` 不是美學：**publish 是最後寫入者，它決定了磁碟上的樣子**，
    所以其餘三支要向它靠攏，不是反過來。改這個函式等於改所有已發布檔的
    未來格式，改之前先想清楚既有封存怎麼辦（它們不改寫）。
    """
    return json.dumps(doc, ensure_ascii=False, indent=1)


def write_day_json(path, doc) -> int:
    """把日檔原子寫入 `path`，回傳寫了幾個位元組。

    **原子寫入不是選配。** 三支 `kbpublish.*` 每 60 秒掃一次 outbox 與 repo，
    非原子的寫入會讓它們讀到寫到一半的 JSON——而那個失敗是隨機出現的。
    """
    body = day_json(doc)
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, p)
    return len(body.encode("utf-8"))


def check_destination(repo: Path, system_id: str) -> str:
    """回傳錯誤訊息；空字串表示通過。"""
    marker = Path(repo) / MARKER
    if not marker.exists():
        return f"{repo} 沒有 {MARKER} —— 它不是一個資料 repo，拒絕動作"
    got = marker.read_text().strip()
    if got != system_id:
        return f"{MARKER} 是 {got!r}，但呼叫指定的是 {system_id!r} —— 目的地不符，拒絕動作"
    return ""
