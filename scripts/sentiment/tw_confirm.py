#!/usr/bin/env python3
"""融資強度是不是真的，還是第 20 次擲骰子擲出來的。**這一支是判決。**

## 為什麼一定要有

這個專案測過大約 20 個訊號。**在完全沒有效果的世界裡，20 個訊號裡有 1 個
通過「樣本外 Sharpe 贏買進持有且回撤更小」是很正常的事。**
我已經在這件事上栽過兩次（Setup→Trigger 的假突破、CFTC 逐格表的分群故事）。

所以「通過 T2」不是結論，是**待驗的候選**。三件事才判得動：

1. **走動式驗證（walk-forward）**：單一切點是一次擲骰子。改成多個切點，
   看優勢是不是每一段都在，還是只靠某一段。
2. **置換檢定**：把訊號環狀位移（保留自相關），重算 Sharpe 優勢一千次，
   看真實值排在虛無分佈的第幾百分位。
3. **多重比較的分母**：把這 20 個訊號的通過數，跟隨機該有的數量比。
"""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing
import tw_analyze as TA

COST, TAIL, WIN, PER = TA.COST, TA.TAIL, 156, 52


def sharpe(x): return x.mean() / x.std() * np.sqrt(PER) if x.std() > 0 else np.nan
def mdd(x):
    c = (1 + x).cumprod(); return float((c / c.cummax() - 1).min())


def positions(rank, px):
    w = pd.Series(0.75, index=px.index)
    w[rank >= 100 - TAIL] = 0.5
    w[rank <= TAIL] = 1.0
    return w.shift(1).fillna(0.75)


def run(w, r):
    return w * r - w.diff().abs().fillna(0) * COST


def main(cache_dir):
    c = TA.load_cache(cache_dir)
    df, counts, err = TA.panel(c)
    parts = TA.build(df, WIN)
    if "融資強度" not in parts.columns:
        print("**融資強度沒建起來**"); return
    px = df["px"]; r = px.pct_change().fillna(0)
    rk = rank_trailing(parts["融資強度"].dropna(), WIN).reindex(px.index)
    valid = rk.notna()
    print(f"面板 {df.index[0].date()} → {df.index[-1].date()}　"
          f"有效訊號 {int(valid.sum())} 週（熱身 {WIN} 週）\n")

    # ---------- 1. 走動式驗證 ----------
    print("=" * 78); print("一、走動式驗證：優勢是每一段都在，還是只靠某一段"); print("=" * 78)
    idx = px.index[valid]
    n = len(idx); k = 5
    bounds = [idx[int(n * i / k)] for i in range(k)] + [idx[-1]]
    w = positions(rk, px); s = run(w, r)
    print(f"{'區段':<26}{'策略':>8}{'持有':>8}{'差':>8}{'策略MDD':>10}{'持有MDD':>10}")
    wins = 0
    for i in range(k):
        a, b = bounds[i], bounds[i + 1]
        ss, rr = s.loc[a:b], r.loc[a:b]
        d = sharpe(ss) - sharpe(rr)
        wins += d > 0
        print(f"{str(a.date())+'→'+str(b.date()):<26}{sharpe(ss):>8.2f}{sharpe(rr):>8.2f}"
              f"{d:>8.2f}{mdd(ss)*100:>9.1f}%{mdd(rr)*100:>9.1f}%")
    print(f"\n  五段裡有 **{wins}／5** 段贏過買進持有"
          f"　→ {'**每段都在，不是靠單一時期**' if wins >= 4 else '**優勢集中在少數時期，不穩**'}")

    # ---------- 2. 置換檢定 ----------
    print("\n" + "=" * 78)
    print("二、置換檢定：把訊號位移一千次，真實的優勢排第幾")
    print("=" * 78)
    obs = sharpe(s) - sharpe(r)
    rng = np.random.default_rng(11)
    rkv = rk.values; null = []
    for _ in range(1000):
        sh = int(rng.integers(1, len(rkv)))
        w2 = positions(pd.Series(np.roll(rkv, sh), index=px.index), px)
        null.append(sharpe(run(w2, r)) - sharpe(r))
    null = np.array([x for x in null if x == x])
    pct = float((null < obs).mean() * 100)
    p = float((np.abs(null) >= abs(obs)).mean())
    print(f"  真實 Sharpe 優勢 {obs:+.3f}")
    print(f"  虛無分佈：中位 {np.median(null):+.3f}、5%–95% [{np.percentile(null,5):+.3f},"
          f" {np.percentile(null,95):+.3f}]")
    print(f"  真實值排在第 **{pct:.0f}** 百分位，雙尾 p = **{p:.3f}**")
    print(f"  → {'**通過**' if p < 0.10 and obs > 0 else '**沒有通過——跟位移到隨機時點沒有差別**'}")

    # ---------- 3. 多重比較的分母 ----------
    print("\n" + "=" * 78); print("三、多重比較：20 個訊號裡通過 1 個，算多嗎"); print("=" * 78)
    N = 20
    from scipy.stats import binomtest
    for rate in (0.05, 0.10):
        bt = binomtest(1, N, rate, alternative="greater")
        print(f"  若每個訊號隨機通過的機率是 {rate:.0%}："
              f"20 個裡至少 1 個通過的機率 = {1-(1-rate)**N:.0%}"
              f"　（單尾 p={bt.pvalue:.2f}）")
    print("  → **「20 個裡有 1 個通過」本身完全在隨機範圍內。**")
    print("    所以判決要看第一、二節，不能看「它通過了 T2」。")

    # ---------- 4. 合起來 ----------
    print("\n" + "=" * 78); print("判決"); print("=" * 78)
    ok = (wins >= 4) and (p < 0.10) and (obs > 0)
    print(f"  走動式 {wins}/5　置換 p={p:.3f}　"
          f"→ **{'候選存活，可以進入前瞻追蹤' if ok else '候選未通過，不要蓋在它上面'}**")
    if not ok:
        print("\n  未通過**不等於**它沒用，而是**這份資料判不動**。")
        print("  照設計書：不發布倉位訊號，只呈現原始序列、百分位與 MAE 分佈。")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/sent-cache"))
