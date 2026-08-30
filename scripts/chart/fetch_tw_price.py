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


def _months_since(iso_date: str, cap: int) -> list:
    """從 `iso_date` 所在的那個月一路到本月，最多 `cap` 個月。

    **含 `iso_date` 自己那個月**，不是從下個月開始 —— 證交所當月的資料每天都在長，
    而且會補前幾天的更正，只抓下個月起會漏掉末日那天之後、月底之前的那幾筆。
    """
    try:
        y, m = int(iso_date[:4]), int(iso_date[5:7])
    except (ValueError, IndexError):
        return []
    today = datetime.date.today()
    out = []
    while (y, m) <= (today.year, today.month):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out[-cap:] if cap and len(out) > cap else out


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


def series(ident: str, months: int = 24, have_through: str = "") -> dict:
    """ident：`2330`／`2330.TW`／`TAIEX`／`^TWII`／`8069.TWO`。回傳與 fetch.get 相同的形狀。

    ## 增量取數（2026-08-30 加）

    `have_through` 給了快取的末日，就只補**那個月起**到本月，而不是每天重下 24 個月。

    **為什麼要改**：2026-08-30 量到六個台股代號（`^TWII`、`2330`、`2317`、`2344`、
    `2382`、`2408`）× 24 個月 ＝ **每天 144 次證交所請求**，而
    `anchors.rate_limits` 只訂了「每次間隔 1 秒」，沒有訂總量、也沒有對
    `stat != "OK"` 退避。當天壞掉的正是抓取順序的**最後兩個**，而且嚴重度隨順序遞增：
    `2382` 只有尾端兩個月回空（安靜，序列變短），`2408` 24 個月全空（`series()` 拋錯，大聲）。
    前四個完好。**那是累積節流的形狀，不是代號的形狀。**
    增量之後同樣六條約 6–8 次請求。

    **退回全量是刻意的預設**：增量一筆都沒拿到時（可能是節流、也可能是快取末日
    落在一段長假裡）就整個重抓，寧可慢也不要回一份殘缺的。
    呼叫端 `fetch.get()` 另外還有「只能長不能縮」的合併守衛，所以最壞情況是白跑一趟，
    **不會把快取弄短**。
    """
    ident = ident.strip()
    if ident in ("TAIEX", "^TWII"):
        kind, code = "index", None
    elif ident.upper().endswith(".TWO"):
        kind, code = "tpex", ident.split(".")[0]
    else:
        kind, code = "twse", ident.split(".")[0]

    def pull(ms: list) -> list:
        out = []
        for y, m in ms:
            try:
                out += _tpex_month(code, y, m) if kind == "tpex" else _twse_month(code, y, m)
            except RuntimeError as e:
                # 單月失敗不該讓整條序列消失，但**要讓呼叫端知道有洞**
                print(f"    ⚠ {ident} {y}-{m:02d} 取數失敗：{e}", file=sys.stderr)
            time.sleep(1.0)
        return out

    incremental = _months_since(have_through, months) if have_through else []
    rows = pull(incremental) if incremental else []
    if not rows:
        if incremental:
            print(f"    ⚠ {ident} 增量（{incremental[0][0]}-{incremental[0][1]:02d} 起 "
                  f"{len(incremental)} 個月）一筆都沒拿到，退回全量重建 {months} 個月",
                  file=sys.stderr)
        rows = pull(_months_back(months))
    rows.sort(key=lambda r: r[0])
    seen, d, v = set(), [], []
    for a, b in rows:
        if a not in seen:
            seen.add(a); d.append(a); v.append(b)
    if not d:
        raise RuntimeError(f"{ident} 一筆都沒抓到——不要當成空序列使用")
    src = {"index": "TWSE 指數", "twse": "TWSE 個股", "tpex": "TPEx 個股"}[kind]
    return {"id": ident, "source": src, "d": d, "v": v}


def selftest_offline() -> int:
    """月份窗口的純邏輯自檢 —— **不連外**，所以沙箱裡也驗得了。

    增量取數的錯法是安靜的（少抓一個月＝快取少一段，而數字看起來都正常），
    所以窗口計算要有自己的回歸案例，不能只靠「跑得動」。
    """
    today = datetime.date.today()
    rc = 0

    def eq(label, got, want):
        nonlocal rc
        if got != want:
            print(f"  ✗ {label}：得到 {got}，預期 {want}"); rc = 1
        else:
            print(f"  ✓ {label}")

    # 1. 含末日那一個月，不是從下個月開始 —— 漏掉它會少掉月中那幾筆
    eq("_months_since 含末日當月",
       _months_since(f"{today.year}-{today.month:02d}-15", 24), [(today.year, today.month)])
    # 2. 跨年
    eq("_months_since 跨年", _months_since("2025-11-20", 24)[:3],
       [(2025, 11), (2025, 12), (2026, 1)])
    # 3. 一路數到本月為止，不會多數到未來
    ms = _months_since("2026-06-30", 24)
    eq("_months_since 末項是本月", ms[-1], (today.year, today.month))
    # 4. cap 生效（快取末日很舊時不要一次拉一百個月）
    eq("_months_since 受 cap 限制", len(_months_since("2020-01-01", 6)), 6)
    # 5. 壞字串回空 list → 呼叫端會走全量那條，不會拋
    eq("_months_since 壞輸入回空", _months_since("not-a-date", 24), [])
    eq("_months_since 空字串回空", _months_since("", 24), [])
    # 6. 全量窗口沒被動到
    eq("_months_back 仍是舊→新且末項為本月",
       (_months_back(3)[-1], len(_months_back(3))), ((today.year, today.month), 3))
    # 7. 增量真的比全量省：末日在本月時只剩 1 個月
    eq("增量請求數 << 全量",
       (len(_months_since(today.isoformat(), 24)), len(_months_back(24))), (1, 24))
    print("  離線邏輯自檢：" + ("全部通過" if rc == 0 else "★ 有錯"))
    return rc


def selftest() -> int:
    """對三個端點各抓一個月，核對形狀與量級。**跑得動不等於對，要看數字合不合理。**"""
    rc0 = selftest_offline()
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
    return rc or rc0


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest-offline" in a:            # 不連外，沙箱裡驗得了
        sys.exit(selftest_offline())
    if not a or a[0] == "--selftest":
        sys.exit(selftest())
    months = int(a[a.index("--months") + 1]) if "--months" in a else 24
    have = a[a.index("--have-through") + 1] if "--have-through" in a else ""
    s = series(a[0], months, have)
    print(f"{s['id']} | {s['source']} | {len(s['d'])} 點 | {s['d'][0]} ~ {s['d'][-1]} | 末值 {s['v'][-1]:,.2f}")
