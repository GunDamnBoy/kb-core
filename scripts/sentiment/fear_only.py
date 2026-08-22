#!/usr/bin/env python3
"""恐懼側是不是真的比貪婪側有用。**這一支專門測那個不對稱。**

## 假設（使用者提的）

> 「貪婪是無限的，恐懼是有限的。牛熊指標拿去測低點會比較有用，
>   高點只會一直創高。」

理論上站得住：**VIX 有地板沒有天花板**。恐懼是**尖峰**（快速、均值回歸），
貪婪是**狀態**（緩慢、可持續數年）。這正好解釋前面 T2 為什麼一路輸——
「極端貪婪→減碼」不是在對事件動作，是在對狀態動作。

## 必須擋掉的混淆：多頭裡「逢低加碼」一定贏

2011–2026 的樣本裡指數漲了五倍多。**任何平均曝險高於買進持有的規則都會贏，
那是槓桿不是擇時。** 所以：

> **曝險對齊（exposure-matched）**：解出基準倉位，使整段期間的**平均曝險等於 1.0**，
> 與買進持有完全相同。這樣贏的部分只能來自「什麼時候多、什麼時候少」。

## 三個對照

1. 買進持有
2. 純 20 日均線（第三階段學到的——新規則裡若含舊的已知有效成分，功勞先歸舊的）
3. 恐懼側 vs 貪婪側的效果差，用置換檢定直接檢驗不對稱本身
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/sent/eng")
from core import rank_trailing, episodes, independent, fwd_returns, WINDOW
from blockstats import circular_block_boot, min_detectable, verdict
from loaddata import load
from backtest import build, TAIL, COST

BOOST = 0.5          # 恐懼時相對基準加多少曝險


def sharpe(x): return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")
def ann(x): return (1 + x).prod() ** (252 / max(len(x), 1)) - 1
def mdd(x):
    c = (1 + x).cumprod(); return float((c / c.cummax() - 1).min())


def matched(mask, target=1.0, boost=BOOST):
    """解出基準倉位使平均曝險 = target。**贏的部分只能來自時機，不能來自槓桿。**"""
    f = mask.astype(float)
    w0 = (target - boost * f.mean())
    return w0 + boost * f


def strat(w, r):
    w = w.shift(1).fillna(w.iloc[0])
    return w * r - w.diff().abs().fillna(0) * COST, w


def effect(mask, fwd):
    ok = ~np.isnan(fwd); m, f = mask[ok].astype(bool), fwd[ok]
    return float(np.median(f[m]) - np.median(f)) if m.sum() >= 3 else np.nan


def perm_gap(fear, greed, fwd, nperm=1500, seed=3):
    """恐懼效果 減 貪婪效果，用環狀位移檢定這個**差**本身。"""
    obs = effect(fear, fwd) - effect(greed, fwd)
    if obs != obs: return np.nan, np.nan
    rng = np.random.default_rng(seed); n = len(fear); null = []
    for _ in range(nperm):
        s = int(rng.integers(1, n))
        d = effect(np.roll(fear, s), fwd) - effect(np.roll(greed, s), fwd)
        if d == d: null.append(d)
    null = np.array(null)
    return obs, float(np.mean(np.abs(null) >= abs(obs))) if len(null) else np.nan


def mae(px, starts, h):
    """買進後在窗內的最大不利變動——「要再痛多久」。實務上比中位數報酬更有用。"""
    pos = {d: i for i, d in enumerate(px.index)}; out = []
    for d in starts:
        i = pos.get(d)
        if i is None or i + h >= len(px): continue
        seg = px.iloc[i:i + h + 1]
        out.append(float(seg.min() / px.iloc[i] - 1))
    return out


def main():
    df = load(); parts, sigs = build(df); px = df["px"]
    r = px.pct_change().fillna(0)
    cut = int(len(px) * 0.6); sp = px.index[cut]
    print(f"樣本 {px.index[0].date()} → {px.index[-1].date()}　樣本外自 {sp.date()}")
    print(f"買進持有樣本外：年化 {ann(r.iloc[cut:])*100:.1f}%、Sharpe {sharpe(r.iloc[cut:]):.2f}、"
          f"MDD {mdd(r.iloc[cut:])*100:.1f}%\n")

    print("=" * 96)
    print("一、恐懼側 vs 貪婪側：效果差本身顯不顯著（置換檢定）")
    print("=" * 96)
    print(f"{'訊號':<14}{'天期':>5}{'恐懼pp':>9}{'貪婪pp':>9}{'差pp':>8}{'置換p':>9}")
    gaps = []
    for name in sigs.columns:
        rk = rank_trailing(sigs[name].dropna(), WINDOW).reindex(px.index)
        lo = (rk <= TAIL).fillna(False).values
        hi = (rk >= 100 - TAIL).fillna(False).values
        for h in (21, 63, 126):
            fwd = fwd_returns(px, h).values
            ef, eg = effect(lo, fwd), effect(hi, fwd)
            gap, p = perm_gap(lo, hi, fwd)
            gaps.append((name, h, ef, eg, gap, p))
            print(f"{name:<14}{h:>5}{ef*100:>9.2f}{eg*100:>9.2f}{gap*100:>8.2f}{p:>9.3f}")
    sig_gaps = [g for g in gaps if g[5] == g[5] and g[5] < 0.10 and g[4] > 0]
    print(f"\n「恐懼效果 > 貪婪效果」且置換 p<0.10 的格數：**{len(sig_gaps)}／{len(gaps)}**"
          f"（純雜訊期望約 {len(gaps)*0.05:.1f}）")

    print("\n" + "=" * 96)
    print("二、只做恐懼側，且**平均曝險對齊買進持有**（贏的部分不能來自槓桿）")
    print("=" * 96)
    ma = px.rolling(20).mean()
    wB = matched(pd.Series((px > ma).values, index=px.index).fillna(False))
    sB, wBs = strat(wB, r)
    print(f"{'規則':<28}{'外 Sharpe':>10}{'外年化':>9}{'外 MDD':>9}{'平均曝險':>9}{'換手':>7}")
    print(f"{'A 買進持有':<28}{sharpe(r.iloc[cut:]):>10.2f}{ann(r.iloc[cut:])*100:>8.1f}%"
          f"{mdd(r.iloc[cut:])*100:>8.1f}%{1.0:>9.2f}{'—':>7}")
    print(f"{'B 純 20 日均線（曝險對齊）':<28}{sharpe(sB.iloc[cut:]):>10.2f}"
          f"{ann(sB.iloc[cut:])*100:>8.1f}%{mdd(sB.iloc[cut:])*100:>8.1f}%"
          f"{wBs.mean():>9.2f}{int((wBs.diff().abs()>0).sum()):>7}")
    print()
    best = None
    for name in sigs.columns:
        rk = rank_trailing(sigs[name].dropna(), WINDOW).reindex(px.index)
        lo = (rk <= TAIL).fillna(False)
        w = matched(lo)
        s, ws = strat(w, r)
        so, mo = sharpe(s.iloc[cut:]), mdd(s.iloc[cut:])
        if best is None or so > best[1]: best = (name, so, mo)
        print(f"{'C 只做恐懼 · ' + name:<28}{so:>10.2f}{ann(s.iloc[cut:])*100:>8.1f}%"
              f"{mo*100:>8.1f}%{ws.mean():>9.2f}{int((ws.diff().abs()>0).sum()):>7}")

    print(f"\n判準：最好的恐懼側規則要贏過**買進持有與純均線兩者**。")
    bh, bma = sharpe(r.iloc[cut:]), sharpe(sB.iloc[cut:])
    print(f"  最好的是「{best[0]}」Sharpe {best[1]:.2f}　vs 買進持有 {bh:.2f}、純均線 {bma:.2f}"
          f"　→ {'**通過**' if best[1] > bh and best[1] > bma else '**沒有通過**'}")

    print("\n" + "=" * 96)
    print("三、買進後要再痛多久：最大不利變動（MAE）")
    print("=" * 96)
    for name in sigs.columns:
        rk = rank_trailing(sigs[name].dropna(), WINDOW).reindex(px.index)
        lo = (rk <= TAIL).fillna(False)
        eps = episodes(lo, 3)
        st = independent(eps, px.index, 63)
        m = mae(px, st, 63)
        if len(m) < 3: continue
        print(f"  {name:<14} 獨立事件 {len(m):>2}　MAE 中位 {np.median(m)*100:>6.1f}%　"
              f"最糟 {min(m)*100:>6.1f}%　"
              f"有 {sum(1 for x in m if x > -0.05)}/{len(m)} 次跌幅未超過 5%")




def section4():
    """恐懼 ＋ 反彈確認：只做恐懼側的 Setup→Trigger，且曝險對齊。

    第二節顯示「恐懼一出現就加碼」會**放大回撤**（−42% ~ −46% vs 買進持有 −34%）——
    因為恐懼訊號說的是「從這裡算起未來報酬高於平均」，不是「底部到了」。
    第三節的 MAE 把代價量出來了。

    那就等反彈確認再進場。**但一樣要贏過純均線**，不然又是一條穿著情緒外衣的均線。
    """
    df = load(); parts, sigs = build(df); px = df["px"]
    r = px.pct_change().fillna(0)
    cut = int(len(px) * 0.6)
    ma = px.rolling(20).mean(); up = (px > ma).fillna(False)
    print("\n" + "=" * 96)
    print("四、恐懼 ＋ 反彈確認（曝險對齊）")
    print("=" * 96)
    wB = matched(pd.Series(up.values, index=px.index)); sB, wBs = strat(wB, r)
    bh, bma = sharpe(r.iloc[cut:]), sharpe(sB.iloc[cut:])
    print(f"{'規則':<30}{'外 Sharpe':>10}{'外年化':>9}{'外 MDD':>9}{'觸發日':>7}")
    print(f"{'A 買進持有':<30}{bh:>10.2f}{ann(r.iloc[cut:])*100:>8.1f}%"
          f"{mdd(r.iloc[cut:])*100:>8.1f}%{'—':>7}")
    print(f"{'B 純 20 日均線':<30}{bma:>10.2f}{ann(sB.iloc[cut:])*100:>8.1f}%"
          f"{mdd(sB.iloc[cut:])*100:>8.1f}%{'—':>7}")
    best = None
    for name in sigs.columns:
        rk = rank_trailing(sigs[name].dropna(), WINDOW).reindex(px.index)
        lo = (rk <= TAIL).fillna(False)
        setup = lo.rolling(20, min_periods=1).max().astype(bool)
        trig = setup & (~lo) & up
        w = matched(trig); s, ws = strat(w, r)
        so, mo = sharpe(s.iloc[cut:]), mdd(s.iloc[cut:])
        if best is None or so > best[1]: best = (name, so, mo)
        print(f"{'D 恐懼＋確認 · ' + name:<30}{so:>10.2f}{ann(s.iloc[cut:])*100:>8.1f}%"
              f"{mo*100:>8.1f}%{int(trig.sum()):>7}")
        eps = episodes(trig, 3); st = independent(eps, px.index, 63)
        m = mae(px, st, 63)
        if len(m) >= 3:
            print(f"{'   → MAE 中位':<30}{np.median(m)*100:>9.1f}%　最糟 {min(m)*100:.1f}%　"
                  f"{sum(1 for x in m if x > -0.05)}/{len(m)} 次跌幅未超過 5%")
    print(f"\n判準：要同時贏過買進持有 {bh:.2f} 與純均線 {bma:.2f}")
    print(f"  最好的是「{best[0]}」{best[1]:.2f} → "
          f"{'**通過**' if best[1] > bh and best[1] > bma else '**沒有通過**'}")


if __name__ == "__main__":
    main()
    section4()
