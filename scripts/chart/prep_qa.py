#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日五圖 · 第 4 步的旗標表。**這支只讀不寫。**

用法：
    python3 ~/kb-core/scripts/chart/prep_qa.py [YYYY-MM-DD]

## 為什麼有這一支

第 4 步的完成條件是「每個旗標都有具名的處置，沒有『不確定』」。
而在這支出現之前，**第 4 步當下沒有任何可以跑的東西**：
5σ 的計算早就寫好了（`chartkit.qa_series`），但它唯一的呼叫點是
`render_day.py` —— 那是**第 6 步**。所以第 4 步的執行者只有兩條路：
自己重算一次，或是等出圖之後才第一次看到旗標。
**每天當場重寫一次的統計，每天都有一次寫錯的機會**（同 `scan_moves.py` 那一條）。

這支把第 6 步會算的那一份提前印出來，用的是**同一個函式、同一組門檻**
（`anchors.quality.sigma`，不是 `qa_series` 的預設值），
所以第 4 步看到的與稍後寫進 `about.qa_flags` 的是同一份東西，不是另一個估算。

## 它不做的事

**不分類、不判斷、不寫檔。** 分類是第 4 步，是判斷。
它只把旗標攤開，並標出三件「分類時一定要知道、但看旗標本身看不出來」的事：

- `derived` —— 衍生序列的窗口效應。**整條序列說明一次即可，不要逐筆。**
  `qa_series` 的註解記著：2026-08-06 那期 18 筆裡有 13 筆是這一種，
  逐筆要求只會逼出罐頭文字。
- `abs_chg` —— 穿越零的流量序列，`pct` 欄記的是**絕對變動不是百分比**。
  拿它跟轉倉的 1–2% 比，是拿兩把不同的尺量同一件事。
- **幅度對照** —— 轉倉價差正常在 `rollover_spread_normal_pct` 以內、
  極少超過 `rollover_spread_rare_pct`。超過那個數量級的旗標
  **在數量級上就不可能是轉倉**。先看幅度再看故事。

## 為什麼這支肯猜路徑，而 `build_series.py` 不肯

