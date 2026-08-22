#!/usr/bin/env python3
"""T1–T4 四項測試。**判準寫在前面，事後補寫的失敗判準沒有拘束力。**

比較的公平性：所有訊號都用**同一個觸發頻率**（自己分佈的前/後 X%）定義極端，
這樣「它比較常觸發」就不會混進結論裡。
"""
import sys, json, numpy as np, pandas as pd
from scipy.stats import mannwhitneyu
sys.path.insert(0, "/tmp/sent/eng")
from core import rank_trailing, composite, consensus, episodes, independent, fwd_returns, WINDOW
from loaddata import load

HORIZONS = [21, 63, 126, 252]
TAIL = 10.0            # 極端 = 訊號自己滾動分佈的前/後 10%
GAP = 3                # episode 合併容許的空檔（交易日）
COST = 0.0005          # 美股來回成本
OOS_FRAC = 0.40


def build(df):
    px, vix = df["px"], df["vix"]
    parts = pd.DataFrame(index=df.index)
    parts["動能"]    = rank_trailing(px / px.rolling(125).mean() - 1)
    parts["波動"]    = rank_trailing(vix / vix.rolling(50).mean() - 1, invert=True)
    rv = np.log(px).diff().rolling(20).std() * np.sqrt(252)
    parts["已實現波動"] = rank_trailing(rv, invert=True)
    sig = {}
    sig["合成3項"] = composite(parts)
    for c in parts.columns:
        sig[f"單項·{c}"] = parts[c]
    sig["CNN F&G"] = df["fg"]
    return parts, pd.DataFrame(sig)


def extremes(s, tail=TAIL):
    """用訊號自己的滾動分佈定極端，兩邊都是 trailing，不偷看未來。"""
    p = rank_trailing(s.dropna(), WINDOW)
    return (p <= tail).reindex(s.index, fill_value=False), \
           (p >= 100 - tail).reindex(s.index, fill_value=False), p


def t1(px, mask, label, horizons=HORIZONS):
    eps = episodes(mask, GAP)
    rows = []
    for h in horizons:
        fwd = fwd_returns(px, h)
        starts = independent(eps, px.index, h)          # 出場端重疊也要合併
        vals = [fwd.get(d) for d in starts]
        vals = [v for v in vals if v == v and v is not None]
        base = fwd.dropna()
        if len(vals) < 2:
            rows.append(dict(訊號=label, 天期=h, 觸發次數=len(eps), 獨立事件=len(starts),
                             樣本=len(vals), 中位數=None, 基準中位數=round(base.median()*100,2),
                             差=None, p=None)); continue
        u, p = mannwhitneyu(vals, base, alternative="two-sided")
        rows.append(dict(訊號=label, 天期=h, 觸發次數=len(eps), 獨立事件=len(starts),
                         樣本=len(vals),
                         中位數=round(float(np.median(vals))*100, 2),
                         基準中位數=round(float(base.median())*100, 2),
                         差=round((float(np.median(vals))-float(base.median()))*100, 2),
                         p=round(float(p), 4)))
    return pd.DataFrame(rows)


def t2(px, lo, hi, split_at):
    """極端恐懼→滿倉、極端貪婪→半倉、其餘→0.75。含成本。"""
    w = pd.Series(0.75, index=px.index)
    w[hi] = 0.5; w[lo] = 1.0
    w = w.shift(1).fillna(0.75)                      # 訊號當天收盤才知道，隔天才建得了倉
    r = px.pct_change().fillna(0.0)
    turn = w.diff().abs().fillna(0.0)
    strat = w * r - turn * COST
    out = {}
    for name, sl in (("樣本內", slice(None, split_at)), ("樣本外", slice(split_at, None))):
        s, b = strat.loc[sl], r.loc[sl]
        out[name] = dict(策略年化=round(ann(s)*100, 2), 持有年化=round(ann(b)*100, 2),
                         策略Sharpe=round(sharpe(s), 2), 持有Sharpe=round(sharpe(b), 2),
                         策略MDD=round(mdd(s)*100, 1), 持有MDD=round(mdd(b)*100, 1),
                         換手次數=int((turn.loc[sl] > 0).sum()))
    return out


def ann(r):  return (1 + r).prod() ** (252 / max(len(r), 1)) - 1
def sharpe(r): return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float("nan")
def mdd(r):
    c = (1 + r).cumprod(); return float((c / c.cummax() - 1).min())


