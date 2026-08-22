#!/usr/bin/env python3
"""台股籌碼三項的探測與回測。**要在有網路的機器上跑**（Mac 或 GitHub Actions）。

用法：
    python3 tw_probe.py --fetch          # 抓資料，會快取，可中斷續跑
    python3 tw_probe.py --analyze        # 只跑分析（用快取）
    python3 tw_probe.py --fetch --analyze

## 這支要回答什麼

第一階段回測（`sentiment/BACKTEST-01.md`）驗掉的是**價格與波動**那一族——
動能、VIX、已實現波動，以及 CNN F&G 自己的七項。全族都沒有可用的前瞻資訊。

**台股籌碼是唯一還沒被測、而且有理由不一樣的東西**：它量的是**部位**不是價格，
與已驗掉的那一族正交。而且它是**日頻**的——美國同類資料（COT 週頻＋3 日延遲、
ICI 週頻＋5 日延遲）做不到。

如果這一族也沒有訊號，就照設計書第十節辦：不要發布合成分數。

## 硬規矩

- **這支只抓與寫快取，不碰 git、不刪任何東西。**
- 每項獨立快取、獨立失敗：一個端點壞掉不會拖垮其他項（沿用既有系統的慣例）。
- **欄位照名字找，不寫死索引**——來源改欄序時，寫死索引會安靜地拿錯數字。
- 抓不到就空著，**永不插補**。
"""
from __future__ import annotations
import argparse, csv, io, json, os, sys, time
import datetime as dt
import urllib.request, urllib.parse, urllib.error

CACHE = os.path.expanduser(os.environ.get("SENT_CACHE", "~/broker-research/../sent-cache"))
CACHE = os.path.abspath(CACHE)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
START = dt.date(2014, 1, 1)      # 當沖統計自民國 103 年（2014）起
TODAY = dt.date.today()


THROTTLE = {"gap": float(os.environ.get("SENT_GAP", "3.0"))}   # 每次請求之間的基本間隔


def get(url, referer=None, data=None, timeout=45, tries=3):
    """**限流（HTTP 428）跟一般錯誤要分開處理。**

    2026-08-22 踩過：TWSE 對逐日抓取回 428，而舊版把它當成一般失敗、
    重試三次還加退避 —— **被擋的時候反而送出三倍請求**，吞吐直接垮，
    三分鐘連存檔門檻都沒摸到，畫面上看起來只是「還在跑」。

    428／429／403 一律視為限流：長冷卻（30／60／90 秒）並**把基本間隔調大**，
    調大之後不再調回去——退讓要是單向的，不然會一直撞同一道牆。
    """
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data)
            req.add_header("User-Agent", UA)
            req.add_header("Accept", "application/json,text/plain,*/*")
            if referer: req.add_header("Referer", referer)
            if data: req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (428, 429, 403):
                THROTTLE["gap"] = min(THROTTLE["gap"] * 1.5, 15.0)
                cool = 30 * (k + 1)
                print(f"    被限流（{e.code}）—— 冷卻 {cool}s，之後間隔調到 "
                      f"{THROTTLE['gap']:.1f}s", flush=True)
                time.sleep(cool)
            elif k < tries - 1:
                time.sleep(2 * (k + 1))
        except Exception as e:
            last = e
            if k < tries - 1: time.sleep(2 * (k + 1))
    raise last


