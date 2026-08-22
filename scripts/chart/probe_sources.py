# -*- coding: utf-8 -*-
"""
probe_sources.py — 一次性探針：量「我們真正想畫卻拿不到的那幾條」在候選來源上拿不拿得到。

**這支不在每日路徑上。** 它不被 prefetch、render_day 或任何檢查呼叫，
跑完把結果登錄進 `chart/SOURCES.md` 之後，它的工作就結束了。

【為什麼是這份清單】
廣度不是抽象的：`data/series` 裡躺著 19 條非美標的與指數（三星、東京威力科創、
愛德萬、`^SOX`、`^KS11`、`^NDX`、`^RUT`、`^DJI`、`^STOXX50E`……），**全部凍在 2026-08-19**。
那些是**曾經畫得出來、現在畫不出來**的題目。WANT 就是從那裡挑出來的，
外加這一週實際被砍掉的兩個（櫃買指數、美元指數）。

【它刻意分成兩個問題，因為它們的性質不同】
1. `--sources`：候選來源（Stooq、Twelve Data）拿不拿得到這些序列。**不碰 Yahoo。**
2. `--yahoo-layer`：Yahoo 對這台機器的封鎖是 IP 層還是客戶端層。
   **跑這一項與規避是同一個動作** —— `anchors.rate_limits` 寫的是
   「429 是對方在說慢一點，等，不要繞；不可以換 host、改用瀏覽器規避」，
   而 yfinance 會先取 cookie 與 crumb、帶瀏覽器樣的標頭。
   **它通了就代表我們已經繞過一次**，要不要留著是下一個決定，不是這支腳本的決定。
   所以它預設不跑，要明確加旗標，而且結果只印出來、不寫進任何快取。

用法（在**有網路的那台機器**上跑，沙箱出口只通 pypi）：
    python3 ~/kb-core/scripts/chart/probe_sources.py --sources
    python3 ~/kb-core/scripts/chart/probe_sources.py --sources --json
    python3 ~/kb-core/scripts/chart/probe_sources.py --yahoo-layer
"""
from __future__ import annotations
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}

# 想要的序列 → 各來源的代號。**空字串代表「這個來源大概沒有」，仍然照打一次** ——
# 猜它沒有跟量到它沒有是兩件事，而前者會讓一個可用的來源被白白放棄。
WANT = [
    # (我們的代號, 說明, stooq, twelvedata)
    # **第一列是對照組，不是想要的序列。** 它是任何來源都一定有的標的：
    # 它也失敗 → 問題在端點或客戶端；只有它成功 → 那才是涵蓋率的問題。
    # 2026-08-22 第二輪十條全部回同一頁 HTML 而沒有對照組，
    # **於是「Stooq 沒有這些序列」與「Stooq 不理這個客戶端」在輸出上分不出來**。
    ("AAPL",       "【對照組】蘋果，任何來源都該有",       "aapl.us",  "AAPL"),
    ("^SOX",       "費城半導體指數（現用 SOXQ ETF 代理）", "^sox",    "SOX"),
    ("^TWOII",     "櫃買指數（Yahoo 落後 22 天，官方端點沒有）", "^tpex",  "TWOII"),
    ("DXY",        "美元指數（現用 DTWEXBGS，週頻發布）", "^dxy",    "DXY"),
    ("005930.KS",  "三星電子",                          "005930.kr", "005930.KS"),
    ("8035.T",     "東京威力科創",                       "8035.jp",  "8035.T"),
    ("6857.T",     "愛德萬測試",                         "6857.jp",  "6857.T"),
    ("^KS11",      "韓國綜合指數",                       "^kospi",   "KS11"),
    ("^STOXX50E",  "歐洲 Stoxx 50（現用 FEZ ETF 代理）",  "^stx50",   "STOXX50E"),
    ("HG=F",       "銅期貨（現用 CPER ETF 代理）",         "hg.f",     "HG"),
    ("^N225",      "日經 225（現用 FRED NIKKEI225，慢一天）", "^nkx",  "N225"),
]


