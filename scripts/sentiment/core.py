#!/usr/bin/env python3
"""情緒指標的計分核心。**這支只算不抓、只讀不寫。**

回測與線上共用這一支——設計書第二節那條「回望禁令」只有在兩邊跑同一份程式時才守得住。
兩套長得很像的實作，會在回測漂亮而線上不漂亮的時候讓人找錯方向。
"""
from __future__ import annotations
import numpy as np
import pandas as pd

WINDOW = 750          # 3 年（交易日）。週頻序列用 156。理由見設計書第十五節末。
WARMUP = WINDOW       # 熱身期不發分數，不用縮短窗口硬湊


def rank_trailing(s: pd.Series, window: int = WINDOW, invert: bool = False) -> pd.Series:
    """每一天的百分位，**只用當天以前（含當天）的 window 筆**算。

    這是整套設計裡最容易被跳過、跳過之後最致命的一行：
    用全樣本算百分位再拿去回測，回測會非常漂亮，而且漂亮得完全合理——
    因為指標偷看了未來的分佈，才知道今天算不算極端。
    """
    r = s.rolling(window, min_periods=window).apply(
        lambda w: (w[:-1] < w[-1]).sum() / (len(w) - 1) * 100.0, raw=True)
    return (100.0 - r) if invert else r


def composite(parts: pd.DataFrame) -> pd.Series:
    """等權平均，**缺項只縮分母、不插補**（設計書第三節）。

    缺 3 項以上當天不發分數——一個湊出來的分數比沒有分數更糟。
    """
    n_ok = parts.notna().sum(axis=1)
    out = parts.mean(axis=1, skipna=True)
    return out.where(n_ok >= max(1, parts.shape[1] - 2))


def consensus(parts: pd.DataFrame, tail: float = 10.0, need: int = None) -> pd.Series:
    """共識門：幾項同時落在自己分佈的前/後 `tail`%。

    回傳有號的計數：正＝貪婪側、負＝恐懼側。合成分數的靈敏度隨成分數衰減，
    這個判準不會——理由見設計書第一節的機制 A。
    """
    hot = (parts >= 100 - tail).sum(axis=1)
    cold = (parts <= tail).sum(axis=1)
    return (hot - cold).where(parts.notna().sum(axis=1) > 0)


def zones(score: pd.Series, cuts) -> pd.Series:
    """cuts = (極端恐懼上界, 恐懼上界, 中性上界, 貪婪上界)。門檻由回測訂，不抄 CNN。"""
    a, b, c, d = cuts
    return pd.cut(score, [-0.01, a, b, c, d, 100.01],
                  labels=["極端恐懼", "恐懼", "中性", "貪婪", "極端貪婪"])


def episodes(mask: pd.Series, gap: int = 3):
    """連續（容許 gap 個交易日空檔）的極端日合併成一段。回傳 [(起, 迄, 天數)]。"""
    idx = list(mask.index[mask.fillna(False).astype(bool)])
    if not idx:
        return []
    pos = {d: i for i, d in enumerate(mask.index)}
    out, s, p = [], idx[0], idx[0]
    for d in idx[1:]:
        if pos[d] - pos[p] <= gap + 1:
            p = d
        else:
            out.append((s, p, pos[p] - pos[s] + 1)); s = p = d
    out.append((s, p, pos[p] - pos[s] + 1))
    return out


def independent(eps, index, horizon: int):
    """把**前瞻窗重疊**的 episode 併成一個獨立事件，回傳每組的首日。

    舊系統的回測報告踩過這一個：「2020-10 與 2022-02 兩個 run-up 的前瞻窗
    涵蓋同一次 2022 熊市，算的是同一段跌幅……37.5%／60% 背後是 2 件事，不是 6 件。」
    只按進場日分組**擋不住**這件事——那是兩段分開的觸發，共用一段未來。
    """
    pos = {d: i for i, d in enumerate(index)}
    groups, cur = [], []
    for st, en, _ in eps:
        if cur and pos[st] - pos[cur[0]] < horizon:
            cur.append(st)
        else:
            if cur: groups.append(cur)
            cur = [st]
    if cur: groups.append(cur)
    return [g[0] for g in groups]


def fwd_returns(px: pd.Series, days: int) -> pd.Series:
    return px.shift(-days) / px - 1.0