def load_cache(name):
    p = os.path.join(CACHE, f"{name}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f: return json.load(f)
    return {}


def save_cache(name, d):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def pick(fields, *keys):
    """照欄名找索引。找不到回 None——不猜、不用位置遞補。"""
    for i, f in enumerate(fields):
        s = str(f)
        if all(k in s for k in keys): return i
    return None


def num(x):
    try: return float(str(x).replace(",", "").strip())
    except Exception: return None


# ---------------------------------------------------------------- 抓取

def fetch_index(cache):
    """加權指數日收盤＋成交金額（FMTQIK，一次回一整月）。"""
    d = cache.setdefault("index", {})
    m = dt.date(START.year, START.month, 1)
    n = 0
    while m <= TODAY:
        key = m.strftime("%Y%m")
        if key not in d or m.strftime("%Y%m") >= TODAY.strftime("%Y%m"):
            try:
                j = json.loads(get(
                    f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={m:%Y%m}01&response=json"))
                if j.get("stat") == "OK":
                    fi = j.get("fields") or []
                    i_amt = pick(fi, "成交金額"); i_cls = pick(fi, "發行量加權股價指數")
                    if i_cls is None: i_cls = pick(fi, "指數")
                    rows = {}
                    for r in j.get("data") or []:
                        day = roc(r[0])
                        if day: rows[day] = [num(r[i_cls]), num(r[i_amt])]
                    d[key] = rows; n += 1
            except Exception as e:
                print(f"  index {key}: {e}", file=sys.stderr)
            time.sleep(0.25)
        m = (m.replace(day=28) + dt.timedelta(days=8)).replace(day=1)
    print(f"index: {len(d)} 個月（本次新增/更新 {n}）")


def roc(s):
    """民國日期 '115/08/21' → '2026-08-21'。認不出回 None，不猜。"""
    p = str(s).strip().split("/")
    if len(p) == 3 and p[0].isdigit():
        y = int(p[0]); y = y + 1911 if y < 1911 else y
        try: return f"{y:04d}-{int(p[1]):02d}-{int(p[2]):02d}"
        except Exception: return None
    return None


def fetch_daily(cache, name, url_tpl, extract, sleep=None):
    """逐日抓一支端點，只補快取裡沒有的日子。

    **進度以「嘗試次數」計，不是以「成功次數」計。**
    2026-08-22 踩過：舊版只在成功或拋例外時加一，於是「每天都回得了應、
    但解析器一律回 None」這種情況**進度不印、快取不存**，跑滿一小時什麼都沒有——
    看起來就只是「還在跑」。**靜默失敗要長得跟成功不一樣。**
    """
    d = cache.setdefault(name, {})
    day, tried, got, fail = START, 0, 0, 0
    print(f"{name}: 開始…", flush=True)
    while day <= TODAY:
        k = day.isoformat()
        if day.weekday() < 5 and k not in d:
            try:
                j = json.loads(get(url_tpl.format(d=day.strftime("%Y%m%d")),
                                   referer="https://www.twse.com.tw/"))
                v = extract(j) if j.get("stat") == "OK" else None
                d[k] = v                      # None 也存：代表「這天問過了、沒有」
                if v is not None: got += 1
            except Exception:
                fail += 1
            tried += 1
            time.sleep(sleep if sleep is not None else THROTTLE["gap"])
            if tried % 20 == 0:
                save_cache("tw", cache)
                rate = got / tried * 100
                flag = "　**解析成功率過低，八成是欄位沒對上**" if tried >= 60 and rate < 5 else ""
                print(f"  {name}: 試 {tried}、有值 {got}（{rate:.0f}%）、失敗 {fail}{flag}",
                      flush=True)
        day += dt.timedelta(days=1)
    save_cache("tw", cache)
    print(f"{name}: 共試 {tried}、有值 {got}、失敗 {fail}")


def ex_margin(j):
    for t in (j.get("tables") or [j]):
        fi = t.get("fields") or []
        i_item = pick(fi, "項目") if pick(fi, "項目") is not None else 0
        i_bal = pick(fi, "今日餘額")
        if i_bal is None: continue
        out = {}
        for r in t.get("data") or []:
            lab = str(r[i_item])
            if "融資金額" in lab or "融資(交易單位)" in lab: out["margin"] = num(r[i_bal])
            if "融券" in lab and "單位" in lab: out["short"] = num(r[i_bal])
        if out.get("margin") is not None: return out
    return None


def ex_daytrade(j):
    for t in (j.get("tables") or [j]):
        if "統計資訊" not in str(t.get("title", "")): continue
        fi = t.get("fields") or []
        i = pick(fi, "買進", "占", "比重") or pick(fi, "占市場比重")
        if i is None: continue
        for r in t.get("data") or []:
            v = num(r[i])
            if v is not None: return v
    return None


def fetch_taifex_oi(cache):
    """外資台指期未平倉淨額。**這支是整份設計的最高風險項**：
    GET 參數會被忽略，必須 POST；歷史深度未經驗證。失敗就明講失敗。"""
    d = cache.setdefault("fut_oi", {})
    day, ok, fail = START, 0, 0
    url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
    while day <= TODAY:
        k = day.isoformat()
        if day.weekday() < 5 and k not in d:
            body = urllib.parse.urlencode({
                "firstDate": day.strftime("%Y/%m/%d"), "lastDate": day.strftime("%Y/%m/%d"),
                "queryStartDate": day.strftime("%Y/%m/%d"), "queryEndDate": day.strftime("%Y/%m/%d"),
                "commodityId": "TXF"}).encode()
            try:
                raw = get(url, referer="https://www.taifex.com.tw/cht/3/futContractsDate",
                          data=body).decode("utf-8", "replace")
                d[k] = parse_taifex(raw); ok += d[k] is not None
            except Exception:
                d[k] = None; fail += 1
            time.sleep(THROTTLE["gap"])
            if (ok + fail) % 20 == 0 and (ok + fail):
                save_cache("tw", cache); print(f"  fut_oi: {ok} 筆…", flush=True)
        day += dt.timedelta(days=1)
    print(f"fut_oi: 有值 {ok} 筆，失敗 {fail}"
          + ("　**拿不到歷史 → 這一項降為候補，用三大法人現貨買賣超遞補**" if ok < 100 else ""))


def parse_taifex(raw):
    rows = list(csv.reader(io.StringIO(raw)))
    if not rows: return None
    hdr = None
    for r in rows[:6]:
        if any("未平倉" in str(c) for c in r): hdr = r; break
    if hdr is None: return None
    i_net = pick(hdr, "未平倉", "多空淨額", "口數")
    if i_net is None: i_net = pick(hdr, "未平倉餘額", "淨額")
    if i_net is None: return None
    for r in rows:
        if any("外資" in str(c) for c in r[:4]):
            v = num(r[i_net])
            if v is not None: return v
    return None


def do_fetch():
    c = load_cache("tw")
    fetch_index(c);                                   save_cache("tw", c)
    fetch_daily(c, "margin",
                "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d}&selectType=MS&response=json",
                ex_margin);                           save_cache("tw", c)
    fetch_daily(c, "daytrade",
                "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?response=json&date={d}",
                ex_daytrade);                         save_cache("tw", c)
    fetch_taifex_oi(c);                               save_cache("tw", c)
    print(f"\n快取寫在 {CACHE}/tw.json")


def peek(day="20260819"):
    """抓一天，把**真實的欄位名與前幾列**印出來。

    解析器是照欄名找的，而欄名只能從真實回應看出來——
    **猜欄名寫進程式，跟寫死索引是同一種錯，只是不容易被發現。**
    """
    tests = [
        ("融資融券 MI_MARGN",
         f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={day}&selectType=MS&response=json"),
        ("當沖 TWTB4U",
         f"https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?response=json&date={day}"),
    ]
    for name, url in tests:
        print("=" * 78); print(name); print("=" * 78)
        try:
            j = json.loads(get(url, referer="https://www.twse.com.tw/"))
        except Exception as e:
            print(f"  抓不到：{e}"); continue
        print(f"  stat = {j.get('stat')}　頂層 keys = {list(j.keys())[:10]}")
        tabs = j.get("tables") or [j]
        for i, t in enumerate(tabs):
            print(f"  --- 表 {i}　title={str(t.get('title',''))[:40]}")
            print(f"      fields = {t.get('fields')}")
            for r in (t.get('data') or [])[:4]:
                print(f"      {r}")
    print("\n把整段貼回來——解析器要照這裡的真實欄名改，不是照我猜的。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--peek", action="store_true", help="抓一天，印出真實欄位名")
    a = ap.parse_args()
    if a.peek:
        peek(); raise SystemExit(0)
    if a.fetch: do_fetch()
    if a.analyze:
        import tw_analyze; tw_analyze.main(CACHE)
    if not (a.fetch or a.analyze): ap.print_help()
