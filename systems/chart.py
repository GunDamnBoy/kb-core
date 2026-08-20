"""每日五圖。payload 要帶兩份 anchors、前一版、當日 JSON 的實際大小，
以及三樣只有摸得到磁碟的人才答得出來的東西：PNG 實際位元組、預抓狀態檔、近 14 期的 data_path。

## 為什麼要帶投顧的 anchors

`theme` 的值域是投顧知識庫那十五個子類別——**它們是同一份東西**，
因為每日五圖的選題就是從投顧庫來的。舊系統把十五個字串硬寫進 `check_day.py`，
2026-08-20 比對發現兩邊逐字相同，**但那是運氣**：沒有任何機制在維持它。
所以這裡把投顧的 anchors 一起讀進來，讓 `chart.theme_unique` 直接讀它的 `groups`。

## 為什麼 size_kb 由這裡量而不是檢查自己量

檢查不做 IO。**而「當日 JSON 多大」只有寫檔的人知道**——
草稿階段還沒落地時它是序列化後的長度，發布之後才是檔案大小。
組 payload 的人負責回答這個問題，並且在答不出來時**留 None 讓檢查判 SKIPPED**，
而不是給一個 0。
"""
import datetime as dt
import json
from pathlib import Path

from kbcore.system import System, register

ROOT = Path(__file__).resolve().parent.parent


def prev_doc(data_dir: Path, date: str):
    """前一版取「小於當日的最大日期」，不是「最新的非當日」。

    歷史重跑時後者會拿到未來的那一版，跨版比較整個反過來。
    """
    if not data_dir.exists():
        return None
    days = sorted(f.stem for f in data_dir.glob("*.json")
                  if f.stem != "index" and f.stem < date)
    return json.loads((data_dir / f"{days[-1]}.json").read_text()) if days else None


def load_anchors(repo: Path):
    """chart 的 anchors 跟著 kb-core 走，不進資料 repo。

    資料 repo 只放**已發布的東西**；門檻是程式的一部分，
    放進資料 repo 會讓「改門檻」跟「改資料」混在同一個歷史裡。
    """
    return json.loads((ROOT / "chart" / "anchors.json").read_text())


def png_bytes(draft, repo: Path) -> dict:
    """每張圖宣稱的 PNG 實際多大。**找不到檔案回 None，不是 0**——
    「沒有這個檔」與「檔案是空的」是兩件事，處置也不同（前者是沒產出、後者是畫壞了）。
    """
    out = {}
    for c in draft.get("charts") or []:
        rel = (c.get("files") or {}).get("png") or ""
        slug = c.get("slug") or "?"
        if not rel:
            out[slug] = None
            continue
        f = repo / rel
        out[slug] = f.stat().st_size if f.exists() else None
    return out


def prefetch_status(repo: Path):
    """預抓狀態檔。讀不動一律回 None 讓檢查判失敗——
    **「當成沒有預抓處理」是刻意的**，安靜跳過會讓整條線變成永遠 PASS。
    """
    f = repo / "data" / "_prefetch_status.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except Exception:
        return None


def recent_data_paths(data_dir: Path, date: str, n: int = 14) -> list:
    """最近 n 期（含當日之前）的 about.data_path，新到舊。

    連續走備援是**跨期**才看得出來的：單看一期，每一期都是「降級但成功」。
    """
    if not data_dir.exists():
        return []
    days = sorted((f.stem for f in data_dir.glob("*.json")
                   if f.stem != "index" and f.stem < date), reverse=True)[:n]
    out = []
    for d in days:
        try:
            out.append(((json.loads((data_dir / f"{d}.json").read_text())
                         .get("about") or {}).get("data_path")) or "")
        except Exception:
            out.append("")
    return out


def build(draft, repo: Path):
    repo = Path(repo)
    date = draft.get("date", "")
    return {
        "doc": draft,
        "prev": prev_doc(repo / "data", date),
        "anchors": load_anchors(repo),
        "advisory_anchors": json.loads((ROOT / "advisory" / "anchors.json").read_text()),
        "size_kb": len(json.dumps(draft, ensure_ascii=False).encode()) / 1024,
        "png": png_bytes(draft, repo),
        "prefetch": prefetch_status(repo),
        "recent_data_paths": recent_data_paths(repo / "data", date),
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


WD = "一二三四五六日"


def index_entry(doc: dict) -> dict:
    """導覽用的欄位。**`kinds` 是給前端篩選鈕用的，去重但保留出現順序**——
    順序就是 slot 順序，用 set 會讓它每天亂跳。
    """
    d = dt.date.fromisoformat(doc["date"])
    cs = doc.get("charts") or []
    kinds, seen = [], set()
    for c in cs:
        k = c.get("kind")
        if k and k not in seen:
            seen.add(k)
            kinds.append(k)
    return {
        "date": doc["date"],
        "weekday": WD[d.weekday()],
        "headline": doc.get("headline", ""),
        "charts": len(cs),
        "themes": [c.get("theme") for c in cs],
        "kinds": kinds,
        "file": f"data/{doc['date']}.json",
    }


def index_meta(doc: dict) -> dict:
    """頂層欄位。`updatedLabel` 存在的理由跟 podcast 那邊一樣：
    `days[0].date` 每天都會被寫成當天，**只看日期看不出推送鏈斷掉**。
    """
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    return {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "updatedLabel": f"{now.month}/{now.day} {now:%H:%M}",
    }


register(System(
    id="chart-of-the-day",
    suite="chart",
    build=build,
    index_entry=index_entry,
    index_meta=index_meta,
))
