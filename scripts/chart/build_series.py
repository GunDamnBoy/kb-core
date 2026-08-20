# -*- coding: utf-8 -*-
"""
build_series.py — 把當日 JSON 裡的 `series_spec` 實體化成 `series`。

**為什麼存在**：2026-08-09 量測，執行者每天親手把 ~34,000 字元的資料點打進 JSON，
是整輪最大的單一 token 成本——而那些數字機器本來就有（`fetch.py` 的快取與轉換函式）。
執行者該做的是「決定畫什麼」，不是「抄寫資料點」。

用法：
    在 chart 裡寫 `series_spec`（見下），然後：
        python3 ~/kb-core/scripts/chart/build_series.py <day>            # 實體化所有含 spec 的圖
        python3 ~/kb-core/scripts/chart/build_series.py <day> --dry-run  # 只印會產生什麼，不寫檔
        python3 ~/kb-core/scripts/chart/build_series.py --selftest       # 離線驗證轉換邏輯

spec 格式（每條序列一個物件）：
    {"id": "^SOX",              ← fetch.py 認得的代號（Yahoo 或 FRED）
     "name": "費城半導體",       ← 圖例名稱，必填
     "t": "rebase",             ← 轉換：raw｜rebase｜diff｜yoy｜ma:3｜vol:60
     "since": "2026-01-02",     ← 起日（rebase 的基期＝起日）
     "style": "bar",            ← 選填，同 series 的欄位
     "axis": "right", "dash": true, "color": "#..."（同上，都選填）}

    chart 層可加 "series_align": true → 先取所有序列交易日交集再轉換
    （跨市場比較必須開，否則台美假日錯位）。

轉換說明：
    raw    原值
    rebase 起日＝100（用 fetch.rebase）
    diff   一階差分（月增；非農用）
    yoy    對 12 期前的年增率 %（CPI／PCE 用；**前 12 期會被消耗掉**）
    ma:N   N 期移動平均，**自動標 derived**
    vol:N  N 期日報酬標準差 %，**自動標 derived**（衍生序列的 QA 四分法見 brief 3.4）

設計原則：
    · `series_spec` 寫進 JSON 後**保留**，與 `series` 並存——spec 是「這條線怎麼來的」
      的紀錄，讓任何一天的圖連轉換方式都可考。
    · 已有 `series` 且無 `series_spec` 的圖**完全不碰**（手工序列仍合法）。
    · 取數走 `fetch.get()`：同日已抓過就吃快取，不重複打外部站台。
"""
from __future__ import annotations
import json, os, statistics, sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()
# 同目錄的兄弟模組。舊制是 os.path.join(REPO, "tools")——
# 那綁在「程式住在資料 repo 底下」這個佈局上，搬家就斷。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F                                       # noqa: E402


def _is_monthly(d: list) -> bool:
    """FRED 月頻序列一律以每月 1 號標記。"""
    return len(d) > 2 and all(x.endswith("-01") for x in d)


def _shift_months(day: str, n: int) -> str:
    y, m = int(day[:4]), int(day[5:7])
    t = y * 12 + (m - 1) - n
    return f"{t // 12:04d}-{t % 12 + 1:02d}{day[7:]}"


def _transform(d: list, v: list, t: str) -> tuple[list, list, bool]:
    """回傳 (dates, values, derived)。

    **`diff` 與 `yoy` 對月頻序列一律按「日曆」回推，不是按「往回數幾個觀測值」。**

    2026-08-09 實測抓到的真實例子：`CPIAUCSL` 缺 2025-10（官方那個月沒發布），
    而原本的 `v[i] / v[i-12]` 是位置對應——跨過缺口就變成**13 個月變動**，
    卻仍標示為「年增率」。當時受影響的是 2025-11 起共 8 個點，
    正好蓋住總體 CPI 由 2.66 跳到 4.27 的那段加速。
    **數字看起來完全正常，不會露餡**——這正是本系統一再遇到的那類錯。

    找不到對應月份就回 `None`（圖上斷開），**不要拿相鄰的月份頂替**。
    """
    if t == "raw":
        return d, v, False
    if t == "rebase":
        s = F.rebase({"d": d, "v": v})
        return s["d"], s["v"], False
    if t == "diff":
        if _is_monthly(d):
            mp = dict(zip(d, v))
            out = [(mp[x] - mp[_shift_months(x, 1)]) if _shift_months(x, 1) in mp else None
                   for x in d[1:]]
            return d[1:], [None if x is None else round(x, 2) for x in out], False
        return d[1:], [round(v[i] - v[i - 1], 2) for i in range(1, len(v))], False
    if t == "yoy":
        if not _is_monthly(d):
            raise ValueError("yoy 只支援月頻序列（FRED 以每月 1 號標記）。"
                             "日頻資料請改用 rebase 或自行指定比較基期。")
        mp = dict(zip(d, v))
        dd, out = [], []
        for x in d:
            b = _shift_months(x, 12)
            if b not in mp:
                continue                      # 前 12 個月本來就沒有基期，跳過
            dd.append(x)
            out.append(None if mp[b] in (0, None) else round((mp[x] / mp[b] - 1) * 100, 2))
        # **yoy 也標 derived。** 年增率是導出量，而 `qa_series` 抓的是「相鄰觀測的
        # 百分比變動」——當年增率本身接近零（2020-05 總體 CPI 年增 0.2%），
        # 下一個月 0.72% 就會被算成 +260%、z＝7.4，固定誤報。這與 MAINTENANCE §2
        # 記過的「不要餵原始報酬率給 qa_series」是同一個坑：**分母趨近零的導出序列**。
        # 標了之後旗標改為整條說明一次，序列本身仍然正確、照常出圖。
        return dd, out, True
    if t.startswith("ma:"):
        n = int(t[3:])
        return d, [round(sum(v[max(0, i - n + 1):i + 1]) / min(i + 1, n), 2)
                   for i in range(len(v))], True
    if t.startswith("vol:"):
        n = int(t[4:])
        r = [v[i] / v[i - 1] - 1 for i in range(1, len(v))]
        out, dd = [], []
        for i in range(n - 1, len(r)):
            out.append(round(statistics.pstdev(r[i - n + 1:i + 1]) * 100, 3))
            dd.append(d[i + 1])
        return dd, out, True
    raise ValueError(f"未知的轉換 {t!r}（可用 raw/rebase/diff/yoy/ma:N/vol:N）")


