#!/usr/bin/env python3
"""檢定力分析：**「不顯著」跟「沒有效果」是兩件事。**

樣本只有十幾個獨立事件時，要多大的效果才驗得出來？
不算這一步，就會把「這個測試看不見」誤讀成「這個效果不存在」。
"""
import sys, numpy as np
from scipy.stats import mannwhitneyu
sys.path.insert(0, "/tmp/sent/eng")
from loaddata import load
import pandas as pd

df = load(); px = df["px"]
rng = np.random.default_rng(1)
print("要多大的效果，才有 80% 機會在 p<0.10 被抓到？（Mann-Whitney，蒙地卡羅 400 次）\n")
print(f"{'天期':>5} {'獨立事件 n':>10} {'可偵測的最小中位數差':>22}")
for h, n in ((21, 15), (63, 9), (126, 8), (252, 3)):
    base = (px.shift(-h)/px - 1).dropna().values
    found = None
    for shift in np.arange(0.0, 0.60, 0.01):
        hits = 0
        for _ in range(400):
            s = rng.choice(base, n, replace=True) + shift
            try: _, p = mannwhitneyu(s, base, alternative="two-sided")
            except ValueError: continue
            hits += (p < 0.10)
        if hits/400 >= 0.80: found = shift; break
    print(f"{h:>5} {n:>10} {(found*100 if found else float('nan')):>20.0f}pp")