def _get(url: str, timeout: int = 20) -> bytes:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def stooq(sym: str) -> dict:
    """Stooq 免金鑰 CSV。

    **它有三種「不是資料」的回法，而三種的處置不同**：空 body、一行 `No data`、
    以及**回一整頁 HTML／JavaScript**（機器人挑戰頁或改版）。
    2026-08-22 首次實測十條全部撞上第三種，而當時這裡只擋前兩種，
    於是 JS 被餵進 `float()`，錯誤訊息是 `could not convert string to float:
    'e.encode(c+n))'` —— **十條看起來像十條都沒有這個序列**。
    這與 SOURCES.md 那條「回空殼與被封鎖是兩件事，處置相反」是同一個坑：
    **把它讀成「來源沒有」，就會白白放棄一條可能可用的路。**

    所以先驗表頭：Stooq 的 CSV 第一行一定是 `Date,Open,High,Low,Close,Volume`。
    不是那一行就照實回報**它到底回了什麼**，不要猜。
    """
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(sym)}&i=d"
    raw = _get(url).decode("utf-8", "replace").strip()
    if not raw:
        raise RuntimeError("空 body —— 是被擋還是查無此代號，這裡分不出來")
    head = raw.splitlines()[0].strip()
    if not head.lower().startswith("date,"):
        # **回了網頁就把網頁的重點抄出來。** 2026-08-22 第二輪十條回的是同一頁 HTML，
        # 而錯誤訊息只印首行 `<!DOCTYPE html><html><head>...` —— 十條長得一模一樣，
        # 看不出它在說什麼。`<title>` 與 cookie／驗證字樣才分得出
        # 「要同意 cookie」「被判定為機器人」「這個代號不存在」是哪一種。
        low = raw[:4000].lower()
        title = ""
        if "<title" in low:
            t = low.index("<title")
            title = raw[t:t + 300].split(">", 1)[-1].split("<", 1)[0].strip()[:80]
        hints = [w for w in ("cookie", "captcha", "robot", "consent", "forbidden",
                             "not found", "brak danych", "no data") if w in low]
        raise RuntimeError(
            f"回的是網頁不是 CSV｜title={title or '（無）'}｜"
            f"線索={'、'.join(hints) or '（無）'}｜{len(raw)} bytes")
    if raw.lower().startswith("no data") or "\n" not in raw:
        raise RuntimeError(f"沒有資料列：{raw[:60]}")
    rows = [r.split(",") for r in raw.splitlines()[1:] if r]
    d = [r[0] for r in rows if len(r) > 4]
    v = [float(r[4]) for r in rows if len(r) > 4 and r[4] not in ("", "N/A")]
    if not v:
        raise RuntimeError("表頭對但沒有一列收盤價")
    return {"n": len(v), "last": d[-1] if d else "?", "first": d[0] if d else "?"}


def twelvedata(sym: str, key: str) -> dict:
    """Twelve Data。**先解析代號，再取序列。**

    它的代號格式跟我們的不一樣（我們寫 `005930.KS`／`8035.T`，它可能要
    `005930` ＋ `exchange=KRX`）。**猜錯格式的失敗與「沒有這條序列」在輸出上一模一樣** ——
    Stooq 那兩輪就是這樣白跑的。所以先問 `/symbol_search` 它認得什麼，
    把它自己給的代號拿去取序列，並把兩步的結果分開回報：
    找不到代號＝涵蓋率問題；找到了卻取不到＝方案權限或限流問題。**兩者處置不同。**
    """
    q = sym.split(".")[0].split(":")[0]
    js = json.loads(_get("https://api.twelvedata.com/symbol_search"
                         f"?symbol={urllib.parse.quote(q)}&outputsize=8").decode("utf-8"))
    cands = js.get("data") or []
    if not cands:
        raise RuntimeError(f"symbol_search 找不到「{q}」—— 這一條是涵蓋率問題")
    best = cands[0]
    got, exch = best.get("symbol"), best.get("exchange")
    url = ("https://api.twelvedata.com/time_series"
           f"?symbol={urllib.parse.quote(got)}&interval=1day&outputsize=30&apikey={key}")
    if exch:
        url += f"&exchange={urllib.parse.quote(exch)}"
    j = json.loads(_get(url).decode("utf-8"))
    if j.get("status") == "error":
        raise RuntimeError(f"找到 {got}@{exch}（{best.get('country')}）但取不到："
                           f"{str(j.get('message'))[:90]}")
    vals = j.get("values") or []
    if not vals:
        raise RuntimeError(f"找到 {got}@{exch} 但回傳沒有 values")
    return {"n": len(vals), "last": vals[0]["datetime"], "first": vals[-1]["datetime"],
            "resolved": f"{got}@{exch}"}


def _lag(last: str) -> str:
    try:
        return f"{(dt.date.today() - dt.date.fromisoformat(last[:10])).days} 天"
    except Exception:
        return "?"


