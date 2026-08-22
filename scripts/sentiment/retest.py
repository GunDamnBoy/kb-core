#!/usr/bin/env python3
"""用 yfinance 重跑整套檢定。**要在有網路的機器上跑**（Mac 或 GitHub Actions）。

用法：
    python3 retest.py --fetch      # 抓資料並快取（第一次約 2–4 分鐘）
    python3 retest.py --run        # 跑檢定（讀快取，可反覆跑）
    python3 retest.py --fetch --run

## 為什麼重測

前六個階段的結論裡，有一部分是**資料拿不到**造成的，不是測出來的：
廣度、信用、選擇權、避險需求全部標成不可行——而那是 USBR-10 四大模組裡的兩個。
yfinance 把它們打開了。

**但真正鬆綁的是樣本長度。** 舊回測是 2011–2026，因為那份 SPY 鏡像從 2011 開始。
`^GSPC` 回到 1927、`^VIX` 回到 1990 —— **15 年變 36 年，涵蓋 2000、2008、2020**，
獨立事件數約多一倍半到兩倍，最小可測效果會從 5pp 降到 3pp 附近。

## 兩個年份組（vintage），刻意分開跑

- **長樣本（1990–）**：只用 `^GSPC` ＋ `^VIX` 建得起來的成分。事件多、檢定力好。
- **全成分（2012–）**：把 ETF 系的廣度、信用、風險偏好全部加進來。成分齊、事件少。

**兩組要分開報。** 混在一起會出現「早期成分少、晚期成分多」的合成分數，
而那個分數在樣本裡前後不可比——這是第六階段踩過的兩軌不一致，換一個樣子。

## 判準沿用，一條都不放寬

T1 區塊自助法 ＋ 檢定力欄 ＋ 獨立事件下限 8；
T3 合成要贏過最好的單項、等權要贏過隨機權重；
**所有含趨勢濾網的規則都要贏過純 20 日均線**。
"""
from __future__ import annotations
import argparse, json, os, sys, warnings
import datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing, composite, episodes, independent
from blockstats import circular_block_boot, min_detectable, verdict

warnings.filterwarnings("ignore")
CACHE = os.path.abspath(os.path.expanduser(os.environ.get("SENT_CACHE", "~/sent-cache")))
PX = os.path.join(CACHE, "retest_px.csv")

# 指數與 ETF。註解寫**它在模型裡做什麼**，不是它是什麼。
TICKERS = {
    "^GSPC": "大盤價格與動能",
    "^VIX": "隱含波動（恐慌）",
    "^VIX9D": "短天期波動（事件型恐慌）",
    "^VVIX": "波動的波動",
    "SPY": "避險需求的股票腳",
    "TLT": "避險需求的債券腳",
    "IEF": "中天期公債（信用比較基準）",
    "HYG": "高收益債（信用風險偏好）",
    "LQD": "投資級債（信用比較基準）",
    "RSP": "等權（廣度）",
    "IWM": "小型股（廣度）",
    "SPHB": "高 Beta（投機risk appetite）",
    "SPLV": "低波動（投機的對照）",
    "XLY": "景氣循環（risk appetite）",
    "XLP": "防禦（risk appetite 的對照）",
    # 全球廣度籃子
    "EFA": "已開發非美", "EEM": "新興", "EWJ": "日本", "EWC": "加拿大",
    "EWA": "澳洲", "EWT": "台灣", "EWY": "韓國", "INDA": "印度", "EWZ": "巴西",
}
BASKET = ["SPY", "EFA", "EEM", "EWJ", "EWC", "EWA", "EWT", "EWY", "INDA", "EWZ"]


def do_fetch():
    import yfinance as yf
    os.makedirs(CACHE, exist_ok=True)
    end = dt.date.today() + dt.timedelta(days=1)
    out = {}
    for t in TICKERS:
        try:
            d = yf.download(t, start="1927-01-01", end=str(end), interval="1d",
                            auto_adjust=False, actions=False, progress=False,
                            multi_level_index=False, threads=False)
            c = d["Close"]
            if hasattr(c, "columns"):
                print(f"  {t}: 回了 MultiIndex，跳過"); continue
            c = pd.to_numeric(c, errors="coerce").dropna()
            c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
            out[t] = c[~c.index.duplicated()]
            print(f"  {t:<7} {len(c):>6} 筆　{c.index[0].date()} → {c.index[-1].date()}"
                  f"　{TICKERS[t]}")
        except Exception as e:
            print(f"  {t:<7} **失敗** {e.__class__.__name__}")
    if not out: print("**一支都沒抓到**"); return
    df = pd.DataFrame(out).sort_index()
    df.to_csv(PX)
    print(f"\n→ {PX}　{len(df)} 個交易日、{df.shape[1]} 支")


def load():
    d = pd.read_csv(PX, parse_dates=[0], index_col=0)
    return d.sort_index()


# ------------------------------------------------------------------ 成分

def rel(a, b, n=63):
    """相對強弱：a 對 b 的 n 日相對報酬。"""
    return (a / a.shift(n)) / (b / b.shift(n)) - 1


