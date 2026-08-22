# -*- coding: utf-8 -*-
"""
fetch.py — 取數層。

兩個來源就覆蓋了九成的題目：
  FRED   總經、利率、利差、信用、匯率、通膨預期
  Yahoo  指數、個股、期貨、匯率的日收盤價

用法：
    python3 ~/kb-core/scripts/chart/fetch.py DGS10 BAMLH0A0HYM2 '^GSPC' '^SOX' 'GC=F'
    python3 ~/kb-core/scripts/chart/fetch.py --since 2015-01-01 SP500
    python3 ~/kb-core/scripts/chart/fetch.py --check-key          # 檢查 FRED key 有沒有被讀到、能不能用

取回的序列會存進 data/series/<id>.csv 當快取，重跑同一天不會重複打外部站台。

──────────────────────────────────────────────────────────────
FRED 有兩條路，程式會自動選：

  A. 官方 API（api.stlouisfed.org）—— 有 key 時走這條
     文件化、有明確流量上限（120 req/min）、回傳 JSON，長期最穩。
  B. 繪圖端點（fredgraph.csv）—— 沒有 key 時的退路
     不需認證，但那是 FRED 的繪圖端點而非文件化 API，哪天改版就會斷。

**key 絕對不要寫進程式碼，也不要進版控。** 放這兩個地方之一即可：
     export FRED_API_KEY=xxxx          （寫進 ~/.zshrc）
     ~/.config/fred/api_key            （檔案內容就是 key 本身）

【注意：API key 不能解決 ICE BofA 的三年限制】
`BAMLxxx` 系列在 FRED 上只有近三年，那是資料授權政策（序列頁面明載
"Starting in April 2026, this series will only include 3 years of observations"），
不是技術限制。有 key 也一樣只有三年。分位數請一律標明「近三年」。

【備援：本機完全連不出去時】
改由瀏覽器同源 fetch，細節見 AGENT_BRIEF 第 3.3 節。
"""
from __future__ import annotations
import csv, io, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()
CACHE = os.path.join(REPO, "data", "series")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

_KEY_RE = re.compile(r"(api_key=)[0-9a-zA-Z]+")


def _redact(s) -> str:
    """任何要往外吐的字串都先過這裡。

    FRED 官方 API 只接受 query string 形式的 key，沒有 header 選項；
    因此錯誤訊息、log、例外裡都可能夾帶 key。所有對外輸出一律遮蔽。
    """
    return _KEY_RE.sub(r"\1***", str(s))


def fred_key():
    """依序找 key：環境變數 → ~/.config/fred/api_key → repo 內 .fred_key（已列入 .gitignore）。"""
    k = os.environ.get("FRED_API_KEY")
    if k and k.strip():
        return k.strip()
    for p in (os.path.expanduser("~/.config/fred/api_key"),
              os.path.join(REPO, ".fred_key")):
        try:
            if os.path.exists(p):
                v = open(p, encoding="utf-8").read().strip()
                if v:
                    return v
        except OSError:
            pass
    return None


def _get(url: str, tries: int = 3) -> bytes:
    """取數並重試。

    **429 要用完全不同的節奏退避。** 2026-08-05 實測：連續抓多個 Yahoo 標的後被限流，
    原本 1.5／3／4.5 秒的退避完全不夠，連打只會讓限流延長。429 屬於「照規矩等」的
    狀況，不是「換條路繞過去」的狀況——所以這裡是等更久，不是換端點。
    """
    last = None
    for k in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=30).read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                wait = 20 * (k + 1)          # 20s / 40s，最後一輪不再等
                if k < tries - 1:
                    print(f"  [限流] 對方回 429，等 {wait}s 再試（第 {k + 1}/{tries} 次）")
                    time.sleep(wait)
                continue
            time.sleep(1.5 * (k + 1))
        except Exception as e:
            last = e
            time.sleep(1.5 * (k + 1))
    hint = ""
    if isinstance(last, urllib.error.HTTPError) and last.code == 429:
        hint = ("\n  ★ 429 有兩種成因，處置相反（brief §3.2 1.5）："
                "\n    · 打了一陣子才 429 ＝ 累積型限流 → **等，不要繞**。"
                "\n    · 第一個請求就 429 ＝ 這個用戶端被擋 → 等再久也沒用，"
                "**改用有授權的其他供應商**（換供應商不是規避限流）。"
                "\n  Yahoo 對本機屬後者（2026-08-14 首測、08-16 複測，零流量下單一標的仍 429）。"
                "\n  替代對照見 brief §3.2：指數用 FRED 等價或 ETF 代理、美股走 Tiingo、台股走證交所。")
    raise RuntimeError(f"取數失敗 {_redact(url)}\n  {_redact(last)}{hint}")


