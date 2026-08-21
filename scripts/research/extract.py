#!/usr/bin/env python3
"""外資報告 → 結構化中間檔。**這支會寫檔。**

用法：extract.py <inbox> [--out <目錄>] [--force] [--dry-run]

寫到 `~/broker-research/extracted/<slug>.json`（可用 `--out` 改）。
**輸出目錄與 inbox 都在所有 repo 之外**，那是結構性的界線不是 `.gitignore`：
原文逐頁蓋有可追溯到個人的浮水印，抽取文字同樣不進版控。

> 這一行是刻意寫在最前面的。2026-08-21 有人（我）拿會寫檔的 `sentinel.py`
> 當診斷工具跑，在三個 repo 裡各偽造了一次心跳。
> **每一支程式的第一句話都該回答「你寫不寫檔」。**

## 三件事，順序不能換

1. **剃浮水印**（最早的一步）—— 裡面有真人的公司信箱。晚一步剃，
   它就有機會進到某個中間狀態；而「曾經寫出去過」是收不回來的。
2. **剃頁首頁尾** —— 靠「重複出現」＋「位置固定」兩個條件，不是只靠重複。
   只靠重複會誤刪真正重複的小標；只靠位置會漏掉浮水印那種浮動的東西。
3. **保留表格** —— 外資報告的數字大量住在表格裡，`pdftotext` 抽不到，
   只有 `pdfplumber` 抽得到。

## 剃掉多少要報出來

**一個剃太多的清洗器，跟一個乾淨的文件，輸出長得一樣。** 所以每一份都回報
剃掉幾行、佔幾成，並把剃掉的樣本印出來。上界寫在 `anchors.extract`，
超過就該有人看一眼——這條刻意不自動擋，因為誤判的方向兩邊都可能。
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

_KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
A = json.load(open(os.path.join(_KB, "research", "anchors.json"), encoding="utf-8"))

# ── 浮水印：兩種形態都要剃 ────────────────────────────────────────────
# `pdftotext` 把旋轉文字讀成正的、`pdfplumber` 讀成逐段反轉（連雜湊都整串反轉）。
# **兩條抽取路徑都可能被走到，所以兩種都列。**
WATERMARK = [
    re.compile(r"For the exclusive use of\s*\S*", re.I),
    re.compile(r"Prepared for\s+[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,3}"),
    re.compile(r"\b(?:evisulcxe|deraperP|semaJ|esu evisulcxe)\b"),
    re.compile(r"\b[0-9a-f]{32}\b"),                     # 逐份追蹤雜湊（正反同形）
    re.compile(r"\b[\w.+-]+@[\w.-]+\.\w{2,}\b"),         # 任何信箱
    re.compile(r"\b[A-Z]{2}\.[A-Z]{3}\.[A-Z]+@\d+\b"),   # 反寫的信箱
    # 分析師電話。信箱已在上面剃掉，電話是同一個聯絡區塊的另一半，
    # 而 `anchors.privacy.analyst_contacts` 說那些不進結構化封存。
    # 形態固定（國碼 ＋ 空白／短橫分隔），誤刪風險低。
    re.compile(r"\+\d{1,3}[-\s]\d[\d\s-]{6,14}\b"),
]

BROKERS = [
    ("Nomura",        re.compile(r"\bNomura\s*\|", re.I)),
    ("Goldman Sachs", re.compile(r"\bGoldman\s+Sachs\b", re.I)),
    ("Citi",          re.compile(r"\bCiti\s*(?:Research|group)\b", re.I)),
]
DATE_RX = [
    (re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]{2,8}\s+20\d\d)\b"), "%d %B %Y"),
    (re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]{2}\s+20\d\d)\b"),   "%d %b %Y"),
    (re.compile(r"\b([A-Z][a-z]{2,8}\s+\d{1,2},\s*20\d\d)\b"), "%B %d, %Y"),
]

ENGINE = None


def pick_engine():
    for want in A["extract"]["engine_order"]:
        if want == "pdftotext" and shutil.which("pdftotext"):
            return want
        if want in ("pdfplumber", "pypdf"):
            try:
                __import__(want); return want
            except ImportError:
                continue
    return None


def raw_pages(path):
    if ENGINE == "pdftotext":
        out = subprocess.run(["pdftotext", "-layout", path, "-"],
                             capture_output=True, text=True, timeout=300).stdout
        pages = out.split("\f")
        # 輸出結尾有一個換頁符，於是尾端多出一個空元素 —— **整份頁數 +1**。
        # 2026-08-21 抓到它的是 `claimed_pages` 那條完整性檢查（花旗自報 26 頁、
        # 我抽到 27 頁）。**那條檢查上線第一天就抓到的是我自己的 bug。**
        while pages and not pages[-1].strip():
            pages.pop()
        return pages
    if ENGINE == "pdfplumber":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return [(p.extract_text(layout=True) or "") for p in pdf.pages]
    import pypdf
    return [(p.extract_text() or "") for p in pypdf.PdfReader(path).pages]


def tables_of(path, max_pages=200):
    try:
        import pdfplumber
    except ImportError:
        return None                      # None ＝ 沒抽，跟「抽了但沒有表格」是兩件事
    out, raw = [], 0
    with pdfplumber.open(path) as pdf:
        for i, pg in enumerate(pdf.pages[:max_pages]):
            for t in (pg.extract_tables() or []):
                raw += 1
                rows = [[(c or "").strip() for c in r] for r in t if any(r)]
                if len(rows) >= 2:
                    out.append({"page": i + 1, "rows": rows})
    # **原始偵測數與留下來的數要分開報。** 2026-08-21 實測 Oil Analyst：
    # `extract_tables` 回 14 個、過濾後剩 0 —— 那 14 個全是**圖框**，
    # pdfplumber 把圖表的框線當成表格，儲存格是空的。
    # 探測程式當初報的「14 個表格」是一個看起來很有說服力的錯數字。
    return out, raw


def strip_watermark(text):
    """回 (乾淨文字, 剃掉幾處)。**這是最早的一步。**"""
    n = 0
    for p in WATERMARK:
        text, k = p.subn(" ", text)
        n += k
    return text, n


def _key(line):
    """比對用的正規形：把連續空白塌成一個。

    頁首是「券商名 …右對齊的產品線」，**中間的空白數會隨抽取器與頁面而變**——
    `pdftotext` 與 `pdfplumber` 給的空白數就不一樣。逐字比對的結果是 0 條命中，
    看起來像「這份沒有頁首」，而它每一頁都有。
    """
    return re.sub(r"\s+", " ", line).strip()


def header_footer_lines(pages, ratio=0.6, edge=3):
    """重複**且位置固定**才算頁首頁尾。

    只靠重複會誤刪真正重複的小標（「Source: Citi Research」出現在每張圖下面，
    那是內容不是頁首）；只靠位置會漏掉浮動的東西。兩個條件同時成立才剃。
    """
    n = len([p for p in pages if p.strip()]) or 1
    seen = collections.Counter()
    for p in pages:
        ls = [l for l in (p or "").splitlines() if l.strip()]
        for l in {_key(x) for x in ls[:edge] + ls[-edge:]}:
            if 3 < len(l) < 120:
                seen[l] += 1
    return {l for l, c in seen.items() if c >= max(2, n * ratio)}


def norm_name(base):
    """檔名正規化：實測有尾隨空白與全形破折號，不正規化同一份會變成兩筆。"""
    s = unicodedata.normalize("NFKC", base)
    return re.sub(r"\s+", " ", s).strip()


def slugify(s):
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:60]


def extract(path):
    base = norm_name(os.path.basename(path)[:-4])
    pages = raw_pages(path)
    npage = len(pages)

    # ① 浮水印先剃
    wm = 0
    pages = [(lambda r: (r[0], r[1]))(strip_watermark(p or "")) for p in pages]
    wm = sum(k for _, k in pages)
    pages = [t for t, _ in pages]

    # ② 頁首頁尾
    hf = header_footer_lines(pages)
    kept, dropped = [], 0
    for p in pages:
        out = []
        for l in (p or "").splitlines():
            if _key(l) in hf:
                dropped += 1
            else:
                out.append(l.rstrip())
        kept.append("\n".join(out))

    before = sum(len((p or "").splitlines()) for p in pages)
    p1 = kept[0] if kept else ""

    # **辨識要在剃頁首之前做，因為券商名就寫在頁首。**
    # 第一版先剃再認，於是野村兩份與花旗一份變成「認不出」—— 7/7 掉到 4/7。
    # 我把雜訊跟訊號一起剃掉了，而輸出只說「認不出」，不會說「我剛剛把它刪了」。
    # `hf` 本身也一起找：那組字串正是頁首，券商名一定在裡面。
    id_src = "\n".join([(pages[i] or "")[:600] for i in range(min(4, npage))] + sorted(hf))
    p1_raw = pages[0] if pages else ""

    broker = next((n for n, rx in BROKERS if rx.search(id_src)), None)
    date = None
    for rx, fmt in DATE_RX:
        m = rx.search(p1_raw)
        if m:
            try:
                date = dt.datetime.strptime(re.sub(r",\s*", ", ", m.group(1)), fmt).date().isoformat()
                break
            except ValueError:
                pass
    product = base.split("_")[0].strip() if "_" in base else base
    issue = (re.search(r"ISSUE\s+(\d+)", p1_raw) or [None, None])[1]
    claimed = (re.search(r"(\d+)\s+pages\b", p1_raw) or [None, None])[1]

    return {
        "slug": f"{date or 'undated'}-{slugify(broker or 'unknown')}-{slugify(product)}",
        "broker": broker, "product": product, "date": date,
        "title": base, "source_file": os.path.basename(path),
        "pages": npage, "claimed_pages": claimed and int(claimed), "issue": issue,
        "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
        "engine": ENGINE,
        "extracted_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        "page_one": p1,
        "body": kept[1:],
        **dict(zip(("tables", "tables_raw"), tables_of(path) or (None, 0))),
        "strip_report": {
            "watermark_hits": wm,
            "header_footer_lines_removed": dropped,
            "header_footer_patterns": sorted(hf)[:8],
            "lines_before": before,
            "removed_pct": round(dropped / before * 100, 1) if before else 0.0,
        },
    }


def main(argv=None):
    global ENGINE
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("inbox", nargs="?")
    ap.add_argument("--out", default="~/broker-research/extracted")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or not a.inbox:
        print(__doc__); return 2
    if unknown:
        print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**。"
              "2026-08-20 有人把 `--dry-run` 打成 `--dry`，於是它被當成沒有旗標、"
              "安靜地改寫了一份已發布的封存。", file=sys.stderr)
        return 12

    ENGINE = pick_engine()
    if ENGINE is None:
        print("**這台機器上沒有任何 PDF 抽取器**（環境問題，不是報告的問題）。\n"
              "  ~/.venvs/kb/bin/pip install pdfplumber", file=sys.stderr)
        return 14
    inbox = os.path.expanduser(a.inbox)
    out = os.path.expanduser(a.out)
    if not os.path.isdir(inbox):
        print(f"找不到 {inbox} —— 跟「資料夾是空的」是兩件事", file=sys.stderr); return 12
    pdfs = sorted(os.path.join(inbox, f) for f in os.listdir(inbox) if f.lower().endswith(".pdf"))
    if not pdfs:
        print("inbox 沒有 PDF —— 空輪次，不是失敗"); return 13

    print(f"抽取器：{ENGINE}　{len(pdfs)} 份"
          + ("　**dry-run，不寫檔**" if a.dry_run else f" → {out}"))
    if not a.dry_run:
        os.makedirs(out, exist_ok=True)
    bad = 0
    for p in pdfs:
        d = extract(p)
        s = d["strip_report"]
        flag = ""
        if not d["broker"] or not d["date"]:
            flag = "　**辨識不全**"; bad += 1
        if s["removed_pct"] > 15:
            flag += "　**剃掉超過 15%，看一眼**"
        cp = d["claimed_pages"]
        if cp and cp != d["pages"]:
            flag += f"　**自報 {cp} 頁 ≠ 抽到 {d['pages']} 頁**"; bad += 1
        print(f"  {d['slug'][:52]:<52} {d['pages']:>3}頁 "
              f"表格{len(d['tables'] or []):>3}/{d['tables_raw']:<3} 浮水印{s['watermark_hits']:>4} "
              f"剃{s['header_footer_lines_removed']:>4}行({s['removed_pct']:>4.1f}%){flag}")
        if not a.dry_run:
            f = os.path.join(out, d["slug"] + ".json")
            if os.path.exists(f) and not a.force and os.path.getmtime(f) > os.path.getmtime(p):
                print("      （已是最新，跳過）"); continue
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=1)
    return 10 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
