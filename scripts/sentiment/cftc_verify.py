#!/usr/bin/env python3
"""把 cftc_probe 那張表放進顯微鏡。**這支才是判準，前一支只是產生假設。**

用法：python3 cftc_verify.py

## 為什麼一定要有這一支

`cftc_probe.py` 跑了 **22 個訊號 × 4 個天期 × 2 側 ＝ 176 個檢定**，
用的是 90% 信賴區間。**在完全沒有效果的世界裡，光是碰運氣就會有大約 17.6 個
「區間不含 0」。** 實際數出來是 20 個。

> **20 跟 17.6 之間的差距，不足以支撐任何結論。**
> 只挑通過的那幾行來看，就是在對雜訊命名。

但那張表裡有一件**雜訊做不出來**的事：符號是**按經濟家族分群**的 ——
槓桿基金那一族全部是「貪婪之後漲更多」（動能），
資產管理那一族全部是「貪婪之後漲更少」（逆勢）。
隨機雜訊不會照「避險基金 vs 長線基金」這條線排隊。

**所以要問的不是「哪幾格顯著」，是「這個分群結構本身，雜訊做得出來嗎」。**
這一支用三件事回答：

1. **置換檢定**：把訊號做環狀位移（保留自相關結構）重算，看 176 格裡
   「顯著」的格數在虛無分佈裡排第幾。
2. **家族層級的合併檢定**：把 176 個檢定收斂成 **2 個假設**
   （槓桿基金＝動能、資產管理＝逆勢），多重比較的問題就消失了。
3. **樣本外**：前 60% 看到的結構，後 40% 還在嗎。

## 順帶訂正前一支的一個顯示缺陷

前一支把「最小可測效果」跟「區塊自助法信賴區間」並排顯示，
**但那是兩把不同的尺**：前者算的是丟到只剩獨立事件之後的檢定力，
後者用的是全部極端週。於是會出現「點估計 5.36 低於最小可測 13，但區間不含 0」
這種讀起來自相矛盾的列。這裡改用**同一套置換分佈**產生 p 值，一把尺量到底。
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing, composite
import cftc_probe as P

NPERM = 2000
COST = 0.0005
HOR = (4, 13, 26, 52)


def effect(mask: np.ndarray, fwd: np.ndarray) -> float:
    """極端週的前瞻報酬中位數 減 全樣本中位數。"""
    ok = ~np.isnan(fwd)
    m, f = mask[ok].astype(bool), fwd[ok]
    if m.sum() < 3: return np.nan
    return float(np.median(f[m]) - np.median(f))


def perm_p(mask: np.ndarray, fwd: np.ndarray, nperm=NPERM, seed=0):
    """環狀位移置換檢定。**位移保留訊號自身的自相關**，
    所以虛無分佈裡的「訊號」跟真的一樣黏，只是對錯了時間。"""
    obs = effect(mask, fwd)
    if obs != obs: return np.nan, np.nan
    rng = np.random.default_rng(seed)
    n = len(mask)
    null = np.empty(nperm)
    for i in range(nperm):
        null[i] = effect(np.roll(mask, int(rng.integers(1, n))), fwd)
    null = null[~np.isnan(null)]
    if len(null) < nperm * 0.5: return obs, np.nan
    p = float(np.mean(np.abs(null) >= abs(obs)))
    return obs, p


def build():
    rows = []
    for y in P.YEARS:
        rows += P.load_year(y)
    df = pd.DataFrame(rows)
    piv = df.pivot_table(index="d", columns="c", values=["am", "lm"], aggfunc="last").sort_index()
    parts = pd.DataFrame(index=piv.index)
    for c in ("ES", "NQ", "RTY"):
        if ("lm", c) in piv: parts[f"LM·{c}"] = rank_trailing(piv[("lm", c)], P.WINDOW_W)
        if ("am", c) in piv: parts[f"AM·{c}"] = rank_trailing(piv[("am", c)], P.WINDOW_W)
    if ("lm", "VX") in piv:
        parts["LM·VIX"] = rank_trailing(piv[("lm", "VX")], P.WINDOW_W, invert=True)
    px = P.prices().reindex(piv.index, method="ffill")
    return parts.dropna(how="all", axis=1), px


def masks(sig, px):
    r = rank_trailing(sig.dropna(), P.WINDOW_W)
    lo = (r <= 10).reindex(px.index, fill_value=False).shift(1).fillna(False)
    hi = (r >= 90).reindex(px.index, fill_value=False).shift(1).fillna(False)
    return lo.values, hi.values


def main():
    print("讀 CFTC 快取…")
    parts, px = build()
    LM = [c for c in parts.columns if c.startswith("LM")]
    AM = [c for c in parts.columns if c.startswith("AM")]
    print(f"面板 {px.index[0].date()} → {px.index[-1].date()}　{len(px)} 週")
    print(f"槓桿基金 {len(LM)} 項、資產管理 {len(AM)} 項\n")

    sigs = {c: parts[c] for c in parts.columns}
    sigs["槓桿基金合成"] = composite(parts[LM])
    sigs["資產管理合成"] = composite(parts[AM])
    sigs["全部合成"] = composite(parts)
    fwds = {h: (px.shift(-h) / px - 1).values for h in HOR}

    # ---------- 1. 全表置換檢定 ----------
    print("=" * 86)
    print("一、全表置換檢定：顯著的格數，跟雜訊比起來多不多")
    print("=" * 86)
    recs = []
    for name, s in sigs.items():
        lo, hi = masks(s, px)
        for side, m in (("恐懼", lo), ("貪婪", hi)):
            for h in HOR:
                e, p = perm_p(m, fwds[h], seed=abs(hash((name, side, h))) % 10**6)
                recs.append(dict(訊號=name, 側=side, 週=h, 效果pp=None if e != e else round(e*100, 2),
                                 置換p=None if p != p else round(p, 4)))
    T = pd.DataFrame(recs).dropna(subset=["置換p"])
    k = int((T["置換p"] < 0.10).sum()); n = len(T)
    print(f"檢定數 {n}，置換 p < 0.10 的有 **{k}** 格；純雜訊的期望值約 {n*0.10:.1f} 格")
    print(f"→ {'高於期望，值得往下看' if k > n*0.10*1.4 else '**與雜訊差不多——單看格數不能下結論**'}\n")

    # ---------- 2. 家族層級：176 個檢定收斂成 2 個 ----------
    print("=" * 86)
    print("二、家族層級合併檢定：176 個假設收斂成 2 個，多重比較問題消失")
    print("=" * 86)

    def family_stat(cols, side, hs=(13, 26, 52)):
        """一族的合併效果：該族每個成分、每個天期的效果取平均。"""
        vals = []
        for c in cols:
            lo, hi = masks(parts[c], px)
            m = hi if side == "貪婪" else lo
            for h in hs:
                e = effect(m, fwds[h])
                if e == e: vals.append(e)
        return float(np.mean(vals)) if vals else np.nan

    def family_perm(cols, side, hs=(13, 26, 52), nperm=600, seed=7):
        obs = family_stat(cols, side, hs)
        rng = np.random.default_rng(seed)
        cache = {c: masks(parts[c], px) for c in cols}
        null = []
        for _ in range(nperm):
            sh = int(rng.integers(1, len(px)))
            vals = []
            for c in cols:
                lo, hi = cache[c]
                m = np.roll(hi if side == "貪婪" else lo, sh)
                for h in hs:
                    e = effect(m, fwds[h])
                    if e == e: vals.append(e)
            if vals: null.append(np.mean(vals))
        null = np.array(null)
        return obs, float(np.mean(np.abs(null) >= abs(obs))) if len(null) else np.nan

    print(f"{'家族':<12}{'側':<6}{'合併效果':>10}{'置換 p':>10}   解讀")
    print("-" * 76)
    out2 = {}
    for cols, fam in ((LM, "槓桿基金"), (AM, "資產管理")):
        for side in ("恐懼", "貪婪"):
            o, p = family_perm(cols, side)
            out2[(fam, side)] = (o, p)
            tag = ("動能" if o > 0 else "逆勢") if side == "貪婪" else ("逆勢" if o > 0 else "動能")
            sig = "**顯著**" if p < 0.10 else "不顯著"
            print(f"{fam:<12}{side:<6}{o*100:>9.2f}pp{p:>10.3f}   {tag}／{sig}")

    print("\n兩族方向是否相反（這是合成分數把訊號洗掉的原因）：")
    for side in ("恐懼", "貪婪"):
        a, b = out2[("槓桿基金", side)][0], out2[("資產管理", side)][0]
        print(f"  {side}：槓桿基金 {a*100:+.2f}pp vs 資產管理 {b*100:+.2f}pp"
              f"　→ {'**方向相反，平均會互相抵銷**' if a*b < 0 else '同向'}")

    # ---------- 3. 樣本外 ----------
    print("\n" + "=" * 86)
    print("三、樣本外：前 60% 看到的結構，後 40% 還在嗎")
    print("=" * 86)
    cut = int(len(px) * 0.6)
    for cols, fam in ((LM, "槓桿基金"), (AM, "資產管理")):
        for side in ("恐懼", "貪婪"):
            res = []
            for seg, lab in ((slice(0, cut), "樣本內"), (slice(cut, None), "樣本外")):
                vals = []
                for c in cols:
                    lo, hi = masks(parts[c], px)
                    m = (hi if side == "貪婪" else lo)[seg]
                    for h in (13, 26):
                        e = effect(m, fwds[h][seg])
                        if e == e: vals.append(e)
                res.append(np.mean(vals) * 100 if vals else float("nan"))
            keep = "符號一致" if res[0] * res[1] > 0 else "**符號翻面**"
            print(f"{fam}·{side}：樣本內 {res[0]:+.2f}pp　樣本外 {res[1]:+.2f}pp　{keep}")

    # ---------- 4. T2／T3 ----------
    print("\n" + "=" * 86)
    print(f"四、T2／T3 擇時（含成本 {COST*100:.2f}%）")
    print("=" * 86)
    r = px.pct_change().fillna(0)
    def sharpe(x): return x.mean() / x.std() * np.sqrt(52) if x.std() > 0 else float("nan")
    idx = px.index; sp = idx[cut]
    print(f"{'訊號':<14}{'樣本內':>10}{'樣本外':>10}")
    print(f"{'買進持有':<14}{sharpe(r.iloc[:cut]):>10.2f}{sharpe(r.iloc[cut:]):>10.2f}")
    best = -9
    for name in ["槓桿基金合成", "資產管理合成", "全部合成"] + list(parts.columns):
        lo, hi = masks(sigs[name] if name in sigs else parts[name], px)
        w = pd.Series(0.75, index=idx); w[hi] = 0.5; w[lo] = 1.0
        s = w * r - w.diff().abs().fillna(0) * COST
        a, b = sharpe(s.iloc[:cut]), sharpe(s.iloc[cut:])
        if not name.endswith("合成"): best = max(best, b)
        print(f"{name:<14}{a:>10.2f}{b:>10.2f}")
    print("\nT3 判準看上表：「合成」那三列的樣本外 Sharpe 要贏過所有單項與買進持有；"
          "輸了就是合成沒有加值。")

    T.to_csv(os.path.join(P.CACHE, "cftc_perm.csv"), index=False)
    print(f"\n置換檢定明細寫到 {os.path.join(P.CACHE, 'cftc_perm.csv')}")


if __name__ == "__main__":
    main()