# ────────────────────────────────────────────────── FRED
def fred_via_api(series_id: str, since: str, key: str) -> dict:
    url = ("https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={urllib.parse.quote(series_id)}"
           f"&api_key={key}&file_type=json&observation_start={since}")
    j = json.loads(_get(url))
    d, v = [], []
    for o in j.get("observations", []):
        if o["value"] not in ("", "."):
            d.append(o["date"]); v.append(float(o["value"]))
    if not d:
        raise RuntimeError(f"{series_id}：FRED API 回傳 0 筆")
    return {"id": series_id, "source": "FRED (api)", "d": d, "v": v}


def fred_via_graph(series_id: str, since: str) -> dict:
    """繪圖端點。一次只能一條——多條會被打包成 zip。"""
    url = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
           f"?id={urllib.parse.quote(series_id)}&cosd={since}")
    raw = _get(url)
    if raw[:2] == b"PK":
        raise RuntimeError(f"{series_id}：FRED 回傳 zip，代表一次請求了多條序列")
    d, v = [], []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        date = row.get("observation_date") or row.get("DATE")
        val = row.get(series_id)
        if date and val not in (None, "", "."):
            d.append(date); v.append(float(val))
    if not d:
        raise RuntimeError(f"{series_id}：FRED 回傳 0 筆")
    return {"id": series_id, "source": "FRED (graph)", "d": d, "v": v}


class NotFredSeries(RuntimeError):
    """FRED 明確表示「沒有這個序列代號」。**與「連不上」是兩回事，處置也不同。**"""


def fred(series_id: str, since: str = "2015-01-01") -> dict:
    """有 key 走官方 API；**連不上**才退回繪圖端點。兩條路都斷才拋錯。

    **400 是「查無此序列」，不是「連不上」，不該退回繪圖端點。**
    2026-08-14 實測踩到：`SOXQ`／`FEZ` 是美股 ETF 不是 FRED 序列，API 回 400，
    但這裡把 400 也當成「API 失敗」而去打 fredgraph，fredgraph 再逾時 30 秒，
    最後拋出來的是逾時錯誤——**外層負責「400 就改試 Tiingo」的判斷因此完全認不出來**，
    只看到一個逾時。**回退機制把原始錯誤變形，外層就失去了判斷依據。**
    現在 400 直接拋 `NotFredSeries`，讓呼叫端知道「這代號不屬於 FRED」。
    """
    key = fred_key()
    if key:
        try:
            return fred_via_api(series_id, since, key)
        except Exception as e:
            if "400" in str(e) or "Bad Request" in str(e):
                raise NotFredSeries(f"{series_id} 不是 FRED 序列代號") from None
            print(f"  [fred] API 失敗，退回繪圖端點：{_redact(e)}")
    return fred_via_graph(series_id, since)


# ────────────────────────────────────────────────── Yahoo
_ANCHORS = None


def anchors() -> dict:
    """門檻的家是 `kb-core/chart/anchors.json`，不是這支程式。

    **讀不到就大聲失敗**：允許清單取不到時若安靜回空集合，
    握手那條路會整條變成「沒有人在清單裡」，而症狀是取數靜靜少幾條。
    """
    global _ANCHORS
    if _ANCHORS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "chart", "anchors.json")
        with open(os.path.abspath(p), encoding="utf-8") as f:
            _ANCHORS = json.load(f)
    return _ANCHORS


def handshake_allowlist() -> dict:
    return (anchors().get("rate_limits") or {}).get("handshake_allowlist") or {}


