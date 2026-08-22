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
"""
from __future__ import annotations
import csv, json, os, sys

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


def scan_one(sid: str, name: str, windows: list, years: int) -> dict:
    d, v = load(sid)
    absolute = sid in ABS_CHANGE
    cut = f"{int(d[-1][:4]) - years}{d[-1][4:]}"
    s = next((k for k, x in enumerate(d) if x >= cut), 0)
    row = {"id": sid, "name": name, "last": d[-1], "value": v[-1],
           "unit": "abs" if absolute else "pct", "since": d[s], "w": {}}
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
    print(f"近 {years} 年分位｜視窗 {windows}｜快取：{SERIES}")
    for r in res["rows"]:
        unit = "" if r["unit"] == "pct" else "（絕對變動）"
        head = f"{r['name']:<14}{r['id']:<14} 末日 {r['last']} {r['value']:>10.4f}{unit}"
        cells = []
        for w in windows:
            x = r["w"].get(str(w))
            if x:
                sign = f"{x['change']:+.2f}" + ("%" if r["unit"] == "pct" else "")
                cells.append(f"{w}日 {sign:>9} 分位 {x['pct_rank']:>5.1f}(n={x['n']})")
        print(head + "  " + "  ".join(cells))
    for k, why in res["missing"].items():
        print(f"  ✗ {k}：{why}")
    return 0


def _opt(argv, key, default):
    return argv[argv.index(key) + 1] if key in argv and len(argv) > argv.index(key) + 1 else default


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
