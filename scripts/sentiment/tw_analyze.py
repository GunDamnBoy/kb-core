#!/usr/bin/env python3
"""台股籌碼的成分建構與回測。跑在 tw_probe.py 的快取上。

## 規模分母規則（設計書第十五節）

**每一個部位或流量變數都要除以一個規模分母。** 不除，量到的是市場自己在長大，
不是情緒在變。台股市值二十年翻了好幾倍，「融資餘額創新高」多數時候
只是市值創新高的影子。

- 融資餘額 ÷ **20 日均成交值**（TWSE 不發布每日總市值，成交值是日頻且同源）
- 外資期貨未平倉淨額 ÷ **自身 250 日絕對值均值**（拿不到全市場未平倉總量時的退援，
  會在報告裡標明這是退援而不是規格）
- 當沖占比本身就是比率，不需要分母
"""
from __future__ import annotations
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing, composite, episodes, independent, fwd_returns, WINDOW
from blockstats import circular_block_boot, min_detectable, verdict

TARGET = 0.03
HORIZONS = (21, 63, 126, 252)
TAIL, GAP, COST = 10.0, 3, 0.00585      # 台股來回成本：手續費 0.1425%×2 ＋ 證交稅 0.3%


def panel(cache_dir):
    c = json.load(open(os.path.join(cache_dir, "tw.json"), encoding="utf-8"))
    rows = {}
    for _, mon in (c.get("index") or {}).items():
        for d, v in mon.items():
            if v and v[0]: rows[d] = {"px": v[0], "amt": v[1]}
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    df.index = pd.to_datetime(df.index)
    def ser(name, f=lambda v: v):
        s = {d: f(v) for d, v in (c.get(name) or {}).items() if v is not None}
        s = pd.Series(s); s.index = pd.to_datetime(s.index)
        return s.sort_index().reindex(df.index)
    df["margin"] = ser("margin", lambda v: v.get("margin") if isinstance(v, dict) else v)
    df["daytrade"] = ser("daytrade")
    df["fut_oi"] = ser("fut_oi")
    return df


def build(df):
    p = pd.DataFrame(index=df.index)
    amt20 = df["amt"].rolling(20).mean()
    # 1) 融資餘額 ÷ 20 日均成交值 —— 規模分母
    if df["margin"].notna().sum() > WINDOW:
        p["融資強度"] = rank_trailing(df["margin"] / amt20)
    # 2) 當沖占市場比重（本身即比率）
    if df["daytrade"].notna().sum() > WINDOW:
        p["當沖熱度"] = rank_trailing(df["daytrade"])
    # 3) 外資期貨未平倉淨額 ÷ 自身 250 日絕對值均值（退援分母）
    if df["fut_oi"].notna().sum() > WINDOW:
        p["外資期貨"] = rank_trailing(df["fut_oi"] / df["fut_oi"].abs().rolling(250).mean())
    return p


def extremes(s, tail=TAIL):
    r = rank_trailing(s.dropna(), WINDOW)
    return (r <= tail).reindex(s.index, fill_value=False), \
           (r >= 100 - tail).reindex(s.index, fill_value=False)


def ann(r): return (1 + r).prod() ** (252 / max(len(r), 1)) - 1
def sharpe(r): return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float("nan")
def mdd(r):
    cu = (1 + r).cumprod(); return float((cu / cu.cummax() - 1).min())


