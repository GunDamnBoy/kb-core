# -*- coding: utf-8 -*-
"""
fetch_tw_price.py — 台股日收盤序列，走證交所與櫃買的官方端點。

【為什麼要這支】
2026-08-14 Yahoo 的 v8 chart 端點對**第一個請求**就回 429（不是累積型限流，
等再久也不會好），台股個股與加權指數因此整批取不到。FRED 沒有台股。
證交所與櫃買本來就有免金鑰的官方端點，**這是走正門不是繞道**——
brief §3.1 一向偏好有文件的官方來源，Yahoo 那條反而是非文件化的。

【三個端點，都實測過】
  上市個股   TWSE  STOCK_DAY        逐月，date=YYYYMMDD
  加權指數   TWSE  MI_5MINS_HIST    逐月，date=YYYYMMDD
  上櫃個股   TPEx  tradingStock     逐月，date=YYYY/MM/DD（**必須帶斜線**）

【四個會咬人的地方】
1. **回傳是一整個月，不是單日。** 要一年的資料就得打 12 次，每次間隔一秒。
2. **日期是民國年**（`115/08/14` ＝ 2026-08-14），要自行 +1911。
3. **櫃買的成交量欄位名稱會隨年代改變**：近年是「成交張數」，2016 年是「成交仟股」。
   **必須讀回傳的 `flagField` 判斷單位，不能寫死欄位名或倍率**——這正是本 repo
   在融資餘額「仟元 vs 元」上踩過的同一類坑（差 1,000 倍而數字看起來都像個數字）。
4. **櫃買對資料中心 IP 節流很兇**（實測從機房 IP 約八成回空、從一般網路全通）。
   回空不是「沒有資料」，是被節流——本程式會重試並在最後誠實拋錯，不回空序列。

用法：
    python3 ~/kb-core/scripts/chart/fetch_tw_price.py 2330 --months 24
    python3 ~/kb-core/scripts/chart/fetch_tw_price.py TAIEX --months 12
    python3 ~/kb-core/scripts/chart/fetch_tw_price.py 8069.TWO --months 24
    python3 ~/kb-core/scripts/chart/fetch_tw_price.py --selftest
"""
from __future__ import annotations
import json, os, re, sys, time, urllib.request, datetime

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

TWSE_STOCK = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={ym}01&stockNo={code}&response=json"
TWSE_INDEX = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={ym}01&response=json"
TPEX_STOCK = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={code}&date={y}/{m}/01&response=json"


def _get(url: str, tries: int = 3, pause: float = 3.0) -> bytes:
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                body = r.read()
            if body.strip():
                return body
            # 櫃買被節流時回空 body 而不是錯誤碼。**空不是「沒資料」，是被擋。**
            last = "回傳空 body（多半是被節流）"
        except Exception as e:                       # noqa: BLE001
            last = e
        if i < tries - 1:
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"取數失敗 {url}：{last}")


def _roc_to_iso(s: str) -> str:
    """`115/08/14` → `2026-08-14`。**民國年轉換錯了不會報錯，只會讓整條序列偏 1911 年。**"""
    y, m, d = s.strip().split("/")
    return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"


