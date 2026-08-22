#!/usr/bin/env python3
"""Setup→Trigger 的功勞到底是誰的。**這一支是對照組，不是驗證。**

Setup→Trigger 的規則裡含兩個東西：
1. **Setup**：過去 20 日曾進入極端區、現在已回落（＝情緒）
2. **Trend confirmation**：收盤跌破／站上 20 日均線（＝純技術濾網）

**均線濾網本身就會降低回撤**，這是幾十年前就知道的事。
所以「Setup→Trigger 比水位法好」有可能完全來自第 2 項，
而情緒那一半一分錢都沒出。

拆成四條規則跑同一套指標：

| | 情緒 | 均線 |
|---|---|---|
| B 純均線 | ✗ | ✓ |
| C 純 Setup | ✓ | ✗ |
| D Setup→Trigger | ✓ | ✓ |

**若 D ≈ B，那情緒沒有加值**，這一整套就只是一條穿著情緒外衣的移動平均線。
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/sent/eng")
from core import rank_trailing, WINDOW
from loaddata import load
from backtest import build, TAIL, COST

LOOKBACK, MA = 20, 20


def sharpe(x): return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")
def ann(x): return (1 + x).prod() ** (252 / max(len(x), 1)) - 1
def mdd(x):
    c = (1 + x).cumprod(); return float((c / c.cummax() - 1).min())


def run(w, r):
    return w.shift(1).fillna(0.75) * r - w.shift(1).fillna(0.75).diff().abs().fillna(0) * COST


def main():
    df = load(); parts, sigs = build(df); px = df["px"]
    r = px.pct_change().fillna(0)
    cut = int(len(px) * 0.6); sp = px.index[cut]
    ma = px.rolling(MA).mean()
    up, dn = px > ma, px < ma

    print(f"樣本外自 {sp.date()}　成本 {COST*100:.2f}%\n")
    bh_s, bh_m = sharpe(r.iloc[cut:]), mdd(r.iloc[cut:])
    print(f"{'規則':<34}{'外 Sharpe':>10}{'外年化':>9}{'外 MDD':>9}{'換手':>7}")
    print(f"{'A 買進持有':<34}{bh_s:>10.2f}{ann(r.iloc[cut:])*100:>8.1f}%{bh_m*100:>8.1f}%{'—':>7}")

    # B：純均線，完全沒有情緒
    wB = pd.Series(0.75, index=px.index); wB[up] = 1.0; wB[dn] = 0.5
    sB = run(wB, r)
    print(f"{'B 純 20 日均線（無情緒）':<34}{sharpe(sB.iloc[cut:]):>10.2f}"
          f"{ann(sB.iloc[cut:])*100:>8.1f}%{mdd(sB.iloc[cut:])*100:>8.1f}%"
          f"{int((wB.diff().abs()>0).sum()):>7}")
    print()

    rows = []
    for name in sigs.columns:
        rk = rank_trailing(sigs[name].dropna(), WINDOW).reindex(px.index)
        lo, hi = rk <= TAIL, rk >= 100 - TAIL
        hs = hi.rolling(LOOKBACK, min_periods=1).max().astype(bool)
        ls = lo.rolling(LOOKBACK, min_periods=1).max().astype(bool)

        wC = pd.Series(0.75, index=px.index)          # 純 Setup，沒有均線
        wC[hs & ~hi] = 0.5; wC[ls & ~lo] = 1.0
        wD = pd.Series(0.75, index=px.index)          # Setup ＋ 均線
        wD[hs & ~hi & dn] = 0.5; wD[ls & ~lo & up] = 1.0

        sC, sD = run(wC, r), run(wD, r)
        rows.append((name, sharpe(sC.iloc[cut:]), mdd(sC.iloc[cut:]),
                     sharpe(sD.iloc[cut:]), mdd(sD.iloc[cut:])))
        print(f"{'C 純 Setup · ' + name:<34}{rows[-1][1]:>10.2f}"
              f"{ann(sC.iloc[cut:])*100:>8.1f}%{rows[-1][2]*100:>8.1f}%"
              f"{int((wC.diff().abs()>0).sum()):>7}")
        print(f"{'D Setup→Trigger · ' + name:<34}{rows[-1][3]:>10.2f}"
              f"{ann(sD.iloc[cut:])*100:>8.1f}%{rows[-1][4]*100:>8.1f}%"
              f"{int((wD.diff().abs()>0).sum()):>7}")

    print("\n" + "=" * 74)
    print("判決：D（情緒＋均線）有沒有贏過 B（純均線）")
    print("=" * 74)
    b_s, b_m = sharpe(sB.iloc[cut:]), mdd(sB.iloc[cut:])
    win = 0
    for name, cs, cm, ds, dm in rows:
        better = ds > b_s and dm > b_m
        win += better
        print(f"  {name:<14} D Sharpe {ds:>5.2f} vs B {b_s:>5.2f}　"
              f"D MDD {dm*100:>6.1f}% vs B {b_m*100:>6.1f}%　"
              f"{'**情緒有加值**' if better else '情緒沒有加值'}")
    print(f"\n{win}/{len(rows)} 個訊號的情緒層真的加了值。")
    if win == 0:
        print("**情緒一分錢都沒出——這一整套只是一條穿著情緒外衣的移動平均線。**")


if __name__ == "__main__":
    main()