def main(cache_dir):
    df = panel(cache_dir)
    parts = build(df)
    if parts.empty:
        print("**沒有任何一項籌碼成分累積到足夠長度（需 > 750 個交易日）——先跑 --fetch**")
        return
    px = df["px"]
    print(f"樣本 {px.index[0].date()} → {px.index[-1].date()}　{len(px)} 個交易日")
    print("可用成分：" + "、".join(parts.columns) +
          f"（設計書列 3 項，本次 {len(parts.columns)} 項）\n")
    for c in parts.columns:
        print(f"  {c}: 有值 {int(parts[c].notna().sum())} 筆")

    sig = {"合成籌碼": composite(parts)}
    for c in parts.columns: sig[f"單項·{c}"] = parts[c]
    sig = pd.DataFrame(sig)

    print("\n" + "=" * 88); print("T1（區塊自助法．含檢定力）"); print("=" * 88)
    rows = []
    for name in sig.columns:
        lo, hi = extremes(sig[name])
        for mask, tag in ((lo, "極端恐懼"), (hi, "極端貪婪")):
            eps = episodes(mask, GAP)
            for h in HORIZONS:
                fwd = fwd_returns(px, h)
                n_ind = len(independent(eps, px.index, h))
                pt, l, u = circular_block_boot(mask.values, fwd.values, h)
                mde = min_detectable(fwd.values, n_ind)
                rows.append(dict(訊號=f"{name}·{tag}", 天期=h, 極端日=int(mask.sum()),
                                 獨立事件=n_ind,
                                 點估計pp=None if pt is None else round(pt*100, 2),
                                 CI下界=None if l is None else round(l*100, 2),
                                 CI上界=None if u is None else round(u*100, 2),
                                 最小可測pp=None if mde is None else round(mde*100, 1),
                                 結論=verdict(pt, l, u, mde, TARGET)))
    t1 = pd.DataFrame(rows); print(t1.to_string(index=False))

    print("\n" + "=" * 88); print(f"T2／T3 擇時（含成本 {COST*100:.3f}% 來回）"); print("=" * 88)
    split = px.index[int(len(px) * 0.6)]
    r = px.pct_change().fillna(0)
    res = {}
    for name in sig.columns:
        lo, hi = extremes(sig[name])
        w = pd.Series(0.75, index=px.index); w[hi] = 0.5; w[lo] = 1.0
        w = w.shift(1).fillna(0.75)
        s = w * r - w.diff().abs().fillna(0) * COST
        res[name] = (sharpe(s.loc[:split]), sharpe(s.loc[split:]), mdd(s.loc[split:]))
    bh = (sharpe(r.loc[:split]), sharpe(r.loc[split:]), mdd(r.loc[split:]))
    print(f"{'訊號':<16}{'樣本內 Sharpe':>14}{'樣本外 Sharpe':>14}{'樣本外 MDD':>12}")
    print(f"{'買進持有':<16}{bh[0]:>14.2f}{bh[1]:>14.2f}{bh[2]*100:>11.1f}%")
    for k, v in res.items():
        print(f"{k:<16}{v[0]:>14.2f}{v[1]:>14.2f}{v[2]*100:>11.1f}%")
    best_single = max((v[1] for k, v in res.items() if k.startswith("單項")), default=None)
    if best_single is not None and "合成籌碼" in res:
        print(f"\nT3 判準：合成樣本外 Sharpe {res['合成籌碼'][1]:.2f} vs "
              f"最好的單項 {best_single:.2f} → "
              f"{'合成有加值' if res['合成籌碼'][1] > best_single else '**合成沒有加值**'}")

    print("\n" + "=" * 88); print("T4 稀有度與時效性"); print("=" * 88)
    yrs = (px.index[-1] - px.index[0]).days / 365.25
    for name in sig.columns:
        lo, hi = extremes(sig[name])
        for mask, tag, side in ((lo, "極端恐懼", "low"), (hi, "極端貪婪", "high")):
            eps = episodes(mask, GAP)
            if not eps: continue
            pos = {d: i for i, d in enumerate(px.index)}
            lags = []
            for st, _, _ in eps:
                i = pos[st]; seg = px.iloc[max(0, i-60): i+61]
                lags.append(i - pos[seg.idxmin() if side == "low" else seg.idxmax()])
            print(f"{name}·{tag}: 事件 {len(eps)}、每年 {len(eps)/yrs:.2f} 次、"
                  f"中位持續 {int(np.median([e[2] for e in eps]))} 日、"
                  f"極端日佔比 {mask.mean()*100:.1f}%、相對轉折中位 {int(np.median(lags))} 日")

    out = os.path.join(cache_dir, "tw_results.json")
    json.dump({"T1": t1.to_dict("records"),
               "T2": {k: [round(x, 3) if x == x else None for x in v] for k, v in res.items()},
               "買進持有": [round(x, 3) for x in bh],
               "樣本": [str(px.index[0].date()), str(px.index[-1].date())],
               "成分": list(parts.columns)}, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"\n結果寫到 {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/sent-cache"))
