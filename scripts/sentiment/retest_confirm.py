#!/usr/bin/env python3
"""重測後的候選，走跟融資強度同一套關卡。**這一支是判決，前一支只是產生假設。**

用法：SENT_CACHE=~/sent-cache python3 retest_confirm.py

## 為什麼

`retest.py` 全成分那組跑了 18 個訊號 × 多個天期，通過 12／102 格（雜訊期望 5.1）。
**但這個專案已經兩次被逐格表騙過**（Setup→Trigger、CFTC 的分群故事），
而融資強度更是通過了 T2 之後死在走動式與置換檢定。

所以逐格通過**不是結論**。四道關卡都過才算候選存活：

1. **走動式驗證**：五段裡贏幾段。單一切點只是一次擲骰子。
2. **置換檢定**：訊號環狀位移一千次，真實優勢排第幾百分位。
   位移到隨機時點也拿得到，優勢就不屬於訊號。
3. **多重比較的分母**：18 個訊號裡通過 1 個，隨機該有幾個。
4. **對照組**：要同時贏過買進持有與純 20 日均線。

## 候選怎麼選的

T2 樣本外 Sharpe 前幾名，**加上** T1 有連續天期一致的那幾個。
選的當下就固定，不會跑完再回頭換一組。

## 兩個刻意保留的約定

- **評估期自「所有候選都累積滿 750 日視窗」的那天起。** 不這樣切的話，
  第一段會有一段時間所有候選都因為還沒有分數而停在中性 0.75 倉位，
  在多頭段落被買進持有輾過——那是視窗還沒填滿造成的，不是訊號的問題。
- **成分本身已經是百分位，這裡再排一次名。** 這是 `retest.py` 的既有做法，
  照抄是刻意的：**確認測試必須測跟當初通過的完全同一條訊號**，
  否則「修正」與「把失敗洗成通過」在程式碼上長得一模一樣。
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing
import retest as R

CAND = ["廣度·等權", "波動·VVIX", "信用·HY對公債", "波動·水位", "合成16項"]
COST, TAIL, NPERM = 0.0005, 10.0, 1000


def sharpe(x): return x.mean()/x.std()*np.sqrt(252) if x.std() > 0 else np.nan
def mdd(x):
    c = (1+x).cumprod(); return float((c/c.cummax()-1).min())


def pos(rk, idx):
    w = pd.Series(0.75, index=idx); w[rk >= 100-TAIL] = 0.5; w[rk <= TAIL] = 1.0
    return w.shift(1).fillna(0.75)


def run(w, r): return w*r - w.diff().abs().fillna(0)*COST


def main():
    d = R.load()
    parts, _ = R.build_parts(d, "full")
    parts = parts.dropna(how="any")
    px = d["^GSPC"].reindex(parts.index).dropna()
    parts = parts.reindex(px.index)
    r = px.pct_change().fillna(0)
    from core import composite
    sig = {"合成16項": composite(parts)}
    for c in parts.columns: sig[c] = parts[c]
    sig = pd.DataFrame(sig)
    print(f"樣本 {px.index[0].date()} → {px.index[-1].date()}　{len(px)} 日"
          f"　成分 {parts.shape[1]} 項\n")

    rks, first = {}, []
    for c in CAND:
        if c not in sig.columns: continue
        rk = rank_trailing(sig[c].dropna(), 750).reindex(px.index)
        rks[c] = rk
        v = rk.first_valid_index()
        if v is not None: first.append(v)
    start = max(first) if first else px.index[0]
    px, r = px.loc[start:], r.loc[start:]
    rks = {c: v.loc[start:] for c, v in rks.items()}
    print(f"評估期自 {start.date()} 起（所有候選都已累積滿 750 日視窗）"
          f"　{len(px)} 日\n")

    ma = px.rolling(20).mean()
    wma = pd.Series(0.75, index=px.index); wma[px > ma] = 1.0; wma[px < ma] = 0.5
    sma = run(wma.shift(1).fillna(.75), r)
    n = len(px); k = 5
    bounds = [px.index[int(n*i/k)] for i in range(k)] + [px.index[-1]]

    print("="*94)
    print("一、走動式驗證（五段各自比買進持有）")
    print("="*94)
    print(f"{'候選':<14}" + "".join(f"{str(bounds[i].date())[2:7]:>9}" for i in range(k))
          + f"{'贏幾段':>8}")
    wf = {}
    for c, rk in rks.items():
        s = run(pos(rk, px.index), r)
        diffs = []
        for i in range(k):
            a, b = bounds[i], bounds[i+1]
            diffs.append(sharpe(s.loc[a:b]) - sharpe(r.loc[a:b]))
        wf[c] = sum(1 for x in diffs if x > 0)
        print(f"{c:<14}" + "".join(f"{x:>9.2f}" for x in diffs) + f"{wf[c]:>8}/5")

    print("\n" + "="*94)
    print("二、置換檢定（環狀位移 1000 次，保留自相關）")
    print("="*94)
    rng = np.random.default_rng(7)
    pv = {}
    for c, rkser in rks.items():
        rkv = rkser.values
        obs = sharpe(run(pos(pd.Series(rkv, index=px.index), px.index), r)) - sharpe(r)
        null = []
        for _ in range(NPERM):
            sh = int(rng.integers(1, len(rkv)))
            null.append(sharpe(run(pos(pd.Series(np.roll(rkv, sh), index=px.index),
                                       px.index), r)) - sharpe(r))
        null = np.array([x for x in null if x == x])
        pct = float((null < obs).mean()*100)
        p1 = float((null >= obs).mean())        # 單尾：虛無不以 0 為中心，雙尾會誤導
        pv[c] = (obs, pct, p1, float(np.median(null)))
        print(f"  {c:<14}優勢 {obs:+.3f}　虛無中位 {np.median(null):+.3f}　"
              f"排第 {pct:>3.0f} 百分位　單尾 p={p1:.3f}"
              f"　{'**通過**' if p1 < 0.10 and obs > 0 else '沒通過'}")

    print("\n" + "="*94)
    print("三、多重比較的分母")
    print("="*94)
    N = 18
    print(f"  這一輪測了 {N} 個訊號。每個隨機通過 T2 的機率若是 5%，"
          f"至少一個通過的機率＝{1-(0.95**N):.0%}")
    print("  → **「18 個裡有 1 個通過」本身沒有證據力。** 判決看第一、二節。")

    print("\n" + "="*94)
    print("四、對照組（樣本外，全期）")
    print("="*94)
    cut = int(len(px)*0.6)
    print(f"{'':<14}{'樣本外 Sharpe':>14}{'樣本外 MDD':>12}")
    print(f"{'買進持有':<14}{sharpe(r.iloc[cut:]):>14.2f}{mdd(r.iloc[cut:])*100:>11.1f}%")
    print(f"{'純20日均線':<14}{sharpe(sma.iloc[cut:]):>14.2f}{mdd(sma.iloc[cut:])*100:>11.1f}%")
    ok = {}
    for c, rk in rks.items():
        s = run(pos(rk, px.index), r)
        beat = (sharpe(s.iloc[cut:]) > sharpe(r.iloc[cut:])
                and sharpe(s.iloc[cut:]) > sharpe(sma.iloc[cut:])
                and mdd(s.iloc[cut:]) > mdd(r.iloc[cut:]))
        ok[c] = beat
        print(f"{c:<14}{sharpe(s.iloc[cut:]):>14.2f}{mdd(s.iloc[cut:])*100:>11.1f}%"
              f"　{'✓ 三個對照都贏' if beat else ''}")

    print("\n" + "="*94); print("判決"); print("="*94)
    for c in CAND:
        if c not in pv: continue
        alive = wf.get(c, 0) >= 4 and pv[c][2] < 0.10 and ok.get(c, False)
        print(f"  {c:<14}走動式 {wf.get(c,0)}/5　置換 p={pv[c][2]:.3f}　"
              f"對照 {'過' if ok.get(c) else '未過'}　→ "
              f"**{'存活，可進入前瞻追蹤' if alive else '未通過，不要蓋在它上面'}**")
    print("\n未通過**不等於**沒用，而是**這份資料判不動**。")
    print("照設計書：不發布倉位訊號，只呈現原始序列、百分位與 MAE 分佈。")


if __name__ == "__main__":
    main()
