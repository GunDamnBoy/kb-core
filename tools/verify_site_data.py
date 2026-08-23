#!/usr/bin/env python3
"""上傳之前，確認**要發出去的資料本身是對的**。

用法：verify_site_data.py <要部署的目錄>

## 這支跟 `verify_live.py` 問的不是同一件事

`verify_live.py` 問「線上那份是不是我剛上傳的那份」—— 那是**投遞**。
它比雜湊、不比欄位，理由寫在它的檔頭：欄位清單會過期。那個設計是對的。

但 2026-08-23 的事故它擋不住，而且**它綠燈是正確的**：
`data/index.json` 上傳的內容本身就是舊標題，線上與本地完全一致。
投遞沒問題，內容有問題。**一個只驗投遞的守衛，對內容錯誤永遠是綠的。**

## 走整棵樹，不列鍵名

那次事故的成因是一張「檔案 → 鍵名」的對照表：
`data/<date>.json` 的報告在 `reports[]`，而 `data/index.json` 的在 `days[].items[]` ——
**深兩層，於是它一筆都沒被檢查到**。當時的驗證程式 glob 到了那個檔、
打開了它、在兩個頂層鍵上各找了一次、都不存在、然後回報「零殘留」。

所以這裡的判準不看鍵名也不看巢狀深度：
**一個物件同時有 `slug` 與 `title`，它就是一份報告。**

## 「檢查了 0 列」要跟「檢查完都對」分得開

上面那個失效的形狀，就是「檢查了 0 列」被當成「都對」。
所以每個檔都印出**看了幾列**，而一個帶 `slug` 的檔案卻找不到任何列時直接失敗。
一張沒有列數的綠燈，跟一張真的檢查過的綠燈長得一模一樣。
"""
from __future__ import annotations

import json
import os
import re
import sys

# 檔名冒充標題的三種樣子（見 scripts/research/title.py 的檔頭）
LOOKS_LIKE_FILENAME = [
    (re.compile(r"^\d{6,}$"), "整個標題就是流水號"),
    (re.compile(r"_\s"), "含有 `_ ` —— 那是檔名把冒號換掉的痕跡"),
    (re.compile(r"\.\.\.$|…$"), "以刪節號結尾 —— 多半是被下載端截斷的檔名"),
]


def walk(node, out):
    """回所有**同時有 `slug` 與 `title`** 的物件。鍵名與巢狀深度都不影響。"""
    if isinstance(node, dict):
        if "slug" in node and "title" in node:
            out.append(node)
        for v in node.values():
            walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)
    return out


def check_row(r):
    """一列的問題清單。空 list ＝ 這一列沒問題。"""
    bad = []
    t = (r.get("title") or "").strip()
    if not t:
        bad.append("標題是空的")
    src = r.get("title_source")
    if src is None:
        bad.append("沒有 `title_source` —— 抽取層比 title.py 舊，"
                   "標題可能是檔名而沒有人知道")
    elif src == "filename":
        bad.append(f"`title_source` 是 filename（{r.get('title_note') or '沒說原因'}）")
    for rx, why in LOOKS_LIKE_FILENAME:
        if rx.search(t):
            bad.append(f"標題{why}")
    return bad


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = argv[1]
    if not os.path.isdir(root):
        print(f"{root} 不是目錄 —— 這不是資料問題，是叫錯了", file=sys.stderr)
        return 2

    files = []
    for dirpath, _, names in os.walk(root):
        for n in sorted(names):
            if n.endswith(".json"):
                files.append(os.path.join(dirpath, n))
    if not files:
        print(f"{root} 底下沒有任何 JSON —— **空的目錄不算通過**", file=sys.stderr)
        return 3

    total, problems, empty = 0, [], []
    for f in sorted(files):
        rel = os.path.relpath(f, root)
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print(f"  {rel}：讀不動 —— {type(e).__name__}: {e}", file=sys.stderr)
            return 3
        rows = walk(doc, [])
        total += len(rows)
        # 帶報告的檔找不到任何列 ＝ 判準跟資料形狀對不上，那正是上次的失效
        if not rows and re.search(r'"slug"', open(f, encoding="utf-8").read()):
            empty.append(rel)
        print(f"  {rel:32s} 帶標題的列 {len(rows):>4}")
        for r in rows:
            for why in check_row(r):
                problems.append(f"{rel}　{r.get('slug', '?')[:44]}　{why}")

    print(f"\n共檢查 {total} 列，來自 {len(files)} 個檔")
    if empty:
        print(f"**{len(empty)} 個檔裡有 `slug` 卻找不到任何帶標題的列**：{empty}\n"
              "  判準與資料形狀對不上。**「檢查了 0 列」不是「都對」** ——"
              "2026-08-23 首頁標題沒換到，就是這樣被漏掉的。", file=sys.stderr)
        return 3
    if problems:
        print(f"**{len(problems)} 列的標題不是報告的真實標題**：", file=sys.stderr)
        for p in problems[:12]:
            print(f"  {p}", file=sys.stderr)
        if len(problems) > 12:
            print(f"  …另外 {len(problems) - 12} 列", file=sys.stderr)
        print("\n  處置：在 Mac 上跑 `scripts/research/backfill_titles.py --apply`，"
              "重新 commit 再推。**不要在這一層過濾** —— 錯的是資料不是顯示。",
              file=sys.stderr)
        return 1
    print("每一列的標題都來自報告本身，沒有檔名冒充的")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
