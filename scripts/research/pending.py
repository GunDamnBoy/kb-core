#!/usr/bin/env python3
"""還沒交件的報告 —— **全部的，不是這一週的。**

用法：pending.py [--dossier]

列出 `extracted/` 裡有、`digest/_parts/` 裡沒有的每一份，依**報告自己的週次**分組。
加 `--dossier` 就順手替每一份組卷宗（呼叫 `dossier.py`）。

## 為什麼要有這支（2026-09-28）

RUN-PROMPT 第 3 步一直寫著「只派沒有交件的那幾份」，但**沒有任何東西把它們列出來**。
各輪是從 `extract.py` 那一輪的輸出、或 `assemble.py` 那一期的清單去湊派工名單 ——
兩者都只看得到「這一輪／這一週」。2026-09-20 那一輪入庫的 W37 三份
（野村 1320031、1320043、高盛《US Economics Analyst》9/13）因此**整整一週沒有精華**，
直到 09-27 那一輪逐檔比對才發現。`assemble.py` 會列出「不屬於這一期」的週次，
但它列的是**所有**報告，已交件與沒交件混在一起，看不出哪幾份掉了。

**看不到的：** 移進 `_pending/` 的那幾份（刻意擱置，等使用者裁決），
以及因 slug 撞號根本沒寫進 `extracted/` 的 —— 那一種要看 `extract.py` 的輸出。
"""
from __future__ import annotations
import datetime as dt, glob, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402


def main(argv):
    ext, parts = _paths.extracted(), _paths.under("digest", "_parts")
    rows = []
    for f in sorted(glob.glob(os.path.join(ext, "*.json"))):
        slug = os.path.basename(f)[:-5]
        if os.path.exists(os.path.join(parts, slug + ".json")):
            continue
        d = json.load(open(f, encoding="utf-8"))
        date = d.get("date")
        wk = "%d-W%02d" % dt.date.fromisoformat(date).isocalendar()[:2] if date else "undated"
        rows.append((wk, slug, d.get("pages")))
    if not rows:
        print(f"沒有待交件的報告（{ext}）")
        return 0
    by = {}
    for wk, slug, pg in rows:
        by.setdefault(wk, []).append((slug, pg))
    print(f"待交件 {len(rows)} 份，橫跨 {len(by)} 週｜{ext}")
    for wk in sorted(by):
        print(f"  {wk}  {len(by[wk])} 份")
        for slug, pg in by[wk]:
            print(f"    {slug}（{pg} 頁）")
    if len(by) > 1:
        print("\n**不只一週** —— 組檔時每一週都要各自跑一次 `assemble.py`。")
    if "--dossier" in argv:
        here = os.path.dirname(os.path.abspath(__file__))
        for _, slug, _ in rows:
            subprocess.run([sys.executable, os.path.join(here, "dossier.py"), slug], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
