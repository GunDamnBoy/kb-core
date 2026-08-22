"""投顧知識庫。payload 要帶前一版與 anchors。

`build` 是這兩個東西的**唯一**組法：publish 用它，`tools/advisory_verify.py` 也用它。
在兩個地方各寫一份就是雙軌漂移的起點——改了一邊忘了另一邊，而且沒有任何訊號。
"""
import datetime as dt
import json
from pathlib import Path

from kbcore.system import System, frozen, register

ANCHORS = "advisory/anchors.json"
PROGRAM_ROOT = Path(__file__).resolve().parent.parent

# 每一條檢查會伸手去拿的 anchors 鍵。缺一個就在組 payload 時大聲失敗——
# **門檻取不到是設定壞了，不是資料壞了**。
#
# 這一段是 2026-08-19 寫檢查時補的：檢查引用了 anchors 沒有的兩個鍵，而 selftest
# 看不見，因為每條檢查的 fixture 自帶 anchors。**fixture 自帶設定，所以它驗不到
# 「真實設定裡有沒有這一項」**——這是 fixture 自檢的第三個盲區。
REQUIRED = ["groups", "site_total", "lengths", "fixed_structure",
            "base_card_groups", "dedup_exempt"]


class AnchorsMissing(Exception):
    pass


def load_anchors(repo: Path) -> dict:
    """資料 repo 優先，其次是程式 repo。兩邊都沒有就是設定壞了。"""
    for p in (Path(repo) / ANCHORS, PROGRAM_ROOT / ANCHORS):
        if p.exists():
            a = json.loads(p.read_text())
            missing = [k for k in REQUIRED if k not in a]
            if missing:
                raise AnchorsMissing(f"{p} 缺少檢查會用到的鍵：{'、'.join(missing)}")
            return a
    raise AnchorsMissing(f"找不到 {ANCHORS} —— 門檻沒有家，這一輪沒有資格判")


def prev_doc(data_dir: Path, date: str):
    """前一版取「小於當日的最大日期」，不是「最新的非當日」。

    歷史重跑時後者會拿到未來的那一版，跨版去重整個反過來。
    """
    if not data_dir.exists():
        return None
    days = sorted(f.stem for f in data_dir.glob("*.json")
                  if f.stem != "index" and f.stem < date)
    return json.loads((data_dir / f"{days[-1]}.json").read_text()) if days else None


def build(draft, repo: Path):
    return {
        "doc": draft,
        "prev": prev_doc(Path(repo) / "data", draft.get("date", "")),
        "anchors": load_anchors(repo),
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


# index.json 的每日 entry 必備欄位。前六個是識別與導覽，後五個是**跨日記憶**。
#
# BRIEF 第二節：「寫今天的 entry 之前先讀前幾天的 entry —— thread 沿用、
# pulse 比對翻轉、watch 寫回顧，全部不用打開任何舊日檔。這是設計，不是巧合：
# 跨日推理的成本被壓在一個索引檔裡。」
#
# 2026-08-19 首日這裡只寫了 date 與 file，那五欄全空，而當天沒有任何訊號報警——
# 因為 `advisory.watch_review` 在沒有前一版時是 SKIPPED。**第一天的 SKIPPED
# 掩蓋了一個第二天才會爆的洞**。
INDEX_FIELDS = ("date", "weekday", "stamp", "headline", "cards", "file",
                "thermo", "threads", "watch", "pulse", "snap")


def index_entry(doc: dict) -> dict:
    """從當日的 doc 組出 index entry。

    **只取跨日推理需要的欄位，不整份塞進去。** index 要能每天被便宜地讀完，
    塞進完整 overview 會讓它隨天數線性膨脹。pulse 只留 k/dir、
    snap 只留 k/num/chgPct 就是這個理由。

    2026-08-20 從 `tools/publish.py` 搬到這裡：它寫的是投顧的欄位，
    住在通用的 publish 裡等於把一套系統的形狀寫進底盤。
    """
    ov = doc.get("overview") or {}
    threads = sorted({c["thread"]
                      for sec in doc.get("sections") or []
                      for g in sec.get("groups") or []
                      for c in g.get("cards") or []
                      if c.get("thread")})
    entry = {
        "date": doc["date"],
        "weekday": doc.get("weekday", ""),
        "stamp": doc.get("stamp", ""),
        "headline": doc.get("headline", ""),
        "cards": doc.get("cards", 0),
        "file": f"data/{doc['date']}.json",
        "thermo": (ov.get("thermo") or {}).get("level"),
        "threads": threads,
        "watch": ov.get("watch") or [],
        "pulse": [{"k": p.get("k"), "dir": p.get("dir")}
                  for p in (ov.get("pulse") or [])],
        "snap": [{"k": s.get("k"), "num": s.get("num"), "chgPct": s.get("chgPct")}
                 for s in (ov.get("snap") or [])],
    }
    # 大聲失敗，而不是安靜寫出殘缺的 entry。**寫出一個看起來正常、但少了跨日
    # 記憶的 index，比寫不出來更糟**——它會讓隔天的推理靜靜地建立在空集合上。
    missing = [k for k in INDEX_FIELDS if k not in entry]
    if missing:
        raise KeyError(f"index entry 缺欄位：{'、'.join(missing)}")
    return entry


def index_meta(doc: dict) -> dict:
    """投顧的站台只讀 `updated`，沒有給人看的標籤欄位。"""
    return {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


register(System(
    id="advisory-knowledge-hub",
    suite="advisory",
    build=build,
    cadence_hours=24,
    republish_rule=frozen,   # 日頻
    # 投顧只產 data/。`raw/` 是 GitHub Actions 那一側寫的，由它自己 commit ——
    # 兩個寫入者共用 main，這裡把 raw/ 也 add 進來會把對方寫到一半的東西帶上車。
    staged_paths=lambda doc, repo: ["data"],
    index_entry=index_entry,
    index_meta=index_meta,
))
