#!/usr/bin/env python3
"""USBR-10 的四階段閘門架構值不值得蓋。**先測架構，再蓋變數。**

## 要回答的問題

USBR-10 的 Gate 3（Reversal Confirmation）核心是 **Close > MA10 ＋ breadth thrust ＋
價格突破前高**——那是**價格轉折濾網**。第三階段已經證明：
Setup→Trigger 看起來五個訊號全改善，拆開之後 100% 的功勞屬於 20 日均線。

所以在蓋 20 個變數之前要先問：

> **「恐慌 → 去槓桿 → 耗竭 → 反轉」這一整套，比得過
>  「跌深了、價格站回 MA10 就買」這條沒有任何恐懼成分的規則嗎？**

比不過的話，那 20 個變數是裝飾。

## 判準用文件自己的（§7），不是我另訂的

- **Tier 1 命中**：訊號距 60 日低點 ±5 個交易日內
- **Tier 2 投資命中**：20 日內最大漲幅 > +7%，且 MAE 不低於 −5%
- **Tier 3 大底**：60 日報酬 > +10%，且訊號後未再出現 >5% 的深跌

外加它 §6 強調的：**Precision、Median Lag、MAE、MFE**，不看 Accuracy。
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/sent/eng")
from core import rank_trailing, episodes, WINDOW
from loaddata import load

DD_THRESH = 0.07        # 60 日回檔門檻
PANIC_PCT = 85          # Panic gate：VIX 百分位
GAP = 10                # 兩個訊號相隔幾天算不同事件


def dedupe(idx_positions, gap=GAP):
    out = []
    for i in idx_positions:
        if not out or i - out[-1] > gap: out.append(i)
    return out


def evaluate(px, sig_pos, name):
    """照 USBR-10 §7 的三層標準評分。"""
    n = len(px); v = px.values
    t1 = t2 = t3 = 0; lags = []; maes = []; mfes = []; r20 = []; r60 = []
    for i in sig_pos:
        if i + 60 >= n: continue
        w60 = v[max(0, i - 30): min(n, i + 31)]          # 訊號前後各 30 日找局部低
        lo_off = int(np.argmin(w60)) - min(i, 30)
        lags.append(-lo_off)                              # 正＝訊號落後低點
        if abs(lo_off) <= 5: t1 += 1
        seg20, seg60 = v[i:i + 21], v[i:i + 61]
        mae = seg60.min() / v[i] - 1
        mfe20 = seg20.max() / v[i] - 1
        maes.append(mae); mfes.append(mfe20)
        r20.append(seg20[-1] / v[i] - 1); r60.append(seg60[-1] / v[i] - 1)
        if mfe20 > 0.07 and mae >= -0.05: t2 += 1
        # Tier 3：60 日報酬 >10% 且過程中未再深跌 5%
        run = np.maximum.accumulate(seg60)
        deep = ((seg60 / run - 1) < -0.05).any()
        if seg60[-1] / v[i] - 1 > 0.10 and not deep: t3 += 1
    k = len([i for i in sig_pos if i + 60 < n])
    if k == 0:
        print(f"{name:<30} 沒有可評估的訊號"); return None
    print(f"{name:<30}{k:>5}{t1/k*100:>8.0f}%{t2/k*100:>8.0f}%{t3/k*100:>8.0f}%"
          f"{np.median(lags):>7.0f}{np.median(maes)*100:>8.1f}%{np.median(mfes)*100:>8.1f}%"
          f"{np.median(r20)*100:>8.1f}%{np.median(r60)*100:>8.1f}%")
    return dict(n=k, t1=t1/k, t2=t2/k, t3=t3/k, lag=np.median(lags),
                mae=np.median(maes), mfe=np.median(mfes))


def main():
    df = load(); px = df["px"]; vix = df["vix"]
    n = len(px); v = px.values
    ma10 = px.rolling(10).mean()
    dd60 = px / px.rolling(60).max() - 1
    vixp = rank_trailing(vix, WINDOW)
    vix5 = vix.rolling(5).mean()

    print(f"樣本 {px.index[0].date()} → {px.index[-1].date()}　{n} 個交易日\n")
    print(f"{'規則':<30}{'訊號':>5}{'Tier1':>8}{'Tier2':>8}{'Tier3':>8}"
          f"{'落後':>7}{'MAE':>8}{'MFE20':>8}{'20D':>8}{'60D':>8}")
    print("-" * 98)

    # --- 對照組 A：完全沒有恐懼成分。跌深 ＋ 站回 MA10。 ---
    reclaim = (px > ma10) & (px.shift(1) <= ma10.shift(1))
    naive = reclaim & (dd60.rolling(20).min() <= -DD_THRESH)
    A = evaluate(px, dedupe([i for i, x in enumerate(naive.fillna(False).values) if x]),
                 "A 跌深＋站回MA10（無恐懼）")

    # --- B：只有 Panic gate（VIX 極端），沒有反轉確認 ---
    panic = (vixp >= PANIC_PCT).fillna(False)
    B = evaluate(px, dedupe([i for i, x in enumerate(panic.values) if x]),
                 "B 只有 Panic（VIX>85pct）")

    # --- C：Panic → Exhaustion（VIX 由高點回落）→ Reversal（站回 MA10）---
    #     這是 USBR-10 四階段的骨架，用手上拿得到的變數做最小可行版
    panic_recent = panic.rolling(10, min_periods=1).max().astype(bool)
    exhaust = (vix5 < vix5.shift(3)) & (vixp.shift(3) >= PANIC_PCT)
    exhaust_recent = exhaust.fillna(False).rolling(10, min_periods=1).max().astype(bool)
    C = evaluate(px, dedupe([i for i, x in enumerate(
        (panic_recent & exhaust_recent & reclaim).fillna(False).values) if x]),
                 "C 四階段骨架（含恐懼）")

    # --- D：C 再加跌深條件（完整版最接近 USBR-10 的樣子）---
    D = evaluate(px, dedupe([i for i, x in enumerate(
        (panic_recent & exhaust_recent & reclaim &
         (dd60.rolling(20).min() <= -DD_THRESH)).fillna(False).values) if x]),
                 "D 四階段＋跌深")

    print("\n" + "=" * 98)
    print("判決：恐懼那一層有沒有加值")
    print("=" * 98)
    if A and C:
        for key, lab in (("t2", "Tier2 投資命中"), ("t3", "Tier3 大底"), ("mae", "MAE（越接近 0 越好）")):
            a, c = A[key], C[key]
            better = (c > a) if key != "mae" else (c > a)
            print(f"  {lab:<20} 無恐懼 {a*100:>6.1f}%　四階段 {c*100:>6.1f}%　"
                  f"{'**恐懼有加值**' if better else '恐懼沒有加值'}")
    if D:
        print(f"\n  完整版（D）訊號數只有 {D['n']} 個 —— "
              f"**這就是 rare-event 的核心問題：n={D['n']} 的 Precision 沒有意義。**")
    print("\n※ 這是最小可行版：只用得到 VIX 與價格，沒有 breadth、credit、put/call。")
    print("  但**恐懼那一層的骨架是完整的**（Panic → Exhaustion → Reversal），")
    print("  而缺的那幾項都屬於同一族——第一階段已測，測不出前瞻資訊。")




def matched_control():
    """數量對齊的對照組。**這一段才是判決。**

    D（四階段＋跌深）只有 23 個訊號，而對照組 A 有 53 個。
    **更挑的規則本來就會有更高的命中率**——所以 D 贏 A 有可能純粹來自「訊號更少」，
    跟恐懼那一層一點關係都沒有。

    做法：把 A 的跌深門檻一路調嚴，直到訊號數也落在 23 附近，再比一次。
    另外用 Fisher 精確檢定看 Tier2 的差距在這個樣本量下測不測得出來。
    """
    from scipy.stats import fisher_exact
    df = load(); px = df["px"]; vix = df["vix"]
    ma10 = px.rolling(10).mean()
    dd60 = px / px.rolling(60).max() - 1
    vixp = rank_trailing(vix, WINDOW); vix5 = vix.rolling(5).mean()
    reclaim = (px > ma10) & (px.shift(1) <= ma10.shift(1))
    panic = (vixp >= PANIC_PCT).fillna(False)
    pr = panic.rolling(10, min_periods=1).max().astype(bool)
    ex = ((vix5 < vix5.shift(3)) & (vixp.shift(3) >= PANIC_PCT)).fillna(False)
    exr = ex.rolling(10, min_periods=1).max().astype(bool)

    print("\n" + "=" * 98)
    print("五、數量對齊的對照：更挑，還是恐懼？")
    print("=" * 98)
    print(f"{'規則':<30}{'訊號':>5}{'Tier1':>8}{'Tier2':>8}{'Tier3':>8}"
          f"{'落後':>7}{'MAE':>8}{'MFE20':>8}{'20D':>8}{'60D':>8}")
    print("-" * 98)
    D = evaluate(px, dedupe([i for i, x in enumerate(
        (pr & exr & reclaim & (dd60.rolling(20).min() <= -DD_THRESH)).fillna(False).values) if x]),
        "D 四階段＋跌深（恐懼）")
    best = None
    for th in (0.09, 0.11, 0.13, 0.15):
        m = (reclaim & (dd60.rolling(20).min() <= -th)).fillna(False)
        pos = dedupe([i for i, x in enumerate(m.values) if x])
        r = evaluate(px, pos, f"A' 只加深跌深門檻 {th*100:.0f}%（無恐懼）")
        if r and (best is None or abs(r["n"] - D["n"]) < abs(best["n"] - D["n"])):
            best = r
    print()
    if D and best:
        print(f"  數量最接近的無恐懼對照：n={best['n']}　vs　D n={D['n']}")
        print(f"    Tier2　恐懼 {D['t2']*100:.1f}%　vs　無恐懼 {best['t2']*100:.1f}%")
        print(f"    MAE 　恐懼 {D['mae']*100:.1f}%　vs　無恐懼 {best['mae']*100:.1f}%")
        a, b = round(D["t2"] * D["n"]), D["n"]
        c, d = round(best["t2"] * best["n"]), best["n"]
        odd, p = fisher_exact([[a, b - a], [c, d - c]])
        print(f"\n  Tier2 命中 {a}/{b} vs {c}/{d}　Fisher 精確檢定 p = {p:.3f}")
        print(f"  → {'**差距測得出來**' if p < 0.10 else '**差距測不出來——樣本量根本不夠**'}")
        need = 0
        base = best["t2"]
        for nn in range(20, 4000, 10):
            k1 = base + 0.07
            from scipy.stats import fisher_exact as fe
            _, pp = fe([[round(k1*nn), nn-round(k1*nn)], [round(base*nn), nn-round(base*nn)]])
            if pp < 0.10: need = nn; break
        print(f"  要驗出「Tier2 高 7 個百分點」這種差距，兩組**各需要約 {need} 個訊號**"
              f"（現在是 {b} 與 {d}）。")


if __name__ == "__main__":
    main()
    matched_control()