def yahoo_handshake(symbol: str) -> dict:
    """做完 cookie／crumb 握手再取 Yahoo 日線。**只走允許清單上的代號。**

    2026-08-22 實測：同一台機器、同一個 IP、相隔幾秒 —— 裸 urllib＋固定 UA
    第一個請求就 429，做完握手的客戶端拿得到 `^GSPC`（5 點，末日 08-21）。
    **封鎖是客戶端層，不是機器。**

    這條路與 `anchors.rate_limits` 的「等，不要繞」**不衝突，因為它處理的不是同一件事**：
    限流退避處理的是「對方叫我們慢一點」，握手處理的是「對方要求先完成認證流程」。
    兩者的界線寫在 `rate_limits.handshake_vs_evasion`，**而那條界線有一半沒有量到**
    （Yahoo 是針對我們，還是對所有無 cookie 的客戶端一律 429），去改它之前先讀那一段。

    **失敗要大聲。** yfinance 每隔幾個月被 Yahoo 改壞一次，而它壞掉的樣子是回空表；
    這裡把空表當失敗拋出去，讓預抓記成 `failed` —— **靜靜少幾條與今天的 skipped 長得一樣。**
    """
    if symbol not in handshake_allowlist():
        raise RuntimeError(
            f"{symbol} 不在 anchors.rate_limits.handshake_allowlist 裡 —— "
            "**握手不是通用退路**，要用就先把它連同理由寫進允許清單")
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError(f"{symbol} 需要握手客戶端，但沒有安裝 yfinance：{e}") from e
    df = yf.Ticker(symbol).history(period="10y", auto_adjust=False)
    if df is None or not len(df):
        raise RuntimeError(f"{symbol}：握手客戶端回空表 —— **空不是「沒有資料」**，"
                           "多半是 yfinance 又被改壞或該代號不存在")
    d = [x.strftime("%Y-%m-%d") for x in df.index]
    v = [round(float(x), 4) for x in df["Close"].tolist()]
    keep = [(a, b) for a, b in zip(d, v) if b == b]          # 濾掉 NaN
    return {"id": symbol, "source": "Yahoo Finance（握手客戶端 yfinance）",
            "d": [a for a, _ in keep], "v": [b for _, b in keep]}


def yahoo(symbol: str, rng: str = "5y") -> dict:
    """指數用 ^GSPC / ^SOX / ^TWII，期貨用 GC=F / BZ=F，匯率用 JPY=X。"""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range={rng}&interval=1d")
    j = json.loads(_get(url))
    if j.get("chart", {}).get("error"):
        raise RuntimeError(f"{symbol}：{j['chart']['error']}")
    r = j["chart"]["result"][0]
    ts, close = r["timestamp"], r["indicators"]["quote"][0]["close"]
    d, v = [], []
    for i, t in enumerate(ts):
        if close[i] is not None:
            d.append(time.strftime("%Y-%m-%d", time.gmtime(t)))
            v.append(round(float(close[i]), 4))
    return {"id": symbol, "source": "Yahoo Finance",
            "currency": r["meta"].get("currency"), "d": d, "v": v}


# ────────────────────────────────────────────────── 對外
def tiingo_key():
    """Tiingo 的 key，比照 FRED：環境變數或 ~/.config/tiingo/api_key，**不進版控**。"""
    k = os.environ.get("TIINGO_API_KEY", "").strip()
    if k:
        return k
    p = os.path.expanduser("~/.config/tiingo/api_key")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    return ""


# 沒有免費來源提供費城半導體指數本身（指數授權限制，不是技術問題）。
# SOXQ 直接追蹤 PHLX Semiconductor Sector Index，是最貼近的代理；
# **但它是 ETF 不是指數**——用了就要在 note 寫明，比照既有的 XLE 註記。
# **這張表是給人看的，不是給取數層自動替換用的。** 要用代理就在 series_spec
# 直接寫 ETF 代號，並依 §3.2 在 note 標明「ETF 非指數」——替換必須是有意識的決定。
# 已知在本機不可用的來源代號。**這不是「暫時失敗」，是複測確認過的封鎖**：
# 2026-08-14 首測 13 條全 429，08-16 複測單一標的、零流量、仍第一個請求就 429。
# 預抓不再每天對它們白試（見 prefetch.CANARY 的例外），但**保留在這裡而不是刪掉**——
# 哪天恢復了要看得出來，而且讀程式的人需要知道為什麼這些代號從清單裡消失。
BLOCKED = {
    "^GSPC": "SP500", "^VIX": "VIXCLS", "^IXIC": "NASDAQCOM",
    "^TNX": "DGS10", "^TYX": "DGS30", "^IRX": "DTB3",
    "JPY=X": "DEXJPUS", "^N225": "NIKKEI225", "BZ=F": "DCOILBRENTEU",
    "^SOX": "SOXQ（ETF 代理）", "^STOXX50E": "FEZ（ETF 代理）", "HG=F": "CPER（ETF 代理）",
}