def t4(px, mask, label, side="low"):
    """side='low' 比對局部低點（恐懼側），'high' 比對局部高點（貪婪側）。

    兩邊都拿低點比是錯的——貪婪訊號該問的是「離頭部多遠」，不是「離底部多遠」。
    """
    eps = episodes(mask, GAP)
    if not eps: return dict(訊號=label, 事件數=0)
    yrs = (px.index[-1] - px.index[0]).days / 365.25
    pos = {d: i for i, d in enumerate(px.index)}
    lags, W = [], 60
    for st, _, _ in eps:
        i = pos[st]; seg = px.iloc[max(0, i-W): min(len(px), i+W+1)]
        ref = seg.idxmin() if side == "low" else seg.idxmax()
        lags.append(i - pos[ref])                     # 正＝訊號落後轉折點
    return dict(訊號=label, 事件數=len(eps), 每年次數=round(len(eps)/yrs, 2),
                中位持續天數=int(np.median([e[2] for e in eps])),
                極端日佔比=round(mask.mean()*100, 1),
                相對轉折中位落後日=int(np.median(lags)))


def near_miss(p, thr=TAIL, band=2.0):
    lo = ((p > thr) & (p <= thr + band)).sum(); hi = ((p < 100-thr) & (p >= 100-thr-band)).sum()
    return dict(門檻=thr, 擦邊帶=band, 恐懼側擦邊日=int(lo), 貪婪側擦邊日=int(hi))


def main():
    df = load()
    parts, sig = build(df)
    px = df["px"]
    split_at = px.index[int(len(px) * (1 - OOS_FRAC))]
    print(f"樣本 {px.index[0].date()} → {px.index[-1].date()}  共 {len(px)} 個交易日")
    print(f"熱身 {WINDOW} 日；樣本內／外切在 {split_at.date()}（樣本外 {OOS_FRAC:.0%}）\n")

    res = {"樣本": [str(px.index[0].date()), str(px.index[-1].date())],
           "切點": str(split_at.date()), "T1": [], "T2": {}, "T4": [], "擦邊": {}}

    print("=" * 78); print("T4 稀有度與時效性"); print("=" * 78)
    t4rows = []
    for name in sig.columns:
        lo, hi, p = extremes(sig[name])
        t4rows.append({**t4(px, lo, f"{name}·極端恐懼", "low")})
        t4rows.append({**t4(px, hi, f"{name}·極端貪婪", "high")})
        res["擦邊"][name] = near_miss(p)
    t4df = pd.DataFrame(t4rows); print(t4df.to_string(index=False)); res["T4"] = t4rows

    print("\n" + "=" * 78); print("T1 極端值之後的報酬分佈（獨立事件，%）"); print("=" * 78)
    allt1 = []
    for name in sig.columns:
        lo, hi, _ = extremes(sig[name])
        for m, tag in ((lo, "極端恐懼"), (hi, "極端貪婪")):
            r = t1(px, m, f"{name}·{tag}")
            allt1.append(r)
    t1df = pd.concat(allt1, ignore_index=True)
    print(t1df.to_string(index=False)); res["T1"] = t1df.to_dict("records")

    print("\n" + "=" * 78); print("T2 擇時 vs 買進持有（含成本 %.2f%% 來回）" % (COST*100)); print("=" * 78)
    for name in sig.columns:
        lo, hi, _ = extremes(sig[name])
        res["T2"][name] = t2(px, lo, hi, split_at)
        a, b = res["T2"][name]["樣本內"], res["T2"][name]["樣本外"]
        print(f"{name:<14} 內: 策略{a['策略年化']:>6}% / 持有{a['持有年化']:>6}%  "
              f"Sharpe {a['策略Sharpe']:>5} vs {a['持有Sharpe']:>5}   "
              f"外: 策略{b['策略年化']:>6}% / 持有{b['持有年化']:>6}%  "
              f"Sharpe {b['策略Sharpe']:>5} vs {b['持有Sharpe']:>5}  MDD {b['策略MDD']} vs {b['持有MDD']}")

    json.dump(res, open("/tmp/sent/results.json", "w"), ensure_ascii=False, indent=1, default=str)
    return sig, parts, df


if __name__ == "__main__":
    main()
