#!/usr/bin/env python3
"""美股「部位」那一族的回測：CFTC TFF 的 Leveraged Funds 與 Asset Manager。

用法：python3 cftc_probe.py

## 為什麼是這一支

第一階段回測驗掉的是**價格與波動**那一族（動能、VIX、已實現波動、CNN F&G 七項），
全族都測不出可用的前瞻資訊。剩下唯一有理由不一樣的是**部位**——它量的不是價格。

台股那一側是日頻的（`tw_probe.py`）。美股這一側最接近的免費資料就是 CFTC 的
**Traders in Financial Futures**：它把交易人拆成 Dealer／**Asset Manager**／
**Leveraged Funds**／Other，也就是

> Leveraged Funds ≈ BofA 的 HF positioning，Asset Manager ≈ BofA 的 LO positioning。
> **一個免費來源同時拿到 BofA 六構面裡的兩個。**

## 為什麼走年度 zip 而不是 Socrata

`publicreporting.cftc.gov` 從這台機器回 **403**（主動拒絕，不是慢）。
CFTC 官網自己的年度檔 `files/dea/history/fut_fin_txt_YYYY.zip` **回 200**，
而且沒有 rate limit、一次一年。**驗過的路徑才寫進程式。**

## 規模分母（設計書第十五節）

淨部位一律除以 **Open Interest**。不除，量到的是市場自己在長大，不是部位在變。
"""
from __future__ import annotations
import csv, io, os, sys, zipfile
import urllib.request
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import rank_trailing, composite, episodes, independent, fwd_returns
from blockstats import circular_block_boot, min_detectable, verdict

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CACHE = os.path.abspath(os.path.expanduser(os.environ.get("SENT_CACHE", "~/sent-cache")))
YEARS = range(2010, 2027)          # TFF 財金期貨的歷史起點約 2010
WINDOW_W = 156                     # 週頻 3 年 ＝ 156 週（與日頻的 3 年同尺度）

CONTRACTS = {
    "ES": ("E-MINI S&P 500", "CHICAGO MERCANTILE"),
    "NQ": ("NASDAQ-100", "MINI"),
    "RTY": ("RUSSELL", "MINI"),
    "VX": ("VIX FUTURES", ""),
}


def fetch(url, timeout=90):
    r = urllib.request.Request(url); r.add_header("User-Agent", UA)
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read()


def _norm(h):
    return "".join(ch for ch in str(h).lower() if ch.isalnum())


def find(hdr, exact=(), need=(), avoid=()):
    """照名字找欄位索引，**但不要求名字一模一樣**。

    2026-08-22 學到的：`Report_Date_as_MM_DD_YYYY` 只用到 2012，
    2013 起 CFTC 改成 `Report_Date_as_YYYY-MM-DD`。
    寫成完全相符，等於把「欄位可能改名」當成「欄位不會改名」——
    **它跳過了十四年而且每一年都印得很像是資料的問題。**

    先試正規化後的完全相符，再退回關鍵字，且用 `avoid` 擋掉
    `Change_in_...`／`Pct_of_...` 這些長得很像的鄰居。
    """
    N = [_norm(h) for h in hdr]
    for e in exact:
        n = _norm(e)
        if n in N: return N.index(n)
    for i, n in enumerate(N):
        if all(k in n for k in need) and not any(a in n for a in avoid):
            return i
    return None


COLS = {
    "market": dict(exact=["Market_and_Exchange_Names"], need=["market", "exchange"]),
    "date":   dict(exact=["Report_Date_as_MM_DD_YYYY", "Report_Date_as_YYYY-MM-DD"],
                   need=["report", "date"], avoid=["asof"]),
    "oi":     dict(exact=["Open_Interest_All"], need=["openinterest", "all"],
                   avoid=["change", "pct", "of"]),
    "am_l":   dict(exact=["Asset_Mgr_Positions_Long_All"], need=["asset", "long", "all"],
                   avoid=["change", "pct", "spread", "other"]),
    "am_s":   dict(exact=["Asset_Mgr_Positions_Short_All"], need=["asset", "short", "all"],
                   avoid=["change", "pct", "spread", "other"]),
    "lm_l":   dict(exact=["Lev_Money_Positions_Long_All"], need=["lev", "long", "all"],
                   avoid=["change", "pct", "spread", "other"]),
    "lm_s":   dict(exact=["Lev_Money_Positions_Short_All"], need=["lev", "short", "all"],
                   avoid=["change", "pct", "spread", "other"]),
}

