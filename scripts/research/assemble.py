#!/usr/bin/env python3
"""把子代理寫的分片組成一期 digest，並重製圖表。**這支會寫檔。**

用法：assemble.py <週> [--parts DIR] [--out DIR] [--extracted DIR] [--no-charts]

## 三件機械的事，撰寫者不做

1. **`summary_chars` 由這裡覆寫。** 自報的字數不可信，而且 2026-08-21 首輪
   兩個子代理各自為了「這個數字怎麼算」繞了一圈、答案差 1,500 字以上。
   **規則沒寫死等於交給運氣**，所以規則寫在 anchors、計算寫在這裡。
2. **圖表由 chartkit 渲染**，撰寫者只給規格。同一張圖不會有兩套畫法。
3. **`file_url` 由檔名組出來**，不由撰寫者填 —— 那是機械的事。

## 已經畫過的圖不重畫（2026-08-31 加）

**規格沒變就沿用磁碟上那一張，連渲染都不跑。** 判準是規格本身的 sha256
（不含 `png`／`svg`／`bytes`／`render_error` 這幾個渲染產物），存成
`charts/<base>.spec.sha`；三個檔都在而且指紋對得上就沿用。

為什麼要有這條 —— 2026-08-30 那一輪的實況：

- 這支**每次組檔都把整期所有報告的圖重畫一次**，包含幾週前就發布過的。
- 每日五圖那邊 08-29 改了 `chartkit.py`、08-30 改了 `chart/anchors.json`，
  於是 `timeseries` 的輸出換了一個位元組數（129,550 → 132,268）。
- 規格一字沒動，`bytes` 卻變了 → 不可改寫守衛判定「已發布的內容被改了」
  → W35 exit 11，連帶那兩個未提交的圖檔把 W34 卡在 exit 15。

**渲染本身是決定性的**（同一份規格連畫兩次 md5 相同），所以那不是雜訊，
是上游改版倒灌進已發布的期別。這次只中一張 —— **下次改到 `grouped_bar`，
W34 那 25 份會一起被守衛指名。**

**要強制重畫就刪掉那張的 `.png`**（不是刪 `.spec.sha`）：檔案不在就一定會畫。
刪 `.spec.sha` 反而會走下面那條認養，把現有的圖當成最新的收下。

**沒有 `.spec.sha` 但 png／svg 都在 → 認養**（那是這條規則上線前畫的圖），
並把張數印出來。認養的正確性建立在「此刻磁碟上那張圖就是最近一次渲染的結果」——
2026-08-31 上線時成立，因為前一輪剛把兩期全部重畫並發布過。
"""
from __future__ import annotations
import argparse, datetime as dt, glob, hashlib, json, os, re, shutil, sys, urllib.parse

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


def _fmt_for(spec):
    """依資料的量級決定資料標籤的小數位。**撰寫者不填這個欄位，而預設是整數。**

    2026-08-22 泰國那張：貢獻 0.3 個百分點被畫成「0」，
    而副標題就寫著 0.3 —— **圖上的數字跟它自己的副標題互相矛盾**，
    而且不丟任何例外。整數格式對百分比是對的，對百分點就不是。
    """
    vals = [v for v in (spec.get("vals") or [])
            if isinstance(v, (int, float))]
    for g in spec.get("groups") or []:
        vals += [v for v in (g.get("values") or []) if isinstance(v, (int, float))]
    if not vals:
        return "{:,.0f}"
    if all(float(v).is_integer() for v in vals):
        return "{:,.0f}"
    m = max(abs(v) for v in vals)
    return "{:,.2f}" if m < 2 else "{:,.1f}"


RENDER_OUTPUTS = ("png", "svg", "bytes", "render_error")


