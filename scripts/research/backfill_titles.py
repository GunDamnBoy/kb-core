#!/usr/bin/env python3
"""把**已經產出**的標題換成真實標題。一次性，寫完就沒事做了。

用法：backfill_titles.py [--apply] [--digest-repo <路徑>]
（預設 dry-run —— **改已發布的東西，預設不能是「動手」**）

## 為什麼需要一支專門的程式，而不是重跑一次

`build_index.merge` 對已收錄的 slug **刻意不改寫**（「已收錄的不改寫」，
見 `build_index.py` 檔頭）。那條規則是對的 —— 它擋掉的正是「悄悄換掉上週那一份」。
所以重跑 `extract.py` ＋ `build_index.py` 不會更新這 27 筆的標題，
**它會安靜地什麼都不做，然後回報成功。**

於是改舊資料必須是一個**明講的、看得到差異的**動作，而不是一次重跑的副作用。
這支就是那個動作，而它跑完之後應該被刪掉。

## 它動哪些檔

| 檔 | 動什麼 | 誰會再產它 |
|---|---|---|
| `extracted/*.json` | `title` ＋ 三個新欄位 | `extract.py`（之後都會對） |
| `index.json` | 同上 | `build_index.py`（**不會改舊的**，所以要在這裡動） |
| `digest/2026-W*.json` | `reports[].title` | `assemble.py` |
| `<digest repo>/data/*.json` | `reports[].title` | 發布層（**已經在公開網站上**） |
| `<digest repo>/data/stances.json` | `items[].title` | `assemble.py --dossier` |

`dossier/*.md` 不在表上：它們由 `dossier.py` 從 `extracted/` 重產，改完源頭重跑一次就好。

## 兩道保險

1. **只有 `title` 與三個新欄位可以變。** 每個檔比對「拿掉這四個鍵之後」的內容，
   不相等就中止 —— 一支只該改標題的程式改到別的東西，是不能靠讀輸出發現的。
2. **`slug` 一個都不動。** 它是 `dossier` 條目 id、圖檔名、已發布 JSON 的鍵。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths   # noqa: E402
import title    # noqa: E402

FIELDS = ("title", "title_source", "title_confident", "title_note")
DEFAULT_REPO = os.path.expanduser("~/broker-research-digest")


def strip(o):
    """把要改的欄位拿掉，剩下的拿來比對「有沒有改到別的東西」。"""
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in FIELDS}
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o


def retitle(node, resolved):
    """遞迴走整棵樹，把**每一個同時有 `slug` 與 `title` 的物件**換掉。
    回 (改了幾筆, 對不到抽取結果幾筆, 總共看到幾筆帶標題的列)。

    ## 為什麼是走樹，不是指定鍵名

    第一版列了一張「檔案 → 鍵名」的表：`index.json` 看 `reports`、
    `stances.json` 看 `items`。**而網站首頁那一份 `data/index.json`
    把每份報告放在 `days[].items[]` —— 比表裡假設的深兩層，於是它一筆都沒被改到。**

    更糟的是驗證也照同一張表寫：它 glob 到了那個檔、打開了它、
    在 `d["reports"]` 與 `d["items"]` 上各找了一次、兩個都不存在、
    於是**一列都沒檢查就回報「零殘留」**。
    看過那個檔而且說它乾淨，跟真的檢查過長得一模一樣。

    走樹之後，鍵名叫什麼、巢狀幾層都不影響 —— 判準變成「這個物件是不是一份報告」，
    而那由它自己的欄位決定，不由它住在哪裡決定。

    **`seen` 要回出去。** 一個檔改了 0 筆有兩種意思：已經是最新的，
    或者這支根本沒找到任何標題。前者是好消息，後者是這次的缺陷本身。
    """
    changed = missing = seen = 0
    if isinstance(node, dict):
        if "slug" in node and "title" in node:
            seen += 1
            r = resolved.get(node.get("slug"))
            if r is None:
                missing += 1                 # 舊週次的報告可能已不在 extracted/
            else:
                if node.get("title") != r["title"]:
                    changed += 1
                node["title"] = r["title"]
                node["title_source"] = r["title_source"]
                node["title_confident"] = r["title_confident"]
        for v in node.values():
            c, m, s2 = retitle(v, resolved)
            changed += c; missing += m; seen += s2
    elif isinstance(node, list):
        for v in node:
            c, m, s2 = retitle(v, resolved)
            changed += c; missing += m; seen += s2
    return changed, missing, seen


def write(path, obj, before, apply):
    """原子寫入 ＋ 只改標題的斷言。**斷言在寫之前。**"""
    if strip(before) != strip(obj):
        print(f"  ✗ {path}：**除了標題還動到別的東西，中止**", file=sys.stderr)
        return False
    if not apply:
        return True
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--digest-repo", default=DEFAULT_REPO)
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
        print(__doc__); return 2

    E, I, F = _paths.extracted(), _paths.inbox(), _paths.under("filed")
    files = sorted(glob.glob(os.path.join(E, "*.json")))
    if not files:
        print(f"{E} 沒有抽取結果", file=sys.stderr); return 13

    # ── 1. extracted/：重新解析，這是唯一的源頭 ──────────────────────
    resolved, changed, weak = {}, [], []
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        before = json.loads(json.dumps(d))
        # 原檔可能已經封存了（`file_reports.py` 移進 `filed/<YYYY-MM>/`）。
        # **只找 inbox 的話，`pdf_meta` 那條路會靜靜地退化成 `page_one`** ——
        # 它照樣回一個標題，只是換了來源，而這支的用途正是修標題。
        pdf = os.path.join(I, d.get("source_file") or "")
        if not os.path.exists(pdf) and d.get("archived_to"):
            pdf = os.path.join(F, d["archived_to"])
        r = title.resolve(d.get("broker"), d.get("source_file"), d.get("page_one"), pdf)
        resolved[d["slug"]] = r
        if r["title"] != d.get("title"):
            changed.append((d["slug"], d.get("title"), r["title"], r["title_source"]))
        if not r["title_confident"]:
            weak.append((d["slug"], r["title_note"]))
        d.update({k: r[k] for k in FIELDS})
        if not write(f, d, before, a.apply):
            return 20

    print(f"抽取結果 {len(files)} 份｜標題有變 {len(changed)} 份｜"
          f"**未標為可信 {len(weak)} 份**")
    for slug, old, new, src in changed:
        print(f"  {slug}\n      舊 {old}\n      新 {new}　[{src}]")
    for slug, note in weak:
        print(f"  ! {slug}　{note}")

    # ── 2. 其餘各處：**走整棵樹**，不指定鍵名 ────────────────────────
    repo = os.path.expanduser(a.digest_repo)
    targets = ([_paths.under("index.json")]
               + sorted(glob.glob(_paths.under("digest", "2026-W*.json")))
               + sorted(glob.glob(os.path.join(repo, "data", "*.json"))))
    for path in targets:
        if not os.path.exists(path):
            print(f"  – {os.path.basename(path)}：不在，跳過"); continue
        d = json.load(open(path, encoding="utf-8"))
        before = json.loads(json.dumps(d))
        n, miss, seen = retitle(d, resolved)
        if not write(path, d, before, a.apply):
            return 20
        tail = f"　（{miss} 筆沒有對應的抽取結果，未動）" if miss else ""
        mark = "✎" if n else ("·" if seen else "！")
        note = "" if seen else "　**這個檔裡一列都沒有標題** —— 確認它本來就不帶標題"
        print(f"  {mark} {os.path.relpath(path, os.path.expanduser('~'))}："
              f"{n} 筆改名{tail}{note}")

    print("\n**dry-run，一個檔都沒寫。加 --apply 才會動。**" if not a.apply
          else "\n寫入完成。**接著要重產 dossier（dossier.py）並重新發布。**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