def build_parts(d, vintage):
    """回傳（成分百分位表, 說明）。每一項都是「愈高愈 risk-on／愈平靜」。"""
    p, why = pd.DataFrame(index=d.index), {}
    has = lambda *t: all(x in d.columns and d[x].notna().sum() > 500 for x in t)
    W = 750

    def add(k, ser, inv, note):
        s = ser.dropna()
        if len(s) < W + 60: return
        p[k] = rank_trailing(s, W, invert=inv).reindex(d.index)
        why[k] = note

    if has("^GSPC"):
        g = d["^GSPC"]
        add("動能·200MA", g / g.rolling(200).mean() - 1, False, "價格相對 200 日均")
        add("動能·63日", g / g.shift(63) - 1, False, "三個月報酬")
    if has("^VIX"):
        v = d["^VIX"]
        add("波動·水位", v, True, "VIX 絕對水位")
        add("波動·相對均線", v / v.rolling(50).mean() - 1, True, "VIX 相對 50 日均")
    if vintage == "full":
        if has("^VIX9D", "^VIX"):
            add("波動·期限結構", d["^VIX9D"] / d["^VIX"], True, "短天期／30 天，逆價差＝急性壓力")
        if has("^VVIX"):
            add("波動·VVIX", d["^VVIX"], True, "波動的波動")
        if has("HYG", "LQD"):
            add("信用·HY對IG", rel(d["HYG"], d["LQD"]), False, "隔離掉存續期的信用偏好")
        if has("HYG", "IEF"):
            add("信用·HY對公債", rel(d["HYG"], d["IEF"]), False, "含利率的信用偏好")
        if has("HYG"):
            add("信用·HY趨勢", d["HYG"] / d["HYG"].rolling(200).mean() - 1, False, "HY 相對 200 日均")
        if has("RSP", "SPY"):
            add("廣度·等權", rel(d["RSP"], d["SPY"]), False, "等權對市值權")
        if has("IWM", "SPY"):
            add("廣度·小型股", rel(d["IWM"], d["SPY"]), False, "小型股對大盤")
        bk = [t for t in BASKET if t in d.columns and d[t].notna().sum() > 800]
        if len(bk) >= 6:
            b50 = sum((d[t] > d[t].rolling(50).mean()).astype(float) for t in bk) / len(bk)
            b200 = sum((d[t] > d[t].rolling(200).mean()).astype(float) for t in bk) / len(bk)
            add("廣度·全球50MA", b50, False, f"{len(bk)} 個市場站上 50 日均的比率")
            add("廣度·全球200MA", b200, False, f"{len(bk)} 個市場站上 200 日均的比率")
        if has("SPHB", "SPLV"):
            add("投機·高Beta", rel(d["SPHB"], d["SPLV"]), False, "高 Beta 對低波動")
        if has("XLY", "XLP"):
            add("投機·景氣循環", rel(d["XLY"], d["XLP"]), False, "循環對防禦")
        if has("SPY", "TLT"):
            add("避險·股減債", (d["SPY"]/d["SPY"].shift(20)) - (d["TLT"]/d["TLT"].shift(20)),
                False, "20 日股債報酬差")
    return p.dropna(how="all", axis=1), why


# ------------------------------------------------------------------ 檢定

def sharpe(x, per=252): return x.mean()/x.std()*np.sqrt(per) if x.std() > 0 else np.nan
def mdd(x):
    c = (1+x).cumprod(); return float((c/c.cummax()-1).min())


