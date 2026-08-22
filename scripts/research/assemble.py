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
import argparse, datetime as dt, glob, json, os, re, shutil, sys, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402   路徑只有一個家，見該檔的檔頭

_KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
A = json.load(open(os.path.join(_KB, "research", "anchors.json"), encoding="utf-8"))
sys.path.insert(0, os.path.join(_KB, "scripts", "chart"))
TPE = dt.timezone(dt.timedelta(hours=8))


def count(s):
    """anchors.summary_tiers.count_rule 的唯一實作。"""
    s = re.sub(r"^#{1,6}\s*", "", s or "", flags=re.M)
    s = re.sub(r"\*\*|__|`|\*|^[-–—]\s*", "", s, flags=re.M)
    return len(re.sub(r"\s+", "", s))


def week_of(datestr):
    y, w = dt.date.fromisoformat(datestr).isocalendar()[:2]
    return f"{y}-W{w:02d}"


def week_range(week):
    """`2026-W34` → `["2026-08-17", "2026-08-23"]`。

    **從週次算出來，不從報告日期的最小最大值算。** 兩者在一批報告剛好
    橫跨整週時看起來一樣，而在只收到一份的那週差很多 ——
    後者會讓「本期區間」變成「那一份的日期」，讀起來像這一週只有那一天。
    """
    y, w = int(week[:4]), int(week.split("W")[1])
    mon = dt.date.fromisocalendar(y, w, 1)
    return [mon.isoformat(), (mon + dt.timedelta(6)).isoformat()]


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
    ap.add_argument("--parts", default=None)   # 見 _paths.py
    ap.add_argument("--out", default=None)
    ap.add_argument("--extracted", default=None)
    ap.add_argument("--no-charts", action="store_true")
    ap.add_argument("--outbox", default="~/outbox/research")
    ap.add_argument("--repo", default="~/broker-research-digest")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if unknown:
        print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr); return 12
    if a.help or not a.week:
        print(__doc__); return 2

    P = os.path.expanduser(a.parts) if a.parts else os.path.join(_paths.digest(), "_parts")
    O = os.path.expanduser(a.out) if a.out else _paths.digest()
    E = os.path.expanduser(a.extracted) if a.extracted else _paths.extracted()
    parts = {json.load(open(f, encoding="utf-8"))["slug"]: json.load(open(f, encoding="utf-8"))
             for f in sorted(glob.glob(os.path.join(P, "*.json")))}
    ex = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8"))
          for f in sorted(glob.glob(os.path.join(E, "*.json")))}
    # **這一期只收這一週的報告。** 一批丟進來的報告可能橫跨好幾週
    # （2026-08-21 實測：18 份橫跨 5 個 ISO 週），全部組進同一期
    # 會讓六月的報告出現在八月那一期裡。
    #
    # **被篩掉的一定要印出來。** 安靜地少收幾份，跟「那幾週本來就沒有報告」
    # 在輸出上長得一模一樣 —— 而後者不需要任何人再做什麼。
    other = {}
    for slug in list(ex):
        w = week_of(ex[slug]["date"])
        if w != a.week:
            other.setdefault(w, []).append(slug)
            del ex[slug]
    if other:
        print(f"  （不屬於 {a.week}，這一期不收）")
        for w in sorted(other):
            print(f"    {w}  {len(other[w])} 份：" + "、".join(x[:40] for x in other[w]))
        print(f"    **那幾週要各自跑一次 assemble.py**，不然它們永遠不會被收錄，"
              f"而且沒有任何東西會提醒你\n")
    if not ex:
        print(f"{a.week} 底下沒有任何報告 —— 空輪次，不是失敗", file=sys.stderr)
        return 13

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
    digest = {
        "week": a.week, "range": week_range(a.week),
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
    # 孤兒圖檔。**用路徑比對，不用「這一輪畫了幾張」。**
    # 每份從三張改成一張之後，舊的 -2 -3 還躺在 charts/ 裡，
    # 而它們不在 digest 裡、卻會跟著 `staged_paths` 一起被推上遠端 ——
    # 一個沒有任何頁面連到、卻公開在網路上的檔案。
    if not a.no_charts:
        # **live 要從所有期的 digest 收集，不是只從這一期。**
        # `charts/` 是跨期共用的一個平坦目錄，而分週之後每次只組一期 ——
        # 只看這一期會把別週的圖全部指成孤兒。
        # 一個每次都會響的警報，跟沒有警報是同一件事，而且更糟：
        # **它會訓練人略過那一段，包括真的響的那次。**
        live = set()
        for jf in sorted(glob.glob(os.path.join(O, "*.json"))):
            try:
                other = json.load(open(jf, encoding="utf-8"))
            except Exception:
                continue
            for r in (other.get("reports") or []):
                for c in (r.get("charts") or []):
                    for k in ("png", "svg"):
                        if c.get(k):
                            live.add(c[k])
        live |= {c[k] for r in reports for c in r["charts"]
                 for k in ("png", "svg") if c.get(k)}
        orph = sorted(f for f in os.listdir(cdir)
                      if f.endswith((".png", ".svg")) and f not in live)
        if orph:
            print(f"\n**{len(orph)} 個孤兒圖檔**（不在這一期 digest 裡，"
                  f"但仍在 {cdir}）：\n    " + "、".join(orph[:8])
                  + (" …" if len(orph) > 8 else "")
                  + "\n  這支不刪檔。要清就自己 mv 到 _to_delete/，"
                  "**留著會跟著發布推上去**")

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
    # **草稿只在明講 `--publish` 時才進 outbox。**
    #
    # 2026-08-22 的教訓：`crosscut`／`watch`／`notes` 要等主代理讀完整期才寫得出來，
    # 所以流程是「組一次 → 寫那三欄 → 再組一次」。但第一次組檔就把草稿丟進 outbox，
    # 而 publish 每 60 秒來收一次 —— **四期在只有空 crosscut 的狀態下就上線了**，
    # 補寫之後的草稿撞上不可改寫守衛，然後每分鐘紅一次、永遠紅下去。
    #
    # 守衛沒有錯，錯的是**在東西還沒寫完的時候就交給發布的人**。
    # 一個永遠會紅的排程，比一個沒有排程更糟：它會訓練人略過那段 log。
    if a.publish:
        print("\n".join(write_draft(digest, os.path.expanduser(a.outbox), O,
                                     os.path.expanduser(a.repo))))
    else:
        print(f"  （沒有加 `--publish`，草稿沒有進 outbox）\n"
              f"  先確認 crosscut／watch／notes 寫好了，再跑一次帶 --publish。"
              f"　目前 crosscut {len(digest.get('crosscut') or '')} 字")
    return 0


def build_stances(digest_dir, repo):
    """跨期的立場帳本 —— **原句牆與帳本是同一份資料，差一個欄位。**

    原句是這個庫唯一可以被驗證的一層：精華是我們寫的、圖是我們畫的，
    只有原句是分析師說的。所以它值得有自己的一份檔，而不是埋在單篇底部。

    `status`／`verdict`／`verdictDate` **由既有檔案沿用，永不覆寫** ——
    這支每一輪重建列表，但**判決是人下的，重建不能把它洗掉**。
    """
    O = A["observations"]
    dst = os.path.join(repo, "data", "stances.json")
    old = {}
    if os.path.exists(dst):
        try:
            for it in json.load(open(dst, encoding="utf-8")).get("items") or []:
                old[it["id"]] = it
        except Exception:
            pass

    items = []
    for jf in sorted(glob.glob(os.path.join(digest_dir, "2026-W*.json")), reverse=True):
        try:
            dg = json.load(open(jf, encoding="utf-8"))
        except Exception:
            continue
        for r in dg.get("reports") or []:
            for n, st in enumerate(r.get("stances") or [], 1):
                sid = f"{r['slug']}-{n}"
                due = (dt.date.fromisoformat(r["date"])
                       + dt.timedelta(days=30 * O["horizon_months"])).isoformat()
                prev = old.get(sid, {})
                items.append({
                    "id": sid, "week": dg.get("week"), "slug": r["slug"],
                    "broker": r.get("broker"), "title": r.get("title"),
                    "date": r.get("date"), "due": due,
                    "theme": st.get("theme"), "tags": r.get("tags") or [],
                    "quote": st.get("quote"), "quote_zh": st.get("quote_zh"),
                    "page": st.get("page"),
                    "status": prev.get("status") or O["status_vocab"][0],
                    "verdict": prev.get("verdict", ""),
                    "verdictDate": prev.get("verdictDate", ""),
                })
    out = {"updated": dt.datetime.now(TPE).isoformat(timespec="seconds"),
           "note": "原句是分析師說的，精華與圖是我們做的。到期日 = 報告日期 + "
                   f"{O['horizon_months']} 個月。",
           "count": len(items), "items": items}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    open(tmp, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    os.replace(tmp, dst)
    judged = sum(1 for i in items if i["status"] != O["status_vocab"][0])
    return f"→ {dst}（{len(items)} 筆立場，已判 {judged} 筆）"


def write_draft(digest, outbox, digest_dir, repo):
    """發布用的草稿。**跟本機那一份不是同一個東西，差別是刻意的。**

    1. **`file` 與 `file_url` 拿掉。** 它們是 `file:///Users/…` ——
       對讀者沒有用，而且會把使用者的帳號名與目錄結構寫在公開頁面上。
       本機的 `.html` 保留它們，那份不上網。
    2. **`grounding` 留著。** 那是圖裡每個數字的出處，是「這張圖不是我們編的」
       唯一的憑據。它短，而且拿掉之後 `research.chart_grounded` 在發布閘門
       就沒有東西可以比對 —— **閘門會變成永遠 PASS。**
    3. **`date` 是該週的週日**，因為 publish 用 `draft["date"]` 命名檔案並排序。

    圖檔另外複製到 `charts/<週>/`：資料 repo 的路徑形狀由 `staged_paths` 宣告，
    而它宣告的是 `charts/<週>/`，不是本機那個平坦的 `charts/`。
    """
    lines = []
    d = json.loads(json.dumps(digest))          # 深拷貝，不動本機那一份
    for r in d.get("reports") or []:
        r.pop("file", None)
        r.pop("file_url", None)
    # publish 用 `date` 命名 `data/<date>.json` 並據以排序。
    # **取該週的週日**，那是從週次算出來的、唯一且可排序的 key。
    d["date"] = (d.get("range") or ["", ""])[1]
    if not d["date"]:
        return ["  草稿沒寫：digest 沒有 range，**取不到週日就沒有檔名**"]
    os.makedirs(outbox, exist_ok=True)
    f = os.path.join(outbox, f"{d['date']}.draft.json")
    tmp = f + ".tmp"
    open(tmp, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
    os.replace(tmp, f)
    lines.append(f"→ {f}（發布草稿，已拿掉 file:// 本機路徑）")

    # 圖檔進**資料 repo**，不是 outbox —— publish 只搬草稿，
    # `staged_paths` 宣告的 `charts/<週>/` 得先有東西在那裡它才推得動。
    # 每日五圖 2026-08-21 那次就是這一格沒有主人：檢查讀本機、全綠，讀者拿到 404。
    src = os.path.join(digest_dir, "charts")
    want = {c[k] for r in d.get("reports") or [] for c in (r.get("charts") or [])
            for k in ("png", "svg") if c.get(k)}
    if not os.path.isdir(repo):
        lines.append(f"  **圖沒有進 repo**：{repo} 不存在。草稿已經寫好了，"
                     "但這一期發布出去會是 7 張 404 —— repo 建好之後重跑這支")
        return lines
    dst = os.path.join(repo, "charts", d["week"])
    os.makedirs(dst, exist_ok=True)
    miss = [n for n in sorted(want) if not os.path.exists(os.path.join(src, n))]
    for n in sorted(want):
        f2 = os.path.join(src, n)
        if os.path.exists(f2):
            shutil.copy2(f2, os.path.join(dst, n))
    lines.append(f"→ {dst}（{len(want) - len(miss)}/{len(want)} 個圖檔）"
                 + (f"　**{len(miss)} 個在本機也找不到：{miss[:3]}**" if miss else ""))
    lines.append(build_stances(digest_dir, repo))
    return lines


if __name__ == "__main__":
    sys.exit(main())
