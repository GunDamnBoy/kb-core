#!/usr/bin/env python3
"""上傳之前，確認**索引跟它指的日檔說的是同一件事**。

用法：verify_site_index.py <要部署的目錄> [--allow-differ 鍵,鍵,…]

## 為什麼四套都需要這一道

四個資料 repo 是同一個形狀：`data/index.json` 有 `days[]`，
每一筆帶著 `file` 指向 `data/<日期>.json`，**而且複製了那個日檔裡的欄位**
（`headline`、`date`、`stamp`、各種計數）。清單頁讀索引的複本，單篇頁讀日檔。

一份意義兩個家。兩邊漂開的時候：**清單顯示 A、點進去顯示 B**，
而兩頁各自看起來都完全正常 —— 沒有人會在只看其中一頁的時候發現。

2026-08-23 外資報告週摘就是這樣：`data/index.json` 的 `days[].items[].title`
還是舊的檔名標題，`data/<日期>.json` 的 `reports[].title` 已經換成真實標題。
首頁一整面舊標題，單篇頁全對，而**部署驗證是綠的而且它是對的**（線上就是剛上傳的那份）。

## 比什麼

1. **同名純量欄位** —— 索引那一筆與日檔頂層，同一個鍵名都有值就必須相等。
2. **以 `slug`／`id` 對上的物件** —— 兩邊樹裡同一個 id 的物件，共有的純量欄位必須相等。
   鍵名與巢狀深度都不看，因為上次漏掉的成因正是一張鍵名對照表
   （報告在 `days[].items[]`，比表裡假設的深兩層）。

## `--allow-differ` 與它自己的防腐

有些欄位是**刻意**兩邊不同的：每日五圖的 `weekday` 在索引是 `六`（下拉選單用），
在日檔是 `週六`（頁首日期列用）。硬擋會讓這道守衛第一天就狼來了，
而一個天天亮紅燈的守衛會被關掉。

所以放行要明講，寫在呼叫端（workflow）並附理由。
**而放行清單本身會過期**，所以這裡回報每一條放行實際擋掉了幾次 ——
`0 次` 代表那個差異已經不存在了，那一條該刪掉。沒有這一行，
放行清單只會愈長，而它有沒有用沒有人知道。

## 「一天都沒比到」直接失敗

上次的失效就是「檢查了 0 列」被當成「都對」。所以每一天都印出比了幾對，
而某一天連一對都比不到時失敗 —— 那代表判準跟資料形狀對不上。
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def scalars(d):
    return {k: v for k, v in d.items() if not isinstance(v, (dict, list))}


def by_id(node, out=None):
    """樹裡所有帶 `slug` 或 `id` 的物件，以那個值為鍵。"""
    if out is None:
        out = {}
    if isinstance(node, dict):
        k = node.get("slug") or node.get("id")
        if isinstance(k, str) and k:
            out.setdefault(k, node)
        for v in node.values():
            by_id(v, out)
    elif isinstance(node, list):
        for v in node:
            by_id(v, out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("site", nargs="?")
    ap.add_argument("--allow-differ", default="")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown or not a.site:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
        print(__doc__); return 2

    allow = {k.strip() for k in a.allow_differ.split(",") if k.strip()}
    used = {k: 0 for k in allow}
    idxp = os.path.join(a.site, "data", "index.json")
    if not os.path.exists(idxp):
        print(f"找不到 {idxp} —— **沒有索引不算通過**", file=sys.stderr); return 3
    idx = json.load(open(idxp, encoding="utf-8"))
    days = idx.get("days") or []
    if not days:
        print("索引裡沒有任何 days —— **空索引不算通過**", file=sys.stderr); return 3

    bad, blank, n_sc, n_id = [], [], 0, 0
    for day in days:
        rel = day.get("file")
        label = rel or day.get("date") or "?"
        if not rel:
            bad.append(f"{label}：索引這一筆沒有 `file`，無從比對"); continue
        p = os.path.join(a.site, rel)
        if not os.path.exists(p):
            bad.append(f"{label}：索引指著 {rel}，而那個檔不在要部署的內容裡"); continue
        try:
            doc = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            bad.append(f"{label}：讀不動 —— {type(e).__name__}: {e}"); continue

        pairs = 0
        A, B = scalars(day), scalars(doc)
        for k in sorted(set(A) & set(B)):
            if k in allow:
                if A[k] != B[k]:
                    used[k] += 1
                continue
            pairs += 1
            if A[k] != B[k]:
                bad.append(f"{label}　欄位 `{k}`：索引 {A[k]!r} ≠ 日檔 {B[k]!r}")
        n_sc += pairs

        IA, IB = by_id(day), by_id(doc)
        idp = 0
        for key in sorted(set(IA) & set(IB)):
            x, y = scalars(IA[key]), scalars(IB[key])
            for f in sorted(set(x) & set(y)):
                if f in allow:
                    if x[f] != y[f]:
                        used[f] += 1
                    continue
                idp += 1
                if x[f] != y[f]:
                    bad.append(f"{label}　{key[:40]} 的 `{f}`："
                               f"索引 {str(x[f])[:44]!r} ≠ 日檔 {str(y[f])[:44]!r}")
        n_id += idp

        if pairs + idp == 0:
            blank.append(label)
        print(f"  {label:34s} 同名純量 {pairs:>3}　以 id 對上 {idp:>4}")

    print(f"\n{len(days)} 天｜同名純量欄位 {n_sc} 對｜以 id 對上的欄位 {n_id} 對")
    for k in sorted(allow):
        print(f"  放行 `{k}`：擋掉 {used[k]} 次"
              + ("　**0 次 —— 這條放行已經沒有作用，刪掉它**" if not used[k] else ""))

    if blank:
        print(f"\n**{len(blank)} 天連一對都比不到**：{blank[:6]}\n"
              "  判準跟資料形狀對不上。**「比了 0 對」不是「都一致」** ——"
              "2026-08-23 首頁標題沒換到，就是這樣被漏掉的。", file=sys.stderr)
        return 3
    if bad:
        print(f"\n**索引與日檔對不起來，{len(bad)} 處**：", file=sys.stderr)
        for b in bad[:14]:
            print(f"  {b}", file=sys.stderr)
        if len(bad) > 14:
            print(f"  …另外 {len(bad) - 14} 處", file=sys.stderr)
        print("\n  清單頁讀索引、單篇頁讀日檔，所以這種漂移的樣子是"
              "**兩頁各自都正常、但說的不是同一件事**。\n"
              "  處置：重新產生索引（或回填），不要在顯示層調和。"
              "刻意的差異用 `--allow-differ` 明講。", file=sys.stderr)
        return 1
    print("索引與每一份日檔說的是同一件事")
    return 0


if __name__ == "__main__":
    sys.exit(main())
