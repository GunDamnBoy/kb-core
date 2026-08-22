#!/usr/bin/env python3
"""台股籌碼的成分建構與回測。跑在 tw_probe.py 的快取上。

## 頻率必須跟抓取一致（2026-08-22 訂正）

上一版把面板建成**日頻**（約 3,083 天），而 `--weekly` 抓到的是**週頻**（652 筆）。
於是 750 列的滾動視窗**永遠湊不滿 750 個觀測**，百分位全部回 NaN，
當沖那項更直接被 `651 < 750` 的門檻擋掉——**輸出是一張看起來完整的空表**，
每一格都寫「樣本不足以判定」，讀起來像結論。

> **抓取的頻率與分析的頻率不一致，會安靜地產出一張全空但格式正確的表。**

修法：**面板建在「實際有資料的日期」上**，視窗以那個頻率計（週頻 156＝3 年），
前瞻天期也改成週。與 CFTC 那組同尺度，兩邊直接可比。

## 規模分母規則（設計書第十五節）

每一個部位或流量變數都要除以規模分母。不除，量到的是市場自己在長大。
台股市值二十年翻了好幾倍，「融資餘額創新高」多數時候只是市值創新高的影子。

- 融資餘額 ÷ 20 期均成交值
- 當沖占比本身就是比率，不需要分母
- 外資期貨未平倉淨額 ÷ 自身 50 期絕對值均值（拿不到全市場未平倉總量時的退援）
"""
from __future__ import annotations
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing, composite, episodes, independent
from blockstats import circular_block_boot, min_detectable, verdict

TARGET = 0.03
TAIL, GAP = 10.0, 1
COST = 0.00585          # 台股來回：手續費 0.1425%×2 ＋ 證交稅 0.3%


def load_cache(cache_dir):
    return json.load(open(os.path.join(cache_dir, "tw.json"), encoding="utf-8"))


def panel(c):
    """**面板建在實際有資料的日期上**，不是所有交易日。"""
    px_all = {}
    for _, mon in (c.get("index") or {}).items():
        for d, v in mon.items():
            if v and v[0]: px_all[d] = (v[0], v[1])
    px_all = pd.DataFrame.from_dict(px_all, orient="index", columns=["px", "amt"]).sort_index()
    px_all.index = pd.to_datetime(px_all.index)

    def ser(name, f):
        raw = {d: f(v) for d, v in (c.get(name) or {}).items() if v is not None}
        raw = {d: x for d, x in raw.items() if x is not None}
        if not raw: return pd.Series(dtype=float)
        s = pd.Series(raw); s.index = pd.to_datetime(s.index)
        return s.sort_index()

    cols = {
        "margin":   ser("margin", lambda v: v.get("margin") if isinstance(v, dict) else v),
        "daytrade": ser("daytrade", lambda v: v),
        "fut_oi":   ser("fut_oi", lambda v: v),
    }
    have = {k: v for k, v in cols.items() if len(v) >= 60}
    if not have:
        return None, None, {k: len(v) for k, v in cols.items()}

    # 取樣日期＝所有成分日期的聯集，且必須有指數
    idx = sorted(set().union(*[set(v.index) for v in have.values()]) & set(px_all.index))
    df = px_all.loc[idx].copy()
    for k, v in have.items():
        df[k] = v.reindex(idx)

    # **強制均勻頻率。** 先前中止的日頻抓取在早期留下密集的點，
    # 於是「156 期視窗」在後段是 3 年、在前段只有 7 個月——
    # **同一個「3 年百分位」在樣本裡代表不同的東西，而表面上完全看不出來。**
    gaps = pd.Series(df.index).diff().dt.days.dropna()
    if len(gaps) and gaps.median() <= 3 < gaps.quantile(0.9):
        pass                                   # 本來就密，不動
    wk = df.index.to_series().dt.to_period("W")
    df = df.groupby(wk).last()
    df.index = df.index.to_timestamp(how="end").normalize()
    return df, {k: len(v) for k, v in cols.items()}, None