PROXY = {"^SOX": ("SOXQ", "SOXQ ETF（追蹤 PHLX 半導體指數；ETF 非指數本身）"),
         "^STOXX50E": ("FEZ", "FEZ ETF（追蹤歐洲 Stoxx 50；ETF 非指數本身）"),
         "HG=F": ("CPER", "CPER ETF（追蹤銅期貨；ETF 非期貨本身，有轉倉成本）")}


def tiingo(symbol: str, since: str = "2015-01-01") -> dict:
    """美股個股與 ETF 日線。**有文件、有認證的來源**，優於非文件化的 Yahoo 端點。

    免費方案實測上限：每日 1,000 次、每小時 50 次，歷史 30 年以上。
    """
    key = tiingo_key()
    if not key:
        raise RuntimeError("找不到 Tiingo API key（TIINGO_API_KEY 或 ~/.config/tiingo/api_key）")
    url = (f"https://api.tiingo.com/tiingo/daily/{urllib.parse.quote(symbol)}/prices"
           f"?startDate={since}&token={key}")
    rows = json.loads(_get(url).decode("utf-8"))
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"Tiingo 回傳空資料：{symbol}")
    d, v = [], []
    for r in rows:
        # adjClose 已還原除權息，跨期比較要用它；close 是原始收盤
        c = r.get("adjClose", r.get("close"))
        if c is not None:
            d.append(str(r["date"])[:10]); v.append(float(c))
    return {"id": symbol, "source": "Tiingo", "d": d, "v": v}


def _cached_source(path: str) -> str | None:
    """從快取檔頭讀出上次是從哪裡抓到的。

    檔頭長這樣：`# GLD | Yahoo (browser) | fetched 2026-08-13`
    **這一行本來就存在，只是從來沒被拿來當路由用。** 它比任何字串啟發式都可靠，
    因為它記的是「實際成功過」的來源，不是猜的。
    """
    try:
        with open(path, encoding="utf-8") as f:
            head = f.readline()
    except OSError:
        return None
    if not head.startswith("#"):
        return None
    parts = [p.strip() for p in head.lstrip("#").split("|")]
    if len(parts) < 2:
        return None
    src = parts[1].lower()
    if "yahoo" in src:
        return "yahoo"
    if "fred" in src:
        return "fred"
    if "tiingo" in src:
        return "tiingo"
    if "twse" in src or "tpex" in src:
        return "tw"
    return None


def _guess_source(ident: str) -> str:
    """沒有快取可參考時的猜測。

    FRED 的序列代號是純大寫英數（DGS10、BAMLH0A0HYM2、CPIAUCSL），
    **不含 `.`、`^`、`=`，也沒有小寫**。所以：
      有 `^` `=` `.` 或小寫  → Yahoo
      其餘                 → FRED

    2026-08-14 修正：原本漏了 `.`，使 `2330.TW`／`8069.TWO` 被送去 FRED。
    **仍有無法分辨的一類**：`GLD`、`XLE`、`MU`、`STX` 這種純大寫的美股代號，
    長得與 FRED 序列代號一模一樣。那一類靠快取檔頭路由，或由下面的 400 回退接住。
    """
    if ident in ("^TWII", "TAIEX") or ident.upper().endswith((".TW", ".TWO")):
        return "tw"
    return "yahoo" if (any(c in ident for c in "^=.") or ident != ident.upper()) else "fred"


def _ambiguous(ident: str) -> bool:
    """這個代號分不分得出來源？

    **純大寫英數、無標點的代號是唯一分不出來的一類**：`GLD`（美股 ETF）與
    `DGS10`（FRED 序列）長得一模一樣。只有這一類才需要靠快取檔頭拆解。

    其餘代號的樣式本身就明確（`.TW`、`^`、`=`、小寫），**樣式要優先於檔頭**——
    檔頭記的是「過去從哪抓到的」，而換來源的時候，過去正是我們要離開的東西。
    2026-08-14 踩到：台股快取檔頭都寫 Yahoo（先前用瀏覽器抓的），
    差點讓新接的證交所官方端點完全不會被走到。
    """
    return ident.isalnum() and ident == ident.upper()


