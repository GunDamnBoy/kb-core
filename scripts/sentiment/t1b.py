#!/usr/bin/env python3
"""用修好的尺重跑 T1。"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/sent/eng")
from core import rank_trailing, composite, episodes, independent, fwd_returns, WINDOW
from blockstats import circular_block_boot, min_detectable, verdict
from backtest import build, extremes, TAIL, GAP
from loaddata import load

TARGET = 0.03      # 設計書判準：63 日 ≥ ＋3pp

def run():
    df = load(); parts, sig = build(df); px = df["px"]
    print(f"樣本 {px.index[0].date()} → {px.index[-1].date()}　{len(px)} 個交易日\n")
    rows = []
    for name in sig.columns:
        lo, hi, _ = extremes(sig[name])
        for mask, tag in ((lo, "極端恐懼"), (hi, "極端貪婪")):
            eps = episodes(mask, GAP)
            for h in (21, 63, 126, 252):
                fwd = fwd_returns(px, h)
                n_ind = len(independent(eps, px.index, h))
                pt, l, u = circular_block_boot(mask.values, fwd.values, h)
                mde = min_detectable(fwd.values, n_ind)
                rows.append(dict(
                    訊號=f"{name}·{tag}", 天期=h, 極端日=int(mask.sum()), 獨立事件=n_ind,
                    點估計pp=None if pt is None else round(pt*100, 2),
                    CI下界=None if l is None else round(l*100, 2),
                    CI上界=None if u is None else round(u*100, 2),
                    最小可測pp=None if mde is None else round(mde*100, 1),
                    結論=verdict(pt, l, u, mde, TARGET)))
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    t.to_csv("/tmp/sent/out/t1b.csv", index=False)
    print("\n--- 只看 63 日（設計書判準的那一格）---")
    print(t[t.天期 == 63].to_string(index=False))

if __name__ == "__main__":
    run()