def spec_fingerprint(spec):
    """規格的指紋。**不含渲染產物** —— 否則它會跟著自己變，永遠對不上。

    比對的是撰寫者給的那份規格，不是畫出來的那張圖：**chartkit 改版不該
    讓已發布的圖被判成「內容變了」**（見檔頭）。
    """
    body = {k: v for k, v in spec.items() if k not in RENDER_OUTPUTS}
    return hashlib.sha256(json.dumps(
        body, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def render_charts(part, ex, outdir):
    """規格 → PNG／SVG。**渲染失敗不中止整期**，記進 chart 的 `render_error`。

    回 `(重畫, 沿用, 認養)` 三個 base 清單 —— **呼叫端要印出來**：
    只驗「位元組數有沒有變」的話，「沒生效」與「生效但沒效果」長得一模一樣。
    """
    os.environ.setdefault("CHART_REPO", "/tmp")
    import chartkit as C
    F = C.Chart.__dataclass_fields__
    made, reused, adopted = [], [], []
    for i, spec in enumerate(part.get("charts") or [], 1):
        base = f"{part['slug']}-{i}"
        png = os.path.join(outdir, base + ".png")
        svg = os.path.join(outdir, base + ".svg")
        sig = os.path.join(outdir, base + ".spec.sha")
        fp = spec_fingerprint(spec)
        if os.path.exists(png) and os.path.exists(svg):
            was = None
            if os.path.exists(sig):
                was = open(sig, encoding="utf-8").read().strip()
            else:
                # 認養：這條規則上線前畫的圖，收下它當作最新的（見檔頭）
                open(sig, "w", encoding="utf-8").write(fp + "\n")
                was, _ = fp, adopted.append(base)
            if was == fp:
                spec["png"] = os.path.basename(png)
                spec["svg"] = os.path.basename(svg)
                spec["bytes"] = os.path.getsize(png)
                reused.append(base)
                continue
        # **只覆寫規格真的給了的欄位。**
        # 原本這裡先 `{k: None for k in F}` 把每個欄位塞成 None ——
        # 那等於把 `Chart` dataclass 二十三個設計好的預設值全部抹掉，
        # 於是 `y_fmt` 變成 None，而 `_draw_waterfall` 對它呼叫 `.format()`。
        # **一個為了「欄位齊全」而寫的初始化，把欄位的意義弄丟了。**
        kw = {k: v for k, v in spec.items() if k in F}
        kw.setdefault("subtitle", "")
        kw.setdefault("y_fmt", _fmt_for(spec))
        kw["slug"] = base
        # **`series` 與 `markers` 是 dataclass，不是 dict。**
        # 2026-08-23 用 `tools/chartkit_smoke.py` 把九種圖型逐一畫過才發現：
        # 這裡把撰寫者給的 dict 原樣塞進 `Chart(**kw)`，於是 `timeseries` 與
        # `range_area` 一定丟 `AttributeError: 'dict' object has no attribute 'dates'`。
        #
        # **那兩種圖型從來沒有被畫出來過**，而失敗被下面的 `except` 收進
        # `render_error`，網站又（直到同一天）對沒有 png 的圖回空字串 ——
        # 三層各自合理的處置疊起來，結果是**撰寫者照規格寫的圖，安靜地不存在**。
        # 已經用過的 `grouped_bar` 與 `waterfall` 剛好只吃 list，所以一路沒露餡。
        for f, cls in (("series", C.Series), ("markers", C.Marker)):
            if kw.get(f) and isinstance(kw[f][0], dict):
                try:
                    kw[f] = [cls(**x) for x in kw[f]]
                except TypeError as e:
                    # 欄位對不上就明講是哪個欄位，不要讓它變成 AttributeError
                    raise TypeError(f"`{f}` 的欄位對不上 {cls.__name__}：{e}") from None
        try:
            out = C.render_static(C.Chart(**kw), outdir, base, brand=A["charts"]["brand"])
            spec["png"] = os.path.basename(out["png"])
            spec["svg"] = os.path.basename(out["svg"])
            spec["bytes"] = os.path.getsize(out["png"])
            open(sig, "w", encoding="utf-8").write(fp + "\n")
            made.append(base)
        except Exception as e:
            spec["render_error"] = f"{type(e).__name__}: {e}"
            # 畫失敗就不要留指紋 —— 留了下一輪會沿用一張不存在的圖
            if os.path.exists(sig):
                os.remove(sig)
    return made, reused, adopted


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
    n_made, n_reused, n_adopted = 0, 0, 0
    for slug, d in sorted(ex.items(), key=lambda kv: (kv[1]["date"], kv[0]), reverse=True):
        p = parts[slug]
        n, t = count(p["summary"]), tier_of(d["pages"])
        lo, hi = t["chars"]
        if n < lo:
            warn.append(f"{slug} {n} < {lo} **不足**")
        elif n > hi:
            warn.append(f"{slug} {n} > {hi} 超出")
        made, reused, adopted = ([], [], []) if a.no_charts else render_charts(p, d, cdir)
        n_made, n_reused, n_adopted = (n_made + len(made), n_reused + len(reused),
                                       n_adopted + len(adopted))
        src = d["source_file"]
        reports.append({
            "slug": slug, "broker": d["broker"], "product": d["product"],
            "title": d["title"], "title_source": d.get("title_source"),
            "title_confident": d.get("title_confident"),
            "date": d["date"], "pages": d["pages"], "issue": d.get("issue"),
            "file": f"~/broker-research/inbox/{src}",
            "file_url": "file:///Users/macmini/broker-research/inbox/" + urllib.parse.quote(src),
            "tier_target": t["target"], "tier_band": [lo, hi],
            "summary": p["summary"], "summary_chars": n,
            "tags": [t.strip() for t in (p.get("tags") or []) if t and t.strip()],
            "stances": p.get("stances") or [], "charts": p.get("charts") or [],
        })
        print(f"  {slug[:46]:<48} {n:>5} 字（目標 {t['target']}）"
              f"　立場 {len(p.get('stances') or [])}"
              f"　圖 {len(made) + len(reused)}/{len(p.get('charts') or [])}"
              f"{('（沿用 %d）' % len(reused)) if reused else ''}"
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
        # 指紋檔跟著它那張圖一起活 —— 不併進來的話，圖被清掉之後
        # `.spec.sha` 會安靜地留在原地，而下一張同名的圖會沿用到它。
        live |= {os.path.splitext(f)[0] + ".spec.sha" for f in live}
        orph = sorted(f for f in os.listdir(cdir)
                      if f.endswith((".png", ".svg", ".spec.sha")) and f not in live)
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
    if not a.no_charts:
        print(f"  圖：重畫 {n_made}　沿用 {n_reused}　"
              + (f"**首次認養 {n_adopted}**" if n_adopted else "認養 0")
              + "　（規格沒變就不重畫，見檔頭；要強制重畫刪掉那張的 .png）")
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

    ## 讀不到既有帳本時要炸，不能吞

    原本這裡是 `except Exception: pass`。於是帳本壞掉（截斷、編碼壞、被半份寫入）時
    `old` 是空的，**全部的 `status` 靜靜退回預設值、`verdict` 全部變成空字串**，
    而輸出跟「第一次建帳本」逐字相同 —— 沒有任何一行 print 不一樣。

    **人下的判決是這個庫裡唯一無法重建的東西。** 抽取可以重跑、精華可以重寫、
    圖可以重畫，判決不行。所以這一步的失敗必須停下來，
    而「檔案本來就不存在」與「檔案在但讀不動」要分得開 —— 前者是第一輪，後者是事故。
    """
    O = A["observations"]
    dst = os.path.join(repo, "data", "stances.json")
    old = {}
    if os.path.exists(dst):
        try:
            doc = json.load(open(dst, encoding="utf-8"))
        except Exception as e:
            raise SystemExit(
                f"**既有帳本讀不動**：{dst}\n"
                f"  {type(e).__name__}: {e}\n"
                "  這裡刻意不繼續。繼續下去會把人工填的 status／verdict 全部重置成預設，\n"
                "  **而產出會跟第一次建帳本長得一模一樣**。\n"
                "  先從 git 取回上一版（`git -C <repo> checkout -- data/stances.json`）再跑。")
        for it in doc.get("items") or []:
            if "id" in it:
                old[it["id"]] = it
        if not old:
            print(f"  **既有帳本讀得動但一筆都沒有**（{dst}）—— "
                  "如果這不是第一輪，那是資料掉了，先確認再往下")
    else:
        print(f"  帳本不存在，這是第一輪（{dst}）")

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
                    # 標題帶到哪裡，來源就要帶到哪裡 —— 理由與 `systems/research.py`
                    # 的 `index_entry` 同一條（那裡寫了整段）。這一份 145 列
                    # 全部缺這個欄位，是 2026-08-31 之前站台不部署的大宗。
                    "title_source": r.get("title_source"),
                    "title_confident": r.get("title_confident"),
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
    # **`assembled_at` 不進不可改寫的那一份。**
    # 它每一輪都不同，於是「內容相同」永遠不成立 ——
    # publish 的 `already` 快速路徑（設計來讓重跑是安全的）對這一套從來沒有觸發過，
    # 而每一次無害的重跑都會撞上 exit 11。
    # **一個放在不可改寫文件裡的時間戳，讓「這一期沒有變」變成無法表達的狀態。**
    # 發布時間本來就記在回執裡，那才是它的家。
    d.pop("assembled_at", None)
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
