"""每日五圖的檢查。

payload 形狀（由 `tools/chart_verify.py` 組出來，檢查本身不做 IO）：

    {"doc":      當日的 data/<date>.json,
     "prev":     前一版的 doc（沒有就 None）,
     "anchors":  chart/anchors.json,
     "advisory_anchors": advisory/anchors.json —— **theme 值域的家在那裡**,
     "size_kb":  當日 JSON 的實際大小,
     "now":      ISO8601}

## theme 的值域刻意不寫在 chart/anchors.json

`theme` 必須是投顧知識庫那十五個子類別之一——它們是同一份東西，
因為每日五圖的選題就是從投顧庫來的。舊系統把十五個字串硬寫進 `check_day.py` 的
`THEMES`，2026-08-20 比對發現**兩邊逐字相同**——但那是運氣：
沒有任何機制在維持它，投顧那邊改一個組名，這裡不會有任何徵兆。

## 數字一個都不寫在這裡

門檻全部從 `anchors` 讀。檢查程式是它的**讀者**而不是第二份副本。
"""
import datetime as dt
import unicodedata

from kbcore.check import Check, fail, ok, register, skipped, warn

TPE = dt.timezone(dt.timedelta(hours=8))


def _A(p, *path):
    """取不到就 KeyError——**門檻取不到是設定壞了，不是資料壞了。**"""
    cur = p["anchors"]
    for k in path:
        cur = cur[k]
    return cur


def _charts(doc):
    return doc.get("charts") or []


