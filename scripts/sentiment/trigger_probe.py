#!/usr/bin/env python3
"""第 2 步：觸發器 ＋ CAPE 的分層假設。**要在有網路的機器上跑。**

用法：python3 trigger_probe.py

## 要回答的問題

設計書第十三節的假設：**「極端恐懼＝買點」在承平時期對，在信用與貨幣環境
惡化時完全失效** —— 而那正是七項引爆觸發器在量的東西。

第一階段回測裡，CAPE 分層是**唯一跑出訊號的東西**
（極端貪婪在高估值環境後 12 個月中位報酬 6.98%，低估值 13.84%，差 6.9pp，但 n=8～10）。
這一支把觸發器加成第二個分層維度，並把六項的原始序列一次補算回 1990。

## 誠實的前提

儀表板的 `history` 只有 32 筆（2026-07-17 → 08-22），`trig` 只有 12 筆有值。
**這七項在那套系統裡從來沒有累積出任何 track record。**
缺的不是資料——六項的原始序列在 FRED 上都有 20 年以上——**是沒有人回頭算過。**
"""
from __future__ import annotations
import io, json, os, sys, urllib.request
import datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing, episodes, independent
from blockstats import circular_block_boot, min_detectable, verdict

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
CACHE = os.path.abspath(os.path.expanduser(os.environ.get("SENT_CACHE", "~/sent-cache")))


def http(url, referer=None):
    r = urllib.request.Request(url); r.add_header("User-Agent", UA)
    if referer: r.add_header("Referer", referer)
    with urllib.request.urlopen(r, timeout=40) as f: return f.read().decode("utf-8", "replace")


def fred(series):
    """FRED 的 CSV 端點。抓不到就回空序列並印出來——不插補、不猜。"""
    try:
        txt = http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
        d = pd.read_csv(io.StringIO(txt), parse_dates=[0], index_col=0).iloc[:, 0]
        s = pd.to_numeric(d, errors="coerce").dropna()
        print(f"  FRED {series:<16} {len(s):>6} 筆  {s.index[0].date()} → {s.index[-1].date()}")
        return s
    except Exception as e:
        print(f"  FRED {series:<16} **失敗**：{e}")
        return pd.Series(dtype=float)


def stooq(sym):
    try:
        txt = http(f"https://stooq.com/q/d/l/?s={sym}&i=d")
        d = pd.read_csv(io.StringIO(txt), parse_dates=["Date"], index_col="Date")["Close"]
        print(f"  stooq {sym:<16} {len(d):>6} 筆  {d.index[0].date()} → {d.index[-1].date()}")
        return d.dropna()
    except Exception as e:
        print(f"  stooq {sym:<16} **失敗**：{e}")
        return pd.Series(dtype=float)


def build_triggers():
    """六項可量化的觸發器 → 每項一個 0–100 的 `prog`（距門檻的進度）。

    第七項（OpenAI／SpaceX 巨型 IPO）是人工二元事件，`prog` 沒有意義，
    **退出計分，只當事件註記**——不要為了湊七項給它一個假的進度。
    """
    print("抓原始序列：")
    hy   = fred("BAMLH0A0HYM2")      # 只剩約 3 年滾動視窗，長歷史用 BAA10Y 代
    baa  = fred("BAA10Y")
    ccc  = fred("BAMLH0A3HYC")
    y10  = fred("DGS10")
    cpi  = fred("CPIAUCSL")
    ff   = fred("FEDFUNDS")
    gdp  = fred("GDP")
    soxx = stooq("soxx.us")

    T = {}
    base = hy if len(hy) > 2500 else baa
    base_name = "BAMLH0A0HYM2" if len(hy) > 2500 else "BAA10Y（HY OAS 只剩 3 年滾動視窗）"
    if len(base):
        chg = (base - base.shift(63)) * 100          # 3 個月變化（bp）
        T["HY 利差 3M 走闊 ≥80bp"] = (chg / 80 * 100).clip(0, 100)
        print(f"  → 信用利差用 {base_name}")
    if len(ccc): T["CCC 利差 ≥12%"] = (ccc / 12 * 100).clip(0, 100)
    if len(y10): T["美債 10Y ≥5%"] = (y10 / 5 * 100).clip(0, 100)
    if len(cpi):
        yoy = cpi.pct_change(12) * 100
        T["CPI 年增 ≥4%"] = (yoy / 4 * 100).clip(0, 100)
    if len(ff) and len(gdp):
        g = gdp.pct_change(4) * 100
        gap = ff.reindex(g.index, method="ffill") - g          # 政策利率 − 名目 GDP 成長
        T["政策利率 ≥ 名目GDP"] = ((gap + 6) / 6 * 100).clip(0, 100)
    if len(soxx):
        r24 = (soxx / soxx.shift(505) - 1) * 100
        T["SOXX 24M 漲幅 ≥150%"] = (r24 / 150 * 100).clip(0, 100)
    print(f"\n可量化的觸發器：{len(T)}／6（第七項是人工二元事件，不計分）")
    return T