def build(df, win):
    p = pd.DataFrame(index=df.index)
    amt20 = df["amt"].rolling(20, min_periods=5).mean()
    if "margin" in df and df["margin"].notna().sum() > win:
        p["融資強度"] = rank_trailing(df["margin"] / amt20, win)
    if "daytrade" in df and df["daytrade"].notna().sum() > win:
        p["當沖熱度"] = rank_trailing(df["daytrade"], win)
    if "fut_oi" in df and df["fut_oi"].notna().sum() > win:
        base = df["fut_oi"].abs().rolling(50, min_periods=10).mean()
        p["外資期貨"] = rank_trailing(df["fut_oi"] / base, win)
    return p.dropna(how="all", axis=1)


def extremes(s, win, tail=TAIL):
    r = rank_trailing(s.dropna(), win)
    return (r <= tail).reindex(s.index, fill_value=False), \
           (r >= 100 - tail).reindex(s.index, fill_value=False)


def sharpe(x, per): return x.mean() / x.std() * np.sqrt(per) if x.std() > 0 else float("nan")
def mdd(x):
    c = (1 + x).cumprod(); return float((c / c.cummax() - 1).min())


def mae(px, starts, h):
    """買進後窗內的最大不利變動——「還要再痛多久」。"""
    pos = {d: i for i, d in enumerate(px.index)}
    out = []
    for d in starts:
        i = pos.get(d)
        if i is None or i + h >= len(px): continue
        out.append(float(px.iloc[i:i + h + 1].min() / px.iloc[i] - 1))
    return out


