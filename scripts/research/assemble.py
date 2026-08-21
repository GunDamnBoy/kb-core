#!/usr/bin/env python3
"""把子代理寫的分片組成一期 digest，並重製圖表。**這支會寫檔。**

用法：assemble.py <週> [--parts DIR] [--out DIR] [--extracted DIR] [--no-charts]

## 三件機械的事，撰寫者不做

1. **`summary_chars` 由這裡覆寫。** 自報的字數不可信，而且 2026-08-21 首輪
   兩個子代理各自為了「這個數字怎麼算」繞了一圈、答案差 1,500 字以上。
   **規則沒寫死等於交給運氣**，所以規則寫在 anchors、計算寫在這裡。
2. **圖表由 chartkit 渲染**，撰寫者只給規格。同一張圖不會有兩套畫法。
3. **`file_url` 由檔名組出來**，不由撰寫者填 —— 那是機械的事。
"""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, re, sys, urllib.parse

_KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
A = json.load(open(os.path.join(_KB, "research", "anchors.json"), encoding="utf-8"))
sys.path.insert(0, os.path.join(_KB, "scripts", "chart"))
TPE = dt.timezone(dt.timedelta(hours=8))


def count(s):
    """anchors.summary_tiers.count_rule 的唯一實作。"""
    s = re.sub(r"^#{1,6}\s*", "", s or "", flags=re.M)
    s = re.sub(r"\*\*|__|`|\*|^[-–—]\s*", "", s, flags=re.M)
    return len(re.sub(r"\s+", "", s))


def tier_of(pages):
    for t in A["summary_tiers"]["tiers"]:
        if t["under_pages"] is None or pages < t["under_pages"]:
            return t
    return A["summary_tiers"]["tiers"][-1]


def _tag_map(reports):
    m = {}
    for r in reports:
        for t in r.get("tags") or []:
            m.setdefault(t, set()).add(r["slug"])
    return m


def render_charts(part, ex, outdir):
    """規格 → PNG／SVG。**渲染失敗不中止整期**，記進 chart 的 `render_error`。"""
    os.environ.setdefault("CHART_REPO", "/tmp")
    import chartkit as C
    F = C.Chart.__dataclass_fields__
    made = []
    for i, spec in enumerate(part.get("charts") or [], 1):
        base = f"{part['slug']}-{i}"
        kw = {k: None for k in F}
        kw.update({"series": [], "markers": [], "pts": [], "hi_pts": [], "vals": [],
                   "zero_line": False, "y_log": False})
        kw.update({k: v for k, v in spec.items() if k in F})
        kw["slug"] = base
        try:
            out = C.render_static(C.Chart(**kw), outdir, base, brand=A["charts"]["brand"])
            spec["png"] = os.path.basename(out["png"])
            spec["svg"] = os.path.basename(out["svg"])
            spec["bytes"] = os.path.getsize(out["png"])
            made.append(base)
        except Exception as e:
            spec["render_error"] = f"{type(e).__name__}: {e}"
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("week", nargs="?")
    ap.add_argument("--parts", default="~/broker-research/digest/_parts")
    ap.add_argument("--out", default="~/broker-research/digest")
    ap.add_argument("--extracted", default="~/broker-research/extracted")
    ap.add_argument("--no-charts", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if unknown:
        print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
    if a.help or not a.week:
        print(__doc__); return 2

    P, O, E = (os.path.expanduser(x) for x in (a.parts, a.out, a.extracted))
    parts = {json.load(open(f, encoding="utf-8"))["slug"]: json.load(open(f, encoding="utf-8"))
             for f in sorted(glob.glob(os.path.join(P, "*.json")))}
    ex = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8"))
          for f in sorted(glob.glob(os.path.join(E, "*.json")))}
    miss = sorted(set(ex) - set(parts))
    if miss:
        print(f"**{len(miss)} 份有抽取結果但沒有精華**：{miss}\n"
              "  子代理沒交件或檔名對不上。**這跟「那幾份不值得寫」是兩件事。**", file=sys.stderr)
        return 10

    cdir = os.path.join(O, "charts")
    if not a.no_charts:
        os.makedirs(cdir, exist_ok=True)
    reports, warn = [], []
    for slug, d in sorted(ex.items(), key=lambda kv: (kv[1]["date"], kv[0]), reverse=True):
        p = parts[slug]
        n, t = count(p["summary"]), tier_of(d["pages"])
        lo, hi = t["chars"]
        if n < lo:
            warn.append(f"{slug} {n} < {lo} **不足**")
        elif n > hi:
            warn.append(f"{slug} {n} > {hi} 超出")
        made = [] if a.no_charts else render_charts(p, d, cdir)
        src = d["source_file"]
        reports.append({
            "slug": slug, "broker": d["broker"], "product": d["product"],
            "title": d["title"], "date": d["date"], "pages": d["pages"], "issue": d.get("issue"),
            "file": f"~/broker-research/inbox/{src}",
            "file_url": "file:///Users/macmini/broker-research/inbox/" + urllib.parse.quote(src),
            "tier_target": t["target"], "tier_band": [lo, hi],
            "summary": p["summary"], "summary_chars": n,
            "tags": [t.strip() for t in (p.get("tags") or []) if t and t.strip()],
            "stances": p.get("stances") or [], "charts": p.get("charts") or [],
        })
        print(f"  {slug[:46]:<48} {n:>5} 字（目標 {t['target']}）"
              f"　立場 {len(p.get('stances') or [])}"
              f"　圖 {len(made)}/{len(p.get('charts') or [])}"
              f"　標籤 {len(p.get('tags') or [])}")

    prev = os.path.join(O, f"{a.week}.json")
    old = json.load(open(prev, encoding="utf-8")) if os.path.exists(prev) else {}
    dates = sorted(r["date"] for r in reports)
    digest = {
        "week": a.week, "range": old.get("range") or [dates[0], dates[-1]],
        "reports_count": len(reports),
        "brokers": {b: sum(1 for r in reports if r["broker"] == b)
                    for b in sorted({r["broker"] for r in reports})},
        # 標籤 → slug。**排序用「先出現次數、後筆畫」而不是 set 的順序**，
        # 否則同一批資料每次組出來的順序都不同，diff 會滿是雜訊。
        "tags": {t: sorted(sl) for t, sl in sorted(
            _tag_map(reports).items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "reports": reports,
        "crosscut": old.get("crosscut", ""), "watch": old.get("watch", []),
        "notes": old.get("notes", []),
        "assembled_at": dt.datetime.now(TPE).isoformat(timespec="seconds"),
    }
    os.makedirs(O, exist_ok=True)
    tmp = prev + ".tmp"
    json.dump(digest, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, prev)
    tot = sum(r["summary_chars"] for r in reports)
    ncharts = sum(len(r["charts"]) for r in reports)
    err = [c.get("render_error") for r in reports for c in r["charts"] if c.get("render_error")]
    print(f"\n{len(reports)} 份｜精華合計 {tot:,} 字｜立場 "
          f"{sum(len(r['stances']) for r in reports)} 筆｜圖 {ncharts} 張"
          + (f"（**{len(err)} 張渲染失敗**）" if err else ""))
    for e in err[:4]:
        print("   ", e)
    if warn:
        print("**篇幅出界**：" + "；".join(warn))
    print(f"→ {prev}")

    # 給人讀的那一份就地產生。**衍生檔不留在手動重跑的路徑上** ——
    # 分開跑就會出現 JSON 改了、MD 沒改，而兩份看起來都像對的。
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import render
    print("\n".join(render.write_all(digest, os.path.splitext(prev)[0] + ".md")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