def _vis(s: str) -> int:
    """視覺寬：中日韓全形算 2，其餘算 1。頁尾行數是照這個算的。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s or "")


# ── 1. 五張圖、slot 順序 ─────────────────────────────────────────────
def _structure(p):
    doc = p["doc"]
    want_n = _A(p, "structure", "charts_per_day")
    slots = _A(p, "structure", "slots")
    cs = _charts(doc)
    bad = []
    if len(cs) != want_n:
        bad.append(f"{len(cs)} 張圖（應為 {want_n}）")
    for i, c in enumerate(cs[:len(slots)]):
        got = (c.get("slot") or "")
        # 第五個 slot 在資料裡寫成「軌道圖｜<軌道名>」，取分隔前那一段比。
        head = got.split("｜", 1)[0]
        if head != slots[i]:
            bad.append(f"第 {i+1} 張的 slot 是「{got}」，該位置應為「{slots[i]}」")
    if bad:
        return fail("；".join(bad))
    return ok(f"{len(cs)} 張、slot 順序正確")


register(Check(
    id="chart.structure",
    covers="當日五張圖、且 slot 依 anchors 的順序逐位對上",
    blind_to=[
        "slot 名字對但那張圖的內容其實屬於別的 slot",
        "**軌道圖分隔後面那一段是哪一條軌道**——那是 chart.track_of_the_day 的事",
        "圖的順序對但當天根本不該出這個題目",
        "已發布的舊日期檔（檢查只跑當日的 doc）",
    ],
    run=_structure,
    fixture={"anchors": {"structure": {"charts_per_day": 5,
                                       "slots": ["當日主圖", "市場異動圖", "重製圖", "主題深掘", "軌道圖"]}},
             "doc": {"charts": [{"slot": "當日主圖"}, {"slot": "重製圖"}]}},
    near_miss={"anchors": {"structure": {"charts_per_day": 2,
                                         "slots": ["當日主圖", "市場異動圖"]}},
               "doc": {"charts": [{"slot": "當日主圖"}, {"slot": "市場異動圖"}]}},
    suite="chart",
))


# ── 2. theme 不重複、且在投顧那十五組裡 ──────────────────────────────
def _themes(p):
    vocab = {g["name"] for g in p["advisory_anchors"]["groups"]}
    cs = _charts(p["doc"])
    got = [c.get("theme") for c in cs]
    bad = []
    unknown = [t for t in got if t not in vocab]
    if unknown:
        bad.append(f"theme 不在投顧的十五組裡：{'、'.join(str(x) for x in unknown)}")
    dupe = sorted({t for t in got if got.count(t) > 1 and t in vocab})
    if dupe:
        bad.append(f"同一天有兩張圖用同一個 theme：{'、'.join(dupe)}")
    if bad:
        return fail("；".join(bad))
    return ok(f"{len(got)} 個 theme 互不重複")


register(Check(
    id="chart.theme_unique",
    covers="五張圖的 theme 互不重複，且每個都在投顧 anchors 的 groups 裡（值域的唯一的家）",
    blind_to=[
        "theme 合法但**選得不對**（一張講利率的圖標成台灣）",
        "投顧那邊改了組名——這條會立刻變紅，但它說不出是誰改的",
        "週末的 theme 分布是否合理（規則只說不重複）",
        "已發布的舊日期檔",
    ],
    run=_themes,
    fixture={"advisory_anchors": {"groups": [{"name": "台灣"}, {"name": "中國"}]},
             "doc": {"charts": [{"theme": "台灣"}, {"theme": "台灣"}]}},
    near_miss={"advisory_anchors": {"groups": [{"name": "台灣"}, {"name": "中國"}]},
               "doc": {"charts": [{"theme": "台灣"}, {"theme": "中國"}]}},
    suite="chart",
))


# ── 3. 每一種圖型的資料欄位都在 ──────────────────────────────────────
def _kind_data(p):
    """**`series` 只是 timeseries 的欄位。** scatter 用 `pts`、heatmap 用 `matrix`。

    2026-08-20 盤點時我只找 `series`，於是 18 張非折線圖全被算成沒有資料——
    而它們的資料一直都在。這條檢查照 `anchors.kinds` 逐圖型驗，
    就是為了讓「資料掉了」與「我找錯欄位」分得出來。
    """
    kinds = _A(p, "kinds")
    bad = []
    for c in _charts(p["doc"]):
        k = c.get("kind")
        spec = kinds.get(k)
        if not isinstance(spec, dict) or "data" not in spec:
            bad.append(f"{c.get('slug', '?')} 的 kind「{k}」不在 anchors.kinds 裡 —— "
                       "**新圖型要先告訴檢查程式它的資料長什麼樣**，否則守門會把選擇窄化成一種")
            continue
        miss = [f for f in spec["data"] if not c.get(f)]
        if miss:
            bad.append(f"{c.get('slug', '?')}（{k}）缺 {'、'.join(miss)}")
    if bad:
        return fail("；".join(bad))
    return ok()


register(Check(
    id="chart.kind_data_present",
    covers="每張圖依 anchors.kinds 該有的資料欄位都在，且 kind 本身有登記",
    blind_to=[
        "**欄位在但內容是錯的**（點數對、數字錯）",
        "資料點數夠不夠——那是 chart.series_shape 的事",
        "欄位在但與 title／takeaway 講的不是同一件事",
        "同一個 kind 在渲染層是否真的畫得出來（檢查不餵 ECharts）",
        "已發布的舊日期檔",
    ],
    run=_kind_data,
    fixture={"anchors": {"kinds": {"scatter": {"data": ["pts"]}}},
             "doc": {"charts": [{"slug": "x", "kind": "scatter"}]}},
    near_miss={"anchors": {"kinds": {"scatter": {"data": ["pts"]}}},
               "doc": {"charts": [{"slug": "x", "kind": "scatter", "pts": [[1, 2]]}]}},
    suite="chart",
))


# ── 4. 份量 ─────────────────────────────────────────────────────────
def _lengths(p):
    L = _A(p, "lengths")
    known = _A(p, "known_exceptions")
    date = p["doc"].get("date", "")
    exempt = " ".join(known.get(date) or [])
    bad = []
    for c in _charts(p["doc"]):
        slug = c.get("slug", "?")
        if slug in exempt:
            continue          # 已登錄的歷史例外：封存不改寫，門檻也不為它調鬆
        def band(field, lo, hi):
            n = len(c.get(field) or "")
            if not (lo <= n <= hi):
                bad.append(f"{slug} {field} {n} 字，不在 {lo}–{hi}")
        band("title", *L["title"])
        band("reading", *L["reading"])
        band("so_what", *L["so_what"])
        n = len(c.get("takeaway") or "")
        if n > L["takeaway_max"]:
            bad.append(f"{slug} takeaway {n} 字，超過 {L['takeaway_max']}")
        paras = len((c.get("reading") or "").split("\n\n"))
        if paras < L["reading_paragraphs_min"]:
            bad.append(f"{slug} reading 只有 {paras} 段，應 ≥{L['reading_paragraphs_min']}")
        for field, key in (("watch", "watch_items"), ("tags", "tags")):
            lo, hi = L[key]
            k = len(c.get(field) or [])
            if not (lo <= k <= hi):
                bad.append(f"{slug} {field} {k} 條，不在 {lo}–{hi}")
    for field in ("headline", "standfirst"):
        lo, hi = L[field]
        n = len(p["doc"].get(field) or "")
        if not (lo <= n <= hi):
            bad.append(f"{field} {n} 字，不在 {lo}–{hi}")
    if bad:
        return fail("；".join(bad))
    return ok()


register(Check(
    id="chart.lengths",
    covers="每張圖的 title／takeaway／reading（含段數）／so_what／watch／tags，"
           "以及當日的 headline／standfirst，全部落在 anchors.lengths 的區間",
    blind_to=[
        "**字數對但內容空洞**——`title` 是不是一個判斷、`so_what` 有沒有寫成空話，這條看不出來",
        "reading 分了三段但三段講同一件事",
        "已登錄在 known_exceptions 的舊日檔會被整張跳過",
        "已發布的舊日期檔",
    ],
    run=_lengths,
    fixture={"anchors": {"lengths": {"title": [12, 30], "takeaway_max": 70,
                                     "reading": [200, 620], "reading_paragraphs_min": 3,
                                     "so_what": [60, 120], "watch_items": [1, 3], "tags": [2, 5],
                                     "headline": [20, 30], "standfirst": [60, 100]},
                         "known_exceptions": {}},
             "doc": {"date": "2026-08-20", "headline": "短", "standfirst": "短",
                     "charts": [{"slug": "x", "title": "太短"}]}},
    near_miss={"anchors": {"lengths": {"title": [2, 30], "takeaway_max": 70,
                                       "reading": [1, 620], "reading_paragraphs_min": 1,
                                       "so_what": [1, 120], "watch_items": [1, 3], "tags": [1, 5],
                                       "headline": [1, 30], "standfirst": [1, 100]},
                           "known_exceptions": {}},
               "doc": {"date": "2026-08-20", "headline": "有", "standfirst": "有",
                       "charts": [{"slug": "x", "title": "剛好", "reading": "一",
                                   "so_what": "一", "watch": ["a"], "tags": ["b"]}]}},
    suite="chart",
))


# ── 5. 序列條數 ─────────────────────────────────────────────────────
def _series_cap(p):
    cap = _A(p, "series", "max_per_chart")
    warn_at = _A(p, "series", "warn_at")
    over, edge = [], []
    for c in _charts(p["doc"]):
        n = len(c.get("series") or [])
        if n > cap:
            over.append(f"{c.get('slug', '?')} {n} 條")
        elif n == warn_at:
            edge.append(f"{c.get('slug', '?')}")
    if over:
        return fail(f"{'、'.join(over)} —— 超過 {cap} 條會讓第 {cap+1} 條繞回主角紅，"
                    "**一張圖出現兩個主角。超過就拆圖，不是換色**")
    if edge:
        return warn(f"{'、'.join(edge)} 用滿 {warn_at} 條，四個角色全用掉了，再加一條就會撞色")
    return ok()


register(Check(
    id="chart.series_cap",
    covers="每張圖的 series 條數不超過 anchors 的上限；用滿上限時警示",
    blind_to=[
        "**非 timeseries 圖型的分項數**——stacked/grouped 的 `groups` 這條不看",
        "條數合格但顏色是手寫且撞在一起",
        "四條之內但其中兩條講同一件事",
        "已發布的舊日期檔",
    ],
    run=_series_cap,
    fixture={"anchors": {"series": {"max_per_chart": 4, "warn_at": 4}},
             "doc": {"charts": [{"slug": "x", "series": [{}, {}, {}, {}, {}]}]}},
    near_miss={"anchors": {"series": {"max_per_chart": 4, "warn_at": 9}},
               "doc": {"charts": [{"slug": "x", "series": [{}, {}, {}, {}]}]}},
    suite="chart",
))


# ── 6. 不要五張全折線 ───────────────────────────────────────────────
def _diversity(p):
    liney = set(_A(p, "diversity", "line_kinds"))
    need = _A(p, "diversity", "min_non_line_per_day")
    since = _A(p, "known_exceptions", "diversity_from")
    date = p["doc"].get("date", "")
    if date < since:
        return skipped(f"{date} 早於規則生效日 {since}")
    kinds = [c.get("kind") for c in _charts(p["doc"])]
    non = [k for k in kinds if k not in liney]
    if len(non) < need:
        return fail(f"五張全是 {'／'.join(sorted(set(kinds)))} —— 至少要有 {need} 張非折線。"
                    "**但若當天真的每個題目都是兩條線的關係，要換的是選題角度，不是硬換圖型**")
    return ok(f"{len(non)} 張非折線（{'、'.join(non)}）")


register(Check(
    id="chart.diversity",
    covers="當日至少有 anchors 指定張數的非折線圖（2026-08-10 起生效，之前的日檔跳過）",
    blind_to=[
        "**圖型換了但不適合那份資料**——為了滿足規則塞進雷達圖比五張折線更糟",
        "非折線那張是不是硬湊的",
        "同一種非折線圖型連續用了一個月",
        "生效日之前的日檔（回傳 SKIPPED 而不是 PASS）",
    ],
    run=_diversity,
    fixture={"anchors": {"diversity": {"line_kinds": ["timeseries"], "min_non_line_per_day": 1},
                         "known_exceptions": {"diversity_from": "2026-08-10"}},
             "doc": {"date": "2026-08-20", "charts": [{"kind": "timeseries"}] * 5}},
    near_miss={"anchors": {"diversity": {"line_kinds": ["timeseries"], "min_non_line_per_day": 1},
                           "known_exceptions": {"diversity_from": "2026-08-10"}},
               "doc": {"date": "2026-08-20",
                       "charts": [{"kind": "timeseries"}] * 4 + [{"kind": "heatmap"}]}},
    suite="chart",
))


# ── 7. 頁尾行數 ─────────────────────────────────────────────────────
def _footer(p):
    w = _A(p, "footer", "visual_width_per_line")
    warn_n = _A(p, "footer", "lines_warn")
    over, edge = [], []
    for c in _charts(p["doc"]):
        lines = -(-_vis(c.get("source")) // w) + -(-_vis(c.get("note")) // w)
        if lines > warn_n:
            over.append(f"{c.get('slug', '?')} {lines} 行")
        elif lines == warn_n:
            edge.append(c.get("slug", "?"))
    if over:
        return fail(f"{'、'.join(over)} —— 頁尾超過 {warn_n} 行。"
                    "**下游直接把 PNG 貼進簡報，頁尾要自帶來源標註**，但它不能吃掉半張圖")
    if edge:
        return warn(f"{'、'.join(edge)} 的頁尾剛好 {warn_n} 行，再多一個字就超過")
    return ok()


register(Check(
    id="chart.footer_lines",
    covers="每張圖的 source ＋ note 依視覺寬（中日韓 2、其餘 1）折行後不超過 anchors 的行數上限",
    blind_to=[
        "**來源標註是否正確**——只算長度，不看它指的是不是真的來源",
        "實際字型下的折行位置（這裡用固定視覺寬估算，不是排版引擎）",
        "note 寫了但講的不是這張圖的事",
        "已發布的舊日期檔",
    ],
    run=_footer,
    fixture={"anchors": {"footer": {"visual_width_per_line": 10, "lines_warn": 3}},
             "doc": {"charts": [{"slug": "x", "source": "中" * 25, "note": "中" * 25}]}},
    # 貼著邊界的合格側：source 20 視覺寬＝2 行、note 空＝0 行，合計 2 < 3。
    near_miss={"anchors": {"footer": {"visual_width_per_line": 10, "lines_warn": 3}},
               "doc": {"charts": [{"slug": "x", "source": "中" * 10, "note": ""}]}},
    suite="chart",
))


# ── 8. 序列新鮮度 ───────────────────────────────────────────────────
def _freshness(p):
    F = _A(p, "freshness")
    now = dt.datetime.fromisoformat(p["now"]).astimezone(TPE).date()
    day_bad, day_warn, mon_bad, mon_warn = [], [], [], []
    for c in _charts(p["doc"]):
        for s in c.get("series") or []:
            pts = s.get("data") or s.get("points") or []
            last = None
            for pt in pts:
                d = pt[0] if isinstance(pt, (list, tuple)) else pt.get("d") or pt.get("date")
                if isinstance(d, str) and len(d) >= 10:
                    last = d[:10] if last is None or d[:10] > last else last
            if not last:
                continue
            monthly = last.endswith("-01")
            gap_days = (now - dt.date.fromisoformat(last)).days
            tag = f"{c.get('slug', '?')}／{s.get('name', '?')} 末日 {last}"
            if monthly:
                months = gap_days // 30
                if months >= F["monthly_fail_periods"]:
                    mon_bad.append(f"{tag}（落後 {months} 期）")
                elif months >= F["monthly_warn_periods"]:
                    mon_warn.append(f"{tag}（落後 {months} 期）")
            else:
                if gap_days >= F["daily_fail_days"]:
                    day_bad.append(f"{tag}（落後 {gap_days} 天）")
                elif gap_days >= F["daily_warn_days"]:
                    day_warn.append(f"{tag}（落後 {gap_days} 天）")
    if day_bad or mon_bad:
        return fail("；".join(day_bad + mon_bad) + " —— 硬失敗，不得發布")
    if day_warn or mon_warn:
        return warn("；".join(day_warn + mon_warn) +
                    " —— subtitle 或 note 必須寫出實際基準日")
    return ok()


register(Check(
    id="chart.series_freshness",
    covers="每條 series 的末日與今天的距離，日頻與月頻各一套門檻（值在 anchors.freshness）",
    blind_to=[
        "**只看 timeseries 的 `series`**——scatter 的 pts、heatmap 的 matrix 沒有日期軸，這條看不到它們",
        "月頻的判準是「末日以每月 1 號標記」，**日頻資料剛好落在 1 號會被誤判成月頻**",
        "序列是新的但值是錯的",
        "末日很新但中間有缺口",
        "已發布的舊日期檔",
    ],
    run=_freshness,
    fixture={"anchors": {"freshness": {"daily_warn_days": 2, "daily_fail_days": 5,
                                       "monthly_warn_periods": 2, "monthly_fail_periods": 3}},
             "now": "2026-08-20T12:00:00+08:00",
             "doc": {"charts": [{"slug": "x", "series": [
                 {"name": "s", "data": [["2026-08-01", 1], ["2026-08-10", 2]]}]}]}},
    near_miss={"anchors": {"freshness": {"daily_warn_days": 2, "daily_fail_days": 5,
                                         "monthly_warn_periods": 2, "monthly_fail_periods": 3}},
               "now": "2026-08-20T12:00:00+08:00",
               "doc": {"charts": [{"slug": "x", "series": [
                   {"name": "s", "data": [["2026-08-19", 1], ["2026-08-20", 2]]}]}]}},
    suite="chart",
))


# ── 9. 不要存 option ────────────────────────────────────────────────
def _no_stored_option(p):
    """**一份 spec，兩個渲染器。** 存了 option 就等於同一張圖有兩份實作。

    舊制最嚴重的一次雙軌漂移：瀑布圖在網頁上每根從 0 往上長，
    **圖上的結論與 takeaway 相反，卻不丟任何例外。**
    """
    if _A(p, "rendering", "stored_option") is not False:
        return skipped("anchors 目前允許存 option")
    if not _A(p, "rendering", "renderer_ready"):
        return skipped("渲染器還沒能從 spec 畫出全部圖型 —— "
                       "**規則已定、機制未建**，這條先不擋。旗標在 anchors.rendering.renderer_ready")
    has = [c.get("slug", "?") for c in _charts(p["doc"]) if c.get("option")]
    if has:
        return fail(f"{len(has)} 張圖存了 option：{'、'.join(has[:4])} —— "
                    "兩軌要從同一份 spec 渲染，存下來的那一份會漂")
    if not p["doc"].get("about", {}).get("renderer_version"):
        return fail("about.renderer_version 沒填 —— 不存 option 的代價是"
                    "「舊圖用新版渲染器重畫會有樣式差異」，那要靠這個欄位定位")
    return ok()


register(Check(
    id="chart.no_stored_option",
    covers="當日的圖都不存 ECharts option，且 about.renderer_version 有填",
    blind_to=[
        "**兩個渲染器是不是真的一致**——這條只擋掉「存第二份」，不驗兩軌畫出來一樣",
        "renderer_version 填了但填錯",
        "**渲染器還沒好的期間這條是 SKIPPED**——它會說出原因，但那段期間沒有東西在擋存 option",
        "2026-08-17 之前那 13 天存了 option，那是舊制，歷史不改寫（檢查只跑當日）",
        "spec 本身缺欄位——那是 chart.kind_data_present 的事",
    ],
    run=_no_stored_option,
    fixture={"anchors": {"rendering": {"stored_option": False, "renderer_ready": True},
                         "known_exceptions": {"diversity_from": "2026-08-10"}},
             "doc": {"date": "2026-08-20", "about": {"renderer_version": "1"},
                     "charts": [{"slug": "x", "option": {"series": []}}]}},
    near_miss={"anchors": {"rendering": {"stored_option": False, "renderer_ready": True},
                           "known_exceptions": {"diversity_from": "2026-08-10"}},
               "doc": {"date": "2026-08-20", "about": {"renderer_version": "1"},
                       "charts": [{"slug": "x"}]}},
    suite="chart",
))


# ── 10. 軌道對得上星期 ──────────────────────────────────────────────
_WD = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def _track(p):
    """**軌道綁死星期，不是輪流。**

    「同一條軌道每週固定同一天出現」才有跨期可比。
    週末若往下數第六、七條，**一輪之後全部錯位**——而錯位不會有任何徵兆，
    只會讓幾週後的跨期比較悄悄變成在比不同的東西。
    """
    T = _A(p, "tracks")
    cs = _charts(p["doc"])
    if not cs:
        return skipped("沒有圖")
    slot = (cs[-1].get("slot") or "")
    if "｜" not in slot:
        return fail(f"最後一張的 slot 是「{slot}」，軌道圖要寫成「軌道圖｜<軌道名>」")
    name = slot.split("｜", 1)[1]
    d = dt.date.fromisoformat(p["doc"]["date"])
    wd = d.weekday()
    if wd >= 5:
        tag = T["weekend_mode"]
        if tag not in name:
            return fail(f"{d}（週{'六日'[wd-5]}）的軌道圖沒有標「{tag}」——"
                        "**週末不推進輪盤**，寫成「軌道圖｜<軌道名>（%s）」" % tag)
        base = name.split("（", 1)[0]
        if base not in T.values():
            return fail(f"週線複查挑的「{base}」不是五條軌道之一")
        return ok(f"{d} 週末，複查「{base}」")
    want = T[_WD[wd]]
    if name != want:
        return fail(f"{d} 是週{'一二三四五'[wd]}，軌道應為「{want}」，實際是「{name}」——"
                    "**錯位一輪就毀掉跨期可比性**")
    return ok(f"{d} → {want}")


register(Check(
    id="chart.track_of_the_day",
    covers="第五張圖的軌道名對得上星期幾（平日綁死五條），週末標「週線複查」且挑的是五條之一",
    blind_to=[
        "**週六與週日挑了同一條**——這條只看單日，看不到兩天之間的關係",
        "軌道名對但那張圖畫的不是那條軌道的東西",
        "軌道圖是否換了算法或基期（規則說不要換，這條驗不到）",
        "已發布的舊日期檔",
    ],
    run=_track,
    fixture={"anchors": {"tracks": {"monday": "利率與匯率", "tuesday": "台股與資金流",
                                    "wednesday": "AI 與半導體", "thursday": "原物料與能源",
                                    "friday": "信用與風險偏好", "weekend_mode": "週線複查"}},
             "doc": {"date": "2026-08-20", "charts": [{"slot": "軌道圖｜台股與資金流"}]}},
    near_miss={"anchors": {"tracks": {"monday": "利率與匯率", "tuesday": "台股與資金流",
                                      "wednesday": "AI 與半導體", "thursday": "原物料與能源",
                                      "friday": "信用與風險偏好", "weekend_mode": "週線複查"}},
               "doc": {"date": "2026-08-20", "charts": [{"slot": "軌道圖｜原物料與能源"}]}},
    suite="chart",
))


# ── 11. 體積 ────────────────────────────────────────────────────────
def _size(p):
    kb = p.get("size_kb")
    if kb is None:
        return skipped("payload 沒有帶 size_kb —— **這不是「沒問題」**")
    warn_kb, fail_kb = _A(p, "size", "json_warn_kb"), _A(p, "size", "json_fail_kb")
    if kb > fail_kb:
        return fail(f"單日 JSON {kb:.0f}KB，超過 {fail_kb} —— 前端載入會明顯卡頓")
    if kb > warn_kb:
        return warn(f"單日 JSON {kb:.0f}KB，超過 {warn_kb} —— 檢查是否有圖用了過長的序列")
    return ok(f"{kb:.0f}KB")


register(Check(
    id="chart.size",
    covers="當日 JSON 的實際位元組數落在 anchors.size 的兩道門檻內",
    blind_to=[
        "**哪一張圖把它撐大的**——只給總量，不歸因",
        "體積小但內容是空的",
        "PNG／SVG 的體積（那些不在 JSON 裡）",
    ],
    run=_size,
    fixture={"anchors": {"size": {"json_warn_kb": 250, "json_fail_kb": 600}}, "size_kb": 700},
    near_miss={"anchors": {"size": {"json_warn_kb": 250, "json_fail_kb": 600}}, "size_kb": 200},
    suite="chart",
))


# ── 12. 取數路徑要具名 ──────────────────────────────────────────────
def _data_path(p):
    order = _A(p, "data_paths", "order")
    since = _A(p, "known_exceptions", "data_path_from")
    if p["doc"].get("date", "") < since:
        return skipped(f"{p['doc'].get('date')} 早於這個欄位生效的 {since}")
    got = (p["doc"].get("about") or {}).get("data_path")
    if not got:
        return fail(f"about.data_path 沒填 —— 三條路徑（{'／'.join(order)}）"
                    "走了哪一條要具名，否則「今天走的是備援」這件事沒有人看得到")
    if got not in order:
        return fail(f"about.data_path 是「{got}」，不在 {order} 裡")
    if got == order[-1]:
        return warn(f"本期走 {got} —— **真正該響的是這一條**：它需要人在場，"
                    "無人值守輪次實際上不可用（2026-08-14 那輪就因為沒有 Chrome 而完全沒有產出）")
    return ok(f"data_path = {got}")


register(Check(
    id="chart.data_path_named",
    covers="about.data_path 有填、在值域內；走到最後一條（需要人在場的那條）時警示",
    blind_to=[
        "**填的跟實際走的是不是同一條**——這是自述，不是量測",
        "prefetch 的狀態檔是否還在有效期內",
        "2026-08-15 之前的日檔沒有這個欄位（回傳 SKIPPED 而不是 PASS）",
        "同一天不同圖走了不同路徑（只有一個欄位）",
    ],
    run=_data_path,
    fixture={"anchors": {"data_paths": {"order": ["prefetch", "direct", "browser"]},
                         "known_exceptions": {"data_path_from": "2026-08-15"}},
             "doc": {"date": "2026-08-20", "about": {}}},
    near_miss={"anchors": {"data_paths": {"order": ["prefetch", "direct", "browser"]},
                           "known_exceptions": {"data_path_from": "2026-08-15"}},
               "doc": {"date": "2026-08-20", "about": {"data_path": "prefetch"}}},
    suite="chart",
))
