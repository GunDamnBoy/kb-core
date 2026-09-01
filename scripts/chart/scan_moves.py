# -*- coding: utf-8 -*-
"""
scan_moves.py — 市場異動掃描：把當日／本週的變動放進各自的歷史分布看分位。

【為什麼需要這支】
BRIEF 把 slot 2（市場異動圖）定義成「程式化掃描：把當日變動放進歷史分布看分位」，
**但這個「程式化」從來沒有程式**。2026-08-21 與 08-22 兩輪都是當場在輸出目錄
寫一支拋棄式腳本算出來的 —— 同一段統計每天重寫一次，而**每天重寫的東西每天都有
一次寫錯的機會，且錯了不會有人比對**（分母取幾年、報酬是 4 日還是 5 日、
台股樣本比美股短，這些都是當場決定的）。

這支把它固定下來：只讀 `data/series` 的快取，**不連外**，
所以它跑在哪一台都一樣，也不會因為沙箱沒網路而失效。

用法：
    python3 ~/kb-core/scripts/chart/scan_moves.py                  掃預抓核心清單
    python3 ~/kb-core/scripts/chart/scan_moves.py --window 5       5 個交易日（預設 1 與 5 都算）
    python3 ~/kb-core/scripts/chart/scan_moves.py --years 3        分位取近幾年（預設 3）
    python3 ~/kb-core/scripts/chart/scan_moves.py --ids GLD,SOXQ   只看指定幾條
    python3 ~/kb-core/scripts/chart/scan_moves.py --json           輸出 JSON 供出圖用
    python3 ~/kb-core/scripts/chart/scan_moves.py --selftest       離線驗算，不碰快取

【三件它刻意不做的事】
· **不挑題**：它只給表，哪一條值得畫是撰寫者的判斷。
· **不補資料**：快取沒有就跳過並列在 `missing`，不去抓。
· **不四捨五入掉樣本數**：每一列都帶 `n`，因為台股快取只回到 2024-09，
  它的分位與美股的分位分母不同 —— **兩個都叫「近三年分位」，但不是同一把尺**。
  2026-09-01 補：光有 `n` 不夠。表頭當時印的是「近 3 年分位」，
  而 `^TWII` 那一列其實只有 2.0 年 —— 這句話在上一行寫著，
  **卻只寫在寫程式的人看的地方，沒有寫在讀表的人看的地方**。
  現在表頭改印「要求近 N 年」，樣本起日與實際年數逐列標在行尾，
  短於要求的加 ★ 並在表尾列出（門檻 `SHORT_TOLERANCE_DAYS`）。
"""
from __future__ import annotations
import csv, datetime as dt, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _repo  # noqa: E402

REPO = _repo.repo()
SERIES = os.path.join(REPO, "data", "series")

# 預設掃描清單：跨資產各一條，全部在預抓核心清單內。
# **代理就是代理**：SOXQ／FEZ／CPER 是 ETF，不是指數或期貨本身，名稱裡直接寫出來，
# 免得表格被複製進判讀時混過去（anchors.proxies）。
DEFAULT = [
    ("GLD", "黃金 ETF"), ("XLE", "能源類股 ETF"), ("CPER", "銅 ETF"),
    ("FEZ", "歐洲 Stoxx50 ETF"), ("^TWII", "台灣加權"), ("SP500", "標普 500"),
    ("NIKKEI225", "日經 225"), ("SOXQ", "費半 ETF"), ("VIXCLS", "VIX"),
    ("DGS10", "10 年期殖利率"), ("BAMLH0A0HYM2", "高收益 OAS"),
]
# 這幾條是「水準本身就是利差或指數點」的序列，百分比變動會誤導（低基期放大），
# 所以改報絕對變動。**同一張表混用兩種單位比漏掉它們更糟，故獨立欄位標示。**
ABS_CHANGE = {"DGS10", "DGS2", "DGS30", "DTB3", "VIXCLS",
              "BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A3HYC", "BAMLH0A1HYBB"}