def main():
    T = build_triggers()
    if not T:
        print("\n**一項都抓不到——這台機器連不出去。** 換一台有網路的再跑。")
        return

    # 月頻主序列：Shiller 價格與 CAPE ＋ VIX 情緒（第一階段唯一有長歷史的訊號）
    sh = pd.read_csv(io.StringIO(http(
        "https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv")),
        parse_dates=["Date"], index_col="Date")
    px = pd.to_numeric(sh["SP500"], errors="coerce").dropna()
    cape = pd.to_numeric(sh["PE10"], errors="coerce").replace(0, np.nan)
    vm = pd.read_csv(io.StringIO(http(
        "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-monthly.csv")),
        parse_dates=[0], index_col=0).iloc[:, -1]

    idx = px.index[px.index >= "1990-01-01"]
    m = pd.DataFrame({"px": px.reindex(idx), "cape": cape.reindex(idx)})
    m["vix"] = vm.reindex(idx, method="nearest", tolerance=pd.Timedelta("20D"))
    prog = pd.DataFrame({k: v.reindex(idx, method="ffill") for k, v in T.items()})
    m["n_lit"] = (prog >= 100).sum(axis=1)
    m["n_near"] = (prog >= 80).sum(axis=1)
    m["prog_mean"] = prog.mean(axis=1)
    m = m.dropna(subset=["px", "vix"])

    print(f"\n月頻面板 {m.index[0].date()} → {m.index[-1].date()}　{len(m)} 個月")
    print("\n歷史上同時亮 ≥N 盞的月數（這是設計書第十三節要的那個數字）：")
    for n in range(0, 5):
        cnt = int((m["n_lit"] >= n).sum())
        eps = episodes(m["n_lit"] >= n, 1)
        print(f"  ≥{n} 盞：{cnt:>4} 個月、{len(eps)} 段獨立期間")
    print("\n`prog` ≥80（接近門檻）的項數分佈：")
    print(m["n_near"].value_counts().sort_index().to_string())

    sig = rank_trailing(m["vix"], 36, invert=True)
    lo, hi = sig <= 10, sig >= 90
    fwd12 = m["px"].shift(-12) / m["px"] - 1

    print("\n" + "=" * 84)
    print("分層：同樣的情緒讀數，在不同環境下是不是同一回事（12 個月前瞻）")
    print("=" * 84)
    cape_hi = m["cape"] >= m["cape"].rolling(240, min_periods=60).median()
    strata = [("觸發器 0–1 盞", m["n_lit"] <= 1), ("觸發器 ≥2 盞", m["n_lit"] >= 2),
              ("接近門檻 ≤2 項", m["n_near"] <= 2), ("接近門檻 ≥3 項", m["n_near"] >= 3),
              ("CAPE 高於長期中位", cape_hi), ("CAPE 低於長期中位", ~cape_hi)]
    for tag, mask in (("極端恐懼", lo), ("極端貪婪", hi)):
        print(f"\n--- {tag} ---")
        for sname, sm in strata:
            mm = (mask & sm).fillna(False)
            eps = episodes(mm, 1); starts = independent(eps, m.index, 12)
            v = [fwd12.get(d) for d in starts]; v = [x for x in v if x == x and x is not None]
            if len(v) < 3:
                print(f"  {sname:<20} 獨立事件 {len(starts):>2}  **樣本不足**"); continue
            print(f"  {sname:<20} 獨立事件 {len(starts):>2}  中位 {np.median(v)*100:>6.2f}%  "
                  f"勝率 {np.mean(np.array(v) > 0)*100:>3.0f}%  "
                  f"最差 {np.min(v)*100:>6.1f}%")

    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, "trigger_results.json")
    m.to_json(out, orient="index", date_format="iso")
    print(f"\n面板寫到 {out}")


if __name__ == "__main__":
    main()
