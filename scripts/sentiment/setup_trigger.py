#!/usr/bin/env python3
"""測 PBB-10／TWBB-10 的核心主張：**Setup → Trigger 兩階段**。

## 為什麼只測這一個

那兩份文件提了很多東西，但絕大多數我們**已經實測過或已知不可行**：
CFTC ES/NQ 槓桿基金（家族檢定 p=0.227、唯一顯著項樣本外翻面）、
FRED BAA10Y（你的機器連不到）、Taiwan VIX（免費只有三個月）、TPEx（403）。

真正**新**而且**我們沒試過**的只有一個：

> 「極端樂觀可以維持很久，高分首先代表 vulnerable，不是立即做空。
>  真正的減碼訊號必須等待 Breadth / Credit / Trend 的 deterioration confirmation。」

這正好對上第一階段回測失敗的方式：T2 的「極端貪婪→減碼」在多頭裡一路輸，
**因為極端貪婪會持續**。Setup→Trigger 說：不要對水位動作，要對**水位＋反轉**動作。

那是一個**不同的訊號**，不是同一個訊號的不同閾值。所以值得單獨測。

## 怎麼測

同一份資料、同一套區塊自助法，只換規則：

- **水位法（舊）**：極端貪婪當天就減碼。
- **Setup→Trigger（新）**：過去 20 日曾極端貪婪 **且** 現在已回落 **且**
  趨勢確認轉弱（收盤跌破 20 日均線）→ 才減碼。恐懼側對稱。

判準沿用設計書：樣本外 Sharpe 要贏買進持有，且最大回撤更小。
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/sent/eng")
from core import rank_trailing, composite, episodes, independent, fwd_returns, WINDOW
from blockstats import circular_block_boot, min_detectable, verdict
from loaddata import load
from backtest import build, extremes, TAIL, GAP, COST

LOOKBACK = 20        # setup 的回看窗（文件用 20 日）


def rules(sig, px, tail=TAIL):
    """回傳三種倉位序列：買進持有、水位法、Setup→Trigger。"""
    r = rank_trailing(sig.dropna(), WINDOW).reindex(px.index)
    lo, hi = r <= tail, r >= 100 - tail
    ma20 = px.rolling(20).mean()
    trend_dn = px < ma20                      # 趨勢轉弱
    trend_up = px > ma20

    # 水位法：當天在極端區就動作
    w_lvl = pd.Series(0.75, index=px.index)
    w_lvl[hi] = 0.5; w_lvl[lo] = 1.0

    # Setup→Trigger：曾極端 ＋ 已回落 ＋ 趨勢確認
    hi_setup = hi.rolling(LOOKBACK, min_periods=1).max().astype(bool)
    lo_setup = lo.rolling(LOOKBACK, min_periods=1).max().astype(bool)
    sell_trig = hi_setup & (~hi) & trend_dn
    buy_trig = lo_setup & (~lo) & trend_up
    w_st = pd.Series(0.75, index=px.index)
    w_st[sell_trig] = 0.5; w_st[buy_trig] = 1.0

    return w_lvl.shift(1).fillna(0.75), w_st.shift(1).fillna(0.75), sell_trig, buy_trig, lo, hi


def stats(w, r, cost=COST):
    s = w * r - w.diff().abs().fillna(0) * cost
    return s


def ann(x): return (1 + x).prod() ** (252 / max(len(x), 1)) - 1
def sharpe(x): return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")
def mdd(x):
    c = (1 + x).cumprod(); return float((c / c.cummax() - 1).min())


def main():
    df = load(); parts, sigs = build(df); px = df["px"]
    r = px.pct_change().fillna(0)
    cut = int(len(px) * 0.6); sp = px.index[cut]
    print(f"樣本 {px.index[0].date()} → {px.index[-1].date()}　{len(px)} 個交易日")
    print(f"樣本內／外切在 {sp.date()}　成本 {COST*100:.2f}%／來回\n")

    print("=" * 92)
    print("T2：水位法 vs Setup→Trigger（樣本外才算數）")
    print("=" * 92)
    print(f"{'訊號':<14}{'規則':<16}{'內 Sharpe':>10}{'外 Sharpe':>10}"
          f"{'外年化':>9}{'外 MDD':>9}{'換手':>7}")
    bh = r
    print(f"{'買進持有':<14}{'—':<16}{sharpe(bh.iloc[:cut]):>10.2f}"
          f"{sharpe(bh.iloc[cut:]):>10.2f}{ann(bh.iloc[cut:])*100:>8.1f}%"
          f"{mdd(bh.iloc[cut:])*100:>8.1f}%{'—':>7}")
    rows = []
    for name in sigs.columns:
        w_lvl, w_st, sell, buy, lo, hi = rules(sigs[name], px)
        for lab, w in (("水位法", w_lvl), ("Setup→Trigger", w_st)):
            s = stats(w, r)
            rows.append(dict(訊號=name, 規則=lab,
                             內=sharpe(s.iloc[:cut]), 外=sharpe(s.iloc[cut:]),
                             年化=ann(s.iloc[cut:]), MDD=mdd(s.iloc[cut:]),
                             換手=int((w.diff().abs() > 0).sum())))
            print(f"{name:<14}{lab:<16}{rows[-1]['內']:>10.2f}{rows[-1]['外']:>10.2f}"
                  f"{rows[-1]['年化']*100:>8.1f}%{rows[-1]['MDD']*100:>8.1f}%"
                  f"{rows[-1]['換手']:>7}")

    t = pd.DataFrame(rows)
    bh_out = sharpe(bh.iloc[cut:]); bh_mdd = mdd(bh.iloc[cut:])
    print("\n判準：樣本外 Sharpe > 買進持有 **且** 最大回撤更小")
    win = t[(t["外"] > bh_out) & (t["MDD"] > bh_mdd)]
    if len(win):
        print("**通過的組合：**")
        print(win.to_string(index=False))
    else:
        print("**沒有任何組合通過。**")
        best = t.loc[t["外"].idxmax()]
        print(f"最接近的是「{best['訊號']}·{best['規則']}」："
              f"樣本外 Sharpe {best['外']:.2f} vs 買進持有 {bh_out:.2f}")

    print("\n" + "=" * 92)
    print("T1：Setup→Trigger 觸發之後的前瞻報酬（區塊自助法）")
    print("=" * 92)
    out = []
    for name in sigs.columns:
        _, _, sell, buy, lo, hi = rules(sigs[name], px)
        for mask, tag in ((buy, "買進確認"), (sell, "賣出確認"),
                          (lo, "（對照）水位·極端恐懼"), (hi, "（對照）水位·極端貪婪")):
            m = mask.fillna(False)
            if m.sum() < 10: continue
            eps = episodes(m, GAP)
            for h in (21, 63):
                fwd = fwd_returns(px, h)
                n_ind = len(independent(eps, px.index, h))
                pt, l, u = circular_block_boot(m.values, fwd.values, h)
                mde = min_detectable(fwd.values, n_ind)
                out.append(dict(訊號=name, 類型=tag, 天期=h, 觸發日=int(m.sum()),
                                獨立事件=n_ind,
                                點估計pp=None if pt is None else round(pt*100, 2),
                                CI下界=None if l is None else round(l*100, 2),
                                CI上界=None if u is None else round(u*100, 2),
                                最小可測pp=None if mde is None else round(mde*100, 1),
                                結論=verdict(pt, l, u, mde, 0.03)))
    o = pd.DataFrame(out)
    for name in sigs.columns:
        sub = o[o["訊號"] == name]
        if len(sub): print(sub.to_string(index=False)); print()


if __name__ == "__main__":
    main()