_reported = {"done": False}


def load_year(y):
    """一年一個 zip。**欄位照名字找，允許改名。**
    解析不出來的年份整年跳過並印出來——不用位置猜。"""
    p = os.path.join(CACHE, f"cftc_{y}.zip")
    if not os.path.exists(p):
        os.makedirs(CACHE, exist_ok=True)
        try:
            b = fetch(f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{y}.zip")
        except Exception as e:
            print(f"  {y}: 抓不到（{e.__class__.__name__}）"); return []
        open(p, "wb").write(b)
    try:
        z = zipfile.ZipFile(p)
        name = [n for n in z.namelist() if n.lower().endswith(".txt")][0]
        txt = z.read(name).decode("utf-8", "replace")
    except Exception as e:
        print(f"  {y}: 解壓失敗（{e.__class__.__name__}）"); return []
    rd = csv.reader(io.StringIO(txt))
    hdr = next(rd, None)
    if not hdr:
        print(f"  {y}: 空檔"); return []
    ix = {k: find(hdr, **v) for k, v in COLS.items()}
    miss = [k for k, v in ix.items() if v is None]
    if miss:
        print(f"  {y}: **解析不出欄位 {miss}，整年跳過**")
        print(f"        該檔標題列前 12 欄：{[str(h)[:34] for h in hdr[:12]]}")
        return []
    if not _reported["done"]:
        print("  對到的欄位：" + "、".join(f"{k}={hdr[i]}" for k, i in ix.items()))
        _reported["done"] = True
    out = []
    for row in rd:
        if len(row) <= max(ix.values()): continue
        mk = row[ix["market"]].upper()
        tag = next((k for k, (a, b) in CONTRACTS.items() if a in mk and (not b or b in mk)), None)
        if not tag: continue
        try:
            oi = float(row[ix["oi"]])
            if oi <= 0: continue
            out.append(dict(
                d=pd.to_datetime(row[ix["date"]]), c=tag, oi=oi,
                am=(float(row[ix["am_l"]]) - float(row[ix["am_s"]])) / oi,
                lm=(float(row[ix["lm_l"]]) - float(row[ix["lm_s"]])) / oi))
        except (ValueError, KeyError, TypeError):
            continue
    return out


def prices():
    """價格用 GitHub 鏡像（Stooq 從這台機器只回 HTML，不是資料）。"""
    def raw(u): return fetch(u).decode("utf-8", "replace")
    spy = pd.read_csv(io.StringIO(raw(
        "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/"
        "datasets/combined/spy_2011_2023.csv")), parse_dates=["Date"], index_col="Date")["Close"]
    spx = pd.read_csv(io.StringIO(raw(
        "https://raw.githubusercontent.com/datasets/s-and-p-500/main/archive/fred_sp500.csv")),
        parse_dates=[0], index_col=0).iloc[:, 0]
    spx = pd.to_numeric(spx, errors="coerce").dropna()
    j = spy.index[-1]; tail = spx[spx.index > j]
    px = pd.concat([spy, tail * (spy.loc[j] / spx.asof(j))]) if len(tail) else spy
    return px[~px.index.duplicated()].sort_index()


def main():
    print("下載 CFTC TFF 年度檔（第一次會慢，之後讀快取）：")
    rows = []
    for y in YEARS:
        r = load_year(y)
        if r: print(f"  {y}: {len(r)} 列"); rows += r
    if not rows:
        print("\n**一年都沒拿到——這一步做不了。** 貼錯誤訊息回來。"); return

    df = pd.DataFrame(rows)
    piv = df.pivot_table(index="d", columns="c", values=["am", "lm"], aggfunc="last")
    piv = piv.sort_index()
    print(f"\n週頻面板 {piv.index[0].date()} → {piv.index[-1].date()}　{len(piv)} 週")

    parts = pd.DataFrame(index=piv.index)
    for c in ("ES", "NQ", "RTY"):
        if ("lm", c) in piv: parts[f"槓桿基金·{c}"] = rank_trailing(piv[("lm", c)], WINDOW_W)
        if ("am", c) in piv: parts[f"資產管理·{c}"] = rank_trailing(piv[("am", c)], WINDOW_W)
    if ("lm", "VX") in piv:                      # 槓桿基金做空 VIX ＝ 風險偏好高，要反轉
        parts["槓桿基金·VIX"] = rank_trailing(piv[("lm", "VX")], WINDOW_W, invert=True)
    parts = parts.dropna(how="all", axis=1)
    if parts.empty or not len(parts.columns):
        print("**一個成分都建不起來——面板太短或合約名稱沒對到。**")
        print("面板裡出現過的合約：" + "、".join(sorted(df["c"].unique())))
        return
    print("可用成分：" + "、".join(parts.columns))

    px = prices()
    pw = px.reindex(piv.index, method="ffill")           # 週二部位對到當週價格
    sig = {"合成部位": composite(parts)}
    sig["槓桿基金合成"] = composite(parts[[c for c in parts.columns if c.startswith("槓桿基金")]])
    sig["資產管理合成"] = composite(parts[[c for c in parts.columns if c.startswith("資產管理")]])
    for c in parts.columns: sig[f"單項·{c}"] = parts[c]
    sig = pd.DataFrame(sig)

    print("\n" + "=" * 92)
    print("T1（區塊自助法．含檢定力）　**前瞻以週計，且部位資料週二、週五才公布 → 訊號延後一週使用**")
    print("=" * 92)
    rows2 = []
    for name in sig.columns:
        s = sig[name].dropna()
        if len(s) < WINDOW_W + 30: continue
        r = rank_trailing(s, WINDOW_W)
        lo = (r <= 10).reindex(pw.index, fill_value=False).shift(1).fillna(False)
        hi = (r >= 90).reindex(pw.index, fill_value=False).shift(1).fillna(False)
        for mask, tag in ((lo, "極端恐懼"), (hi, "極端貪婪")):
            eps = episodes(mask, 1)
            for h in (4, 13, 26, 52):                    # 週
                fwd = pw.shift(-h) / pw - 1
                n_ind = len(independent(eps, pw.index, h))
                pt, l, u = circular_block_boot(mask.values, fwd.values, h)
                mde = min_detectable(fwd.values, n_ind)
                rows2.append(dict(訊號=f"{name}·{tag}", 週=h, 極端週=int(mask.sum()),
                                  獨立事件=n_ind,
                                  點估計pp=None if pt is None else round(pt*100, 2),
                                  CI下界=None if l is None else round(l*100, 2),
                                  CI上界=None if u is None else round(u*100, 2),
                                  最小可測pp=None if mde is None else round(mde*100, 1),
                                  結論=verdict(pt, l, u, mde, 0.03)))
    t = pd.DataFrame(rows2)
    if t.empty:
        print("**一個成分都沒累積到足夠長度（週頻需 > 156 週）——上面的年份解析全掛了。**")
        print("把整段輸出貼回來，特別是「該檔標題列前 12 欄」那幾行。")
        return
    print(t.to_string(index=False))
    out = os.path.join(CACHE, "cftc_results.json")
    t.to_json(out, orient="records", force_ascii=False, indent=1)
    print(f"\n結果寫到 {out}")
    print("\n--- 只看 13 週（約一季）---")
    print(t[t["週"] == 13].to_string(index=False))


if __name__ == "__main__":
    main()