def main(cache_dir):
    c = load_cache(cache_dir)
    df, counts, err = panel(c)
    print("快取筆數：" + "、".join(f"{k}={v}" for k, v in (counts or err).items()))
    if df is None:
        print("**沒有任何成分累積到 60 筆以上——先跑 --fetch**"); return

    gaps = pd.Series(df.index).diff().dt.days.dropna()
    weekly = True if gaps.median() >= 5 else gaps.median() > 3
    win = 156 if weekly else 750
    per = 52 if weekly else 252
    HOR = (4, 13, 26, 52) if weekly else (21, 63, 126, 252)
    unit = "週" if weekly else "日"
    print(f"面板 {df.index[0].date()} → {df.index[-1].date()}　{len(df)} 筆"
          f"　中位間隔 {gaps.median():.0f} 天 → **{'週頻' if weekly else '日頻'}**"
          f"　視窗 {win} {unit}（3 年）\n")

    parts = build(df, win)
    if parts.empty or not len(parts.columns):
        print(f"**沒有成分通過 {win} 筆的熱身門檻。** 各成分有效筆數：")
        for k in ("margin", "daytrade", "fut_oi"):
            if k in df: print(f"  {k}: {int(df[k].notna().sum())}")
        print(f"→ 需要 > {win} 筆才發分數（熱身期不縮短，縮短會讓前後不可比）")
        return
    print("可用成分：" + "、".join(f"{c_}（{int(parts[c_].notna().sum())} 筆）"
                                  for c_ in parts.columns))

    px = df["px"]
    sig = {"合成籌碼": composite(parts)} if len(parts.columns) > 1 else {}
    for c_ in parts.columns: sig[f"單項·{c_}"] = parts[c_]
    sig = pd.DataFrame(sig)

    print("\n" + "=" * 92); print("T1（區塊自助法．含檢定力）"); print("=" * 92)
    rows = []
    for name in sig.columns:
        lo, hi = extremes(sig[name], win)
        for m, tag in ((lo, "極端恐懼"), (hi, "極端貪婪")):
            eps = episodes(m, GAP)
            for h in HOR:
                fwd = (px.shift(-h) / px - 1)
                n_ind = len(independent(eps, px.index, h))
                pt, l, u = circular_block_boot(m.values, fwd.values, h)
                md = min_detectable(fwd.values, n_ind)
                rows.append(dict(訊號=f"{name}·{tag}", 期=h, 極端=int(m.sum()), 獨立事件=n_ind,
                                 點估計pp=None if pt is None else round(pt*100, 2),
                                 CI下界=None if l is None else round(l*100, 2),
                                 CI上界=None if u is None else round(u*100, 2),
                                 最小可測pp=None if md is None else round(md*100, 1),
                                 結論=verdict(pt, l, u, md, TARGET, n_ind)))
    t1 = pd.DataFrame(rows); print(t1.to_string(index=False))

    print("\n" + "=" * 92); print(f"T2／T3 擇時（含成本 {COST*100:.3f}%）"); print("=" * 92)
    cut = int(len(px) * 0.6); r = px.pct_change().fillna(0)
    ma = px.rolling(10 if weekly else 20).mean()
    wma = pd.Series(0.75, index=px.index); wma[px > ma] = 1.0; wma[px < ma] = 0.5
    sma = wma.shift(1).fillna(0.75) * r - wma.shift(1).fillna(0.75).diff().abs().fillna(0) * COST
    print(f"{'訊號':<16}{'內':>8}{'外':>8}{'外 MDD':>10}")
    print(f"{'買進持有':<16}{sharpe(r.iloc[:cut], per):>8.2f}{sharpe(r.iloc[cut:], per):>8.2f}"
          f"{mdd(r.iloc[cut:])*100:>9.1f}%")
    print(f"{'純均線（對照）':<16}{sharpe(sma.iloc[:cut], per):>8.2f}"
          f"{sharpe(sma.iloc[cut:], per):>8.2f}{mdd(sma.iloc[cut:])*100:>9.1f}%")
    res = {}
    for name in sig.columns:
        lo, hi = extremes(sig[name], win)
        w = pd.Series(0.75, index=px.index); w[hi] = 0.5; w[lo] = 1.0
        w = w.shift(1).fillna(0.75)
        s = w * r - w.diff().abs().fillna(0) * COST
        res[name] = sharpe(s.iloc[cut:], per)
        print(f"{name:<16}{sharpe(s.iloc[:cut], per):>8.2f}{res[name]:>8.2f}"
              f"{mdd(s.iloc[cut:])*100:>9.1f}%")
    singles = [v for k, v in res.items() if k.startswith("單項")]
    if "合成籌碼" in res and singles:
        print(f"\nT3：合成 {res['合成籌碼']:.2f} vs 最好的單項 {max(singles):.2f} → "
              f"{'合成有加值' if res['合成籌碼'] > max(singles) else '**合成沒有加值**'}")
    print(f"對照：任何規則都要贏過純均線 {sharpe(sma.iloc[cut:], per):.2f}")

    print("\n" + "=" * 92); print("MAE 與恐懼／貪婪不對稱"); print("=" * 92)
    h = HOR[1]
    for name in sig.columns:
        lo, hi = extremes(sig[name], win)
        eps = episodes(lo, GAP); st = independent(eps, px.index, h)
        m = mae(px, st, h)
        fwd = (px.shift(-h) / px - 1)
        ef, _, _ = circular_block_boot(lo.values, fwd.values, h)
        eg, _, _ = circular_block_boot(hi.values, fwd.values, h)
        line = f"  {name:<16}"
        line += (f"MAE 中位 {np.median(m)*100:>6.1f}%（n={len(m)}）"
                 if len(m) >= 3 else f"MAE 樣本不足（n={len(m)}）")
        if ef is not None and eg is not None:
            line += f"　恐懼 {ef*100:>6.2f}pp　貪婪 {eg*100:>6.2f}pp　差 {(ef-eg)*100:>6.2f}pp"
        print(line)

    out = os.path.join(cache_dir, "tw_results.json")
    json.dump({"T1": t1.to_dict("records"), "T2": {k: round(v, 3) for k, v in res.items()},
               "頻率": "週" if weekly else "日", "視窗": win,
               "樣本": [str(df.index[0].date()), str(df.index[-1].date())],
               "成分": list(parts.columns)}, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"\n結果寫到 {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/sent-cache"))
