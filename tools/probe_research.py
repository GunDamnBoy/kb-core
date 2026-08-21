#!/usr/bin/env python3
"""外資報告：**看清楚真實形狀**，在寫任何規格之前。

用法：probe_research.py <報告資料夾或單一 PDF> [--full]

**這支只讀不寫。** 一個位元組都不寫進磁碟 —— 2026-08-21 有人（我）拿會寫檔的
`sentinel.py` 當診斷工具跑，在三個 repo 裡各偽造了一次心跳。
**在拿一支程式當診斷之前，先問它寫不寫檔。**

## 抽取器：純 python 優先，系統執行檔是選配

第一版只認 `pdftotext`，而**那支在發布機上不存在** —— 沙箱有、Mac 沒有，
於是七份報告回報七次一模一樣的 FileNotFoundError，看起來像七份檔案各有問題。
兩條教訓都寫進來了：

1. **每日關鍵路徑不依賴系統執行檔。** 跟 podfetch 對 ffmpeg 的處理同一條：
   有就用（`pdftotext -layout` 的版面保留最好），沒有就走 `pdfplumber`／`pypdf`，
   兩者都在 venv 裡跟著 requirements 走。
2. **環境問題只報一次，而且報在最前面。** 同一個環境失敗重複 N 次，
   讀起來像 N 個資料問題。

## 它回答的六個問題（全部是「這份 PDF 長什麼樣」，不是「它說了什麼」）

1. **有沒有文字層** —— 掃描檔抽不出字，那是完全不同的一條管線（要 OCR）
2. **每頁字數分布** —— 首頁通常是封面（字少），內頁才是內容
3. **斷行災難程度** —— 兩欄排版抽出來會左右欄交錯，那會毀掉一切
4. **頁首頁尾污染** —— 每頁重複出現的行（券商名、免責聲明、頁碼）
5. **表格抽不抽得到**
6. **中繼資料與檔名** —— 有時比內文好認；檔名還帶著產品線名稱

**下面每一個門檻都是估的**，要拿第一批真檔校準之後才算數。
"""
import collections
import os
import re
import shutil
import subprocess
import sys

ENGINE = None          # 決定一次，全程沿用；訊息也只印一次


def pick_engine():
    if shutil.which("pdftotext"):
        return "pdftotext"
    try:
        import pdfplumber          # noqa: F401
        return "pdfplumber"
    except ImportError:
        pass
    try:
        import pypdf               # noqa: F401
        return "pypdf"
    except ImportError:
        return None


def pages_text(path):
    """逐頁抽文字，回 (pages, err)。**保留版面** —— 兩欄排版才看得出來是兩欄。"""
    try:
        if ENGINE == "pdftotext":
            out = subprocess.run(["pdftotext", "-layout", path, "-"],
                                 capture_output=True, text=True, timeout=180).stdout
            return out.split("\f"), None
        if ENGINE == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return [(p.extract_text(layout=True) or "") for p in pdf.pages], None
        import pypdf
        r = pypdf.PdfReader(path)
        return [(p.extract_text() or "") for p in r.pages], None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def meta_of(path):
    if shutil.which("pdfinfo"):
        out = subprocess.run(["pdfinfo", path], capture_output=True, text=True).stdout
        return dict(re.findall(r"^([A-Za-z ]+):\s+(.*)$", out, re.M))
    try:
        import pypdf
        d = pypdf.PdfReader(path).metadata or {}
        return {k.lstrip("/"): str(v) for k, v in d.items()}
    except Exception:
        return {}


