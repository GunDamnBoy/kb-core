#!/usr/bin/env python3
"""區塊自助法 ＋ 檢定力。**這支取代 T1 原本的 Mann-Whitney 判準。**

## 為什麼要換

原本的 T1 把重疊的前瞻報酬砍到「獨立事件首日」才做檢定，理由是對的
（重疊視窗會讓 p 值假得離譜），**但代價是 63 日只剩 9 個事件**。
補做檢定力才發現：n=9 要 **＋5pp** 才驗得出來，而判準寫的是 ＋3pp ——
**那條判準寫下來的當下就只能失敗，或者靠雜訊過關。**

## 換成什麼

不丟資料，改用**環狀區塊自助法**處理自相關：區塊長度取前瞻天期，
重抽整段面板重算統計量。這樣重疊被區塊結構吸收，而樣本量拿得回來。

**回報一律三件事一起給**：點估計、90% 信賴區間、以及那個樣本量下**測得到的最小效果**。
少了第三個，「不顯著」讀起來就會像「沒效果」——那是兩件事。
"""
from __future__ import annotations
import numpy as np


def circular_block_boot(flag: np.ndarray, fwd: np.ndarray, block: int,
                        B: int = 800, seed: int = 0):
    """回傳 (點估計, 下界, 上界)：極端日的前瞻報酬中位數 減 全樣本中位數。"""
    ok = ~np.isnan(fwd)
    flag, fwd = flag[ok].astype(bool), fwd[ok]
    n = len(fwd)
    if n < block * 3 or flag.sum() < 3:
        return None, None, None
    point = float(np.median(fwd[flag]) - np.median(fwd))
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    off = np.arange(block)
    stats = np.empty(B)
    for b in range(B):
        idx = ((rng.integers(0, n, nb)[:, None] + off[None, :]).ravel()[:n]) % n
        f, r = flag[idx], fwd[idx]
        stats[b] = (np.median(r[f]) - np.median(r)) if f.sum() >= 3 else np.nan
    stats = stats[~np.isnan(stats)]
    if len(stats) < B * 0.5:
        return point, None, None
    return point, float(np.percentile(stats, 5)), float(np.percentile(stats, 95))


def min_detectable(fwd: np.ndarray, n_events: int, B: int = 4000,
                   alpha: float = 0.10, power: float = 0.80, seed: int = 1):
    """這個樣本量下，**測得到的最小中位數差**（小數，非百分點）。

    做法：先抽出「n_events 個獨立事件的中位數」在**沒有效果**時的分佈，
    取它的 95 百分位當臨界值；再問要多大的位移，才有 `power` 的機會越過臨界值。
    一層抽樣、全向量化——巢狀重抽跑不完，而且不會更準。
    """
    base = fwd[~np.isnan(fwd)]
    if len(base) < 50 or n_events < 3:
        return None
    rng = np.random.default_rng(seed)
    draws = rng.choice(base, size=(B, n_events), replace=True)
    M = np.median(draws, axis=1)                 # 無效果時的中位數分佈
    crit = np.percentile(M, 100 * (1 - alpha / 2))
    for shift in np.arange(0.0, 0.80, 0.005):
        if np.mean(M + shift > crit) >= power:
            return float(shift)
    return None


MIN_EVENTS = 8      # 少於這個數，任何「通過」都只是在對兩三次行情命名


def verdict(point, lo, hi, mde, target, n_events=None):
    """三種結論，不是兩種。

    設計書第十節原本只有「有效」「無效」，於是所有**看不見**都被記成無效。
    加上「樣本不足以判定」才分得開。

    **2026-08-22 補上獨立事件數下限。** 上一版只檢查「區間不含 0 且點估計夠大」，
    於是 `當沖熱度·極端貪婪 52 週` 在 **n=2** 的情況下被判「通過」——
    點估計 +44pp、信賴區間 [32, 70]，那是同一波行情被數了兩次。
    **自助法的信賴區間不會因為只有兩個事件就變寬到誠實的程度**，
    因為它重抽的是同一批資料。事件數必須另外擋。
    """
    if n_events is not None and n_events < MIN_EVENTS:
        return f"樣本不足以判定（獨立事件僅 {n_events}）"
    if point is None or lo is None:
        return "樣本不足以判定"
    if lo > 0 and point >= target:
        return "通過"
    if mde is not None and abs(point) < mde and lo < 0 < hi:
        return f"樣本不足以判定（測得到的最小效果 {mde*100:.0f}pp）"
    if hi < 0:
        return "反向且信賴區間不含 0"
    return "不通過"
