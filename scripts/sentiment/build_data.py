#!/usr/bin/env python3
"""產出儀表板的 data.json。**這支只讀來源、只寫 data.json。**

## 這個儀表板刻意不做的事

六個階段的回測（`sentiment/BACKTEST-01..06`）測掉了下面這些，所以它們不在輸出裡：

- **沒有 0–100 合成分數**：T3 在三個獨立資料族上五次判「合成沒有加值」。
- **沒有買賣訊號、沒有倉位建議**：沒有任何規則通過完整驗證
  （最好的候選走動式 2／5、置換 p=0.754）。
- **沒有命中率比較**：要驗出 7 個百分點的差距需要兩組各約 260 個訊號，
  十五年只給我們 20 到 50 個。

輸出的是**狀態 ＋ 歷史類比分佈 ＋ 每個數字的獨立事件數**。
分佈可以用 20 個事件誠實表述；命中率不行。
"""
from __future__ import annotations
import io, json, os, sys, datetime as dt
import urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing, episodes, independent

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
GH = "https://raw.githubusercontent.com"
TAIL = 10.0


def fetch(url, timeout=60):
    r = urllib.request.Request(url); r.add_header("User-Agent", UA)
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read().decode("utf-8", "replace")


def csv(url, **kw):
    return pd.read_csv(io.StringIO(fetch(url)), **kw)


# ------------------------------------------------------------------ 美股

def yf_daily(sym, years=20):
    """yfinance。**兩個預設值會安靜改掉資料，必須明寫關掉。**

    - `auto_adjust=True`（1.x 起的預設）會回還原價。指數沒有配息拆股所以看不出差別，
      但同一支函式將來拿去抓 ETF 就會**悄悄換成另一種價格序列**。明寫 False。
    - `multi_level_index=True`（預設）讓單一標的也回 MultiIndex 欄位，
      於是 `df["Close"]` 拿到的是 DataFrame 不是 Series ——
      後面的 `.rolling()` 不會報錯，**只是算出一整張表**。明寫 False。

    這兩個都屬於「不報錯、只是換一種東西給你」，正是這個專案一路在防的失效形態。
    """
    import yfinance as yf
    end = dt.date.today() + dt.timedelta(days=1)
    d = yf.download(sym, start=str(end - dt.timedelta(days=int(years * 366))),
                    end=str(end), interval="1d", auto_adjust=False,
                    actions=False, progress=False, multi_level_index=False,
                    threads=False)
    if d is None or not len(d):
        raise RuntimeError(f"yfinance {sym}: 空的")
    c = d["Close"]
    if hasattr(c, "columns"):
        raise RuntimeError(f"yfinance {sym}: 回了 MultiIndex，欄位形狀不對")
    c = pd.to_numeric(c, errors="coerce").dropna()
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    return c[~c.index.duplicated()].sort_index()


