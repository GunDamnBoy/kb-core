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
import urllib.request
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

def us_panel():
    """VIX ＋ S&P 500。優先用 CBOE 官方（每日更新），退援 GitHub 鏡像。"""
    src = []
    try:
        v = csv("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
                parse_dates=["DATE"], index_col="DATE")["CLOSE"]
        src.append("CBOE VIX_History.csv")
    except Exception:
        v = csv(f"{GH}/datasets/finance-vix/main/data/vix-daily.csv",
                parse_dates=["DATE"], index_col="DATE")["CLOSE"]
        src.append("GitHub datasets/finance-vix（CBOE 抓不到時的鏡像）")
    spy = csv(f"{GH}/whit3rabbit/fear-greed-data/main/datasets/combined/spy_2011_2023.csv",
              parse_dates=["Date"], index_col="Date")["Close"]
    spx = csv(f"{GH}/datasets/s-and-p-500/main/archive/fred_sp500.csv",
              parse_dates=[0], index_col=0).iloc[:, 0]
    spx = pd.to_numeric(spx, errors="coerce").dropna()
    src.append("SPY 收盤（2011–2022）接 FRED S&P 500（2016–）")
    j = spy.index[-1]; tail = spx[spx.index > j]
    px = pd.concat([spy, tail * (spy.loc[j] / spx.asof(j))]) if len(tail) else spy
    px = px[~px.index.duplicated()].sort_index()
    df = pd.DataFrame({"px": px})
    df["vix"] = v.reindex(df.index).ffill(limit=3)
    return df.dropna(), src


def build_market(df, sig_raw, win, per, hor, name, sig_label, invert, cost, src, freq):
    """一個市場的完整輸出。**恐懼側優先，貪婪側只當對照。**"""
    px = df["px"]
    rk = rank_trailing(sig_raw, win, invert=invert)
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

    maes = [a["mae"] for a in ana if a["mae"] is not None]
    return {
        "name": name, "sigLabel": sig_label, "freq": freq,
        "asof": str(px.index[-1].date()),
        "pct": round(float(rk.iloc[-1]), 1) if rk.iloc[-1] == rk.iloc[-1] else None,
        "raw": round(float(sig_raw.iloc[-1]), 3),
        "dd60": round(float(dd60.iloc[-1]) * 100, 1),
        "window": win, "horizons": list(hor),
        "series": series, "analogs": ana, "baseline": base,
        "n": len(ana),
        "maeMedian": round(float(np.median(maes)), 1) if maes else None,
        "derisk": segs, "deriskSegs": derisk_holds, "sources": src,
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
        out["markets"]["us"] = build_market(
            df, df["vix"] / df["vix"].rolling(50).mean() - 1,
            750, 252, (21, 63, 126), "美股 · S&P 500",
            "VIX 相對 50 日均（隱含波動）", True, 0.0005, src, "日")
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
                out["markets"]["tw"] = build_market(
                    tdf, tdf["margin"] / amt20, 156, 52, (4, 13, 26),
                    "台股 · 加權指數", "融資餘額 ÷ 20 期均成交值", False, 0.00585,
                    ["TWSE FMTQIK（指數與成交值）", "TWSE MI_MARGN（信用交易統計）"], "週")
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


if __name__ == "__main__":
    main()
