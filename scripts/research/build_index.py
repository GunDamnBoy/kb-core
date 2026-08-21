#!/usr/bin/env python3
"""抽取結果 → 可查詢的索引。**這支會寫檔**（`~/broker-research/index.json`）。

用法：build_index.py [抽取目錄] [--out <索引路徑>] [--dry-run]

## 索引是「跨批」的那一層

單批的檢查看不見跨批重複——`research.no_duplicates` 的 blind_to 第一條就寫著
「上週已經收過的這一批又收一次，這條看不到（它只看眼前這批）」。
**索引是唯一知道歷史的東西**，所以跨批去重在這裡做。

## 索引不放全文

只放中繼資料與**第一頁的立場段**。理由有兩個，第二個才是主要的：

1. 全文放進來索引會變成幾 MB，而它要被反覆讀。
2. **全文已經在 `extracted/` 裡了。** 同一份內容出現在兩個地方時，
   只要有一次是「再寫一遍」，兩邊就會開始漂移而且沒有訊號。
   索引存的是**指標**（slug），不是副本。

## 已收錄的不改寫

同一個 slug 再次出現、而 sha256 不同時：**保留舊的、記一筆 `revisions`**。
報告的修訂版是真實存在的形態，而「悄悄換掉上週那一份」會讓
「上週我讀到的是什麼」永遠答不出來。
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

TPE = dt.timezone(dt.timedelta(hours=8))


def visible(s):
    return re.sub(r"\s+", " ", s or "").strip()


def entry(d):
    """索引裡的一筆。**刻意不含 body 與 tables** —— 那些在 extracted/ 裡。"""
    return {
        "slug": d.get("slug"),
        "broker": d.get("broker"),
        "product": d.get("product"),
        "date": d.get("date"),
        "title": d.get("title"),
        "pages": d.get("pages"),
        "issue": d.get("issue"),
        "sha256": d.get("sha256"),
        "source_file": d.get("source_file"),
        "engine": d.get("engine"),
        "thesis_chars": len(visible(d.get("page_one"))),
        "tables": len(d.get("tables") or []),
        "first_seen": None,      # 由 merge 填；已收錄的不改寫
    }


def merge(old, new_entries, now):
    """回 (索引, 報告)。**新的不覆蓋舊的**，只補與記。"""
    by_slug = {e["slug"]: e for e in (old.get("reports") or [])}
    added, dupes, revisions = [], [], []
    for e in new_entries:
        prev = by_slug.get(e["slug"])
        if prev is None:
            e["first_seen"] = now
            by_slug[e["slug"]] = e
            added.append(e["slug"])
            continue
        if prev.get("sha256") == e.get("sha256"):
            dupes.append(e["slug"])                      # 同一份又收一次，什麼都不做
            continue
        # slug 相同、內容不同 ＝ 修訂版。**舊的留著。**
        prev.setdefault("revisions", []).append(
            {"seen": now, "sha256": e.get("sha256"), "source_file": e.get("source_file"),
             "pages": e.get("pages")})
        revisions.append(e["slug"])
    reports = sorted(by_slug.values(), key=lambda x: (x.get("date") or "", x.get("slug") or ""),
                     reverse=True)
    brokers = sorted({r["broker"] for r in reports if r.get("broker")})
    idx = {
        "updated": now,
        "updatedLabel": dt.datetime.fromisoformat(now).strftime("%-m/%-d %H:%M"),
        "count": len(reports),
        "brokers": brokers,
        "date_range": [reports[-1].get("date"), reports[0].get("date")] if reports else [None, None],
        "reports": reports,
    }
    return idx, {"added": added, "already_indexed": dupes, "revisions": revisions}


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)   # 見 extract.py 的理由
    ap.add_argument("src", nargs="?", default="~/broker-research/extracted")
    ap.add_argument("--out", default="~/broker-research/index.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
        print(__doc__); return 2

    src = os.path.expanduser(a.src)
    out = os.path.expanduser(a.out)
    files = sorted(glob.glob(os.path.join(src, "*.json")))
    if not files:
        print(f"{src} 沒有抽取結果 —— 空輪次，不是失敗"); return 13

    docs = [json.load(open(f, encoding="utf-8")) for f in files]
    bad = [d.get("source_file") for d in docs if not d.get("broker") or not d.get("date")]
    if bad:
        print(f"**{len(bad)} 份辨識不全，不進索引**：{bad}\n"
              "  索引是給人查的，一筆沒有券商或日期的紀錄查不到也對不上。"
              "先修抽取層再建索引。", file=sys.stderr)
        return 10
    old = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    now = dt.datetime.now(TPE).isoformat(timespec="seconds")
    idx, rep = merge(old, [entry(d) for d in docs], now)

    print(f"索引 {idx['count']} 筆｜{len(idx['brokers'])} 家｜"
          f"{idx['date_range'][0]} → {idx['date_range'][1]}")
    print(f"  新增 {len(rep['added'])}　已收錄 {len(rep['already_indexed'])}　"
          f"修訂版 {len(rep['revisions'])}")
    if rep["revisions"]:
        print(f"  **修訂版**：{rep['revisions']} —— 舊的留著，新的記進 revisions")
    if a.dry_run:
        print("  **dry-run，未寫檔**"); return 0
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, out)                    # 原子寫入：半份索引比沒有索引更糟
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