def yahoo_daily(sym, years=20):
    """Yahoo v8 圖表端點（yfinance 掛掉時的第二層）。**必須帶瀏覽器 UA。**"""
    import time as _t
    p2 = int(_t.time()); p1 = p2 - years * 366 * 86400
    j = json.loads(fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/"
                         f"{urllib.parse.quote(sym)}?period1={p1}&period2={p2}&interval=1d"))
    res = j["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    cl = res["indicators"]["quote"][0]["close"]
    s = pd.Series(cl, index=idx).dropna()
    return s[~s.index.duplicated()].sort_index()


def us_panel():
    """VIX ＋ S&P 500。

    **價格來源必須是活的。** 2026-08-22 踩過：用 GitHub 上的 FRED S&P 500 鏡像，
    那份**半年前就停更**，而頁面照樣渲染得完整漂亮，只在角落小字寫資料截止日。
    **過期的資料跟新鮮的資料在頁面上長得一模一樣。**
    所以來源改成階梯式，而且**把實際用到的那一階寫進輸出**，不是寫「預期用哪一階」。
    """
    src = []
    v = None
    for name, fn in (
        ("CBOE VIX_History.csv（官方，日更）",
         lambda: csv("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
                     parse_dates=["DATE"], index_col="DATE")["CLOSE"]),
        ("yfinance ^VIX", lambda: yf_daily("^VIX")),
        ("Yahoo v8 ^VIX", lambda: yahoo_daily("^VIX")),
        ("GitHub datasets/finance-vix（鏡像，可能落後）",
         lambda: csv(f"{GH}/datasets/finance-vix/main/data/vix-daily.csv",
                     parse_dates=["DATE"], index_col="DATE")["CLOSE"]),
    ):
        try:
            v = fn(); src.append(f"VIX：{name}"); break
        except Exception as e:
            print(f"  VIX 來源 {name} 失敗：{e.__class__.__name__}", file=sys.stderr)
    if v is None: raise RuntimeError("VIX 三個來源全部失敗")

    px = None
    for name, fn in (
        ("yfinance ^GSPC（日更）", lambda: yf_daily("^GSPC")),
        ("Yahoo v8 ^GSPC", lambda: yahoo_daily("^GSPC")),
        ("Stooq ^spx", lambda: csv("https://stooq.com/q/d/l/?s=%5Espx&i=d",
                                   parse_dates=["Date"], index_col="Date")["Close"]),
    ):
        try:
            px = fn(); src.append(f"價格：{name}"); break
        except Exception as e:
            print(f"  價格來源 {name} 失敗：{e.__class__.__name__}", file=sys.stderr)
    if px is None:
        spy = csv(f"{GH}/whit3rabbit/fear-greed-data/main/datasets/combined/spy_2011_2023.csv",
                  parse_dates=["Date"], index_col="Date")["Close"]
        spx = pd.to_numeric(csv(f"{GH}/datasets/s-and-p-500/main/archive/fred_sp500.csv",
                                parse_dates=[0], index_col=0).iloc[:, 0],
                            errors="coerce").dropna()
        j = spy.index[-1]; tail = spx[spx.index > j]
        px = pd.concat([spy, tail * (spy.loc[j] / spx.asof(j))]) if len(tail) else spy
        px = px[~px.index.duplicated()].sort_index()
        src.append("價格：GitHub 鏡像（**兩個活來源都失敗，這一份可能過期**）")

    df = pd.DataFrame({"px": px})
    df["vix"] = v.reindex(df.index).ffill(limit=3)
    return df.dropna(), src


def build_market(df, sig_raw, win, per, hor, name, sig_label, invert, cost, src, freq,
                 level_raw=None, level_label=None, components=None, last_obs=None):
    """一個市場的完整輸出。**恐懼側優先，貪婪側只當對照。**

    `level_raw` 是**絕對水位**（例如 VIX 本身），與 `sig_raw`（相對自身均線）分開顯示。
    2026-08-22 使用者問「2026-02-05 為什麼會觸發、大跌明明在三月」——
    因為訊號量的是**相對自身 50 日均線的極端**，那天回檔只有 −2.6%。
    **兩個都要顯示，否則「極端恐懼」這個標籤會誤導。**
    """
    px = df["px"]
    rk = rank_trailing(sig_raw, win, invert=invert)
    lv = None if level_raw is None else rank_trailing(level_raw, win, invert=True)
    lo = (rk <= TAIL).fillna(False)
    hi = (rk >= 100 - TAIL).fillna(False)
    dd60 = (px / px.rolling(60 if freq == "日" else 13).max() - 1)

    eps = episodes(lo, 3 if freq == "日" else 1)
    h_mid = hor[1]
    starts = independent(eps, px.index, h_mid)
    pos = {d: i for i, d in enumerate(px.index)}

    def fwd(i, h):
        return float(px.iloc[i + h] / px.iloc[i] - 1) if i + h < len(px) else None

    ana = []
    for d in starts:
        i = pos[d]
        row = {"d": str(d.date()), "pct": round(float(rk.iloc[i]), 1),
               "lvl": None if lv is None or lv.iloc[i] != lv.iloc[i]
                      else round(float(lv.iloc[i]), 1),
               "raw": round(float(sig_raw.iloc[i]), 2),
               "dd": round(float(dd60.iloc[i]) * 100, 1) if dd60.iloc[i] == dd60.iloc[i] else None}
        for h in hor:
            f = fwd(i, h)
            row[f"f{h}"] = None if f is None else round(f * 100, 1)
        seg = px.iloc[i:min(len(px), i + h_mid + 1)]
        row["mae"] = round(float(seg.min() / px.iloc[i] - 1) * 100, 1) if len(seg) > 1 else None
        ana.append(row)

    base = {}
    for h in hor:
        f = (px.shift(-h) / px - 1).dropna() * 100
        base[f"f{h}"] = [round(float(x), 1) for x in
                         np.percentile(f, [10, 25, 50, 75, 90])]

    # 降險特性：五段走動式的回撤對照。**這是機械結果，不是預測能力。**
    # 倉位規則與回測時完全相同（基準 0.75、恐懼 1.0、貪婪 0.5），
    # 不然頁面上的數字會跟報告裡的對不起來。
    r = px.pct_change().fillna(0)
    w = pd.Series(0.75, index=px.index); w[hi] = 0.5; w[lo] = 1.0
    s = (w.shift(1).fillna(1.0) * r - w.shift(1).fillna(1.0).diff().abs().fillna(0) * cost)
    def mdd(x):
        c = (1 + x).cumprod(); return float((c / c.cummax() - 1).min())

    step = max(len(px) // 5, 1)
    segs = []
    for k in range(5):
        a, b = k * step, min((k + 1) * step, len(px) - 1)
        if b - a < 20: continue
        segs.append({"from": str(px.index[a].date()), "to": str(px.index[b].date()),
                     "hold": round(mdd(r.iloc[a:b]) * 100, 1),
                     "light": round(mdd(s.iloc[a:b]) * 100, 1)})
    # 差距太小就直說沒有，不要讓讀者自己去比五組幾乎一樣的數字
    diffs = [x["light"] - x["hold"] for x in segs]
    derisk_holds = sum(1 for d in diffs if d > 0.5)

    keep = px.index[::max(len(px) // 900, 1)]
    series = [{"d": str(d.date()), "p": round(float(rk.loc[d]), 1),
               "x": round(float(px.loc[d]), 1)}
              for d in keep if rk.loc[d] == rk.loc[d]]

    # **比值到極端時，要分得出是分子變了還是分母變了。**
    # 融資強度＝融資餘額 ÷ 均成交值：**成交量暴衝也會把比值壓到極端**，
    # 而那是多頭不是恐慌。只印比值會讓兩種完全相反的情況長得一模一樣。
    comp = []
    for cname, cser in (components or {}).items():
        cs = cser.reindex(px.index)
        cr = rank_trailing(cs, win)
        comp.append({"name": cname,
                     "now": round(float(cs.iloc[-1]), 1) if cs.iloc[-1] == cs.iloc[-1] else None,
                     "pct": round(float(cr.iloc[-1]), 1) if cr.iloc[-1] == cr.iloc[-1] else None,
                     "chg20": (None if len(cs) < 21 or cs.iloc[-21] != cs.iloc[-21]
                               else round(float(cs.iloc[-1] / cs.iloc[-21] - 1) * 100, 1))})

    # **比值到恐懼側極端時，先問是分子還是分母把它推過去的。**
    # 融資強度低＝去槓桿，前提是**分子（融資餘額）在下降**。
    # 若分子反而在高位、還在增加，那是成交量暴衝造成的——**和恐慌相反**。
    # 沒有這道檢查，兩種相反的市場狀態在頁面上會長得一模一樣。
    ratio_warn = None
    if len(comp) >= 2 and rk.iloc[-1] == rk.iloc[-1] and float(rk.iloc[-1]) <= TAIL:
        num, den = comp[0], comp[1]
        if num["pct"] is not None and num["pct"] >= 50:
            ratio_warn = {"num": num["name"], "numPct": num["pct"], "numChg": num["chg20"],
                          "den": den["name"], "denPct": den["pct"], "denChg": den["chg20"]}

    # **週頻的索引標籤是「該週結束的星期日」，可能落在未來。**
    # 直接拿它算新鮮度，staleDays 會少報最多 6 天，而且頁面會顯示一個未來的日期。
    # `last_obs` 是該週真正最後一筆資料的日期。
    maes = [a["mae"] for a in ana if a["mae"] is not None]
    last = px.index[-1].date()
    if last_obs:
        try: last = min(last, dt.date.fromisoformat(str(last_obs)[:10]))
        except ValueError: pass
    stale = max(0, (dt.date.today() - last).days)
    return {
        "staleDays": stale,
        "name": name, "sigLabel": sig_label, "freq": freq,
        "asof": str(last),
        "ratioWarn": ratio_warn,
        "pct": round(float(rk.iloc[-1]), 1) if rk.iloc[-1] == rk.iloc[-1] else None,
        "levelPct": (None if lv is None else
                     (lambda x: None if x != x else round(float(x), 1))(lv.iloc[-1])),
        "levelLabel": level_label,
        "levelNow": None if level_raw is None else round(float(level_raw.iloc[-1]), 2),
        "raw": round(float(sig_raw.iloc[-1]), 2),
        "dd60": round(float(dd60.iloc[-1]) * 100, 1),
        "window": win, "horizons": list(hor),
        "series": series, "analogs": ana, "baseline": base,
        "n": len(ana),
        "maeMedian": round(float(np.median(maes)), 1) if maes else None,
        "derisk": segs, "deriskSegs": derisk_holds, "components": comp, "sources": src,
        "warmup": int(rk.isna().sum()),
    }


def main():
    out = {"meta": {"built": dt.datetime.now(dt.timezone.utc)
                    .astimezone(dt.timezone(dt.timedelta(hours=8)))
                    .strftime("%Y-%m-%d %H:%M 台北"),
                    "schema": "sentiment-v1"},
           "markets": {}}

    try:
        df, src = us_panel()
        # **主訊號用 VIX 的絕對水位，不是相對 50 日均。**
        #
        # 2026-08-22 訂正：相對均線的寫法（從 CNN 抄來的）量的是**加速度**不是水位，
        # 於是 29 次觸發裡有 6 次的 VIX 絕對水位在 30 百分位以上——
        # 其中一次 VIX 只有 13.1、絕對水位 57.9 百分位，而它被標成「極端恐懼」。
        # **一個叫「極端恐懼」的標籤，在市場一點都不恐慌的日子亮起來，就是錯的。**
        #
        # 五種定義都測過，**統計上沒有一個比較好**（63 日中位 4.9%～5.6%，
        # 基準 3.8%，差距全在雜訊裡）。所以這個選擇不是靠績效挑的，
        # 是靠「標籤有沒有說到做到」——而絕對水位不需要第二個參數，
        # MAE 也最低（−2.2% vs −2.8%）。
        out["markets"]["us"] = build_market(
            df, df["vix"],
            750, 252, (21, 63, 126), "美股 · S&P 500",
            "VIX 絕對水位（隱含波動）", True, 0.0005, src, "日",
            level_raw=df["vix"] / df["vix"].rolling(50).mean() - 1,
            level_label="VIX 相對 50 日均")
        print(f"美股 OK：{out['markets']['us']['asof']}、"
              f"{out['markets']['us']['n']} 個歷史類比")
    except Exception as e:
        print(f"美股失敗：{e.__class__.__name__}: {e}", file=sys.stderr)

    cache = os.path.expanduser(os.environ.get("SENT_CACHE", "~/sent-cache"))
    twf = os.path.join(cache, "tw.json")
    if os.path.exists(twf):
        try:
            import tw_analyze as TA
            c = TA.load_cache(cache)
            tdf, counts, err = TA.panel(c)
            parts = TA.build(tdf, 156)
            if "融資強度" in parts.columns:
                amt20 = tdf["amt"].rolling(20, min_periods=5).mean()
                # **單位對齊**：TWSE 的「融資金額」是**仟元**、FMTQIK 的成交金額是**元**。
                # 直接相除得到 0.0018，四捨五入成 0.0——數字看起來像壞掉，其實只是單位。
                # 乘回 1000 之後是「融資餘額相當於幾倍的日均成交值」，那才讀得懂。
                ratio = (tdf["margin"] * 1000.0) / amt20
                out["markets"]["tw"] = build_market(
                    tdf, ratio, 156, 52, (4, 13, 26),
                    "台股 · 加權指數", "融資餘額 ÷ 20 期均成交值", False, 0.00585,
                    ["TWSE FMTQIK（指數與成交值）", "TWSE MI_MARGN（信用交易統計）"], "週",
                    components={"融資餘額（億元）": tdf["margin"] * 1000.0 / 1e8,
                                "20 期均成交值（億元）": amt20 / 1e8},
                    last_obs=tdf.attrs.get("last_obs"))
                print(f"台股 OK：{out['markets']['tw']['asof']}、"
                      f"{out['markets']['tw']['n']} 個歷史類比")
        except Exception as e:
            print(f"台股失敗：{e.__class__.__name__}: {e}", file=sys.stderr)
    else:
        print(f"（沒有 {twf}，這一輪不含台股）")

    # ---- 下游相容（設計書第六節）----
    # 投顧的晨間匯流條讀 composite / tw.heat / meta.built 三個鍵。
    # **鍵名保留、語意換掉**：現在是恐懼百分位（高＝平靜／自滿），
    # 方向與舊的「泡沫溫度」一致（高＝熱），但**門檻必須重設**——
    # 舊的 59.4 是「黃·警戒」，新的尺不是同一把。
    us = out["markets"].get("us") or {}
    tw = out["markets"].get("tw") or {}
    out["composite"] = us.get("pct")
    out["tw_compat"] = {"heat": tw.get("pct")}
    out["meta"]["compat"] = ("composite=美股恐懼百分位、tw_compat.heat=台股恐懼百分位；"
                             "高＝平靜/自滿，低＝恐懼。**門檻與舊版不同，不可沿用。**")

    p = os.environ.get("SENT_OUT", "data.json")
    json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
    print(f"→ {p}　{os.path.getsize(p)/1024:.0f} KB")

    # **同時把快照灌進同目錄的 index.html。**
    # 頁面用 fetch("data.json") 取新資料，但 `file://` 下 fetch 會被 CORS 擋，
    # 於是只剩內嵌快照——若那份是空的，**畫面會是「沒有可用資料」而不是報錯**。
    # 灌進去之後兩種開法都有東西。
    html = os.path.join(os.path.dirname(os.path.abspath(p)), "index.html")
    if os.path.exists(html):
        import re
        src_html = open(html, encoding="utf-8").read()
        new, n = re.subn(
            r'(<script id="snapshot" type="application/json">).*?(</script>)',
            lambda m: m.group(1) + json.dumps(out, ensure_ascii=False) + m.group(2),
            src_html, count=1, flags=re.S)
        if n:
            open(html, "w", encoding="utf-8").write(new)
            print(f"→ 快照已灌進 {html}（file:// 也開得起來）")
        else:
            print(f"**{html} 找不到 snapshot 區塊，沒灌**", file=sys.stderr)


if __name__ == "__main__":
    main()
