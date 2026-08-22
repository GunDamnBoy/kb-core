"""每日五圖的檢查。

payload 形狀（由 `tools/chart_verify.py` 組出來，檢查本身不做 IO）：

    {"doc":      當日的 data/<date>.json,
     "prev":     前一版的 doc（沒有就 None）,
     "anchors":  chart/anchors.json,
     "advisory_anchors": advisory/anchors.json —— **theme 值域的家在那裡**,
     "size_kb":  當日 JSON 的實際大小,
     "png":      {slug: 位元組數 or None} —— **None 是「檔案不在」，不是 0**,
     "prefetch": data/_prefetch_status.json 的內容（讀不動就 None）,
     "recent_data_paths": 當日之前 14 期的 about.data_path，新到舊,
     "now":      ISO8601}

後面三樣都要摸磁碟，所以由 `systems/chart.py` 的 `build()` 負責取，
**檢查只讀它拿到的東西**。取不到一律留 None 讓檢查判 SKIPPED——
給 0 或給空 dict 會讓「沒量到」長得跟「量到了而且沒問題」一模一樣。

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
    """**有量測就用量測，沒有才估。**

    2026-08-22 拿當期五張圖對過：估算與 `render_static` 量到的 3／3／2／3／3 一致，
    **估算沒有失準**。改用量測不是因為估算算錯，而是因為**估算照不到截斷** ——
    超過上限時 render 會切字補刪節號，估算只回一個大於上限的數字，
    說不出「已經被切了」，而被切掉的正是頁尾要自帶的來源標註。
    `render_static` 現在把截斷前的行數寫進 `chart.footer_lines`，這裡優先讀它；
    舊日檔沒有這個欄位就退回估算，所以回測不會因為改這裡變紅。
    """
    w = _A(p, "footer", "visual_width_per_line")
    warn_n = _A(p, "footer", "lines_warn")
    over, edge = [], []
    for c in _charts(p["doc"]):
        measured = c.get("footer_lines")
        if isinstance(measured, int):
            lines = measured
        else:
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
    covers="每張圖的頁尾行數不超過 anchors 的上限。**有 chart.footer_lines（render_static 量到的"
           "截斷前行數）就用它**，沒有才退回視覺寬估算（中日韓 2、其餘 1）",
    blind_to=[
        "**來源標註是否正確**——只算長度，不看它指的是不是真的來源",
        "**有沒有被截斷**——量測值是截斷前的行數，這條只判它超不超過上限，"
        "不會告訴你 PNG 上那一行結尾的刪節號吃掉了什麼",
        "沒有 footer_lines 的舊日檔仍然只有估算（2026-08-22 對過一次，五張圖估算與量測一致）",
        "量測值是 render_static 回報的，**它與最後存進 PNG 的是同一次呼叫，但仍是自述**"
        "——真正的證據是看圖",
        "note 寫了但講的不是這張圖的事",
        "已發布的舊日期檔",
    ],
    run=_footer,
    # **兩條路徑各放一張圖**：`m` 走量測（footer_lines=4），`e` 走估算。
    # 只放量測那一張的話，估算那條退路會變成沒有人驗的程式碼。
    fixture={"anchors": {"footer": {"visual_width_per_line": 10, "lines_warn": 3}},
             "doc": {"charts": [{"slug": "m", "footer_lines": 4},
                                {"slug": "e", "source": "中" * 25, "note": "中" * 25}]}},
    # 貼著邊界的合格側：量測 2 行；估算那張 source 20 視覺寬＝2 行、note 空＝0 行，合計 2 < 3。
    near_miss={"anchors": {"footer": {"visual_width_per_line": 10, "lines_warn": 3}},
               "doc": {"charts": [{"slug": "m", "footer_lines": 2},
                                  {"slug": "e", "source": "中" * 10, "note": ""}]}},
    suite="chart",
))


# ── 8. 序列新鮮度 ───────────────────────────────────────────────────
def _freshness(p):
    F = _A(p, "freshness")
    now = dt.datetime.fromisoformat(p["now"]).astimezone(TPE).date()
    # **週頻發布的日頻序列**：觀測每天都有，但一週只發一次（H.10 每週一）。
    # 日頻門檻只看得到「最後一筆觀測有多舊」，於是它們週三就過硬失敗——
    # 資料沒壞，是門檻的形狀不對。識別靠 series_spec 的 id：序列名稱是寫給讀者看的。
    weekly_ids = F.get("weekly_release_series") or {}
    since_wk = F.get("weekly_release_from") or "9999-12-31"
    weekly_on = bool(weekly_ids) and p["doc"].get("date", "") >= since_wk
    day_bad, day_warn, mon_bad, mon_warn, wk_bad, wk_warn = [], [], [], [], [], []
    for c in _charts(p["doc"]):
        spec_id = {sp.get("name"): sp.get("id")
                   for sp in (c.get("series_spec") or []) if isinstance(sp, dict)}
        for s in c.get("series") or []:
            # **序列的真實形狀是 `dates`／`values` 兩個平行陣列。**
            # 這條檢查原本只認 `data`／`points`，而 build_series.py 與
            # render_day.py 從來沒有寫過那兩個鍵 —— 於是 `last` 永遠是 None、
            # 每條序列都被 continue 掉，整條檢查回 ok()。2026-08-21 發現時，
            # 它已經對著 13 天封存與當期產出「全綠」了一整輪都沒讀到一個數字。
            # BRIEF 第六節第 3 條（序列落後超過硬失敗門檻）等於沒有守門人。
            #
            # 兩種形狀都認，因為 `pts` 那條路是給手工序列與未來圖型留的；
            # 但 `dates` 擺在前面，那才是每天實際走的那一條。
            last = None
            dates = s.get("dates")
            if isinstance(dates, list):
                for d in dates:
                    if isinstance(d, str) and len(d) >= 10:
                        last = d[:10] if last is None or d[:10] > last else last
            else:
                pts = s.get("data") or s.get("points") or []
                for pt in pts:
                    d = pt[0] if isinstance(pt, (list, tuple)) else pt.get("d") or pt.get("date")
                    if isinstance(d, str) and len(d) >= 10:
                        last = d[:10] if last is None or d[:10] > last else last
            if not last:
                continue
            monthly = last.endswith("-01")
            gap_days = (now - dt.date.fromisoformat(last)).days
            tag = f"{c.get('slug', '?')}／{s.get('name', '?')} 末日 {last}"
            sid = spec_id.get(s.get("name"))
            if weekly_on and sid in weekly_ids and not monthly:
                periods = gap_days // 7
                if periods >= F["weekly_fail_periods"]:
                    wk_bad.append(f"{tag}（{sid}，週頻發布，落後 {periods} 期）")
                elif periods >= F["weekly_warn_periods"]:
                    wk_warn.append(f"{tag}（{sid}，週頻發布，落後 {periods} 期）")
                continue
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
    if day_bad or mon_bad or wk_bad:
        return fail("；".join(day_bad + mon_bad + wk_bad) + " —— 硬失敗，不得發布")
    if day_warn or mon_warn or wk_warn:
        return warn("；".join(day_warn + mon_warn + wk_warn) +
                    " —— subtitle 或 note 必須寫出實際基準日")
    return ok()


register(Check(
    id="chart.series_freshness",
    covers="每條 series 的末日與今天的距離，日頻／月頻／週頻發布各一套門檻（值在 anchors.freshness）。"
           "序列形狀認 `dates`（實際產出的那一種）與 `data`／`points`（手工序列）兩種",
    blind_to=[
        "**週頻發布只認得出 series_spec 裡有 id 的序列**——手工序列（沒有 spec）會回頭走日頻門檻，"
        "而週頻那兩條若被寫成手工序列就會照舊硬失敗",
        "**這份週頻清單是人工登錄的**——FRED 改了某條的發布頻率，這裡不會自己知道",
        "**只看 timeseries 的 `series`**——scatter 的 pts、heatmap 的 matrix 沒有日期軸，這條看不到它們",
        "**第三種序列形狀**——2026-08-21 之前它只認 `data`／`points`，而真實產出是 `dates`／`values`，"
        "於是它對著 13 天封存全綠、一個數字都沒讀到。fixture 現在用真實形狀，但**再冒出第四種鍵名，"
        "它一樣會安靜地全部跳過**；形狀變了要回來改這裡",
        "月頻的判準是「末日以每月 1 號標記」，**日頻資料剛好落在 1 號會被誤判成月頻**",
        "序列是新的但值是錯的",
        "末日很新但中間有缺口",
        "已發布的舊日期檔",
    ],
    run=_freshness,
    fixture={"anchors": {"freshness": {"daily_warn_days": 2, "daily_fail_days": 5,
                                       "monthly_warn_periods": 2, "monthly_fail_periods": 3,
                                       "weekly_warn_periods": 2, "weekly_fail_periods": 3,
                                       "weekly_release_from": "2026-01-01",
                                       "weekly_release_series": {"DTWEXBGS": "H.10 每週一"}}},
             "now": "2026-08-20T12:00:00+08:00",
             # **fixture 用的是實際產出的 `dates`／`values` 形狀**，不是 `data`。
             # 舊 fixture 用 `data`，於是自檢照樣觸發、照樣 selftest OK，
             # 而真實資料一條都讀不到 —— fixture 對得上程式、對不上產出。
             "doc": {"date": "2026-08-20", "charts": [
                 {"slug": "x", "series": [
                     {"name": "s", "dates": ["2026-08-01", "2026-08-10"], "values": [1, 2]}]},
                 # 週頻那一條：落後 43 天＝6 期，週頻門檻也擋得下來
                 {"slug": "w", "series_spec": [{"id": "DTWEXBGS", "name": "美元指數"}],
                  "series": [{"name": "美元指數",
                              "dates": ["2026-07-01", "2026-07-08"], "values": [1, 2]}]}]}},
    near_miss={"anchors": {"freshness": {"daily_warn_days": 2, "daily_fail_days": 5,
                                         "monthly_warn_periods": 2, "monthly_fail_periods": 3,
                                         "weekly_warn_periods": 2, "weekly_fail_periods": 3,
                                         "weekly_release_from": "2026-01-01",
                                         "weekly_release_series": {"DTWEXBGS": "H.10 每週一"}}},
               "now": "2026-08-20T12:00:00+08:00",
               # **合格側的重點在 `w`**：落後 6 天，照日頻是硬失敗，照週頻是 0 期 —— 這條規則就是為它加的。
               "doc": {"date": "2026-08-20", "charts": [
                   {"slug": "x", "series": [
                       {"name": "s", "dates": ["2026-08-19", "2026-08-20"], "values": [1, 2]}]},
                   {"slug": "w", "series_spec": [{"id": "DTWEXBGS", "name": "美元指數"}],
                    "series": [{"name": "美元指數",
                                "dates": ["2026-08-07", "2026-08-14"], "values": [1, 2]}]}]}},
    suite="chart",
))


# ── 9. option 有沒有忠實地把 spec 編碼進去 ────────────────────────
CAT_KINDS = ("grouped_bar", "stacked_bar", "pct_stacked_bar", "waterfall")


def _waterfall_bases(vals):
    """瀑布圖每一根的底。**這是從 vals 反推的，不是從 option 抄的** ——
    抄過來比對就變成拿它自己驗它自己。"""
    base, run = [], 0.0
    for v in vals:
        base.append(round(min(run, run + v), 6))
        run = round(run + v, 6)
    base.append(0.0)      # 合計那一根從 0 起
    return base


def _option_spec(p):
    if _A(p, "rendering", "stored_option") is not True:
        return skipped("anchors 目前不存 option —— 沒有第二軌可比")
    want_color = [_A(p, "palette", k) for k in ("lead", "contrast", "overflow", "background")]
    bad = []
    for c in _charts(p["doc"]):
        slug, kind = c.get("slug", "?"), c.get("kind")
        o = c.get("option")
        if not o:
            bad.append(f"{slug} 沒有 option —— 互動軌畫不出來，而網頁不會有人回報")
            continue
        srs = o.get("series") or []
        if o.get("color") and o["color"] != want_color:
            bad.append(f"{slug} option.color 不是 anchors 的四個角色")

        # ①類別軸對齊：ECharts 按位置貼資料，錯位不報錯、整條位移
        if kind in CAT_KINDS:
            cats = c.get("cats") or []
            want = list(cats) + ([c.get("total_label", "合計")] if kind == "waterfall" else [])
            got = ((o.get("xAxis") or {}) if isinstance(o.get("xAxis"), dict)
                   else (o.get("xAxis") or [{}])[0]).get("data")
            if got is not None and len(got) != len(want):
                bad.append(f"{slug} xAxis.data {len(got)} 項，cats 是 {len(want)} 項")
            for si in srs:
                if si.get("type") == "bar" and si.get("data") is not None \
                        and len(si["data"]) != len(want):
                    bad.append(f"{slug} 序列「{si.get('name', '?')}」{len(si['data'])} 筆，"
                               f"軸上是 {len(want)} 格")

        # ②瀑布圖的 stackStrategy：漏掉時**資料完全不變**，只有渲染行為變
        if kind == "waterfall":
            bars = [si for si in srs if si.get("type") == "bar"]
            off = [si.get("name", "?") for si in bars if si.get("stackStrategy") != "all"]
            if off:
                bad.append(f"{slug} 的 bar 序列缺 stackStrategy=all（{'、'.join(str(x) for x in off)}）"
                           " —— 網頁上每根會從 0 往上長，**結論與 takeaway 相反**")
            vals = c.get("vals")
            if vals and bars and isinstance(bars[0].get("data"), list):
                want_base = _waterfall_bases(vals)
                got_base = [x if isinstance(x, (int, float)) else None for x in bars[0]["data"]]
                if len(got_base) == len(want_base):
                    diff = [i for i, (g, w) in enumerate(zip(got_base, want_base))
                            if g is None or abs(g - w) > 0.01]
                    if diff:
                        bad.append(f"{slug} 底柱與 vals 反推的對不上（第 {diff[:3]} 格）")

        # ③長條幾何：barWidth 是「每一條」不是「一整組」
        if kind in ("grouped_bar", "stacked_bar", "pct_stacked_bar"):
            hand = [si.get("name", "?") for si in srs if si.get("barWidth")]
            if hand and len(srs) > 1:
                bad.append(f"{slug} 用了逐序列的 barWidth（{'、'.join(str(x) for x in hand)}）"
                           " —— 那是每一條的寬度，兩條各 62% 會讓一組實佔 143%。用 barCategoryGap")

        # ④zero_line 兩軌都要有。gauge 與 heatmap 排除 ——
        #   靜態軌 render_static() 就是這樣寫的，兩邊的排除條件要逐字相同。
        if c.get("zero_line") and kind not in ("gauge", "heatmap"):
            has = any(any((d or {}).get("yAxis") == 0
                          for d in ((si.get("markLine") or {}).get("data") or []))
                      for si in srs)
            if not has:
                bad.append(f"{slug} 標了 zero_line 但 option 裡沒有 yAxis=0 的 markLine"
                           " —— **這條當初只有 PNG 有**")
    if bad:
        return fail("；".join(bad))
    return ok(f"{len(_charts(p['doc']))} 張圖的 option 與 spec 一致")


register(Check(
    id="chart.option_matches_spec",
    covers="每張圖的 ECharts option 忠實編碼了 spec：類別軸對齊、waterfall 的 stackStrategy 與底柱、"
           "長條幾何用 barCategoryGap、zero_line 兩軌都有、配色是 anchors 的四個角色",
    blind_to=[
        "**驗不到「matplotlib 畫錯了」** —— 靜態軌被當成參考實作，"
        "因為 PNG 每天有人看、網頁沒有人複查，會藏住的是後者",
        "純排版問題（heatmap 中文列標籤在 PNG 被切掉那種）—— 那是像素層的事",
        "option 合法但 ECharts 版本不支援那個鍵（`stackStrategy` 需 ≥5.3.3）",
        "類別軸格數對但**內容順序**錯了（只比長度，不比字串）",
        "非類別軸圖型的資料是否對齊（timeseries／scatter 走日期或數值軸）",
        "gauge 與 heatmap 的 zero_line（兩軌都刻意不畫）",
    ],
    run=_option_spec,
    fixture={"anchors": {"rendering": {"stored_option": True},
                         "palette": {"lead": "#D70C18", "contrast": "#1F4E79",
                                     "overflow": "#8A8F95", "background": "#B8BBBE"}},
             "doc": {"charts": [{"slug": "w", "kind": "waterfall",
                                 "cats": ["a", "b"], "vals": [1.0, -2.0],
                                 "option": {"series": [{"type": "bar", "data": [0, 1, 0]}]}}]}},
    near_miss={"anchors": {"rendering": {"stored_option": True},
                           "palette": {"lead": "#D70C18", "contrast": "#1F4E79",
                                       "overflow": "#8A8F95", "background": "#B8BBBE"}},
               "doc": {"charts": [{"slug": "w", "kind": "waterfall",
                                   "cats": ["a", "b"], "vals": [1.0, -2.0],
                                   "option": {"xAxis": {"data": ["a", "b", "合計"]},
                                              "series": [{"type": "bar", "stackStrategy": "all",
                                                          "data": [0.0, -1.0, 0.0]}]}}]}},
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
        # **週六與週日不得挑同一條**（anchors.tracks.weekend_distinct_days）。
        # 這條規則到 2026-08-22 為止沒有任何程式在守 —— 當天那輪只能把
        # 「明天要挑另一條」寫進 about.run，而**自述不是守門人**。
        # payload 本來就帶著前一期（systems/chart.py 的 prev_doc），拿來比就好。
        if T.get("weekend_distinct_days") and wd == 6:
            prev = p.get("prev") or {}
            pslot = ((prev.get("charts") or [{}])[-1].get("slot") or "")
            pdate = prev.get("date") or ""
            if pdate and (d - dt.date.fromisoformat(pdate)).days == 1 and "｜" in pslot:
                pbase = pslot.split("｜", 1)[1].split("（", 1)[0]
                if pbase == base:
                    return fail(
                        f"週日複查挑了「{base}」，與前一天（{pdate}）同一條 —— "
                        "**同一個週末看兩次同一條軌道，等於少看一條**，"
                        "而跨期可比是靠不同軌道各自連續才成立的")
        return ok(f"{d} 週末，複查「{base}」")
    want = T[_WD[wd]]
    if name != want:
        return fail(f"{d} 是週{'一二三四五'[wd]}，軌道應為「{want}」，實際是「{name}」——"
                    "**錯位一輪就毀掉跨期可比性**")
    return ok(f"{d} → {want}")


register(Check(
    id="chart.track_of_the_day",
    covers="第五張圖的軌道名對得上星期幾（平日綁死五條），週末標「週線複查」且挑的是五條之一；"
           "週日再比對前一期（payload 的 prev），不得與週六同一條",
    blind_to=[
        "**週六那一天看不出來**——同一條的判定要等週日那期才成立，"
        "週六當下沒有任何訊號說「明天不能再挑這條」",
        "**前一期不是週六時整條略過**（例如週六那期根本沒產出），此時週日挑什麼都不會紅",
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


# ── 13. 重製圖的出處 ─────────────────────────────────────────────────
def _provenance(p):
    doc = p["doc"]
    slot = _A(p, "structure", "slots")[2]          # 「重製圖」——名字的家在 anchors
    lim = _A(p, "structure", "slot_freshness", "within_days")[slot]
    day = dt.date.fromisoformat(doc["date"])
    bad = []
    for c in _charts(doc):
        if (c.get("slot") or "").split("｜", 1)[0] != slot:
            continue
        who = c.get("slug") or "?"
        ib = ((c.get("provenance") or {}).get("inspired_by") or {})
        if not ib.get("url"):
            bad.append(f"{who} 缺 provenance.inspired_by.url")
        pub = ib.get("published") or ""
        if not pub:
            bad.append(f"{who} 缺 provenance.inspired_by.published（原文日期）")
            continue
        try:
            pd = dt.date.fromisoformat(pub)
        except ValueError:
            bad.append(f"{who} published 不是 YYYY-MM-DD：{pub}")
            continue
        lag = (day - pd).days
        if lag < 0:
            bad.append(f"{who} 原文日期 {pub} 在未來")
        elif lag > lim:
            bad.append(f"{who} 原文 {pub} 距今 {lag} 天，超過 {lim} 天上限")
    if bad:
        return fail("；".join(bad) + " —— **重製的是「題」，不是「圖」**："
                    "原題可以是七天內的專題，我們的圖必須用最新資料，"
                    "而沒有出處就分不出這兩者")
    return ok("重製圖出處齊備")


register(Check(
    id="chart.provenance",
    covers="重製圖 slot 的 provenance.inspired_by 有 url 與 published，日期格式正確、不在未來、"
           "且落在 anchors.structure.slot_freshness.within_days 的天數內",
    blind_to=[
        "**url 指的是不是真的那一篇**——這條只看欄位在不在，不連外驗證",
        "**我們的圖有沒有用最新資料**——原題七天內合格，圖用三天前的資料這條看不出來（那是 series_freshness 的事）",
        "非重製圖 slot 的出處（其他四張本來就沒有 provenance）",
        "付費牆內的圖被當成資料來源（SOURCES.md 的規則，程式判不了）",
    ],
    run=_provenance,
    fixture={"anchors": {"structure": {"slots": ["當日主圖", "市場異動圖", "重製圖", "主題深掘", "軌道圖"],
                                       "slot_freshness": {"within_days": {"重製圖": 7}}}},
             "doc": {"date": "2026-08-20",
                     "charts": [{"slot": "重製圖", "slug": "x",
                                 "provenance": {"inspired_by": {"url": "u", "published": "2026-08-01"}}}]}},
    near_miss={"anchors": {"structure": {"slots": ["當日主圖", "市場異動圖", "重製圖", "主題深掘", "軌道圖"],
                                         "slot_freshness": {"within_days": {"重製圖": 7}}}},
               "doc": {"date": "2026-08-20",
                       "charts": [{"slot": "重製圖", "slug": "x",
                                   "provenance": {"inspired_by": {"url": "u", "published": "2026-08-14"}}}]}},
    suite="chart",
))


# ── 14. 序列本身的形狀 ───────────────────────────────────────────────
def _series_wellformed(p):
    doc = p["doc"]
    lo = _A(p, "series", "min_points_timeseries")
    can_mark = _A(p, "kinds", "marker_support")
    bad = []
    for c in _charts(doc):
        who = c.get("slug") or "?"
        kind = c.get("kind") or "timeseries"
        # 類別軸圖型寫了 marker 不會報錯、也不會畫出來——**規則要求標記卻靜默丟掉**，
        # 比沒有 marker 更糟，因為 reading 會照著寫「已標在圖上」。
        if c.get("markers") and kind not in can_mark:
            bad.append(f"{who} kind={kind} 是類別軸，標不出日期 marker —— "
                       f"請改把錨點寫進 note，或換成 {can_mark} 之一")
        for s in c.get("series") or []:
            n, v = len(s.get("dates") or []), len(s.get("values") or [])
            if n != v:
                bad.append(f"{who}／{s.get('name','?')} 日期({n})與值({v})長度不符")
            elif n < lo:
                bad.append(f"{who}／{s.get('name','?')} 只有 {n} 點，不足 {lo}")
    if bad:
        return fail("；".join(bad))
    return ok("序列長度對齊、點數足夠")


register(Check(
    id="chart.series_wellformed",
    covers="每條 series 的 dates 與 values 等長且點數不少於 anchors.series.min_points_timeseries；"
           "markers 只出現在 anchors.kinds.marker_support 列的圖型上",
    blind_to=[
        "**值本身對不對**——長度對齊不代表數字是對的",
        "非 series 圖型的資料點數（cats／groups／matrix 這條不看）",
        "序列末日夠不夠新（那是 series_freshness）",
        "dates 是不是遞增、有沒有重複日期",
    ],
    run=_series_wellformed,
    fixture={"anchors": {"series": {"min_points_timeseries": 20},
                         "kinds": {"marker_support": ["timeseries", "range_area"]}},
             "doc": {"date": "2026-08-20",
                     "charts": [{"slug": "x", "kind": "grouped_bar", "markers": [{"date": "2026-08-01"}]}]}},
    near_miss={"anchors": {"series": {"min_points_timeseries": 2},
                           "kinds": {"marker_support": ["timeseries", "range_area"]}},
               "doc": {"date": "2026-08-20",
                       "charts": [{"slug": "x", "kind": "timeseries", "markers": [{"date": "2026-08-01"}],
                                   "series": [{"name": "s", "dates": ["a", "b"], "values": [1, 2]}]}]}},
    suite="chart",
))


# ── 15. PNG 真的落地了 ───────────────────────────────────────────────
def _png_present(p):
    sizes = p.get("png")
    if sizes is None:
        return skipped("payload 沒帶 png —— 組 payload 的人才摸得到磁碟，"
                       "**這裡不自己去看**，也不當成通過")
    lo = _A(p, "quality", "png_min_bytes")
    missing = [k for k, v in sizes.items() if v is None]
    tiny = [f"{k} {v}B" for k, v in sizes.items() if v is not None and v < lo]
    if missing:
        return fail(f"PNG 不存在：{'、'.join(missing)} —— JSON 說有、磁碟上沒有，"
                    "**網站會顯示一張破圖，而檢查以外的每個訊號都是正常的**")
    if tiny:
        return fail(f"PNG 過小：{'、'.join(tiny)}（下限 {lo}B）—— "
                    "**空白圖不會拋例外**，matplotlib 照樣寫出一張合法的 PNG，只是上面沒有線")
    return ok(f"{len(sizes)} 張 PNG 都在，最小 {min(sizes.values())}B")


register(Check(
    id="chart.png_present",
    covers="每張圖宣稱的 files.png 在磁碟上存在，且大於 anchors.quality.png_min_bytes",
    blind_to=[
        "**圖畫得對不對**——位元組數只證明它不是空白，不證明它畫的是對的資料",
        "PNG 與 option 是不是同一份 spec（那是 option_matches_spec）",
        "SVG 那一份（只看 files.png）",
        "檔案是不是這一輪產的（沒有比對時間戳，舊圖留在原地會通過）",
    ],
    run=_png_present,
    fixture={"anchors": {"quality": {"png_min_bytes": 20000}},
             "doc": {"date": "2026-08-20"},
             "png": {"a": 120000, "b": None}},
    near_miss={"anchors": {"quality": {"png_min_bytes": 20000}},
               "doc": {"date": "2026-08-20"},
               "png": {"a": 120000, "b": 20000}},
    suite="chart",
))


# ── 16. 預抓狀態 ─────────────────────────────────────────────────────
def _prefetch_fresh(p):
    doc = p["doc"]
    claimed = ((doc.get("about") or {}).get("data_path")) or ""
    if claimed != "prefetch":
        return skipped(f"本期 data_path 是「{claimed or '（未填）'}」，不走預抓")
    st = p.get("prefetch")
    if not st:
        return fail("本期宣稱走 prefetch，但讀不到 data/_prefetch_status.json —— "
                    "**沒有狀態檔＝預抓沒跑，不是「都成功」**，無從確認快取何時刷新")
    hours = _A(p, "prefetch", "status_valid_hours")
    try:
        fin = dt.datetime.fromisoformat(st["finished"])
    except Exception:
        return fail(f"狀態檔的 finished 讀不動（{st.get('finished')!r}）—— 當成沒有預抓處理")
    # 參照點是**這一輪的名目時刻**（日期＋anchors.schedule.run），不是 now。
    # 用 now 的話，拿舊封存回測時每一天都會判「快取過期」——**那是回測本身的產物，
    # 不是那天的事實**，而一條在回測裡永遠紅的檢查，看的人很快就會學會忽略它。
    hh, mm = (_A(p, "schedule", "run") or "11:30").split(":")
    ref = dt.datetime.combine(dt.date.fromisoformat(doc["date"]),
                              dt.time(int(hh), int(mm)), tzinfo=TPE)
    age = (ref - fin).total_seconds() / 3600
    unavailable = set(st.get("failed") or {}) | set(st.get("skipped") or {})
    used = {s.get("id") or s.get("name") for c in _charts(doc) for s in (c.get("series") or [])}
    miss = sorted(x for x in used if x and x in unavailable)
    if age < 0:
        # 狀態檔只有一份、會被後面的輪次覆寫，所以回測舊日期時它常常來自未來。
        # **那種情況答不出「當時新不新鮮」——答不出就要說答不出**，
        # 判 PASS 等於拿一份根本不是那一輪用的快取替它背書。
        return skipped(f"狀態檔（{st['finished']}）晚於這一輪的名目時刻 {ref:%Y-%m-%d %H:%M}，"
                       "已被後來的輪次覆寫 —— 這一輪用的是哪一份快取，現在查不到了")
    if age > hours:
        return fail(f"預抓已 {age:.0f} 小時未更新（上限 {hours}h，狀態檔停在 {st['finished']}，"
                    f"跑在 {st.get('host','?')}）—— launchd 可能沒在跑，"
                    "而**這一輪照樣會成功**，用的是舊快取")
    if miss:
        return fail(f"本期用到的序列有 {len(miss)} 條在預抓的失敗／跳過清單裡：{miss} —— "
                    "那些值不可能來自這次預抓，data_path 填錯了")
    return ok(f"預抓 {age:.1f} 小時前完成（{st.get('ok')}/{st.get('requested')} 條，{st.get('host','?')}）")


register(Check(
    id="chart.prefetch_fresh",
    covers="宣稱走 prefetch 時，狀態檔存在、在 anchors.prefetch.status_valid_hours 之內，"
           "且本期用到的序列不在它的 failed／skipped 裡",
    blind_to=[
        "**不宣稱 prefetch 的輪次整條跳過**（回 SKIPPED，不是 PASS）",
        "**狀態檔說成功不代表值是對的**——它只記「抓到了」",
        "跑預抓的機器對不對（會把 host 印出來，但不判）",
        "序列在 doc 裡沒有 id／name 時對不上清單，會被當成沒用到",
        "**用的是名目輪次時刻**（日期＋schedule.run），不是實際起跑時刻——輪次延後幾小時這條看不出來",
    ],
    run=_prefetch_fresh,
    fixture={"anchors": {"prefetch": {"status_valid_hours": 30}, "schedule": {"run": "11:30"}},
             "doc": {"date": "2026-08-20", "about": {"data_path": "prefetch"}},
             "prefetch": {"finished": "2026-08-18T11:06:21+08:00", "host": "old", "ok": 34,
                          "requested": 46, "failed": {}, "skipped": {}}},
    near_miss={"anchors": {"prefetch": {"status_valid_hours": 30}, "schedule": {"run": "11:30"}},
               "doc": {"date": "2026-08-20", "about": {"data_path": "prefetch"}},
               "prefetch": {"finished": "2026-08-20T11:06:21+08:00", "host": "mini", "ok": 34,
                            "requested": 46, "failed": {}, "skipped": {}}},
    suite="chart",
))


# ── 17. 連續走備援 ───────────────────────────────────────────────────
def _data_path_streak(p):
    order = _A(p, "data_paths", "order")
    cap = _A(p, "data_paths", "browser_streak_max")
    last = order[-1]
    hist = [((p["doc"].get("about") or {}).get("data_path")) or ""] + list(p.get("recent_data_paths") or [])
    n = 0
    for x in hist:
        if x != last:
            break
        n += 1
    if n >= cap:
        return fail(f"取數已連續 {n} 期走 {last} 備援（上限 {cap}）—— "
                    "**問題不在失敗那天，在成功的前幾天**："
                    "那條路需要有人指定 Chrome，無人值守輪次實際上不可用，"
                    "而它每天都「降級但成功」，於是結構性故障從來不會被當成故障")
    if n:
        return warn(f"已連續 {n} 期走 {last} 備援（上限 {cap}）")
    return ok(f"本期走 {hist[0] or '（未填）'}")


register(Check(
    id="chart.data_path_streak",
    covers="含當日在內連續走最後一條（browser）備援的期數，不到 anchors.data_paths.browser_streak_max",
    blind_to=[
        "**這是自述的統計**——每一期填的都是自己說的，不是量測出來的",
        "沒有 data_path 欄位的舊日檔（空字串會中斷連續計數，看起來像恢復了）",
        "連續走 prefetch 或 direct（那兩條不是備援，不計）",
        "同一期不同圖走了不同路徑",
    ],
    run=_data_path_streak,
    fixture={"anchors": {"data_paths": {"order": ["prefetch", "direct", "browser"],
                                        "browser_streak_max": 3}},
             "doc": {"date": "2026-08-20", "about": {"data_path": "browser"}},
             "recent_data_paths": ["browser", "browser", "prefetch"]},
    near_miss={"anchors": {"data_paths": {"order": ["prefetch", "direct", "browser"],
                                          "browser_streak_max": 3}},
               "doc": {"date": "2026-08-20", "about": {"data_path": "prefetch"}},
               "recent_data_paths": ["browser", "browser", "browser"]},
    suite="chart",
))


# ── 18. 三大數據發布日的當日主圖 ─────────────────────────────────────
def _release_day(p):
    doc = p["doc"]
    mr = (doc.get("about") or {}).get("macro_release")
    if mr is None:
        return skipped("about.macro_release 未寫入 —— 沒有人跑過偵測，"
                       "**發布日漏圖在這一輪偵測不到**（偵測要網路，判定不要，"
                       "所以這裡不自己去問 FRED）")
    # 兩種方言：2026-08-22 之前是一個 list，之後是 prefetch 寫的
    # `_macro_release.json` 整份（dict，含 checked_at 與可能的 error）。
    # **偵測失敗時 items 是空的，而空 list 與「今天沒發布」在下游長得一模一樣** ——
    # 所以帶 error 的那一種要判 SKIPPED 並把錯誤原樣說出來，不能讓它安靜地綠。
    if isinstance(mr, dict):
        if mr.get("error") and not mr.get("items"):
            return skipped(f"偵測失敗（{str(mr['error']).splitlines()[0][:90]}）—— "
                           "**這不是「今天沒發布」**，發布日漏圖這一輪一樣偵測不到")
        mr = mr.get("items") or []
    rd = _A(p, "structure", "release_day")
    slot1_name = _A(p, "structure", "slots")[0]
    fresh = [r for r in mr if r.get("fresh")]
    if not fresh:
        return ok("今日無三大數據發布")
    s1 = next((c for c in _charts(doc)
               if (c.get("slot") or "").split("｜", 1)[0] == slot1_name), {})
    bad = []
    for r in fresh:
        want = f"{str(r.get('kind','')).lower()}{rd['slug_suffix']}"
        if s1.get("slug") != want:
            bad.append(f"{r.get('label')}（{r.get('kind')}）今日發布，"
                       f"{slot1_name}必須是它：預期 slug `{want}`，實際 `{s1.get('slug')}`")
    if s1.get("theme") != rd["theme"]:
        bad.append(f"發布日的{slot1_name} theme 應為「{rd['theme']}」，實際「{s1.get('theme')}」")
    if bad:
        return fail("；".join(bad))
    return ok(f"發布日圖到位：{'、'.join(str(r.get('label')) for r in fresh)}")


register(Check(
    id="chart.release_day",
    covers="當 about.macro_release 標記今日有三大數據發布時，當日主圖的 slug 與 theme 對得上 "
           "anchors.structure.release_day",
    blind_to=[
        "**今天到底有沒有發布**——這條讀的是 doc 自述的欄位，偵測那一半需要網路，不在檢查裡",
        "欄位沒寫時整條跳過（SKIPPED），所以「忘了跑 --check」不會變成 FAIL",
        "圖畫的是不是真的那份數據（只比 slug 與 theme）",
        "非美國的數據發布（清單只有非農／CPI／PCE）",
    ],
    run=_release_day,
    fixture={"anchors": {"structure": {"slots": ["當日主圖", "市場異動圖", "重製圖", "主題深掘", "軌道圖"],
                                       "release_day": {"slug_suffix": "-release", "theme": "央行、利率與匯率"}}},
             "doc": {"date": "2026-08-20",
                     "about": {"macro_release": [{"kind": "CPI", "label": "消費者物價", "fresh": True}]},
                     "charts": [{"slot": "當日主圖", "slug": "tw-export", "theme": "總體經濟"}]}},
    near_miss={"anchors": {"structure": {"slots": ["當日主圖", "市場異動圖", "重製圖", "主題深掘", "軌道圖"],
                                         "release_day": {"slug_suffix": "-release", "theme": "央行、利率與匯率"}}},
               "doc": {"date": "2026-08-20",
                       "about": {"macro_release": [{"kind": "CPI", "label": "消費者物價", "fresh": True}]},
                       "charts": [{"slot": "當日主圖", "slug": "cpi-release", "theme": "央行、利率與匯率"}]}},
    suite="chart",
))