def load(sid: str):
    fn = os.path.join(SERIES, sid.replace("^", "_") + ".csv")
    d, v = [], []
    with open(fn, encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#") or row[0] == "date":
                continue
            try:
                val = float(row[1])
            except (ValueError, IndexError):
                continue
            d.append(row[0])
            v.append(val)
    return d, v


def pct_rank(hist: list, x: float) -> float:
    """x 在 hist 裡的分位（≤ x 的比率 ×100）。hist 空的就拋錯，不回 0。"""
    if not hist:
        raise ValueError("樣本為空——分位沒有意義，不要回 0")
    return 100.0 * sum(1 for a in hist if a <= x) / len(hist)


def changes(v: list, w: int, absolute: bool) -> list:
    """所有重疊的 w 期變動。absolute 為真時回絕對變動，否則回百分比。"""
    out = []
    for k in range(w, len(v)):
        if absolute:
            out.append(v[k] - v[k - w])
        elif v[k - w]:
            out.append(100.0 * (v[k] / v[k - w] - 1))
    return out


# 首筆比切點晚幾天之內**不算**樣本短。切點那天本來就常常不是觀測日
# （週末、國定假日、或那條序列剛好沒發布），而三年窗口裡差兩週是 0.4%，
# 不足以讓它變成「另一把尺」。**這個容差是 2026-09-01 當場逼出來的**：
# 第一版寫成 `since > cut` 逐字比，`BAMLH0A0HYM2` 首筆 2023-08-29、切點 2023-08-28，
# 差一天就被標成短樣本 —— 一條在資料正常時也會響的警示，跟沒有警示一樣。
# 台股農曆年可連休九天，加上前後週末約十一天，所以容差取 14。
SHORT_TOLERANCE_DAYS = 14


def _cut_date(last: str, years: int) -> "dt.date":
    """要求的切點。**2 月 29 日要退回 28 日**——回推三年會落在平年，
    直接用字串拼出 `2025-02-29` 再去 parse 會拋 ValueError，
    而這支每天都在跑，四年一次的例外不該由呼叫端來記得。"""
    x = dt.date.fromisoformat(last)
    try:
        return x.replace(year=x.year - years)
    except ValueError:
        return x.replace(year=x.year - years, day=28)


def sample_window(d: list, years: int) -> dict:
    """分位樣本從哪裡起算，以及**它有沒有短於要求**。

    回傳 `i`（起點索引）、`cut`（要求的切點）、`since`（實際起日）、
    `span_years`（實際跨幾年）、`short_by_days`（首筆比切點晚幾天）、
    `truncated`（短得足以構成另一把尺，門檻見 `SHORT_TOLERANCE_DAYS`）。

    **`truncated` 是這支唯一說得出「這一列跟別列不是同一把尺」的地方。**
    2026-09-01 的實例：文字輸出的表頭印「近 3 年分位」，而 `^TWII` 的快取
    只回到 2024-09-02、實際樣本 2.0 年。本檔開頭的 docstring 從第一版就寫著
    「兩個都叫『近三年分位』，但不是同一把尺」，`--json` 也逐列帶著 `since` ——
    **只有人在看的那個文字輸出把 `since` 丟掉了，只留 `n=`**，
    而 `n` 要先知道一年有幾個交易日才讀得出來。那一天是靠人工發現並繞開的，
    也就是靠賭的：**一個要靠讀者自己心算才發現的錯，就是一個每天都在賭的錯。**
    """
    cut = _cut_date(d[-1], years)
    cs = cut.isoformat()
    i = next((k for k, x in enumerate(d) if x >= cs), 0)
    since = dt.date.fromisoformat(d[i])
    span = (dt.date.fromisoformat(d[-1]) - since).days / 365.25
    short_by = (since - cut).days
    return {"i": i, "cut": cs, "since": d[i], "span_years": round(span, 1),
            "short_by_days": short_by,
            "truncated": short_by > SHORT_TOLERANCE_DAYS}


def scan_one(sid: str, name: str, windows: list, years: int) -> dict:
    d, v = load(sid)
    absolute = sid in ABS_CHANGE
    sw = sample_window(d, years)
    s = sw["i"]
    row = {"id": sid, "name": name, "last": d[-1], "value": v[-1],
           "unit": "abs" if absolute else "pct", "since": sw["since"],
           "span_years": sw["span_years"], "truncated": sw["truncated"],
           "cut": sw["cut"], "short_by_days": sw["short_by_days"], "w": {}}
    for w in windows:
        if len(v) <= w or len(d) <= s + w:
            continue
        cur = (v[-1] - v[-1 - w]) if absolute else 100.0 * (v[-1] / v[-1 - w] - 1)
        hist = changes(v[s:], w, absolute)
        row["w"][str(w)] = {"from": d[-1 - w], "change": round(cur, 4),
                            "pct_rank": round(pct_rank(hist, cur), 1), "n": len(hist)}
    return row


def run(ids: list, windows: list, years: int) -> dict:
    rows, missing = [], {}
    for sid, name in ids:
        try:
            rows.append(scan_one(sid, name, windows, years))
        except FileNotFoundError:
            missing[sid] = "快取裡沒有這條——預抓沒抓到或從未用過，**不代表沒有變動**"
        except Exception as e:
            missing[sid] = f"{type(e).__name__}: {e}"[:160]
    return {"years": years, "windows": windows, "rows": rows, "missing": missing}


def selftest() -> int:
    """離線驗算：分位與變動的定義各一組手算對照。"""
    ok = True
    v = [100.0, 101.0, 99.0, 103.0, 102.0]
    got = changes(v, 1, False)
    want = [1.0, -1.980198019801982, 4.040404040404042, -0.970873786407767]
    if any(abs(a - b) > 1e-9 for a, b in zip(got, want)) or len(got) != 4:
        print(f"✗ changes(pct): {got}")
        ok = False
    if changes(v, 1, True) != [1.0, -2.0, 4.0, -1.0]:
        print(f"✗ changes(abs): {changes(v, 1, True)}")
        ok = False
    if abs(pct_rank([1, 2, 3, 4], 3) - 75.0) > 1e-9:
        print("✗ pct_rank")
        ok = False
    try:
        pct_rank([], 1)
        print("✗ 空樣本沒有拋錯——那會安靜回一個看起來合理的分位")
        ok = False
    except ValueError:
        pass

    # 樣本窗口：四個案例，每一個對應 2026-09-01 那一輪踩到或差點踩到的一種形狀。
    # （1）快取夠長（美股 ETF）。
    long_cache = ["2021-06-11", "2023-08-30", "2023-08-31", "2025-01-02", "2026-08-31"]
    sw = sample_window(long_cache, 3)
    if sw["truncated"] or sw["since"] != "2023-08-31" or sw["cut"] != "2023-08-31":
        print(f"✗ sample_window(足夠長): {sw}")
        ok = False
    # （2）快取被自己的起始日截短（^TWII 只回到 2024-09）。
    short_cache = ["2024-09-02", "2025-06-02", "2026-08-31"]
    sw = sample_window(short_cache, 3)
    if not sw["truncated"] or sw["since"] != "2024-09-02" or sw["span_years"] != 2.0:
        print(f"✗ sample_window(被截短): {sw}")
        ok = False
    # （3）**假警報那一種**：首筆只比切點晚一天（切點不是觀測日）。
    # 第一版逐字比 `since > cut` 會把 BAMLH0A0HYM2 標成短樣本。
    sw = sample_window(["2023-09-01", "2025-01-02", "2026-08-31"], 3)
    if sw["truncated"] or sw["short_by_days"] != 1:
        print(f"✗ sample_window(晚一天不該算截短): {sw}")
        ok = False
    # （4）容差邊界：剛好等於容差不算，多一天才算。
    base = dt.date(2026, 8, 31)
    edge = (base.replace(year=2023) + dt.timedelta(days=SHORT_TOLERANCE_DAYS)).isoformat()
    over = (base.replace(year=2023) + dt.timedelta(days=SHORT_TOLERANCE_DAYS + 1)).isoformat()
    if sample_window([edge, "2026-08-31"], 3)["truncated"]:
        print("✗ sample_window(剛好等於容差不該算截短)")
        ok = False
    if not sample_window([over, "2026-08-31"], 3)["truncated"]:
        print("✗ sample_window(超過容差一天應算截短)")
        ok = False
    # （5）閏日：2 月 29 日回推三年落在平年，切點要退回 28 日而不是拋錯。
    if _cut_date("2028-02-29", 3).isoformat() != "2025-02-28":
        print(f"✗ _cut_date(閏日): {_cut_date('2028-02-29', 3)}")
        ok = False

    print("selftest 全部通過 ✓" if ok else "★ selftest 有錯")
    return 0 if ok else 1


def main(argv) -> int:
    if "--selftest" in argv:
        return selftest()
    years = int(_opt(argv, "--years", "3"))
    windows = [int(x) for x in _opt(argv, "--window", "1,5").split(",")]
    pick = _opt(argv, "--ids", "")
    ids = ([(x, x) for x in pick.split(",") if x] if pick else DEFAULT)
    res = run(ids, windows, years)
    if "--json" in argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    # **表頭寫「要求」，不寫「實際」。** 每一列的樣本各自標在該列尾端 ——
    # 舊版表頭直接斷言「近 N 年分位」，而那句話對快取較短的序列是假的。
    print(f"分位樣本：要求近 {years} 年，實際逐列標示｜視窗 {windows}｜快取：{SERIES}")
    for r in res["rows"]:
        unit = "" if r["unit"] == "pct" else "（絕對變動）"
        head = f"{r['name']:<14}{r['id']:<14} 末日 {r['last']} {r['value']:>10.4f}{unit}"
        cells = []
        for w in windows:
            x = r["w"].get(str(w))
            if x:
                sign = f"{x['change']:+.2f}" + ("%" if r["unit"] == "pct" else "")
                cells.append(f"{w}日 {sign:>9} 分位 {x['pct_rank']:>5.1f}(n={x['n']})")
        tail = f"  樣本 {r['since']} 起 {r['span_years']} 年"
        if r["truncated"]:
            tail = "  ★" + tail.strip()
        print(head + "  " + "  ".join(cells) + tail)
    short = [r for r in res["rows"] if r["truncated"]]
    if short:
        # **這一行是給複製表格的人看的。** 單看一列的 `n=` 讀不出樣本有多長，
        # 要先知道一年有幾個交易日；★ 與這一行把那個心算拿掉。
        print("★ " + "、".join(f"{r['name']}（{r['span_years']} 年，{r['since']} 起）"
                               for r in short)
              + f" 的快取短於要求的近 {years} 年 —— **它們的分位與其他列不是同一把尺**，"
                "引用時措辭要跟著限縮（anchors.history_limits），"
                "不可寫成「歷史上」或「近三年」。")
    for k, why in res["missing"].items():
        print(f"  ✗ {k}：{why}")
    return 0


def _opt(argv, key, default):
    return argv[argv.index(key) + 1] if key in argv and len(argv) > argv.index(key) + 1 else default


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
