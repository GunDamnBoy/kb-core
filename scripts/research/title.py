#!/usr/bin/env python3
"""報告的**真實標題**從哪裡來。

用法：title.py --selftest [--fixture <路徑>]

## 這支存在的理由

在它之前，`extract.py` 的 `title` 是**檔名去副檔名**。名字叫 title，量到的是
檔名 —— 低一層的東西。而它壞掉的樣子有三種，只有一種會被看見：

| 樣子 | 例 | 看得見嗎 |
|---|---|---|
| 檔名是流水號 | `1317180` | **會**（野村全部如此，這是被回報的那一種） |
| 檔名被下載端截斷 | `…Data C` ＋ `...`（固定 128 字元） | 不會，尾巴斷得很像正常標題 |
| 檔名只有系列名 | `Oil Monitor` | **完全不會** —— 它看起來就是一個好標題 |

第三種最危險：花旗那五份在網站上一直是「Oil Monitor」「US Economics Weekly」，
沒有任何人會覺得不對，而真正的標題是
「Oil Monitor: At visible draw rates, when do we "run out" of oil stockpiles?」。
**一個量錯維度的欄位，壞掉的時候跟正常輸出長得一模一樣。**

## 三家券商，三個來源 —— 這不是調參，是三家的匯出器不一樣

先量過再接（27 份全部量過，見 `--selftest`）：

| 券商 | 用什麼 | 為什麼不是別的 |
|---|---|---|
| Nomura | 第一頁字級座標（pdfplumber） | **`/Title` 是空的**，檔名是流水號 —— 另外兩條路都沒有東西 |
| Citi | `/Title` | 它本來就帶正確標點（`Oil Monitor: At visible draw rates…`），且 5 份全部未觸上限 |
| Goldman Sachs | `/Title` ＋ 用檔名還原冒號；觸到上限時再用第一頁補尾 | 它的 `/Title` 把所有冒號丟掉，而**檔名正好把冒號寫成 `_`**；`/Title` 在第 139 字元硬截（13 份中 2 份中招），那 2 份的完整標題在第一頁 |

**沒有一條規則對三家都成立，而這是三家匯出器的性質，不是門檻沒調好。**
把它寫成一張對照表，比寫成一條「通用」規則誠實 —— 通用規則會在第四家出現時
安靜地給出一個看起來很正常的錯答案。

## 試過而放棄的：一條通用的「裁切第一頁大字塊」

pdfplumber 量出大字塊的 y 範圍、再用 `pdftotext -x -y -W -H` 裁那一塊出來，
看起來能一次解決三家。實測不行，而失敗的方式值得記著：

- 裁切的 `-W` 會**從字中間切斷** —— `AN AI JOB APOCALYPS`、`IPO SURGE: A RED FLAG FOR M`。
  放寬 `-W` 就把右側分析師欄一起收進來（`Re Implications of the Failed 'Bessent Put' Str`）。
  **同一個參數同時要求兩件相反的事**，跟 `split_columns` 第一版撞的是同一堵牆。
- GS 的 Top of Mind 與 India Financials 是封面式版型：**內文與標題同縮排、同一塊**，
  「縮排變淺就是內文」在那兩份上會把整段摘要吃進標題。

放棄它不是因為調不出來，是因為**調得出來的東西沒有驗證集可以證明它調對了**。
改走對照表之後，每一家都有第二個來源可以對（GS 對 `/Title`、Citi 對第一頁、
野村對人工讀出來的 fixture），對不起來就回 `filename` 並出聲。

## 認不出來的時候會怎樣

回 `("<檔名>", "filename", False)`。**不猜。** `title_source` 與 `title_confident`
一路寫進 `extracted/`、`index.json`、`digest/`，`checks/research.py` 的
`research.title_resolved` 看到 `filename` 就出聲。

第四家券商進來的時候，這裡會回 `filename` 而檢查會說「N 份沒認出真實標題」——
**它不會安靜地把檔名當標題發布出去**，那正是這支要終結的失效模式。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# ── 共用 ────────────────────────────────────────────────────────────
_PUNCT = re.compile(r"[^0-9a-z]+")


def norm(s: str) -> str:
    """比對用的正規化：只留小寫英數。

    **標點是不能拿來比對的**：檔名把 `:` 換成 `_`、把 `?` 換成 `_`、
    把 `/` 換成什麼要看下載端；GS 的 `/Title` 把冒號整個丟掉。
    三個來源的標點各自失真，只有字母是三邊都保住的。
    """
    return _PUNCT.sub("", (s or "").lower())


def _sq(s: str) -> str:
    """彎引號 → 直引號，全形空白 → 半形。只動字元，不動內容。"""
    return (s or "").translate(str.maketrans({
        "‘": "'", "’": "'", "“": '"', "”": '"',
        " ": " ", "　": " ", "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    }))


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", _sq(s)).strip()


def join(parts) -> str:
    """系列名 ＋ 標題 → 一行。**空的那一段不會留下一個孤兒冒號。**"""
    p = [clean(x) for x in parts if clean(x)]
    if not p:
        return ""
    head = p[0].rstrip(":：").strip()
    return head if len(p) == 1 else head + ": " + " ".join(p[1:])


# ── 來源 1：PDF 中繼資料 ────────────────────────────────────────────
# **`[ \t]*` 不是 `\s*`。** `\s` 含換行：第一版寫 `^Title:\s*(.*)$`，
# 遇到沒有 Title 的野村檔時 `\s*` 吃掉換行、`(.*)` 抓到下一行，
# 於是七份野村的「標題」全部變成 `Creator:` ——
# **一個空欄位被讀成了下一個欄位的名字，而輸出看起來只是個怪標題。**
_META_RX = re.compile(r"^Title:[ \t]*(.*)$", re.M)
META_CAP = 139   # GS 匯出器的硬上限，量出來的（Americas Construction 與 APAC Kickstart 都正好 139）


def meta_title(pdf_path: str):
    """回 (標題, 是否完整)；沒有中繼標題回 (None, None)。"""
    try:
        out = subprocess.run(["pdfinfo", pdf_path], capture_output=True,
                             text=True, timeout=60).stdout
    except Exception:
        return None, None
    m = _META_RX.search(out)
    t = clean(m.group(1)) if m else ""
    if not t:
        return None, None
    return t, len(t) < META_CAP


# ── 來源 2：第一頁文字（pdftotext 版面）── Goldman Sachs ──────────────
_CAPS_RX = re.compile(r"^[^a-z]*[A-Z][^a-z]*$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def from_page_one_gs(page_one: str):
    """GS 第一頁：**全大寫的系列行 ＋ 其下同縮排的標題行**。

    版面（`extracted/*.json` 的 `page_one`，pdftotext 產）長這樣：

        (58)  AMERICAS CONSTRUCTION: BUILDING PRODUCTS
        (58)  Non-Residential Construction: Data Centers and Institutional Projects
        (58)  Support Growth in DMI while Billings Deteriorate
        (54)  Inflation and Exposure to Key Verticals Drive YOY Momentum …   ← 內文

    **界線是縮排變淺，不是空行。** 空行在標題塊裡出現一到三行都看過
    （13 份裡三種都有），拿空行當終止條件會在其中一種上把標題砍成半句。
    內文一定比標題塊淺 —— 那是 GS 版型固定的事，13/13 成立。
    """
    lines = _sq(page_one or "").splitlines()
    ci = None
    for i, ln in enumerate(lines[:24]):
        s = ln.strip()
        if len(s) >= 6 and _CAPS_RX.match(s) and re.search(r"[A-Z]{3}", s):
            ci = i
            break
    if ci is None:
        return None, None
    ind = _indent(lines[ci])
    caps, body = lines[ci].strip(), []
    for ln in lines[ci + 1:ci + 12]:
        if not ln.strip():
            continue
        if _indent(ln) < ind - 2:      # 縮排變淺 ＝ 進內文了
            break
        if abs(_indent(ln) - ind) > 2:
            break
        body.append(ln.strip())
    return caps, (" ".join(body) if body else None)


def recase(caps: str, source_file: str):
    """把全大寫的系列名，用檔名裡的大小寫還原。

    檔名 `Americas Construction_ Building Products_ Non-Residential…` 的前綴
    正規化後 ＝ `AMERICAS CONSTRUCTION: BUILDING PRODUCTS` 正規化後。
    **逐字元對，取最長相等前綴**；對不上就原樣回去（全大寫難看，但沒有猜）。
    """
    base = os.path.splitext(os.path.basename(source_file or ""))[0]
    want = norm(caps)
    if not want:
        return caps
    acc = ""
    for ch in base:
        acc += ch
        n = norm(acc)
        if n == want:
            return clean(acc.replace("_", ":"))
        if not want.startswith(n):
            return caps
    return caps


def restore_punct(meta: str, source_file: str):
    """GS 的 `/Title` 沒有冒號，而**檔名正好把冒號寫成 `_`** —— 兩邊合起來才完整。

    量到的關係（3 份逐字元核過）：`len(檔名) - len(/Title) == 底線個數`，
    也就是 `/Title` ＝ 檔名把每個 `_` 拿掉。所以用檔名的分段去切 `/Title`：
    每一段的正規化形式，應該正好是 `/Title` 接下來那一段的正規化形式。

    **檔名被截（128 字元）而 `/Title` 沒有時，剩下的尾巴接回最後一段，不另起一段** ——
    第一版用 `": ".join()` 收尾，於是
    `…Support Growt` ＋ `h in DMI while Bi` 變成 `…Support Growt: h in DMI while Bi`。
    一個字被冒號劈開，而那句話讀起來仍然像個標題。

    對不上就回 None（交給呼叫端決定），**不做局部修補** ——
    一個「大致對齊」的標點還原，錯的地方看起來跟對的地方一樣。
    """
    base = os.path.splitext(os.path.basename(source_file or ""))[0]
    segs = [s for s in base.split("_")]
    out, pos = [], 0
    for s in segs:
        want = norm(s)
        if not want:
            continue
        acc = ""
        while pos < len(meta) and norm(acc) != want:
            acc += meta[pos]; pos += 1
            if not want.startswith(norm(acc)):
                return None
        if norm(acc) != want:
            return None
        out.append(acc.strip())
    if not out:
        return None
    tail = meta[pos:]
    if tail.strip():
        out[-1] = (out[-1] + tail).strip()
    t = ": ".join(x.strip().rstrip(":").strip() for x in out)
    return t + "?" if base.rstrip().endswith("_") else t


# ── 來源 3：第一頁座標（pdfplumber）── Nomura ────────────────────────
def from_page_one_nomura(pdf_path: str, side_frac=0.68, gap_mult=1.4):
    """野村第一頁：**左欄裡字級大於內文的那兩組**。

    右側 x0≈418／頁寬 595 是分析師欄（姓名、信箱、電話），逐行抽取會把它
    插進標題中間 —— `split_columns` 的檔頭記的就是同一件事。這裡切在 0.68W，
    因為要的只有標題，不必像那支一樣把整頁重排。

    分組要**同時**看字級與垂直間距：`1317175` 的系列名與標題**都是 15pt**
    （`Matsuzawa's View: Macro Strategy Weekly` ／ `Implications of the Failed
    'Bessent Put'`），只看字級會把兩者黏成一句；它們的 top 差 57pt，
    而換行只差 16pt，間距分得開。只看間距則會在 `1316582` 上失敗（封面式版型，
    系列名在 y=94、標題在 y=479）。**兩個條件缺一不可。**
    """
    try:
        import pdfplumber
    except ImportError:
        return None, None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return None, None
            page = pdf.pages[0]
            words = page.extract_words(extra_attrs=["size"])
            W = float(page.width)
    except Exception:
        return None, None
    cut = W * side_frac
    rows = {}
    for w in words:
        if w["x0"] >= cut:
            continue
        rows.setdefault(round(w["top"], 1), []).append(w)
    if not rows:
        return None, None
    seq = []
    for top in sorted(rows):
        g = sorted(rows[top], key=lambda w: w["x0"])
        seq.append({"top": top, "size": max(round(w["size"], 1) for w in g),
                    "text": " ".join(w["text"] for w in g)})
    # 內文字級 ＝ 左欄裡最常見的字級。**不是最小的** —— 最小的是頁首那一行 7pt。
    freq = {}
    for r in seq:
        freq[round(r["size"])] = freq.get(round(r["size"]), 0) + 1
    body = max(freq, key=lambda k: (freq[k], k))
    big = [r for r in seq if r["size"] > body + 1.5]
    if not big:
        return None, None
    groups, cur = [], None
    for r in big:
        same = (cur and abs(r["size"] - cur["size"]) < 0.6
                and r["top"] - cur["last"] <= cur["size"] * gap_mult)
        if same:
            cur["text"] += " " + r["text"]
            cur["last"] = r["top"]
        else:
            cur = {"size": r["size"], "text": r["text"], "last": r["top"]}
            groups.append(cur)
    g = [x for x in groups if clean(x["text"])]
    if not g:
        return None, None
    return clean(g[0]["text"]), (clean(g[1]["text"]) if len(g) > 1 else None)


# ── 對照表 ──────────────────────────────────────────────────────────
def resolve(broker, source_file, page_one, pdf_path=None):
    """回 `{"title", "title_source", "title_confident", "title_note"}`。

    `pdf_path` 是 None（回填舊資料時拿不到原檔）就只用 `page_one` 那條路；
    需要原檔的券商會回 `filename` 而不是**用另一條沒驗過的路頂替**。
    """
    base = os.path.splitext(os.path.basename(source_file or ""))[0]
    fallback = {"title": clean(base) or (source_file or ""), "title_source": "filename",
                "title_confident": False, "title_note": ""}

    if broker == "Citi":
        if not pdf_path or not os.path.exists(pdf_path):
            fallback["title_note"] = "花旗要 PDF 中繼資料，而原檔不在手上"
            return fallback
        t, complete = meta_title(pdf_path)
        if not t:
            fallback["title_note"] = "花旗這一份沒有 /Title"
            return fallback
        return {"title": t, "title_source": "pdf_meta", "title_confident": bool(complete),
                "title_note": "" if complete else f"/Title 觸到 {META_CAP} 字元上限，尾巴可能被截"}

    if broker == "Goldman Sachs":
        if not pdf_path or not os.path.exists(pdf_path):
            fallback["title_note"] = "GS 要 PDF 中繼資料，而原檔不在手上"
            return fallback
        mt, complete = meta_title(pdf_path)
        if not mt:
            fallback["title_note"] = "GS 這一份沒有 /Title"
            return fallback
        title = restore_punct(mt, source_file) or mt
        if complete:
            return {"title": title, "title_source": "pdf_meta", "title_confident": True,
                    "title_note": "" if title != mt else "檔名對不上 /Title，冒號沒有還原"}

        # `/Title` 觸到上限了。**只有這一條路會走到第一頁** ——
        # 它在 GS 的封面式版型（Top of Mind、India Financials）上會把摘要吃進標題，
        # 而那幾份的 `/Title` 都沒有觸到上限，永遠走不到這裡。
        caps, head = from_page_one_gs(page_one)
        if caps:
            p1 = join([recase(caps, source_file), head])
            if norm(p1).startswith(norm(mt)):     # 第一頁必須**含蓋**被截的那一段
                return {"title": p1, "title_source": "page_one", "title_confident": True,
                        "title_note": f"/Title 在 {META_CAP} 字元被截，尾巴取自第一頁"}
        return {"title": title, "title_source": "pdf_meta", "title_confident": False,
                "title_note": f"/Title 觸到 {META_CAP} 字元上限，而第一頁補不回尾巴"}

    if broker == "Nomura":
        if not pdf_path or not os.path.exists(pdf_path):
            fallback["title_note"] = "野村要第一頁座標，而原檔不在手上"
            return fallback
        series, head = from_page_one_nomura(pdf_path)
        if not series:
            fallback["title_note"] = "野村第一頁切不出標題塊"
            return fallback
        return {"title": join([series, head]), "title_source": "page_one",
                "title_confident": bool(head), "title_note":
                "" if head else "只切到系列名，沒有標題行"}

    fallback["title_note"] = f"沒有 {broker!r} 的取法 —— **新券商要先量過再加進對照表**"
    return fallback


# ── 自我檢查 ────────────────────────────────────────────────────────
def selftest(fixture, extracted_dir, inbox_dir):
    """對著人工讀出來的 27 個標題跑。**這就是 `split_columns` 當時沒有的驗證集。**

    沒有驗證集的門檻調整，是在對雜訊調參：判為成功的份數會在兩個數字之間跳，
    而你分不出哪一次是對的。有驗證集之後，`gap_mult` 這種數字才是可以動的。
    """
    exp = {k: v for k, v in json.load(open(fixture, encoding="utf-8")).items()
           if not k.startswith("_")}
    bad, low = [], []
    for slug, want in sorted(exp.items()):
        ep = os.path.join(extracted_dir, slug + ".json")
        if not os.path.exists(ep):
            bad.append(f"{slug}：沒有抽取結果"); continue
        d = json.load(open(ep, encoding="utf-8"))
        pdf = os.path.join(inbox_dir, d.get("source_file") or "")
        got = resolve(d.get("broker"), d.get("source_file"), d.get("page_one"), pdf)
        if norm(got["title"]) != norm(want):
            bad.append(f"{slug}\n     期望 {want}\n     得到 {got['title']}"
                       f"　[{got['title_source']}] {got['title_note']}")
        elif not got["title_confident"]:
            low.append(f"{slug}　[{got['title_source']}] {got['title_note']}")
    print(f"自我檢查：{len(exp)} 份，{len(exp) - len(bad)} 份標題正確")
    for b in bad:
        print(f"  ✗ {b}")
    if low:
        print(f"  **{len(low)} 份正確但未標為可信**（會被 checks 出聲）：")
        for l in low:
            print(f"    - {l}")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)  # 見 extract.py 的理由
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fixture", default=None)
    ap.add_argument("--extracted", default=None)
    ap.add_argument("--inbox", default=None)
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown or not a.selftest:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
        print(__doc__); return 2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _paths
    fx = a.fixture or _paths.under("title_fixture.json")
    ex = a.extracted or _paths.extracted()
    ib = a.inbox or _paths.under("inbox")
    if not os.path.exists(fx):
        print(f"沒有 {fx} —— **驗證集不在就不要跑**，"
              "一個沒有期望值的自我檢查只會永遠通過", file=sys.stderr)
        return 13
    return selftest(fx, ex, ib)


if __name__ == "__main__":
    sys.exit(main())
