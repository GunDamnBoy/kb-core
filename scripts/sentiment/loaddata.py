#!/usr/bin/env python3
"""把手上拿得到的真實序列拼成一張日頻面板。

**這一版的資料來源是 GitHub 上的公開鏡像**，不是設計書第三節那些正式端點——
本工作階段的對外連線只通 GitHub 與 PyPI，FRED／CBOE／Yahoo／TWSE／TAIFEX 全部不通。
所以這次回測**驗的是方法，不是最終的成分表**。涵蓋範圍逐項標在下面。
"""
import pandas as pd, numpy as np, pathlib

D = pathlib.Path("/tmp")

def load():
    # CNN F&G 總分（2011-01-03 →），七成分等權、由 CNN 自己維護。當成「別人做好的合成指標」對照組。
    fg = pd.read_csv(D/"sd/fg.csv", parse_dates=["Date"]).set_index("Date")["Fear Greed"].sort_index()

    # VIX 日收（1990 →）
    vix = pd.read_csv(D/"sd/vix.csv", parse_dates=["DATE"]).set_index("DATE")["CLOSE"].sort_index()

    # 價格：SPY 收盤（2011–2023，價格型不含息）→ 之後用 FRED SP500 的報酬接續。
    # 兩段都用「價格型」，不混含息與不含息。
    spy = pd.read_csv(D/"ds_fear-greed-data/datasets/combined/spy_2011_2023.csv",
                      parse_dates=["Date"]).set_index("Date")["Close"].sort_index()
    spx = pd.read_csv(D/"ds_s-and-p-500/archive/fred_sp500.csv",
                      parse_dates=["observation_date"]).set_index("observation_date")["SP500"]
    spx = pd.to_numeric(spx, errors="coerce").dropna().sort_index()

    join = spy.index[-1]                      # 2022-12-30
    tail = spx[spx.index > join]
    if len(tail):
        scale = spy.loc[join] / spx.asof(join)
        px = pd.concat([spy, tail * scale])
    else:
        px = spy
    px = px[~px.index.duplicated()].sort_index()

    # Shiller 月頻：CAPE（PE10）當估值分層變數，不進合成（設計書第十四／十五節）
    sh = pd.read_csv(D/"ds_s-and-p-500/data/data.csv", parse_dates=["Date"]).set_index("Date")
    cape = pd.to_numeric(sh["PE10"], errors="coerce").replace(0, np.nan).dropna().sort_index()

    idx = px.index
    df = pd.DataFrame(index=idx)
    df["px"] = px
    df["vix"] = vix.reindex(idx).ffill(limit=3)
    df["fg"] = fg.reindex(idx).ffill(limit=3)
    df["cape"] = cape.reindex(idx, method="ffill")
    return df.dropna(subset=["px"])

if __name__ == "__main__":
    d = load()
    print(d.shape, d.index[0].date(), "→", d.index[-1].date())
    print(d.notna().sum())
    print(d.tail(3))