def probe_sources(td_key: str | None, as_json: bool) -> int:
    out = []
    for ours, label, s_sym, t_sym in WANT:
        row = {"id": ours, "label": label, "stooq": None, "twelvedata": None}
        if s_sym:
            try:
                r = stooq(s_sym)
                row["stooq"] = {"symbol": s_sym, **r, "lag": _lag(r["last"])}
            except Exception as e:
                row["stooq"] = {"symbol": s_sym, "error": f"{type(e).__name__}: {e}"[:120]}
            time.sleep(1.0)                     # 逐標的間隔，比照既有取數層
        if t_sym and td_key:
            try:
                r = twelvedata(t_sym, td_key)
                row["twelvedata"] = {"symbol": t_sym, **r, "lag": _lag(r["last"])}
            except Exception as e:
                row["twelvedata"] = {"symbol": t_sym, "error": f"{type(e).__name__}: {e}"[:120]}
            time.sleep(8.0)                     # 免費方案每分鐘 8 次，這裡貼著走
        out.append(row)

    if as_json:
        print(json.dumps({"probed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                          "twelvedata_key": bool(td_key), "rows": out}, ensure_ascii=False, indent=1))
        return 0
    if not td_key:
        print("（沒有 TWELVEDATA_API_KEY，這一輪只量 Stooq —— **沒量到不等於它沒有**）\n")
    for r in out:
        print(f"{r['id']:<12} {r['label']}")
        for src in ("stooq", "twelvedata"):
            x = r[src]
            if x is None:
                print(f"    {src:<12} —（本輪未試）")
            elif "error" in x:
                print(f"    {src:<12} ✗ {x['symbol']:<12} {x['error']}")
            else:
                shown = x.get("resolved") or x["symbol"]
                print(f"    {src:<12} ✓ {shown:<14} {x['n']:>5} 點，末日 {x['last']}（落後 {x['lag']}）")
    got = sum(1 for r in out if (r["stooq"] and "error" not in r["stooq"])
              or (r["twelvedata"] and "error" not in r["twelvedata"]))
    print(f"\n{got}/{len(out)} 條至少有一個候選來源拿得到。"
          "\n**下一步是把結果登錄進 chart/SOURCES.md，連同限流與落後天數** —— "
          "沒登錄的實測，下一個人會再測一次。")
    return 0


def probe_yahoo_layer() -> int:
    """封鎖是 IP 層還是客戶端層。**跑它與規避是同一個動作**，見檔頭。"""
    print("★ 這一項會用瀏覽器樣的客戶端去敲 Yahoo。**它通了就代表已經繞過一次。**")
    print("  規則在 anchors.rate_limits：「不可以換 host、改用瀏覽器規避」。\n")
    sym = "^GSPC"
    print("[1/2] 現有客戶端（裸 urllib＋固定 UA，與 fetch.py 同一條路）")
    try:
        raw = _get("https://query1.finance.yahoo.com/v8/finance/chart/"
                   f"{urllib.parse.quote(sym)}?range=5d&interval=1d")
        j = json.loads(raw)
        n = len(((j.get("chart") or {}).get("result") or [{}])[0].get("timestamp") or [])
        print(f"      ✓ 通了，{n} 點 —— **封鎖已經解除**，這個實驗到此為止，不需要第 2 步")
        return 0
    except urllib.error.HTTPError as e:
        print(f"      ✗ HTTP {e.code}（第一個請求就這樣＝不是流量問題）")
    except Exception as e:
        print(f"      ✗ {type(e).__name__}: {str(e)[:100]}")

    print("[2/2] yfinance（會先取 cookie 與 crumb、帶瀏覽器樣標頭）")
    try:
        import yfinance as yf
    except ImportError:
        print("      —— 沒安裝。要量這一層就 `pip3 install yfinance`，"
              "**但先讀一次上面那兩行**")
        return 0
    try:
        df = yf.Ticker(sym).history(period="5d")
        if len(df):
            print(f"      ✓ 通了，{len(df)} 點，末日 {df.index[-1].date()}")
            print("\n判定：**客戶端層**。同一個 IP、同一個 host，換一隻手就通了。")
            print("      這代表 yfinance 能拿回廣度，也代表**留著它就是留著一次規避**。")
        else:
            print("      ✗ 回空表 —— 空不是「沒有資料」，多半也是被擋")
            print("\n判定：**IP 層**。換客戶端不會改變任何事，廣度要從別的來源拿。")
    except Exception as e:
        print(f"      ✗ {type(e).__name__}: {str(e)[:140]}")
        print("\n判定：**IP 層**（或 yfinance 自己壞了 —— 它每隔幾個月被 Yahoo 改壞一次，"
              "而它壞掉的樣子就是這種例外）。")
    return 0


def main(argv: list) -> int:
    import os
    if "--yahoo-layer" in argv:
        return probe_yahoo_layer()
    if "--sources" in argv:
        return probe_sources(os.environ.get("TWELVEDATA_API_KEY"), "--json" in argv)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