def materialize(c: dict) -> list:
    """把一張圖的 series_spec 變成 series。回傳 series 清單。"""
    specs = c["series_spec"]
    fetched = []
    for sp in specs:
        s = F.get(sp["id"], since=sp.get("since", "2015-01-01"))
        d, v = s["d"], s["v"]
        if sp.get("since"):
            k = next((i for i, x in enumerate(d) if x >= sp["since"]), 0)
            d, v = d[k:], v[k:]
        fetched.append((sp, d, v))

    if c.get("series_align"):
        common = set(fetched[0][1])
        for _, d, _v in fetched[1:]:
            common &= set(d)
        dates = sorted(common)
        fetched = [(sp, dates, [dict(zip(d, v))[x] for x in dates]) for sp, d, v in fetched]

    out = []
    for sp, d, v in fetched:
        t = sp.get("t", "raw")
        dd, vv, derived = _transform(d, v, t)
        item = {"name": sp["name"], "dates": dd, "values": vv}
        for k in ("style", "axis", "dash", "color", "width"):
            if k in sp:
                item[k] = sp[k]
        if derived or sp.get("derived"):
            item["derived"] = True          # ma/vol 自動標，免得忘了（QA 四分法靠它）
        out.append(item)
    return out


def run(day: str, dry: bool = False) -> bool:
    path = os.path.join(REPO, "data", f"{day}.json")
    doc = json.load(open(path, encoding="utf-8"))
    changed = []
    for c in doc.get("charts", []):
        if "series_spec" not in c:
            continue
        series = materialize(c)
        n = sum(len(s["values"]) for s in series)
        changed.append(f"{c.get('slug','?')}（{len(series)} 條，{n} 點）")
        if not dry:
            c["series"] = series            # spec 保留，與 series 並存
    if not changed:
        print(f"·  {day}：沒有任何圖帶 series_spec，未變更")
        return True
    if dry:
        print(f"·  {day}：（dry-run）會實體化：{'；'.join(changed)}")
        return True
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"✓  {day}：已實體化 {'；'.join(changed)}")
    return True


def selftest() -> int:
    ok = True
    d = [f"2026-{m:02d}-01" for m in range(1, 13)] + ["2027-01-01"]
    v = [float(100 + i) for i in range(13)]
    for t, exp_len, exp_last, exp_derived in [
            ("raw", 13, 112.0, False), ("rebase", 13, 112.0, False),
            ("diff", 12, 1.0, False), ("yoy", 1, 12.0, True),
            ("ma:3", 13, 111.0, True)]:
        dd, vv, der = _transform(d, v, t)
        if len(vv) != exp_len or abs(vv[-1] - exp_last) > 1e-9 or der != exp_derived:
            print(f"✗ {t}: len={len(vv)} last={vv[-1]} derived={der}"); ok = False
    dd, vv, der = _transform(d, [100.0] * 13, "vol:5")
    if any(x != 0.0 for x in vv) or not der:
        print(f"✗ vol: {vv[:3]} derived={der}"); ok = False
    try:
        _transform(d, v, "nope"); print("✗ 未知轉換沒有拋錯"); ok = False
    except ValueError:
        pass
    print("selftest 全部通過 ✓" if ok else "★ selftest 有錯")
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(selftest())
    days = [x for x in a if not x.startswith("--")]
    if not days:
        print(__doc__); sys.exit(1)
    sys.exit(0 if all(run(x, "--dry-run" in a) for x in days) else 1)
