# -*- coding: utf-8 -*-
"""
render_day.py — 讀 data/YYYY-MM-DD.json，畫出當天五張圖的 PNG / SVG，
並把 ECharts option 回寫進同一個 JSON。

用法：  python3 ~/kb-core/scripts/chart/render_day.py 2026-08-05
設計原則：JSON 是唯一事實來源；圖是 JSON 的函數。
只要 JSON 還在，任何一天的圖都能被重畫——這是「歷史可查閱」的實作方式。
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chartkit as ck

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()


def to_chart(c: dict) -> ck.Chart:
    ch = ck.Chart(
        slug=c["slug"], title=c["title"], subtitle=c.get("subtitle", ""),
        kind=c.get("kind", "timeseries"),
        y_label=c.get("y_label", ""), y2_label=c.get("y2_label", ""),
        y_fmt=c.get("y_fmt", "{:,.0f}"), y2_fmt=c.get("y2_fmt", "{:,.2f}"),
        source=c.get("source", ""), note=c.get("note", ""),
        zero_line=c.get("zero_line", False), x_label=c.get("x_label", ""),
        y_log=c.get("y_log", False),
    )
    for s in c.get("series", []):
        ch.series.append(ck.Series(
            name=s["name"], dates=s["dates"], values=s["values"],
            color=s.get("color"), axis=s.get("axis", "left"),
            style=s.get("style", "line"), width=s.get("width", 1.9),
            dash=s.get("dash", False), derived=s.get("derived", False)))
    for m in c.get("markers", []):
        ch.markers.append(ck.Marker(date=m["date"], label=m["label"]))
    ch.pts = [tuple(p) for p in c.get("pts", [])]
    ch.hi_pts = [tuple(p) for p in c.get("hi_pts", [])]
    # 非時間序列圖型的欄位一律照 dataclass 的欄位名自動帶過去。
    # **不要改回逐欄手寫**——2026-08-09 加 `derived` 時就是在這裡漏接，
    # 欄位加了、schema 寫了、圖卻是空的，而且不會報錯。
    for f in ("cats", "vals", "groups", "band", "band_label", "matrix",
              "rows", "gauge", "total_label"):
        if f in c:
            setattr(ch, f, c[f])
    return ch


def main(day: str):
    path = os.path.join(REPO, "data", f"{day}.json")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    outdir = os.path.join(REPO, "charts", day)
    os.makedirs(outdir, exist_ok=True)

    flags = []
    for i, c in enumerate(doc["charts"], 1):
        ch = to_chart(c)
        base = f"{i:02d}-{c['slug']}"
        files = ck.render_static(ch, outdir, base)
        c["files"] = {
            "png": f"charts/{day}/{base}.png",
            "svg": f"charts/{day}/{base}.svg",
        }
        c["option"] = ck.echarts_option(ch)
        flags += ck.qa_series(ch)
        print(f"  [{i}] {c['title'][:36]:<38} -> {os.path.basename(files['png'])}")

    doc.setdefault("about", {})["qa_flags"] = flags
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK  {day}：{len(doc['charts'])} 張圖，JSON 已回寫 option")
    if flags:
        print(f"⚠  {len(flags)} 筆單日跳動異常，需人工覆核（多半是期貨轉倉或來源錯價）：")
        for f_ in flags:
            print(f"     {f_['series']:<12} {f_['date']}  {f_['pct']:+.2f}%  z={f_['z']}")
    else:
        print("   資料品質檢查：無異常跳動")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