def route_of(ident: str) -> str:
    """這個代號會走哪個來源。**單一實作**——prefetch 與診斷都用它，
    不要各自重算一份，否則兩邊對同一個代號的判斷會漂移。"""
    safe = ident.replace("^", "_").replace("=", "-").replace("/", "-")
    path = os.path.join(CACHE, f"{safe}.csv")
    src = (_cached_source(path) or _guess_source(ident)) if _ambiguous(ident) \
        else _guess_source(ident)
    # 判定為 Yahoo 的**美股個股與 ETF**（沒有 `^` 也沒有 `=`），若有 Tiingo key 就走 Tiingo。
    # 理由不是「Yahoo 現在不通」，而是 §3.1 的既有偏好：**有文件、有認證的來源優先**。
    # 指數（`^...`）與期貨／匯率（`...=...`）Tiingo 沒有，維持 Yahoo。
    #
    # 2026-08-14 踩到：`GLD`／`XLE`／`MU`／`STX` 原本判為 yahoo，而 prefetch 的熔斷
    # **在呼叫之前就攔截**，於是 `_route_and_fetch` 裡的 Tiingo 回退永遠到不了。
    # **回退路徑若只存在於例外處理裡，任何提前中止的機制都會讓它形同不存在。**
    if src == "yahoo" and not any(c in ident for c in "^=") and tiingo_key():
        return "tiingo"
    return src


def _route_and_fetch(ident: str, since: str, path: str) -> dict:
    """決定來源並取數；FRED 說「查無此序列」時改試 Yahoo。

    **FRED 回 400 代表代號不是它的，不是認證問題**——原本會退回 fredgraph 繪圖端點，
    在發布機上那條又是不通的，於是每條白等 30 秒逾時才失敗。
    2026-08-14 實測：9 條 Yahoo 代號因此各耗 30 秒且全部失敗。
    """
    src = route_of(ident)

    # 允許清單上的代號走握手客戶端。**它排在所有路由之前**，因為那幾條的處境就是
    # 「裸客戶端一定 429」——先跑一次路由再回退，等於每條白等一次限流退避。
    if ident in handshake_allowlist():
        return yahoo_handshake(ident)

    if src == "tw":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import fetch_tw_price as TW
        return TW.series(ident)

    if src == "tiingo":
        return tiingo(ident, since)

    if src == "yahoo":
        # **不做靜默的代理替換。** 曾經寫成「`^SOX` 取不到就改抓 `SOXQ`」，
        # 但那會把 ETF 的資料寫進 `^SOX` 的快取檔，圖上標的是指數、數字卻是 ETF——
        # **正是 brief §3.2 要求「用代理必須在 note 標明」所要防的事。**
        # 代理要換就在 series_spec 明寫 `SOXQ`，由判讀負責說明，不由取數層偷偷決定。
        return yahoo(ident)

    try:
        return fred(ident, since)
    except NotFredSeries:
        # 純大寫代號分不出是 FRED 序列還是美股代號（`GLD` 與 `DGS10` 長得一樣），
        # 所以第一次用一定會先白打一次 FRED。**抓到之後快取檔頭就記住來源，不會再繞。**
        if tiingo_key() and not any(c in ident for c in "^="):
            return tiingo(ident, since)         # 有文件、有認證的優先
        return yahoo(ident)


def get(ident: str, since: str = "2015-01-01", use_cache: bool = True) -> dict:
    """自動判斷來源。路由優先序：快取檔頭記錄的來源 → 字串啟發式 → FRED 400 時回退 Yahoo。"""
    os.makedirs(CACHE, exist_ok=True)
    safe = ident.replace("^", "_").replace("=", "-").replace("/", "-")
    path = os.path.join(CACHE, f"{safe}.csv")
    today = time.strftime("%Y-%m-%d")
    if use_cache and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            head = f.readline().strip()
        if head.startswith("#") and today in head:
            d, v = [], []
            with open(path, encoding="utf-8") as f:
                next(f); next(f)
                for line in f:
                    a, b = line.strip().split(",")
                    d.append(a); v.append(float(b))
            return {"id": ident, "source": "cache", "d": d, "v": v}

    s = _route_and_fetch(ident, since, path)

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {ident} | {s['source']} | fetched {today}\n")
        f.write("date,value\n")
        for a, b in zip(s["d"], s["v"]):
            f.write(f"{a},{b}\n")
    return s