def _num(s: str) -> float | None:
    s = str(s).replace(",", "").strip()
    if s in ("", "--", "---", "X", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _months_back(n: int) -> list:
    today = datetime.date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _twse_month(code: str | None, y: int, m: int) -> list:
    """回 [(iso_date, close), ...]；非交易月回空 list（那不是錯誤）。"""
    ym = f"{y:04d}{m:02d}"
    url = TWSE_INDEX.format(ym=ym) if code is None else TWSE_STOCK.format(ym=ym, code=code)
    doc = json.loads(_get(url).decode("utf-8"))
    if doc.get("stat") != "OK" or not doc.get("data"):
        return []
    fields = doc.get("fields", [])
    # 欄位位置不寫死：指數是「收盤指數」，個股是「收盤價」
    try:
        ci = next(i for i, f in enumerate(fields) if "收盤" in f)
    except StopIteration:
        raise RuntimeError(f"找不到收盤欄位，fields={fields}")
    out = []
    for row in doc["data"]:
        v = _num(row[ci])
        if v is not None:
            out.append((_roc_to_iso(row[0]), v))
    return out


def _tpex_month(code: str, y: int, m: int) -> list:
    doc = json.loads(_get(TPEX_STOCK.format(code=code, y=y, m=f"{m:02d}")).decode("utf-8"))
    tables = [t for t in (doc.get("tables") or []) if t.get("data")]
    if not tables:
        return []
    t = tables[0]
    fields = t.get("fields", [])
    try:
        ci = next(i for i, f in enumerate(fields) if "收盤" in f)
    except StopIteration:
        raise RuntimeError(f"找不到收盤欄位，fields={fields}")
    out = []
    for row in t["data"]:
        v = _num(row[ci])
        if v is not None:
            out.append((_roc_to_iso(row[0]), v))
    return out


def series(ident: str, months: int = 24) -> dict:
    """ident：`2330`／`2330.TW`／`TAIEX`／`^TWII`／`8069.TWO`。回傳與 fetch.get 相同的形狀。"""
    ident = ident.strip()
    if ident in ("TAIEX", "^TWII"):
        kind, code = "index", None
    elif ident.upper().endswith(".TWO"):
        kind, code = "tpex", ident.split(".")[0]
    else:
        kind, code = "twse", ident.split(".")[0]

    rows = []
    for y, m in _months_back(months):
        try:
            rows += _tpex_month(code, y, m) if kind == "tpex" else _twse_month(code, y, m)
        except RuntimeError as e:
            # 單月失敗不該讓整條序列消失，但**要讓呼叫端知道有洞**
            print(f"    ⚠ {ident} {y}-{m:02d} 取數失敗：{e}", file=sys.stderr)
        time.sleep(1.0)
    rows.sort(key=lambda r: r[0])
    seen, d, v = set(), [], []
    for a, b in rows:
        if a not in seen:
            seen.add(a); d.append(a); v.append(b)
    if not d:
        raise RuntimeError(f"{ident} 一筆都沒抓到——不要當成空序列使用")
    src = {"index": "TWSE 指數", "twse": "TWSE 個股", "tpex": "TPEx 個股"}[kind]
    return {"id": ident, "source": src, "d": d, "v": v}


def selftest() -> int:
    """對三個端點各抓一個月，核對形狀與量級。**跑得動不等於對，要看數字合不合理。**"""
    today = datetime.date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    rc = 0
    for label, fn in [("加權指數", lambda: _twse_month(None, y, m)),
                      ("2330 台積電", lambda: _twse_month("2330", y, m)),
                      ("8069 元太（櫃買）", lambda: _tpex_month("8069", y, m))]:
        try:
            rows = fn()
            if not rows:
                print(f"  ✗ {label}：{y}-{m:02d} 回空"); rc = 1; continue
            lo, hi = min(r[1] for r in rows), max(r[1] for r in rows)
            print(f"  ✓ {label}：{len(rows)} 個交易日，{rows[0][0]}～{rows[-1][0]}，"
                  f"收盤 {lo:,.2f}～{hi:,.2f}")
            if not rows[0][0].startswith(str(y)):
                print(f"    ✗ 日期年份是 {rows[0][0][:4]} 不是 {y}——民國年轉換有問題"); rc = 1
        except Exception as e:                       # noqa: BLE001
            print(f"  ✗ {label}：{type(e).__name__}: {e}"); rc = 1
    print("\n核對重點：")
    print("  · 加權指數應在四萬多點、台積電四位數、元太三位數以內——量級不對就是欄位取錯")
    print("  · 日期年份必須是西元且等於查詢月份，偏 1911 年代表民國年沒轉換")
    print("  · 櫃買回空多半是被節流不是沒資料，重跑看看")
    return rc


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        sys.exit(selftest())
    months = int(a[a.index("--months") + 1]) if "--months" in a else 24
    s = series(a[0], months)
    print(f"{s['id']} | {s['source']} | {len(s['d'])} 點 | {s['d'][0]} ~ {s['d'][-1]} | 末值 {s['v'][-1]:,.2f}")
