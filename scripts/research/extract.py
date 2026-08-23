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
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402   路徑只有一個家，見該檔的檔頭
import title   # noqa: E402   真實標題的取法，見該檔的檔頭

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
    # **`\bNomura\b`，不是 `\bNomura\s*\|`。** 2026-08-23 量出來的：
    # 舊規則在剃除頁首頁尾之後的文字上得分是 **0**（7 份全部） ——
    # 它整條依賴 `Nomura |` 這個頁尾字串，而那正是流程下一步要刪掉的東西。
    # 辨識刻意跑在剃除之前，所以它能work；但那讓野村的訊號強度只有 6–9 次，
    # 而高盛是 81–134、花旗 144–200。**三家不在同一個尺度上被量。**
    # 放寬之後野村 60–83，`min_hits=3` 的餘裕從 2.0× 變成 20×，
    # 而 27 份的歸屬**一份都沒有改變**，非野村的報告提到 Nomura 的次數是 0。
    ("Nomura",        re.compile(r"\bNomura\b", re.I)),
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
    """回 (表格, 原始偵測數, 表格裡剃掉幾處浮水印)。

    ## 這裡也要剃浮水印

    2026-08-23：`research.no_pii` 擴大到掃 `tables` 之後，**27 份裡 6 份當場亮紅燈** ——
    分析師信箱 ×19（花旗那份）、一個 32 位追蹤雜湊、一個反寫的 `evisulcxe`。

    原因就在這個函式：浮水印剃除跑在 `extract()` 的第 ① 步，剃的是 `raw_pages()`
    出來的**文字流**；而這裡**用 pdfplumber 重開一次 PDF**，走的是另一條路，
    從來沒經過 `strip_watermark`。

    **同一份文件的兩個表示法，守衛只裝在其中一個上面。**
    而 `no_pii` 當時也只掃那一個，於是它對 27 份一致回報「PII 與追蹤碼零殘留」——
    **一個只檢查了一半的守衛，輸出跟全部檢查過長得一模一樣。**

    剃除用的是同一組 `WATERMARK` 規則，因為問題本來就是同一個，
    分成兩份規則遲早會變成兩種判準。
    """
    try:
        import pdfplumber
    except ImportError:
        return None                      # None ＝ 沒抽，跟「抽了但沒有表格」是兩件事
    out, raw, wm = [], 0, 0
    with pdfplumber.open(path) as pdf:
        for i, pg in enumerate(pdf.pages[:max_pages]):
            for t in (pg.extract_tables() or []):
                raw += 1
                rows = []
                for r in t:
                    if not any(r):
                        continue
                    cells = []
                    for c in r:
                        c, k = strip_watermark((c or "").strip())
                        wm += k
                        cells.append(c.strip())
                    rows.append(cells)
                if len(rows) >= 2:
                    out.append({"page": i + 1, "rows": rows})
    # **原始偵測數與留下來的數要分開報。** 2026-08-21 實測 Oil Analyst：
    # `extract_tables` 回 14 個、過濾後剩 0 —— 那 14 個全是**圖框**，
    # pdfplumber 把圖表的框線當成表格，儲存格是空的。
    # 探測程式當初報的「14 個表格」是一個看起來很有說服力的錯數字。
    return out, raw, wm


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