def rebase(s: dict, base_date: str = None) -> dict:
    """把序列改成「基期 = 100」。跨市場比較強弱時一律用這個，不要比絕對點數。"""
    i = 0
    if base_date:
        i = next((k for k, d in enumerate(s["d"]) if d >= base_date), 0)
    b = s["v"][i]
    return {**s, "d": s["d"][i:], "v": [round(x / b * 100, 2) for x in s["v"][i:]]}


def align(*series: dict) -> tuple:
    """取多條序列的交集日期，回傳 (dates, [values...])。跨市場（台美）務必先對齊再計算。"""
    common = set(series[0]["d"])
    for s in series[1:]:
        common &= set(s["d"])
    dates = sorted(common)
    return dates, [[dict(zip(s["d"], s["v"]))[d] for d in dates] for s in series]


def check_key() -> int:
    """自我檢查：key 讀不讀得到、能不能用、拿不拿得到比繪圖端點更長的歷史。"""
    key = fred_key()
    if not key:
        print("✗ 找不到 FRED API key。請設定其中之一：")
        print("    export FRED_API_KEY=你的key        （寫進 ~/.zshrc 後開新視窗）")
        print("    echo 你的key > ~/.config/fred/api_key")
        return 1
    print(f"✓ 讀到 key（{len(key)} 字元，開頭 {key[:4]}…，不顯示全文）")
    try:
        a = fred_via_api("DGS10", "1962-01-01", key)
        print(f"✓ 官方 API 可用：DGS10 取得 {len(a['d'])} 筆，{a['d'][0]} → {a['d'][-1]}")
    except Exception as e:
        print(f"✗ 官方 API 失敗：{_redact(e)}")
        return 1
    try:
        b = fred_via_graph("DGS10", "1962-01-01")
        print(f"  對照繪圖端點：{len(b['d'])} 筆，{b['d'][0]} → {b['d'][-1]}")
        print(f"  → API 多拿到 {len(a['d']) - len(b['d'])} 筆")
    except Exception as e:
        print(f"  繪圖端點失敗（不影響，API 已可用）：{_redact(e)}")
    try:
        h = fred_via_api("BAMLH0A0HYM2", "1996-01-01", key)
        yrs = int(h["d"][-1][:4]) - int(h["d"][0][:4])
        print(f"  ICE BofA 高收益 OAS：{len(h['d'])} 筆，{h['d'][0]} → {h['d'][-1]}")
        print("  → 仍受三年授權限制，分位數請標明「近三年」" if yrs <= 4
              else "  → ★ 取得長於三年的歷史，請更新 AGENT_BRIEF 第 3.2 節與 MAINTENANCE")
    except Exception as e:
        print(f"  ICE BofA 檢查略過：{_redact(e)}")
    return 0


if __name__ == "__main__":
    if "--check-tiingo" in sys.argv:
        k = tiingo_key()
        print(f"Tiingo key：{'找到，' + str(len(k)) + ' 字元，前四碼 ' + k[:4] if k else '找不到'}")
        if k:
            try:
                s_ = tiingo("SPY", "2026-08-01")
                print(f"  實測 SPY：{len(s_['d'])} 點，末日 {s_['d'][-1]}，末值 {s_['v'][-1]:,.2f}")
            except Exception as e:                    # noqa: BLE001
                print(f"  ✗ 實測失敗：{_redact(e)}")
                sys.exit(1)
        sys.exit(0 if k else 1)
    if "--check-key" in sys.argv:
        sys.exit(check_key())
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    since = "2015-01-01"
    if "--since" in sys.argv:
        since = sys.argv[sys.argv.index("--since") + 1]
        args = [a for a in args if a != since]
    print(f"FRED 取數路徑：{'官方 API（已讀到 key）' if fred_key() else '繪圖端點（未設定 key）'}")
    # 連續打同一個站台是招來 429 的主因（2026-08-05 實測）。標的之間隔一下，
    # 五個標的也才多花 4 秒，遠比被限流之後整輪重跑划算。快取命中則不必等。
    for n, ident in enumerate(args):
        if n:
            time.sleep(1.0)
        try:
            s = get(ident, since=since)
            print(f"OK   {ident:<16} {len(s['d']):>5} 筆  {s['d'][0]} → {s['d'][-1]}  最新 {s['v'][-1]}")
        except Exception as e:
            print(f"FAIL {ident:<16} {_redact(e)}")
