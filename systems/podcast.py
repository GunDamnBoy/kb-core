"""Podcast 知識庫。payload 要帶 anchors、前一版、帳本，以及金句的回稿比對結果。

`build` 是這些東西的**唯一**組法：publish 用它，日後的 `podcast_verify` 也用它。

## 為什麼要把逐字稿讀進來

`quotes[].original` 存在的唯一理由是**讓「金句是不是編的」變成機械可判**。
比對必須在發布的閘門上跑，不能只在撰寫端自己驗——**依賴自覺的紀律不是紀律**。

逐字稿住在 repo 外面（`~/podcast-transcripts/<date>/`，版權界線，結構性的），
所以這裡是整套程式裡唯一知道那個路徑的地方。讀不到就把 `quote_misses` 設成 None，
檢查那一側會判成 SKIPPED 並具名說明——**「沒比對」與「比對過沒問題」必須分得出來**。
"""
import datetime as dt
import json
import os
from pathlib import Path

from kbcore.system import System, register

ANCHORS = "podcast/anchors.json"
PROGRAM_ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS = Path(os.path.expanduser("~/podcast-transcripts"))

# 每一條檢查會伸手去拿的 anchors 鍵。缺一個就在組 payload 時大聲失敗——
# fixture 自帶 anchors，所以 selftest 驗不到「真實設定裡有沒有這一項」。
REQUIRED = ["length_tiers", "_length_tiers_rules", "per_episode",
            "topics_vocabulary", "quality", "observations"]


class AnchorsMissing(Exception):
    pass


def load_anchors(repo: Path) -> dict:
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

    歷史重跑時後者會拿到未來的那一版，跨版比較整個反過來。
    """
    if not data_dir.exists():
        return None
    days = sorted(f.stem for f in data_dir.glob("*.json")
                  if f.stem not in ("index", "observations") and f.stem < date)
    return json.loads((data_dir / f"{days[-1]}.json").read_text()) if days else None


def quote_misses(doc, date: str):
    """回頭比對每一條金句的 `original` 是不是逐字稿裡真的出現過。

    回傳 [(集 id, 講者, 原句前 40 字)]；**逐字稿目錄不在就回 None**，
    那跟「比對過、沒有漏網」是兩個結果。

    用子字串包含，不用整行相等——Bloomberg 有幾行的講者標籤是 `Speaker 6]`
    （右方括號不是冒號），整行比對會把完整的發言誤判成對不上。
    """
    day = TRANSCRIPTS / date
    if not day.is_dir():
        return None
    cache, misses = {}, []
    for e in doc.get("episodes") or []:
        tid = e.get("trackId") or ""
        hits = list(day.glob(f"{e.get('showKey')}-{tid}.md")) if tid else []
        if not hits:
            return None  # 有一集找不到稿就整輪不判，不要半套
        f = hits[0]
        if f not in cache:
            cache[f] = f.read_text()
        text = cache[f]
        for q in e.get("quotes") or []:
            o = (q.get("original") or "").strip()
            if not o or o not in text:
                misses.append([e.get("id"), q.get("by"), o[:40]])
    return misses


def build(draft, repo: Path):
    repo = Path(repo)
    date = draft.get("date", "")
    ledger = repo / "data" / "observations.json"
    return {
        "doc": draft,
        "prev": prev_doc(repo / "data", date),
        "ledger": json.loads(ledger.read_text()) if ledger.exists() else None,
        "quote_misses": quote_misses(draft, date),
        "anchors": load_anchors(repo),
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


# 這個站的 index entry 只需要導覽用的五欄——它不做跨日推理，
# 跨日的東西住在 `data/observations.json`（帳本）而不是索引裡。
INDEX_FIELDS = ("date", "label", "short", "episodeCount", "shows", "file")

WD = "一二三四五六日"


def index_entry(doc: dict) -> dict:
    """從當日的 doc 組出 index entry。

    `shows` 去重但**保留出現順序**（順序是 show_priority 排過的），
    因為前端的節目篩選鈕就照這個順序長出來。用 set 會讓它每天亂跳。
    """
    d = dt.date.fromisoformat(doc["date"])
    eps = doc.get("episodes") or []
    entry = {
        "date": doc["date"],
        "label": doc.get("label") or f"{d.year}年{d.month}月{d.day}日（週{WD[d.weekday()]}）",
        "short": f"{d.month}/{d.day} 週{WD[d.weekday()]}",
        "episodeCount": len(eps),
        "shows": list(dict.fromkeys(e.get("show") for e in eps if e.get("show"))),
        "file": f"data/{doc['date']}.json",
    }
    missing = [k for k in INDEX_FIELDS if k not in entry]
    if missing:
        raise KeyError(f"index entry 缺欄位：{'、'.join(missing)}")
    return entry


register(System(
    id="podcast-knowledge-digest",
    suite="podcast",
    build=build,
    index_entry=index_entry,
))
