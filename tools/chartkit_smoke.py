#!/usr/bin/env python3
"""每一種圖型都真的畫得出來嗎。**這支不驗圖畫得對，只驗它畫得出來。**

用法：chartkit_smoke.py [--outdir <目錄>] [--keep]

## 為什麼需要它

`chart/anchors.json` 的 `kinds` 表列了 9 種圖型。實際被用過的只有 2 種
（`grouped_bar` 25 次、`waterfall` 2 次），另外 7 種**一次都沒有被畫過** ——
`timeseries`、`scatter`、`stacked_bar`、`pct_stacked_bar`、`range_area`、
`heatmap`、`gauge`。

沒被畫過不等於畫不出來，但也不等於畫得出來，而**這兩件事目前分不開**。
`chartkit.py` 自己記著 2026-08-11 的事故：那一期的 `range_area` 標了 marker，
**檢查通過、兩軌都沒畫出來** —— 規則要求標記，實作默默丟掉。
一個從沒被執行過的分支，它的失效會在第一次被用到的那天才出現，
而那天是週日晚上的排程。

## 三個判準，第三個才是重點

1. 渲染不丟例外。
2. PNG 產出來了，而且不是零位元組。
3. **PNG 裡真的有東西** —— 不同顏色數要超過門檻。

第 3 條存在，是因為前兩條會被一張**空白圖**完全滿足。
matplotlib 對「資料進不去」的反應通常不是丟例外，是畫一張有標題、有座標軸、
中間什麼都沒有的圖 —— 檔案有幾十 KB、`os.path.getsize` 看起來很正常，
而 `assemble.py` 只記錄 `bytes`。**那正是 2026-08-11 那張圖的形狀。**

## 樣本規格從 anchors 的 `kinds` 表長出來，不是寫死的

`kinds` 表宣告每種圖型的 `data` 欄位。這支照著表生成最小樣本，
所以**表裡新增一種圖型，這支下一次執行就會測到它** ——
一個手寫的樣本清單會停在寫的那天，而它「全部通過」的樣子跟真的測完一模一樣。
表裡出現這支不會生成的欄位時，它會明講「不知道怎麼給這個欄位」而不是跳過。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

_KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_KB, "scripts", "chart"))

MIN_BYTES = 4_000
MIN_COLORS = 24        # 空白圖（白底＋黑軸＋標題）實測約 5–15 種顏色

_DAYS = [(dt.date(2026, 1, 1) + dt.timedelta(days=30 * i)).isoformat() for i in range(6)]


def _series():
    import chartkit as C
    return [C.Series(name="甲", dates=_DAYS, values=[100 + 7 * i for i in range(len(_DAYS))]),
            C.Series(name="乙", dates=_DAYS, values=[80 + 5 * i for i in range(len(_DAYS))])]


def sample(field, kind):
    """一個欄位的最小合理樣本。**認不得的欄位回 KeyError，不回空值。**

    回空值等於「這個欄位我給了」，然後渲染層拿到空 list 畫出一張空白圖 ——
    而空白圖正是這支要抓的東西。**測試自己製造出它要抓的失效，是最糟的一種。**
    """
    return {
        # **`Series` 物件，不是 dict。** 這正是這支第一次執行時抓到的東西：
        # `timeseries` 與 `range_area` 在研究線上從來沒畫出來過，因為
        # `assemble.py` 把 dict 原樣塞進 `Chart`。樣本用真正的形狀，
        # 才問得出「渲染層畫不畫得出來」這個問題本身。
        "series": _series(),
        "cats": ["台灣", "韓國", "日本", "印度"],
        "vals": [12.0, -4.5, 8.25, 3.0],
        "groups": [{"name": "2025", "values": [10, 20, 30, 15]},
                   {"name": "2026", "values": [14, 18, 36, 21]}],
        "pts": [[1.0, 2.0], [2.5, 3.5], [4.0, 1.5], [5.5, 4.25]],
        "hi_pts": [[4.0, 1.5, "離群"]],
        "band": [[d, 90 + 3 * i, 130 + 4 * i] for i, d in enumerate(_DAYS)],
        "band_label": "近十年區間",
        "matrix": [[1.0, -2.0, 3.0], [0.5, 4.0, -1.5], [2.0, 1.0, 0.0]],
        "rows": ["能源", "科技", "金融"],
        "gauge": {"value": 62.0, "lo": 0.0, "hi": 100.0, "ref": 50.0},
    }[field]


def colors_in(png):
    """PNG 裡有幾種不同顏色。畫不出東西的圖只有底色與軸線。"""
    try:
        from PIL import Image
    except ImportError:
        return None                    # None ＝ 沒量，跟「量了而且很少」是兩件事
    with Image.open(png) as im:
        return len(im.convert("RGB").getcolors(maxcolors=1 << 20) or [])


def run(outdir):
    A = json.load(open(os.path.join(_KB, "chart", "anchors.json"), encoding="utf-8"))
    # `kinds` 表在 anchors 的頂層，不是 `charts` 底下。
    # **這裡不 `.get(..., {})`** —— 取不到表就沒有資格說「全部圖型都測過了」，
    # 而一個空 dict 會讓下面的迴圈跑零圈、印出「0/0 種畫得出來」並回 exit 0。
    # **判準是「有沒有 `data` 欄位」，不是「是不是 dict」。**
    # `kinds._pick` 是給撰寫者看的選型判準表，它也是 dict ——
    # 第一版把它當成一種圖型測，然後回報「畫得出來」。
    # 一個測了不存在的東西的測試，通過的樣子跟真的測完一模一樣。
    kinds = {k: v for k, v in A["kinds"].items()
             if isinstance(v, dict) and v.get("data")}
    os.environ.setdefault("CHART_REPO", outdir)
    import chartkit as C
    F = C.Chart.__dataclass_fields__

    rows, bad = [], []
    for kind, spec in sorted(kinds.items()):
        kw = {"slug": f"smoke-{kind}", "title": f"冒煙測試：{kind}",
              "subtitle": "這張圖只用來確認這一種圖型畫得出來", "kind": kind,
              "y_label": "單位", "source": "smoke"}
        try:
            for f in spec.get("data") or []:
                if f not in F:
                    raise KeyError(f"`kinds` 表要 `{f}`，而 Chart 沒有這個欄位")
                kw[f] = sample(f, kind)
        except KeyError as e:
            rows.append((kind, "樣本", f"不知道怎麼給這個欄位：{e}", None, None))
            bad.append(kind)
            continue
        if kind == "pct_stacked_bar" and "cats" not in kw:
            kw["cats"], kw["groups"] = sample("cats", kind), sample("groups", kind)
        try:
            out = C.render_static(C.Chart(**kw), outdir, f"smoke-{kind}")
        except Exception as e:
            rows.append((kind, "例外", f"{type(e).__name__}: {e}", None, None))
            bad.append(kind)
            continue
        png = out.get("png")
        n = os.path.getsize(png) if png and os.path.exists(png) else 0
        c = colors_in(png) if n else None
        verdict = ("沒有 PNG" if not n else
                   f"PNG 只有 {n:,} 位元組" if n < MIN_BYTES else
                   "（沒裝 Pillow，顏色數沒量）" if c is None else
                   f"**只有 {c} 種顏色，像一張空白圖**" if c < MIN_COLORS else "")
        rows.append((kind, "OK" if not verdict or c is None else "空白?", verdict, n, c))
        if verdict and c is not None:
            bad.append(kind)

    w = max(len(k) for k in kinds)
    print(f"{'圖型'.ljust(w)}  {'結果':6s}{'位元組':>10}{'顏色數':>7}  說明")
    for kind, st, why, n, c in rows:
        print(f"{kind.ljust(w)}  {st:6s}{(f'{n:,}' if n else '—'):>10}"
              f"{(str(c) if c is not None else '—'):>7}  {why}")
    print(f"\n{len(kinds) - len(bad)}/{len(kinds)} 種畫得出來"
          + (f"　**失敗：{bad}**" if bad else ""))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
        print(__doc__); return 2
    d = a.outdir or tempfile.mkdtemp(prefix="chartsmoke-")
    os.makedirs(d, exist_ok=True)
    try:
        return run(d)
    finally:
        if a.keep or a.outdir:
            print(f"  圖留在 {d}")
        else:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
