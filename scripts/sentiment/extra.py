#!/usr/bin/env python3
"""兩個補測：(A) 1990 起的月頻長樣本；(B) CAPE 分層；(C) 共識門與隨機權重。

(A) 是這次最重要的一項。日頻樣本 2011–2026 幾乎整段是多頭
（買進持有年化 13%），**在那種樣本裡任何「減碼」規則都一定輸**——
那不是指標沒用的證據，是樣本說不出話。月頻樣本回到 1990，
才涵蓋得到 2000、2008 這兩次真的熊市。
"""
import sys, numpy as np, pandas as pd
from scipy.stats import mannwhitneyu
sys.path.insert(0, "/tmp/sent/eng")
from core import rank_trailing, episodes, independent
from loaddata import load

D = "/tmp"

def monthly_panel():
    sh = pd.read_csv(f"{D}/ds_s-and-p-500/data/data.csv", parse_dates=["Date"]).set_index("Date")
    px = pd.to_numeric(sh["SP500"], errors="coerce").dropna()
    cape = pd.to_numeric(sh["PE10"], errors="coerce").replace(0, np.nan)
    vm = pd.read_csv(f"{D}/ds_finance-vix/data/vix-monthly.csv", parse_dates=[0], index_col=0).iloc[:, -1]
    df = pd.DataFrame({"px": px, "cape": cape})
    df["vix"] = vm.reindex(df.index, method="nearest", tolerance=pd.Timedelta("20D"))
    return df.dropna(subset=["px", "vix"])


def t1_monthly(df, sig, mask, label, horizons=(1, 3, 6, 12)):
    px = df["px"]; rows = []
    eps = episodes(mask, 1)
    for h in horizons:
        fwd = px.shift(-h) / px - 1
        starts = independent(eps, px.index, h)
        v = [fwd.get(d) for d in starts]; v = [x for x in v if x == x and x is not None]
        base = fwd.dropna()
        if len(v) < 2: rows.append(dict(訊號=label, 月=h, 樣本=len(v))); continue
        u, p = mannwhitneyu(v, base, alternative="two-sided")
        rows.append(dict(訊號=label, 月=h, 觸發=len(eps), 獨立事件=len(starts), 樣本=len(v),
                         中位數=round(np.median(v)*100, 2), 基準=round(base.median()*100, 2),
                         差=round((np.median(v)-base.median())*100, 2), p=round(float(p), 4),
                         勝率=round(float(np.mean(np.array(v) > 0))*100, 0)))
    return pd.DataFrame(rows)


def main():
    print("="*78); print("(A) 月頻長樣本：1990 → 2026，含 2000 與 2008"); print("="*78)
    m = monthly_panel()
    print(f"樣本 {m.index[0].date()} → {m.index[-1].date()}  共 {len(m)} 個月")
    sig = rank_trailing(m["vix"], 36, invert=True)          # 36 個月 ＝ 3 年，與日頻同尺度
    lo, hi = sig <= 10, sig >= 90
    print(f"極端恐懼 {int(lo.sum())} 個月、極端貪婪 {int(hi.sum())} 個月\n")
    out = pd.concat([t1_monthly(m, sig, lo, "VIX情緒·極端恐懼"),
                     t1_monthly(m, sig, hi, "VIX情緒·極端貪婪")], ignore_index=True)
    print(out.to_string(index=False))

    print("\n" + "="*78); print("(B) CAPE 分層：同樣是極端恐懼，估值高低差多少"); print("="*78)
    cape_hi = m["cape"] >= m["cape"].rolling(240, min_periods=60).median()
    for tag, mask in (("極端恐懼", lo), ("極端貪婪", hi)):
        for cl, cn in ((cape_hi, "CAPE 高於長期中位"), (~cape_hi, "CAPE 低於長期中位")):
            mm = mask & cl
            eps = episodes(mm, 1); starts = independent(eps, m.index, 12)
            fwd = m["px"].shift(-12)/m["px"] - 1
            v = [fwd.get(d) for d in starts]; v = [x for x in v if x == x and x is not None]
            if len(v) < 2: print(f"{tag:<6} {cn:<16} 樣本不足 (n={len(v)})"); continue
            print(f"{tag:<6} {cn:<16} 獨立事件 {len(starts):>2}  12個月中位報酬 {np.median(v)*100:>6.2f}%  "
                  f"勝率 {np.mean(np.array(v)>0)*100:>3.0f}%")

    print("\n" + "="*78); print("(C) 共識門 與 隨機權重"); print("="*78)
    from backtest import build, extremes, t1, ann, sharpe, mdd, COST
    from core import consensus
    d = load(); parts, sg = build(d); px = d["px"]
    cs = consensus(parts, tail=10.0)
    lo2, hi2 = cs <= -2, cs >= 2                     # 3 項裡有 ≥2 項同側極端
    print(f"共識門（3 項裡 ≥2 項同側）：恐懼 {int(lo2.sum())} 日、貪婪 {int(hi2.sum())} 日")
    print(t1(px, lo2, "共識門·極端恐懼").to_string(index=False))
    print(t1(px, hi2, "共識門·極端貪婪").to_string(index=False))

    rng = np.random.default_rng(0); real = None; sh_list = []
    r = px.pct_change().fillna(0)
    for k in range(300):
        w = rng.dirichlet(np.ones(parts.shape[1])) if k else np.ones(parts.shape[1])/parts.shape[1]
        comp = (parts * w).sum(axis=1, min_count=1)
        p = rank_trailing(comp.dropna(), 750).reindex(px.index)
        pos = pd.Series(0.75, index=px.index); pos[p >= 90] = 0.5; pos[p <= 10] = 1.0
        pos = pos.shift(1).fillna(0.75)
        s = pos*r - pos.diff().abs().fillna(0)*COST
        if k == 0: real = sharpe(s)
        else: sh_list.append(sharpe(s))
    pct = float(np.mean(np.array(sh_list) < real))*100
    print(f"\n等權 Sharpe {real:.3f}；300 組隨機權重的中位數 {np.median(sh_list):.3f}；"
          f"等權排在第 {pct:.0f} 百分位")
    print(f"（買進持有 Sharpe {sharpe(r):.3f}）")

if __name__ == "__main__":
    main()
