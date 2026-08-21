#!/usr/bin/env python3
"""外資報告：**看清楚真實形狀**，在寫任何規格之前。

用法：probe_research.py <報告資料夾> [--full]

**這支只讀不寫。** 一個位元組都不寫進磁碟 —— 2026-08-21 有人（我）拿會寫檔的
`sentinel.py` 當診斷工具跑，在三個 repo 裡各偽造了一次心跳。
**在拿一支程式當診斷之前，先問它寫不寫檔。**

## 為什麼需要這一步

這套系統的輸入是別人排版的 PDF，而**合成測試驗得了邏輯、驗不出資料的真實形狀**。
在看過真的報告之前就把 anchors 的欄位寫死，會複製 2026-08-21 那個缺陷：
`chart.series_freshness` 讀 `data`／產出寫 `dates`，對著 13 天封存全綠、一個數字都沒讀到。

它回答的六個問題（全部是「這份 PDF 到底長什麼樣」，不是「它說了什麼」）：

1. **有沒有文字層** —— 掃描檔抽不出字，那是完全不同的一條管線（要 OCR）
2. **每頁字數分布** —— 首頁通常是封面（字少），內頁才是內容
3. **斷行災難程度** —— 兩欄排版抽出來會左右欄交錯，那會毀掉一切
4. **頁首頁尾污染** —— 每頁重複出現的行（券商名、免責聲明、頁碼）
5. **表格抽不抽得到**
6. **中繼資料** —— 標題、作者、建立時間，有時比內文好認
"""
import collections
import os
import re
import subprocess
import sys


def sh(*a):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=120).stdout
    except Exception as e:
        return f"__ERR__ {type(e).__name__}: {e}"


def pages_text(path):
    """逐頁抽文字。用 pdftotext -layout —— **保留版面**，兩欄排版才看得出來是兩欄。"""
    out = sh("pdftotext", "-layout", path, "-")
    if out.startswith("__ERR__"):
        return None, out
    return out.split("\f"), None


def probe(path, full=False):
    name = os.path.basename(path)
    size = os.path.getsize(path) / 1024
    info = sh("pdfinfo", path)
    meta = dict(re.findall(r"^([A-Za-z ]+):\s+(.*)$", info, re.M))
    pages, err = pages_text(path)
    print(f"\n{'='*72}\n{name}　{size:,.0f} KB")
    if err:
        print("  抽字失敗：", err); return
    n = len([p for p in pages if p.strip()]) or 1
    chars = [len(p) for p in pages]
    total = sum(chars)
    print(f"  頁數 {meta.get('Pages','?')}（有字的 {n}）　總字元 {total:,}"
          f"　每頁中位 {sorted(chars)[len(chars)//2]:,}")

    # ① 文字層：整份幾乎沒字＝掃描檔，要走 OCR，是另一條管線
    per = total / max(1, int(meta.get("Pages", n) or n))
    verdict = ("**疑似掃描檔（沒有文字層）** —— 要 OCR，是另一條管線" if per < 200
               else "有文字層" if per > 800 else "文字層稀薄，要人工看一眼")
    print(f"  ① 文字層：{verdict}（平均每頁 {per:,.0f} 字元）")

    # ② 中繼資料：有時比內文好認，但也常常是排版軟體留下的垃圾
    for k in ("Title", "Author", "Subject", "CreationDate", "Creator"):
        if meta.get(k, "").strip():
            print(f"     {k}: {meta[k].strip()[:70]}")

    # ③ 頁首頁尾污染：每頁都出現的行
    counts = collections.Counter()
    for p in pages:
        for line in {l.strip() for l in p.splitlines() if 3 < len(l.strip()) < 90}:
            counts[line] += 1
    rep = [(c, l) for l, c in counts.items() if c >= max(2, n * 0.6)]
    print(f"  ② 頁首頁尾重複行：{len(rep)} 條"
          + ("（抽取層要剃掉，否則每頁都混進內文）" if rep else ""))
    for c, l in sorted(rep, reverse=True)[:6]:
        print(f"     ×{c:<3} {l[:66]}")

    # ④ 斷行：兩欄排版的指紋是「大量偏短的行」
    body = "\n".join(pages[1:]) if len(pages) > 1 else pages[0]
    lines = [l.rstrip() for l in body.splitlines() if l.strip()]
    if lines:
        short = sum(1 for l in lines if len(l.strip()) < 45)
        print(f"  ③ 行數 {len(lines):,}　偏短行 {short/len(lines)*100:.0f}%"
              + ("　**偏短行過半，很可能是兩欄排版**，抽出來會左右欄交錯" if short > len(lines)*0.5 else ""))

    # ⑤ 表格：pdfplumber 才看得到，pdftotext 看不到
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            t = sum(len(pg.extract_tables() or []) for pg in pdf.pages[:12])
        print(f"  ④ 前 12 頁偵測到 {t} 個表格")
    except Exception as e:
        print(f"  ④ 表格偵測跳過：{type(e).__name__}")

    if full:
        print("  ---- 第 2 頁前 900 字（原樣，含空白）----")
        print("\n".join("     " + l for l in (pages[1] if len(pages) > 1 else pages[0])[:900].splitlines()))


def main(argv):
    if not argv:
        print(__doc__); return 2
    root = os.path.expanduser(argv[0])
    full = "--full" in argv
    if os.path.isfile(root):
        probe(root, full); return 0
    if not os.path.isdir(root):
        print(f"找不到 {root} —— **這跟「資料夾是空的」是兩件事**", file=sys.stderr); return 12
    pdfs = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(root)
                  for f in fs if f.lower().endswith(".pdf"))
    others = sorted(f for dp, _, fs in os.walk(root) for f in fs
                    if not f.lower().endswith(".pdf") and not f.startswith("."))
    print(f"{root}：{len(pdfs)} 份 PDF" + (f"，另有 {len(others)} 個非 PDF 檔：{others[:6]}" if others else ""))
    if not pdfs:
        print("**資料夾在但沒有 PDF** —— 這跟「資料夾不存在」是兩件事，兩者的處置不同")
        return 13
    for p in pdfs[:12]:
        probe(p, full)
    if len(pdfs) > 12:
        print(f"\n（只探測前 12 份，還有 {len(pdfs)-12} 份未看）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
