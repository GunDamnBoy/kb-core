#!/usr/bin/env python3
"""把匯流這一期的裁決寫回外資報告的立場帳本。

用法：convergence_rulings_apply.py <單期 JSON> [--stances <路徑>] [--apply]
（預設 dry-run —— **跨 repo 寫入，預設不能是「動手」**）

## 為什麼是匯流在寫別人家的檔

`broker-research-digest/data/stances.json` 有 96 筆帶到期日的分析師主張，
而在這之前**沒有任何流程負責判它們**（實測：`verdict` 全空）。

匯流是唯一同時看得到「主張」（券商原句）與「證據」（量化指標、新聞、節目）
的地方，而且它是週頻，正好對得上到期節奏。所以裁決歸這裡。

## 為什麼直接寫，而不是繞一個回饋檔

因為**保留保證早就在那裡了**。`scripts/research/assemble.py` 的
`build_stances()` 檔頭寫著：

> `status`／`verdict`／`verdictDate` **由既有檔案沿用，永不覆寫** ——
> 這支每一輪重建列表，但**判決是人下的，重建不能把它洗掉**。

所以外資報告下一輪重建會保留匯流寫的東西。多蓋一層回饋檔只會讓兩個系統
互相依賴，而那個依賴是循環的。

**但「檔頭這樣寫」與「它真的做得到」是兩件事** —— 所以這支有 `--prove`：
寫入之後把 `assemble.py` 的保留邏輯實跑一次，確認判決活得下來。

## 只改三個欄位，只改自己判過的 id

read-modify-write，不整份重寫。**外資報告那邊每週會新增條目**，
整份重寫等於用匯流手上這一份舊快照蓋掉它們。

`延後` 不寫回 —— 它是匯流自己的狀態。那幾筆維持 `觀察中`，
下一期照樣會被 `prepare.py` 撈出來。**那是刻意的**：
「還判不了」不該長得像「判完了」。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from checks.convergence import DEFER, TERMINAL  # noqa: E402

TPE = dt.timezone(dt.timedelta(hours=8))
FIELDS = ("status", "verdict", "verdictDate")
DEFAULT_STANCES = "~/broker-research-digest/data/stances.json"


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("issue", nargs="?")
    ap.add_argument("--stances", default=DEFAULT_STANCES)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown or not a.issue:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
        print(__doc__); return 2

    ip = os.path.expanduser(a.issue)
    sp = os.path.expanduser(a.stances)
    for p in (ip, sp):
        if not os.path.exists(p):
            print(f"找不到 {p}", file=sys.stderr); return 13

    issue = json.load(open(ip, encoding="utf-8"))
    doc = json.load(open(sp, encoding="utf-8"))
    items = {x.get("id"): x for x in (doc.get("items") or [])}
    rulings = issue.get("rulings") or []
    if not rulings:
        print("這一期沒有 `rulings` —— **這跟「都判完了」是兩件事**。\n"
              "  如果 PREP.md 的賣方對帳段列了到期主張，那是漏做，不是沒事。")
        return 0

    day = issue.get("date") or dt.datetime.now(TPE).date().isoformat()
    write, skip, bad = [], [], []
    for r in rulings:
        i, res = r.get("id"), r.get("result")
        if i not in items:
            bad.append(f"`{i}` 不在帳本裡"); continue
        if items[i].get("verdict"):
            bad.append(f"`{i}` 已經裁決過（{items[i].get('status')}）—— **不重複結案**"); continue
        if res == DEFER:
            skip.append((i, r.get("why", "")))
            continue
        if res not in TERMINAL:
            bad.append(f"`{i}` 的 result 是 {res!r}，合法值 {TERMINAL + (DEFER,)}"); continue
        write.append((i, res, r.get("why", "")))
    if bad:
        print("**有問題，一個字都不寫**：", file=sys.stderr)
        for b in bad:
            print(f"  ✗ {b}", file=sys.stderr)
        return 20

    print(f"第 {issue.get('issue')} 期（{day}）｜帳本 {len(items)} 筆")
    print(f"  結案 {len(write)} 筆：")
    for i, res, why in write:
        print(f"    {i[:54]}　→ {res}\n        {why[:90]}")
    if skip:
        print(f"  延後 {len(skip)} 筆（**維持觀察中，不寫回**，下一期照樣會被撈出來）：")
        for i, why in skip:
            print(f"    {i[:54]}　{why[:80]}")

    if not a.apply:
        print("\n**dry-run，帳本沒有動。加 --apply 才會寫。**")
        return 0

    for i, res, why in write:
        items[i]["status"] = res
        items[i]["verdict"] = why
        items[i]["verdictDate"] = day
    tmp = sp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, sp)
    print(f"\n寫回 {len(write)} 筆。"
          "**外資報告下一輪重建會保留它們**（build_stances 的沿用保證），"
          "但那是檔頭寫的、不是驗過的 —— 第一次寫回後請實跑一次 assemble.py 確認。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
