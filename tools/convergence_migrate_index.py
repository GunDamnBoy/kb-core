#!/usr/bin/env python3
"""把匯流訊號報的索引鍵從 `issues` 改成 `days`。一次性，跑完就可以刪。

用法：convergence_migrate_index.py <資料 repo> [--apply]
（預設 dry-run —— **改已發布的東西，預設不能是「動手」**）

## 為什麼要遷移

`tools/publish.py` 寫死 `days`，`tools/verify_site_index.py`、哨兵、
`verify_live.py` 也全部走 `days`。這一套是唯一用 `issues` 的。

**選擇對齊，而不是給 `System` 加第五個 `index_key` 參數。**
理由寫在 `systems/convergence.py` 的檔頭：加一個維度的成本不是這一次的改動，
是之後每一支共用工具都要記得尊重它 —— 而忘記的那次不會有徵兆。

## 兩邊要一起改，不能只改一邊

`data/index.json` 的鍵，與 `index.html` 裡讀它的那五處。
**只改其中一邊的樣子是：網站空白，而所有檢查全綠** ——
檢查看的是 JSON，看不到前端讀哪個鍵。

所以這支同時改兩個檔，而且**任一邊對不上就整個中止**，不做半套。

## 每一期的內容一個字都不動

只改頂層那個鍵的名字。`data/YYYY-MM-DD.json` 完全不碰 ——
歷史全部保留，而這次要動的本來就只有索引的容器。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# `index.html` 裡讀 `index.issues` 的**處數**（不是行數）。
# 2026-08-23：第一版寫 5，那是 `grep -n` 回的**行數** —— 第 513 行
# （`index.issues.find(...) || index.issues[0]`）一行裡有兩處，實際是 6。
# **我量了行，然後宣稱那是處數。** 守衛當場擋下來，那正是它存在的理由：
# 一個「差一處」的替換不會報錯，它會讓網站少一個分支安靜地壞掉。
HTML_SITES = 6


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("repo", nargs="?")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown or not a.repo:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
        print(__doc__); return 2

    repo = os.path.expanduser(a.repo)
    idx_p = os.path.join(repo, "data", "index.json")
    html_p = os.path.join(repo, "index.html")
    for p in (idx_p, html_p):
        if not os.path.exists(p):
            print(f"找不到 {p}", file=sys.stderr); return 13

    idx = json.load(open(idx_p, encoding="utf-8"))
    html = open(html_p, encoding="utf-8").read()

    # ── 先確認兩邊都還是舊的樣子，再動 ──────────────────────────────
    if "days" in idx and "issues" not in idx:
        print("索引已經是 `days` —— 這支跑過了"); return 0
    if "issues" not in idx:
        print(f"索引既沒有 `issues` 也沒有 `days`（有 {sorted(idx)}）—— "
              "**這不是預期的形狀，中止**", file=sys.stderr); return 20
    hits = len(re.findall(r"index\.issues", html))
    if hits != HTML_SITES:
        print(f"`index.html` 讀 `index.issues` 的地方有 {hits} 處，預期 {HTML_SITES} 處 —— "
              "**前端變過了，中止**。先看一眼再決定要不要改這支的常數", file=sys.stderr)
        return 20

    n = len(idx["issues"])
    print(f"索引 {n} 期　`issues` → `days`")
    print(f"index.html　`index.issues` → `index.days`，{hits} 處")
    for e in idx["issues"]:
        print(f"  第 {e.get('issue')} 期 {e.get('date')}　"
              f"composite {e.get('composite')}　快照 {len(e)} 欄")

    # 鍵改名，順序保持（days 在原本 issues 的位置）
    new_idx = {("days" if k == "issues" else k): v for k, v in idx.items()}
    new_html = html.replace("index.issues", "index.days")

    # **只准改鍵名，內容一個位元組都不能變。**
    if json.dumps(new_idx.get("days"), sort_keys=True, ensure_ascii=False) != \
       json.dumps(idx.get("issues"), sort_keys=True, ensure_ascii=False):
        print("  ✗ 期別內容在改名過程中變了 —— 中止", file=sys.stderr); return 20
    if len(new_html) != len(html) - hits * len("issues") + hits * len("days"):
        print("  ✗ index.html 的替換動到了預期以外的長度 —— 中止", file=sys.stderr); return 20

    if not a.apply:
        print("\n**dry-run，兩個檔都沒寫。加 --apply 才會動。**"); return 0

    for p, body in ((idx_p, json.dumps(new_idx, ensure_ascii=False, indent=1) + "\n"),
                    (html_p, new_html)):
        tmp = p + ".tmp"
        open(tmp, "w", encoding="utf-8").write(body)
        os.replace(tmp, p)          # 原子寫入
    print("\n兩個檔都改好了。**接著跑 convergence_verify.py 確認 index_snapshot 轉綠。**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