def gauntlet(px, sig, label, cost=0.0005, tail=10.0, hor=(21, 63, 126)):
    r = px.pct_change().fillna(0)
    cut = int(len(px)*0.6)
    rows = []
    for name in sig.columns:
        rk = rank_trailing(sig[name].dropna(), 750).reindex(px.index)
        lo, hi = (rk <= tail).fillna(False), (rk >= 100-tail).fillna(False)
        for m, tag in ((lo, "恐懼"), (hi, "貪婪")):
            eps = episodes(m, 3)
            for h in hor:
                fwd = (px.shift(-h)/px - 1)
                n = len(independent(eps, px.index, h))
                pt, l, u = circular_block_boot(m.values, fwd.values, h)
                md = min_detectable(fwd.values, n)
                rows.append(dict(訊號=name, 側=tag, 天期=h, 事件=n,
                                 效果pp=None if pt is None else round(pt*100, 2),
                                 CI下=None if l is None else round(l*100, 2),
                                 CI上=None if u is None else round(u*100, 2),
                                 最小可測=None if md is None else round(md*100, 1),
                                 結論=verdict(pt, l, u, md, 0.03, n)))
    t1 = pd.DataFrame(rows)
    print(f"\n{'='*100}\n[{label}] T1　樣本 {px.index[0].date()}→{px.index[-1].date()}"
          f"　{len(px)} 日\n{'='*100}")
    passed = t1[t1["結論"] == "通過"]
    print(f"通過 {len(passed)}／{len(t1)} 格（雜訊期望約 {len(t1)*0.05:.1f}）")
    if len(passed): print(passed.to_string(index=False))
    print("\n恐懼側 vs 貪婪側（63 日，效果差）：")
    for name in sig.columns:
        a = t1[(t1.訊號 == name)&(t1.側 == "恐懼")&(t1.天期 == 63)]["效果pp"].values
        b = t1[(t1.訊號 == name)&(t1.側 == "貪婪")&(t1.天期 == 63)]["效果pp"].values
        if len(a) and len(b) and a[0] is not None and b[0] is not None:
            print(f"  {name:<16}恐懼 {a[0]:>6.2f}　貪婪 {b[0]:>6.2f}　差 {a[0]-b[0]:>6.2f}")

    print(f"\n{'='*100}\n[{label}] T2／T3　樣本外自 {px.index[cut].date()}\n{'='*100}")
    ma = px.rolling(20).mean()
    wma = pd.Series(0.75, index=px.index); wma[px > ma] = 1.0; wma[px < ma] = 0.5
    sma = wma.shift(1).fillna(.75)*r - wma.shift(1).fillna(.75).diff().abs().fillna(0)*cost
    base = {"買進持有": (sharpe(r.iloc[:cut]), sharpe(r.iloc[cut:]), mdd(r.iloc[cut:])),
            "純20日均線": (sharpe(sma.iloc[:cut]), sharpe(sma.iloc[cut:]), mdd(sma.iloc[cut:]))}
    res = {}
    for name in sig.columns:
        rk = rank_trailing(sig[name].dropna(), 750).reindex(px.index)
        w = pd.Series(0.75, index=px.index); w[rk >= 100-tail] = 0.5; w[rk <= tail] = 1.0
        w = w.shift(1).fillna(.75)
        s = w*r - w.diff().abs().fillna(0)*cost
        res[name] = (sharpe(s.iloc[:cut]), sharpe(s.iloc[cut:]), mdd(s.iloc[cut:]))
    print(f"{'訊號':<18}{'內':>7}{'外':>7}{'外MDD':>9}")
    for k, v in {**base, **res}.items():
        print(f"{k:<18}{v[0]:>7.2f}{v[1]:>7.2f}{v[2]*100:>8.1f}%")
    singles = {k: v[1] for k, v in res.items() if not k.startswith("合成")}
    comp = {k: v[1] for k, v in res.items() if k.startswith("合成")}
    if comp and singles:
        bs = max(singles.values()); bc = max(comp.values())
        print(f"\nT3　合成 {bc:.2f} vs 最好單項 {bs:.2f} → "
              f"{'合成有加值' if bc > bs else '**合成沒有加值**'}")
        print(f"對照　全部要贏過純均線 {base['純20日均線'][1]:.2f} "
              f"與買進持有 {base['買進持有'][1]:.2f}")
    return t1


def random_weights(px, parts, cost=0.0005, n=300):
    """等權在隨機權重裡排第幾。排不進前 10% 就代表權重是配適出來的。"""
    r = px.pct_change().fillna(0); cut = int(len(px)*0.6)
    rng = np.random.default_rng(0); k = parts.shape[1]; out = []
    for i in range(n+1):
        w = np.ones(k)/k if i == 0 else rng.dirichlet(np.ones(k))
        c = (parts*w).sum(axis=1, min_count=1)
        rk = rank_trailing(c.dropna(), 750).reindex(px.index)
        pos = pd.Series(0.75, index=px.index); pos[rk >= 90] = .5; pos[rk <= 10] = 1.
        pos = pos.shift(1).fillna(.75)
        s = pos*r - pos.diff().abs().fillna(0)*cost
        out.append(sharpe(s.iloc[cut:]))
    eq, null = out[0], np.array(out[1:])
    null = null[~np.isnan(null)]
    print(f"\n等權 Sharpe {eq:.3f}；{len(null)} 組隨機權重中位 {np.median(null):.3f}；"
          f"等權排第 {(null < eq).mean()*100:.0f} 百分位"
          f" → {'**通過**' if (null < eq).mean() >= .9 else '**沒通過——權重是配適出來的**'}")


def do_run():
    d = load()
    print(f"快取 {d.index[0].date()} → {d.index[-1].date()}　{len(d)} 日、{d.shape[1]} 支")
    for vintage, lab in (("long", "長樣本（^GSPC＋^VIX，1990–）"),
                         ("full", "全成分（含 ETF 系，2012–）")):
        parts, why = build_parts(d, vintage)
        parts = parts.dropna(how="any")
        if parts.empty or parts.shape[1] < 2:
            print(f"\n[{lab}] 成分不足，跳過"); continue
        px = d["^GSPC"].reindex(parts.index).dropna()
        parts = parts.reindex(px.index)
        print(f"\n\n########## {lab} ##########")
        print(f"成分 {parts.shape[1]} 項：" + "、".join(parts.columns))
        sig = {f"合成{parts.shape[1]}項": composite(parts)}
        for c in parts.columns: sig[c] = parts[c]
        gauntlet(px, pd.DataFrame(sig), lab)
        random_weights(px, parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.fetch: do_fetch()
    if a.run: do_run()
    if not (a.fetch or a.run): ap.print_help()