`_repo.py` 刻意不從 `__file__` 推導資料 repo，理由是**寫錯地方是安靜的**。
這支只讀，而讀錯地方是大聲的（檔案不在就停）。所以它照 `prep_chart.py` 的
兄弟層規則找，並且 `CHART_REPO` 有設就以它為準 —— 兩邊不會各走各的。
"""
import argparse
import datetime as dt
import json
import os
import sys

TPE = dt.timezone(dt.timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
KBCORE = os.path.dirname(os.path.dirname(HERE))
SIB = os.path.dirname(KBCORE)


def chart_repo():
    """資料 repo。`CHART_REPO` 優先，其次兄弟層，其次 `~`。找不到回空字串。"""
    p = os.environ.get("CHART_REPO")
    if p:
        return os.path.expanduser(p)
    for c in (os.path.join(SIB, "chart-of-the-day"),
              os.path.expanduser("~/chart-of-the-day")):
        if os.path.isdir(os.path.join(c, "data")):
            return c
    return ""


def load(path, what):
    """讀不到就說出來並回 None。**讀不到與「裡面是空的」是兩件事。**"""
    if not os.path.exists(path):
        return None, f"{what} 不在：{path}"
    try:
        return json.load(open(path, encoding="utf-8")), None
    except Exception as e:
        return None, f"{what} 讀不開：{type(e).__name__}: {e}"


def key_of(f):
    """處置要對得上旗標，所以鍵長什麼樣子印出來，不要讓人猜。"""
    return f"{f.get('chart','?')}|{f.get('series','?')}|{f.get('date','?')}"


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args(argv[1:])
    if a.help:
        print(__doc__)
        return 0

    day = a.date or dt.datetime.now(TPE).date().isoformat()
    anchors, e1 = load(os.path.join(KBCORE, "chart", "anchors.json"), "chart/anchors.json")
    if anchors is None:
        print(e1, file=sys.stderr)
        return 12

    repo = chart_repo()
    if not repo:
        print("找不到 chart-of-the-day 的 data/ —— 設 CHART_REPO 或確認資料夾連上了",
              file=sys.stderr)
        return 12
    doc, e2 = load(os.path.join(repo, "data", f"{day}.json"), f"{day} 的日檔")
    if doc is None:
        print(e2, file=sys.stderr)
        print("　**第 4 步要在第 3 步之後跑** —— 序列還沒實體化就沒有東西可以檢查。",
              file=sys.stderr)
        return 12

    # `render_day` 的模組層會呼叫 `_repo.repo()`，沒有 CHART_REPO 就 sys.exit。
    # 這裡先把我們解出來的那一個 export 出去再 import —— 兩支因此**必然**指向
    # 同一個 repo。刻意不自己複製一份 `to_chart`：那個函式與 `Chart` 的欄位是
    # 一組兩份，複製出去之後加欄位只會加一邊（2026-08-09 `derived` 就是這樣漏接的）。
    os.environ["CHART_REPO"] = repo
    sys.path.insert(0, HERE)
    import chartkit as ck                                        # noqa: E402
    import render_day as rd                                      # noqa: E402

    Q = anchors.get("quality") or {}
    sigma = Q.get("sigma")
    if sigma is None:
        print("anchors.quality.sigma 不在 —— 門檻的家在 anchors，這裡不寫死",
              file=sys.stderr)
        return 12
    normal = (Q.get("rollover_spread_normal_pct") or [0, 1])[-1]
    rare = Q.get("rollover_spread_rare_pct")
    cats = Q.get("disposition_categories") or []

    print(f"# 每日五圖 · 第 4 步旗標表　{day}\n")
    print(f"門檻 **{sigma}σ**（`anchors.quality.sigma`）　相鄰交易日合併成一筆事件")
    print(f"日檔 {os.path.join(repo, 'data', f'{day}.json')}\n")

    flags, broken = [], []
    for i, c in enumerate(doc.get("charts") or [], 1):
        slug = c.get("slug", f"第{i}張")
        try:
            flags += ck.qa_series(rd.to_chart(c), z=sigma)
        except Exception as e:
            # **組不起來與「沒有旗標」不是同一件事**，而它們在輸出上長得一樣。
            broken.append(f"{slug}：{type(e).__name__}: {e}")

    if broken:
        print("## ⚠︎ 有圖組不起 Chart —— 這幾張**沒有被檢查過**，不是「沒有旗標」\n")
        for b in broken:
            print(f"　· {b}")
        print()

    if not flags:
        print("## 旗標 0 筆\n")
        print("　本期沒有超過門檻的單日跳動。第 4 步的處置是空的 —— "
              "**但那是一個結論，要寫進 `about`**，不是什麼都不寫。")
        if broken:
            print("　**上面那幾張沒被檢查過**，所以這個 0 不涵蓋它們。")
            return 1
        return 0

    print(f"## 旗標 {len(flags)} 筆\n")
    derived_by_series, impossible = {}, []
    for n, f in enumerate(sorted(flags, key=lambda x: (str(x.get("chart")),
                                                       str(x.get("date")))), 1):
        span = ""
        if f.get("days"):
            span = f" → {f.get('date_end')}（{f['days']} 個交易日，同一次事件）"
        unit = "" if f.get("abs_chg") else "%"
        tags = [t for t, on in (("derived", f.get("derived")),
                                ("abs_chg", f.get("abs_chg"))) if on]
        tag = f"　[{'／'.join(tags)}]" if tags else ""
        print(f"{n:>3}  {f.get('chart','?'):<22} {f.get('series','?')}")
        print(f"     {f.get('date','?')}{span}　{f.get('pct'):+}{unit}　z={f.get('z')}{tag}")
        print(f"     鍵 `{key_of(f)}`")
        if f.get("derived"):
            derived_by_series.setdefault((f.get("chart"), f.get("series")), 0)
            derived_by_series[(f.get("chart"), f.get("series"))] += 1
            print("     └ 衍生序列：極端值滾出窗口造成的階梯，"
                  "**不是市場事件、不是轉倉、也不是錯價**")
        elif f.get("abs_chg"):
            print("     └ 穿越零的流量序列：`pct` 是**絕對變動**，"
                  "不要拿它跟轉倉的百分比門檻比")
        elif rare is not None and abs(f.get("pct") or 0) > rare:
            impossible.append(key_of(f))
            print(f"     └ |{f.get('pct')}%| > {rare}%（極少超過的那條線，正常在 "
                  f"{normal}% 以內）—— **在數量級上不可能是轉倉**")
        print()

    if derived_by_series:
        print("## 衍生序列可以整條說明一次\n")
        for (sl, se), n in derived_by_series.items():
            print(f"　· {sl}｜{se}　{n} 筆 —— 鍵可寫 `{sl}|{se}|*`")
        print("\n　**逐筆要求只會逼出罐頭文字**（2026-08-06：18 筆裡 13 筆是這一種）。\n")

    if impossible:
        print("## 幅度上不可能是轉倉的旗標\n")
        for k in impossible:
            print(f"　· {k}")
        print("\n　**先看幅度再看故事。** 這幾筆若被分類成轉倉，那個分類是錯的。\n")

    print("## 這一步要交出什麼\n")
    print(f"　每一筆一個具名處置，值域：{'／'.join(cats) if cats else '（anchors.quality.disposition_categories 還沒設）'}")
    print("　**「不確定」不是處置**（SKILL 第 4 步的完成條件）。")
    print(f"　衍生序列合併之後，最少要寫 "
          f"{len(flags) - sum(derived_by_series.values()) + len(derived_by_series)} 筆。")
    print("\n**分類是第 4 步，這支不分類。**")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
