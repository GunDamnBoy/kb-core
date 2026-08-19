"""Tracer bullet 的示範檢查——刻意讓五種結果各出現一次。

真實系統的檢查之後會取代這些，但**這幾條要留著當契約的活範例**：
每一條都有 covers、blind_to、fixture 三樣，缺一不可。
"""
import os
import re

from kbcore.check import Check, env, fail, ok, register, skipped, warn

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date_present(p):
    d = p.get("date")
    if d is None:
        return fail("缺 date")
    if not DATE_RE.match(str(d)):
        return fail(f"date 格式錯：{d!r}")
    return ok()


register(Check(
    id="demo.date_present",
    covers="頂層有 date 且形如 YYYY-MM-DD",
    blind_to=[
        "date 格式合法但語意錯（例如寫成明天）",
        "date 與 items 裡各筆的日期不一致",
    ],
    run=_date_present,
    fixture={"items": [1]},
    no_boundary="缺欄位／格式對不對是離散的，沒有「差一點就合格」這種狀態",
))


def _items_nonempty(p):
    items = p.get("items")
    if items is None:
        return skipped("payload 沒有 items 欄位，該項未執行")
    if len(items) == 0:
        return fail("items 是空的")
    return ok()


register(Check(
    id="demo.items_nonempty",
    covers="items 存在且非空",
    blind_to=[
        "items 有內容但每一筆都是重複的",
        "items 筆數合理但內容全部來自前一版（跨版去重看不到）",
    ],
    run=_items_nonempty,
    fixture={"date": "2026-08-19", "items": []},
    near_miss={"date": "2026-08-19", "items": [1]},
))


def _note_length(p):
    note = p.get("note")
    if note is None:
        return skipped("沒有 note 欄位，該項未執行")
    if len(note) > 100:
        return warn(f"note {len(note)} 字，超過 100")
    return ok()


register(Check(
    id="demo.note_length",
    covers="note 不超過 100 字",
    blind_to=[
        "note 長度合格但內容是空話（機器驗不了）",
    ],
    run=_note_length,
    fixture={"date": "2026-08-19", "note": "x" * 101},
    near_miss={"date": "2026-08-19", "note": "x" * 100},
))


def _upstream_fresh(p):
    if os.environ.get("KB_UPSTREAM_DOWN"):
        return env("上游今日尚未更新（環境狀態，非資料故障）")
    if p.get("upstream_date") is None:
        return skipped("payload 沒有 upstream_date")
    return ok()


register(Check(
    id="demo.upstream_fresh",
    covers="上游資料已更新",
    blind_to=[
        "上游有更新但內容與昨日完全相同",
        "上游更新了但只更新了一部分欄位",
    ],
    run=_upstream_fresh,
    fixture={"date": "2026-08-19"},
    no_boundary="只看 upstream_date 這個欄位在不在，沒有連續量可以貼邊界",
))