def split_columns(path, min_gap=18.0, right_max_frac=0.42, straddle_max_frac=0.03):
    """第一頁用**字級座標**切欄，讓右側的分析師欄不再插進本文中間。

    `known_limits.page_one_right_column_bleed` 記的就是這件事：第一頁右側是
    分析師姓名與電話，逐行抽取會把它插進句子中間 ——
    `…quarters, yet its` ／ `Niklas Garnadt` ／ `labour market remains weak.`
    撰寫者因此得把原句截在名字出現之前，**寧可短也不要跨過去**，
    於是好幾句立場只剩半句。

    ## 第一版錯在哪

    要求「整頁沒有任何字跨過那條線」。實際量出來（2026-08-22，歐洲經濟分析師那份）：
    本文到 x≈412、側欄從 x≈443 起，中間**確實有空白帶** ——
    但頁首標題橫跨整頁，一個字就把整條線否掉了。
    **一條規則同時要求兩件事（欄界存在、且頁面上下都成立），會被上緣的標題否決。**

    現在改成容許少量橫跨（預設 3%），並挑橫跨最少的那條線。

    ## 回 None 是「這一頁本來就是單欄」

    跟失敗要分得開 —— 把單欄硬切成兩欄，會製造一個比原本更難發現的錯。
    右側佔比超過 `right_max_frac` 也回 None：那不是側欄，是真正的兩欄正文，
    **而兩欄正文不能重排**，左右欄是連續的閱讀順序，接起來會打亂段落。
    """
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None
            page = pdf.pages[0]
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            W = float(page.width)
    except Exception:
        return None
    if len(words) < 40:
        return None

    # **取合格切點裡最左邊的那一條，不是橫跨最少的那一條。**
    # 挑「橫跨最少」會選到最右緣 —— 那裡幾乎沒有字，當然沒有人橫跨它，
    # 而切出去的只有浮水印，側欄仍然留在本文裡。
    # 2026-08-22 第一版就是這樣：**規則跑完了、切點也存在，而它什麼都沒分開。**
    cut = None
    limit = len(words) * straddle_max_frac
    x = W * 0.45
    while x < W * 0.92:
        right = sum(1 for w in words if w["x0"] >= x)
        if (right and right / len(words) <= right_max_frac
                and sum(1 for w in words if w["x0"] < x < w["x1"]) <= limit):
            cut = x
            break
        x += 2.0
    if cut is None:
        return None

    # 切點兩側要真的隔開。**用分位數，不用極值** ——
    # 既然容許 3% 的字橫跨，極值一定被那幾個字拉過界（實測間隙會變成負的），
    # 於是這道守衛永遠不通過，而它看起來只是「這頁是單欄」。
    def pct(vals, q):
        v = sorted(vals)
        return v[min(len(v) - 1, int(len(v) * q))] if v else 0.0
    lmax = pct([w["x1"] for w in words if w["x0"] < cut], 0.97)
    rmin = pct([w["x0"] for w in words if w["x0"] >= cut], 0.03)
    if rmin - lmax < min_gap:
        return None

    def lines(ws):
        out, cur, top = [], [], None
        for w in sorted(ws, key=lambda w: (round(w["top"], 1), w["x0"])):
            if top is None or abs(w["top"] - top) > 3:
                if cur:
                    out.append(" ".join(cur))
                cur, top = [], w["top"]
            cur.append(w["text"])
        if cur:
            out.append(" ".join(cur))
        return out

    left = [w for w in words if w["x0"] < cut]
    right = [w for w in words if w["x0"] >= cut]
    # **這裡也要剃。** 這是第三個繞過浮水印剃除的表示法（前兩個是文字流與表格）——
    # 它同樣用 pdfplumber 重開 PDF，而剃除只裝在 `extract()` 第 ① 步的文字流上。
    # 右欄整欄就是分析師聯絡區塊，所以殘留幾乎必然：實測 5 份、30 個信箱、
    # 4 個 `Prepared for`。而 `no_pii` 當時連掃都沒掃到這個欄位。
    #
    # **同一個守衛漏掉三次，三次都是「同一份文件的另一個表示法」。**
    # 教訓不是「再補一個地方」，是**任何新的 `pdfplumber.open(path)` 都要先問
    # 它的輸出會不會被存下來** —— 會的話就得經過 `strip_watermark`。
    return strip_watermark("\n".join(lines(left)) + "\n\n"
                           + "─── 右欄（分析師欄，原句不要從這裡取）───\n"
                           + "\n".join(lines(right)))[0]


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

    # **辨識在剃頁首之前做，因為券商名就寫在頁首**（先剃再認會讓 7/7 掉到 4/7 ——
    # 我把雜訊跟訊號一起剃掉，而輸出只說「認不出」，不會說「我剛剛把它刪了」）。
    #
    # 但窗口式的「前 N 頁前 600 字」也不行：Top of Mind 的 `Goldman` 第一次出現
    # 在第 4,082（pdfplumber）／6,472（pdftotext）個字元。第一版靠 `hf` 補救，
    # 而 `hf` 本身是**抽取器相依**的 —— 於是同一份檔在沙箱認得出、在發布機認不出。
    # **我把辨識建在一個會隨工具變的東西上。**
    id_src = "\n".join(pages)
    p1_raw = pages[0] if pages else ""

    # **計次取最大，不是首次命中。** 掃全文會撞到互相引用（這份 Top of Mind 的
    # 圖表來源就寫著 `Goldman Sachs GIR`，而花旗的報告也可能引用高盛）。
    # 自己家的名字會出現在頁首、頁尾、免責聲明、法律實體名裡，數十次起跳；
    # 被引用的那家通常只有個位數。差距本身就是證據，所以把計數留在輸出裡備查。
    tally = {n: len(rx.findall(id_src)) for n, rx in BROKERS}
    top = max(tally, key=tally.get)
    margin = A["brokers"]["min_margin"]
    second = sorted(tally.values(), reverse=True)[1] if len(tally) > 1 else 0
    broker = top if tally[top] >= A["brokers"]["min_hits"] and tally[top] >= second * margin else None
    date = None
    for rx, fmt in DATE_RX:
        m = rx.search(p1_raw)
        if m:
            try:
                date = dt.datetime.strptime(re.sub(r",\s*", ", ", m.group(1)), fmt).date().isoformat()
                break
            except ValueError:
                pass
    # **`product` 與 `slug` 刻意還是從檔名來，即使檔名是 `1317180`。**
    # slug 是這一套的身分：`dossier` 的條目 id 是 `{slug}-{n}`、圖檔名、
    # `digest/*.json` 的鍵、已發布的 `data/*.json` 全部指著它。
    # 改 slug 不是改顯示，是**讓已發布的追蹤紀錄失去它追的那份報告**。
    # 而且 `build_index.merge` 對新 slug 的反應是「新增」而不是「更新」——
    # 重跑一次抽取就會多出五筆孤兒。標題可以改，身分不行。
    product = base.split("_")[0].strip() if "_" in base else base
    issue = (re.search(r"ISSUE\s+(\d+)", p1_raw) or [None, None])[1]
    claimed = (re.search(r"(\d+)\s+pages\b", p1_raw) or [None, None])[1]
    # 真實標題：見 title.py 的檔頭（三家券商三個來源，認不出來就回檔名並標記）
    tt = title.resolve(broker, os.path.basename(path), p1, path)

    return {
        "slug": f"{date or 'undated'}-{slugify(broker or 'unknown')}-{slugify(product)}",
        "broker": broker, "broker_tally": tally, "product": product, "date": date,
        "title": tt["title"], "title_source": tt["title_source"],
        "title_confident": tt["title_confident"], "title_note": tt["title_note"],
        "source_file": os.path.basename(path),
        "pages": npage, "claimed_pages": claimed and int(claimed), "issue": issue,
        "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
        "engine": ENGINE,
        "extracted_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        "page_one": p1,
        # **切欄的結果是附加的，不取代 `page_one`。**
        # 2026-08-22 調了三輪門檻，判為有側欄的份數在 2/23 與 6/23 之間跳 ——
        # 那是在對雜訊調參，而手上沒有驗證集。
        # 讓一個不可靠的猜測**安靜地取代**原始記錄，比不猜更糟：
        # 既有的原句與 grounding 全部是對著 `page_one` 驗過的。
        # 所以它只多給一份重排版，由讀的人一眼判斷哪一份可用。
        "page_one_columns": split_columns(path),
        "body": kept[1:],
        **dict(zip(("tables", "tables_raw", "tables_watermark_hits"),
                   tables_of(path) or (None, 0, 0))),
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
    # **allow_abbrev=False 是這一行存在的全部理由。**
    # argparse 預設做前綴展開：`--dry` → `--dry-run`、`--pr` → `--prune`（會刪檔）、
    # `--f` → `--force`。於是底下那個「不認得的旗標就中止」的守衛**永遠不會觸發** ——
    # argparse 保證 `unknown` 是空的。
    #
    # 那個守衛正是為了 2026-08-20 的事故寫的（有人把 `--dry-run` 打成 `--dry`，
    # 於是它被當成沒有旗標、安靜地改寫了一份已發布的封存）。
    # **我為了防那個錯而寫的守衛，被它底下那一層的預設架空了。**
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("inbox", nargs="?")
    ap.add_argument("--out", default=None)   # 見 _paths.py：`~` 會展開到別的地方
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prune", action="store_true")
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
    out = os.path.expanduser(a.out) if a.out else _paths.extracted()
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
    fresh_files = set()          # 這一輪**應該存在**的輸出路徑
    written = {}                 # slug → (sha256, source_file)，撞號守衛用
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
            # **先登記再判斷要不要重寫。** 跳過重寫的檔案照樣是「這一輪該有的」，
            # 漏掉這一行會讓沒更動的檔全部被當成孤兒。
            fresh_files.add(os.path.abspath(f))

            # ── slug 撞號：兩份不同的報告算出同一個 slug ──────────────
            # `slug` ＝ 日期 ＋ 券商 ＋ 產品線，而產品線來自檔名的第一段。
            # 同一天、同一家、同一個系列出兩篇（`Oil Monitor` 這種日頻系列很平常），
            # 兩份就會撞在同一個檔名上，而**第二份直接覆蓋第一份**。
            #
            # 損失比「少一個檔」更糟：`build_index.merge` 對已收錄的 slug 不改寫，
            # 於是**索引留著第一份的標題與 sha256，而 `extracted/` 裡是第二份的內文**。
            # 之後每一條逐字比對都拿第二份的原句去比第二份的文字 —— 全部通過，
            # 而網站顯示的是第一份的標題。
            #
            # `research.no_duplicates` 有一條專門抓 slug 撞號，但**它抓不到這個**：
            # 它讀的是 `extracted/`，而覆蓋發生在它執行之前 ——
            # 到它看的時候，兩份已經變成一份，`by_slug` 只有一個值。
            # **守衛量的是撞號之後的狀態，而證據在那時已經被刪掉了。**
            #
            # 所以這裡不寫、記一筆 bad、讓整輪回非零。要哪一份由人決定。
            prev = written.get(d["slug"])
            other = None
            if prev and prev[0] != d["sha256"]:
                other = prev[1]
            elif not prev and os.path.exists(f):
                try:
                    old_doc = json.load(open(f, encoding="utf-8"))
                except Exception:
                    old_doc = {}
                if (old_doc.get("sha256") and old_doc["sha256"] != d["sha256"]
                        and old_doc.get("source_file") != d["source_file"]):
                    other = old_doc.get("source_file")
            if other:
                print(f"      **slug 撞號，這一份沒有寫入**：{d['slug']}\n"
                      f"        這份　{os.path.basename(p)}\n"
                      f"        已占用 {other}\n"
                      "        同一天同一家同一個系列的兩篇。**覆蓋會讓索引與內文指向不同的報告。**\n"
                      "        處置：把其中一份的檔名加上區別（例如結尾加 ` II`）再重跑。")
                bad += 1
                continue

            if os.path.exists(f) and not a.force and os.path.getmtime(f) > os.path.getmtime(p):
                written[d["slug"]] = (d["sha256"], d["source_file"])
                print("      （已是最新，跳過）"); continue
            written[d["slug"]] = (d["sha256"], d["source_file"])
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=1)
    # **孤兒**：輸出檔名是從 slug 來的，而 slug 是**衍生值**（日期＋券商＋產品線）。
    # 辨識規則一改，同一份 PDF 就換一個檔名，舊的留在原地 ——
    # 2026-08-21 修好 Top of Mind 的券商辨識之後，`extracted/` 裡同時有
    # `unknown-top-of-mind` 與 `goldman-sachs-top-of-mind`，內容一樣。
    #
    # 判準是「**這個檔是不是這一輪寫出來的**」，不是「它的 sha256 還在不在這一批」。
    # 第一版用了後者，於是那份孤兒永遠測不出來 —— 它是同一份 PDF，sha256 當然在。
    # **我答了另一個問題**（內容還在嗎），而要問的是檔案的來歷。
    #
    # 這個判準同時涵蓋第二種情況：某份 PDF 從 inbox 拿掉了，它的輸出也該是孤兒。
    #
    # 預設只報不刪：刪除要明確。`--prune` 才真的動手。
    if not a.dry_run:
        orphans = [f for f in sorted(glob.glob(os.path.join(out, "*.json")))
                   if os.path.abspath(f) not in fresh_files]
        if orphans:
            print(f"\n**{len(orphans)} 份孤兒**（不是這一輪寫的）："
                  f"{[os.path.basename(x) for x in orphans]}")
            if a.prune:
                for f in orphans:
                    os.remove(f)
                print("  已刪除（--prune）")
            else:
                print("  留著。確認過就加 --prune 重跑，或自己刪。"
                      "**留著的話 research_verify 會判 FAIL**，那是對的。")
                bad += 1
    return 10 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
