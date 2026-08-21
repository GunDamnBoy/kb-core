"""tracer bullet 的靶子。payload 就是草稿本身。

`index_entry` 只寫 date 與 file——**它是靶子，不是系統**，沒有跨日推理要支撐。
刻意不沿用投顧那份：那會讓一個 demo 的 index 帶著五個永遠是空的跨日欄位，
而空欄位跟「有欄位但沒填」在資料上長得一樣。
"""
import datetime as dt

from kbcore.system import System, register


def index_entry(doc: dict) -> dict:
    return {"date": doc["date"], "file": f"data/{doc['date']}.json"}


def index_meta(doc: dict) -> dict:
    return {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


register(System(
    id="kb-tracer",
    suite="draft",
    build=lambda draft, repo: draft,
    staged_paths=lambda doc, repo: ["data"],
    index_entry=index_entry,
    index_meta=index_meta,
))