def probe(path, full=False):
    name = os.path.basename(path)
    print(f"\n{'='*74}\n{name}　{os.path.getsize(path)/1024:,.0f} KB")
    # 檔名本身是證據：macOS 把 `:` 換成 `_`，所以 `Top of Mind_ Assessing…`
    # 原本是 `Top of Mind: Assessing…` —— 冒號前那一段是**券商的產品線名稱**。
    if "_" in name:
        print(f"  ⓪ 檔名疑似含產品線：「{name.split('_')[0].strip()}」"
              "（macOS 會把 `:` 存成 `_`）")
    if name != name.strip() or "  " in name or name.endswith(" .pdf"):
        print("  ⓪ **檔名有多餘空白** —— 入庫時要正規化，否則同一份會變成兩筆")

    pages, err = pages_text(path)
    if err:
        print(f"  抽字失敗：{err}"); return
    n = len([p for p in pages if p.strip()]) or 1
    chars = [len(p) for p in pages]
    total = sum(chars)
    npage = len(pages)
    print(f"  頁數 {npage}（有字的 {n}）　總字元 {total:,}　每頁中位 {sorted(chars)[len(chars)//2]:,}")

    per = total / max(1, npage)
    verdict = ("**疑似掃描檔（沒有文字層）**，要 OCR" if per < 200
               else "有文字層" if per > 800 else "文字層稀薄，要人工看一眼")
    print(f"  ① 文字層：{verdict}（平均每頁 ~{per:,.0f} 字元；門檻 200／800 是估的）")

    m = meta_of(path)
    for k in ("Title", "Author", "Subject", "CreationDate", "Creator", "Producer"):
        v = (m.get(k) or "").strip()
        if v and v.lower() not in ("untitled", "unspecified", "anonymous"):
            print(f"     {k}: {v[:72]}")

    counts = collections.Counter()
    for p in pages:
        for line in {l.strip() for l in (p or "").splitlines() if 3 < len(l.strip()) < 90}:
            counts[line] += 1
    rep = [(c, l) for l, c in counts.items() if c >= max(2, n * 0.6)]
    print(f"  ② 頁首頁尾重複行：{len(rep)} 條"
          + ("（抽取層要剃掉，否則每頁都混進內文）" if rep else ""))
    for c, l in sorted(rep, reverse=True)[:6]:
        print(f"     ×{c:<3} {l[:68]}")

    body = "\n".join(pages[1:]) if npage > 1 else (pages[0] or "")
    lines = [l.rstrip() for l in body.splitlines() if l.strip()]
    if lines:
        short = sum(1 for l in lines if len(l.strip()) < 45)
        pct = short / len(lines) * 100
        print(f"  ③ 內頁行數 {len(lines):,}　偏短行 {pct:.0f}%"
              + ("　**過半，很可能是兩欄排版**，抽出來會左右欄交錯" if pct > 50 else ""))

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            t = sum(len(pg.extract_tables() or []) for pg in pdf.pages[:12])
        print(f"  ④ 前 12 頁偵測到 {t} 個表格")
    except ImportError:
        print("  ④ 表格偵測跳過：沒有 pdfplumber")
    except Exception as e:
        print(f"  ④ 表格偵測跳過：{type(e).__name__}")

    if full:
        pick = pages[1] if npage > 1 else pages[0]
        print("  ---- 第 2 頁前 1000 字（原樣，含空白）----")
        print("\n".join("     " + l for l in (pick or "")[:1000].splitlines()))


def main(argv):
    global ENGINE
    if not argv:
        print(__doc__); return 2
    ENGINE = pick_engine()
    if ENGINE is None:
        print("**這台機器上沒有任何 PDF 抽取器。** 這是環境問題，不是報告的問題。\n"
              "  裝其中一個（擇一即可）：\n"
              "    ~/.venvs/kb/bin/pip install pdfplumber     ← 建議，版面與表格最好\n"
              "    ~/.venvs/kb/bin/pip install pypdf\n"
              "    brew install poppler                        （提供 pdftotext）",
              file=sys.stderr)
        return 14                                    # ENVIRONMENT
    print(f"抽取器：{ENGINE}"
          + ("（系統執行檔，版面保留最好）" if ENGINE == "pdftotext" else "（純 python）"))

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
    print(f"{root}：{len(pdfs)} 份 PDF"
          + (f"，另有 {len(others)} 個非 PDF：{others[:6]}" if others else ""))
    if not pdfs:
        print("**資料夾在但沒有 PDF** —— 跟「資料夾不存在」是兩件事，處置不同")
        return 13
    for p in pdfs[:12]:
        probe(p, full)
    if len(pdfs) > 12:
        print(f"\n（只探測前 12 份，還有 {len(pdfs)-12} 份未看）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
