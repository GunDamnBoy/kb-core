"""Per-system renderers: issue JSON -> (properties dict, list of Notion blocks).

Every renderer lays out the fields it knows, then hands any key it does not know
to `_leftover()` so a schema addition upstream shows up in Notion instead of
being dropped silently. Keys in SKIP_* are machine data (chart series, ECharts
options, file paths, ids) and are deliberately not rendered.
"""
from __future__ import annotations

import html
import re

from blocks import (bullet, callout, divider, heading, image, link_para, md_blocks, meta,
                    numbered, para, plain, quote, quote_rt, rich)

RAW = "https://raw.githubusercontent.com/GunDamnBoy/{repo}/main/{path}"

# Bump when the layout changes: it is mixed into each page's hash, so the newest
# issues (sync.py --recheck window) get re-rendered with the new layout.
RENDER_VERSION = "2026-09-25c"

# ------------------------------------------------------------------ tags ----

REGIONS = {
    "美國": ["美國", "美股", "美債", "聯準會", "Fed", "FOMC", "華府", "白宮", "S&P", "標普", "那斯達克",
             "道瓊", "美元", "川普", "財政部"],
    "中國": ["中國", "人民幣", "陸股", "港股", "恒生", "北京", "習近平", "川習", "中國人民銀行", "人行", "A 股"],
    "台灣": ["台灣", "台股", "加權指數", "加權", "台積電", "新台幣", "櫃買"],
    "日本": ["日本", "日圓", "日經", "日銀", "日本銀行", "BOJ", "東證", "TOPIX", "東京"],
    "韓國": ["韓國", "南韓", "韓元", "KOSPI", "三星", "SK 海力士", "SK海力士"],
    "東南亞": ["東南亞", "東協", "ASEAN", "越南", "泰國", "印尼", "馬來西亞", "新加坡", "菲律賓"],
    "歐洲": ["歐洲", "歐元", "歐洲央行", "ECB", "德國", "法國", "英國", "英鎊", "英格蘭銀行", "STOXX", "歐盟"],
    "新興市場": ["新興市場", "印度", "巴西", "墨西哥", "拉丁美洲", "拉美", "南非", "土耳其", "阿根廷"],
    "全球": ["全球", "跨國", "世界經濟"],
}
THEMES = {
    "貨幣政策": ["聯準會", "Fed", "FOMC", "升息", "降息", "央行", "日銀", "歐洲央行", "點陣圖", "前瞻指引",
                 "貨幣政策", "縮表", "Rate Monitor"],
    "利率與債市": ["殖利率", "公債", "美債", "債市", "利差", "信用債", "OAS", "期限溢", "標售", "債券", "長債"],
    "通膨": ["通膨", "CPI", "PCE", "物價", "通縮"],
    "經濟成長": ["GDP", "經濟成長", "衰退", "非農", "失業", "勞動市場", "就業", "PMI", "景氣", "零售銷售"],
    "貿易與關稅": ["關稅", "貿易", "出口", "進口", "川習"],
    "供應鏈": ["供應鏈", "產能", "斷鏈", "在地化"],
    "關鍵礦產": ["稀土", "關鍵礦", "鋰", "鈷", "鎳", "銅價", "戰略礦"],
    "半導體與AI": ["半導體", "AI", "人工智慧", "晶片", "台積電", "輝達", "NVIDIA", "Nvidia", "資料中心",
                   "記憶體", "HBM", "光通訊", "伺服器", "算力", "費半", "大模型"],
    "金融業": ["銀行", "保險", "券商", "資產管理", "金融業", "私募", "創投", "投資銀行", "壽險"],
    "資本流動": ["資金流", "外資", "ETF", "流入", "流出", "資本流動", "匯率", "匯市", "美元指數", "套利交易"],
    "房地產": ["房地產", "房市", "地產", "房價", "REIT", "商用不動產"],
    "消費": ["消費", "零售", "電子商務", "電商", "消費者", "餐飲"],
    "地緣政治": ["地緣", "戰爭", "戰事", "中東", "荷莫茲", "伊朗", "以色列", "俄羅斯", "烏克蘭", "制裁",
                 "國防", "停火"],
    "政策與改革": ["財政", "監理", "改革", "選舉", "法案", "預算", "政府", "期中選舉", "產業政策"],
}


def _score(vocab: dict, lead: str, body: str) -> list[tuple[str, int]]:
    s = []
    for tag, words in vocab.items():
        n = sum(5 * lead.count(w) + body.count(w) for w in words)
        if n:
            s.append((tag, n))
    return sorted(s, key=lambda x: -x[1])


def pick_tags(lead: str, body: str) -> tuple[list[str], list[str]]:
    """Deterministic keyword tagging onto the fixed 區域／主題 lists."""
    reg = _score({k: v for k, v in REGIONS.items() if k != "全球"}, lead, body)
    top = reg[0][1] if reg else 0
    regions = [t for t, n in reg if n >= max(5, top * 0.25)][:3]
    strong = [t for t, n in reg if n >= max(5, top * 0.25)]
    if len(strong) >= 4 or any(w in lead for w in REGIONS["全球"]):
        regions = (["全球"] + regions)[:3]
    th = _score(THEMES, lead, body)
    ttop = th[0][1] if th else 0
    themes = [t for t, n in th if n >= max(5, ttop * 0.2)][:4]
    return regions, themes


def _flatten(x) -> str:
    if isinstance(x, dict):
        return "\n".join(_flatten(v) for v in x.values())
    if isinstance(x, list):
        return "\n".join(_flatten(v) for v in x)
    return str(x) if isinstance(x, str) else ""


def L(v):
    """Iterate a field that upstream sometimes ships as a list, sometimes as one string."""
    if isinstance(v, list):
        return v
    if v in (None, "", {}):
        return []
    return [v]


# --------------------------------------------------------------- generic ----

TITLE_KEYS = ("title", "name", "h", "t", "k", "label", "heading", "d", "id")


def _generic(key, val, level=3, mode="md") -> list[dict]:
    """Best-effort rendering of an unknown field."""
    out: list[dict] = []
    if val in (None, "", [], {}):
        return out
    if isinstance(val, str):
        out += para(f"**{key}**：{val}" if key else val, mode)
    elif isinstance(val, bool):
        pass  # machine flags (e.g. series_align) carry no reading value
    elif isinstance(val, (int, float)):
        out += meta(f"{key}：{val}")
    elif isinstance(val, list):
        if all(isinstance(v, str) for v in val):
            if key:
                out += heading(level, key)
            for v in val:
                out += bullet(v, mode)
        else:
            if key:
                out += heading(level, key)
            for v in val:
                if isinstance(v, dict):
                    tk = next((k for k in TITLE_KEYS if isinstance(v.get(k), str) and v.get(k)), None)
                    rest = "；".join(f"{k}：{plain(x, mode)}" for k, x in v.items()
                                    if k != tk and isinstance(x, (str, int, float))
                                    and not isinstance(x, bool) and str(x))
                    head = f"**{v[tk]}**" if tk else ""
                    out += bullet(f"{head}{'：' if head and rest else ''}{rest}", mode)
                    for k, x in v.items():
                        if isinstance(x, (list, dict)) and x:
                            out += _generic(k, x, min(level + 1, 3), mode)
                else:
                    out += _generic("", v, level, mode)
    elif isinstance(val, dict):
        if key:
            out += heading(level, key)
        for k, v in val.items():
            out += _generic(k, v, min(level + 1, 3), mode)
    return out


def _leftover(d: dict, known: set, skip: set, level=2, mode="md") -> list[dict]:
    out = []
    for k, v in d.items():
        if k in known or k in skip:
            continue
        out += _generic(k, v, level, mode)
    return out


def _props(title, system, date, issue, regions, themes, url):
    return {"title": title, "system": system, "date": date, "issue": issue,
            "regions": regions, "themes": themes, "url": url}


# -------------------------------------------------------------- advisory ----

def advisory(d: dict, repo: str, site: str):
    H = "html"
    b: list[dict] = []
    b += callout(d.get("headline", ""), "📰", H)
    w = d.get("window") or {}
    b += meta(f"{d.get('stamp', '')}｜卡片 {d.get('cards', '')} 張"
              + (f"｜窗口 {w.get('from', '')} → {w.get('to', '')}" if w else ""))
    b += link_para("在原站開啟這一期", f"{site}#{d['date']}")

    ov = d.get("overview") or {}
    b += heading(1, "總覽")
    if ov.get("snap"):
        b += heading(2, "市場快照")
        for s in L(ov["snap"]):
            b += bullet(f"**{s.get('k', '')}**：{s.get('v', '')}"
                        + (f"（{s['tone']}）" if s.get("tone") else ""), H)
    if ov.get("focus"):
        b += heading(2, "今日焦點")
        for f in L(ov["focus"]):
            b += heading(3, f.get("t") or f.get("k", ""), H)
            b += para(f.get("d") or f.get("v", ""), H)
            b += _leftover(f, {"t", "k", "d", "v"}, {"tag"}, 3, H)
    if ov.get("takeaways"):
        b += heading(2, ov.get("takeawaysTitle") or "重點")
        for t in L(ov["takeaways"]):
            b += numbered(t, H)
    if ov.get("thermo"):
        th = ov["thermo"]
        b += heading(2, f"市場溫度計：{th.get('level', '')}")
        b += para(th.get("note", ""), H)
    if ov.get("pulse"):
        b += heading(2, "各市場脈動")
        for p in L(ov["pulse"]):
            b += bullet(f"**{p.get('k', '')}**（{p.get('dir', '')}）：{p.get('note', '')}", H)
    if ov.get("watch"):
        b += heading(2, "觀察清單")
        for x in L(ov["watch"]):
            b += bullet(f"**{x.get('d', '')}**：{x.get('t', '')}", H)
    if ov.get("watchReview"):
        b += heading(2, "前期觀察回顧")
        for x in L(ov["watchReview"]):
            b += heading(3, f"{x.get('d', '')}【{x.get('verdict', '')}】", H)
            b += para(x.get("t", ""), H)
            if x.get("w"):
                b += para(x["w"], H)
            if x.get("note"):
                b += para(x["note"], H)
            b += _leftover(x, {"d", "verdict", "t", "w", "note"}, set(), 3, H)
    b += _leftover(ov, {"snap", "focus", "takeaways", "takeawaysTitle", "thermo", "pulse",
                        "watch", "watchReview"}, set(), 2, H)

    es = d.get("essay") or {}
    if es:
        b += divider()
        b += heading(1, es.get("title", "短評"), H)
        if es.get("kick"):
            b += quote(es["kick"], H)
        if es.get("by"):
            b += meta(es["by"])
        for p in L(es.get("paras")):
            b += para(p, H)

    for sec in L(d.get("sections")):
        b += divider()
        b += heading(1, f"{sec.get('title', '')}　{sec.get('en', '')}".strip(), H)
        if sec.get("intro"):
            b += para(sec["intro"], H)
        for g in L(sec.get("groups")):
            b += heading(2, g.get("label", ""), H)
            for c in L(g.get("cards")):
                deep = str(c.get("deep")).lower() == "true"
                b += heading(3, ("【深度】" if deep else "") + c.get("title", ""), H)
                b += meta("｜".join(str(x) for x in (c.get("src"), c.get("tag"), c.get("date"),
                                                     c.get("tone")) if x))
                b += para(c.get("body", ""), H)
                for bl in L(c.get("bullets")):
                    b += bullet(bl, H)
                b += link_para("原文連結", html.unescape(c.get("url") or ""))
                b += _leftover(c, {"src", "tag", "tagcls", "date", "ts", "title", "deep", "body",
                                   "bullets", "url", "tone"}, set(), 3, H)
            b += _leftover(g, {"label", "accent", "cards"}, set(), 3, H)
        b += _leftover(sec, {"id", "title", "en", "intro", "groups"}, set(), 2, H)

    ab = d.get("about") or {}
    if ab:
        b += divider()
        b += heading(1, "關於本期")
        for k, lab in (("timeliness", "時效"), ("run", "執行"), ("limits", "限制")):
            v = ab.get(k)
            if isinstance(v, dict):
                b += _generic(lab, v, 2, H)
            elif isinstance(v, list):
                b += para(f"**{lab}**", H)
                for x in v:
                    b += bullet(x, H)
            elif v:
                b += para(f"**{lab}**：{v}", H)
        for n in L(ab.get("notes")):
            b += _generic("", n, 2, H) if isinstance(n, (dict, list)) else bullet(n, H)
        b += _leftover(ab, {"timeliness", "run", "limits", "notes"}, set(), 2, H)
    b += _leftover(d, {"date", "weekday", "stamp", "headline", "window", "cards", "overview",
                       "essay", "sections", "about"}, {"keptDates"}, 1, H)

    lead = plain(d.get("headline", ""), H) + "\n" + "\n".join(plain(t, H) for t in L(ov.get("takeaways")))
    regions, themes = pick_tags(lead, plain(_flatten(d), H))
    title = plain(d.get("headline", ""), H)
    return _props(title, "投顧知識庫", d["date"], f"{d['date']}（{d.get('weekday', '')}）",
                  regions, themes, f"{site}#{d['date']}"), b


# ----------------------------------------------------------------- chart ----

CHART_SKIP = {"slug", "kind", "y_label", "y2_label", "y_fmt", "y2_fmt", "y_log", "zero_line",
              "series_spec", "series", "pts", "hi_pts", "files", "footer_lines", "option",
              "markers", "series_align",
              # plotted data of bar / band / matrix / gauge kinds — it is in the image
              "cats", "groups", "vals", "rows", "matrix", "band", "band_label", "x_label",
              "total_label", "pts_labels", "gauge"}


def chart(d: dict, repo: str, site: str):
    b: list[dict] = []
    if d.get("standfirst"):
        b += callout(d["standfirst"], "📈")
    w = d.get("window") or {}
    if w:
        b += meta(f"產出窗口 {w.get('from', '')} → {w.get('to', '')}")
        if w.get("note"):
            b += meta(f"資料時點：{w['note']}")
    b += link_para("在原站開啟", site)
    for i, c in enumerate(L(d.get("charts")), 1):
        b += divider()
        b += heading(2, f"{i}. {c.get('slot', '')}｜{c.get('title', '')}")
        b += meta("｜".join(x for x in (c.get("theme"), "、".join(L(c.get("tags")) or [])) if x))
        if c.get("subtitle"):
            b += para(c["subtitle"], italic=True)
        png = (c.get("files") or {}).get("png")
        if png:
            b += image(RAW.format(repo=repo, path=png), c.get("title"))
        if c.get("takeaway"):
            b += callout(f"**重點**：{c['takeaway']}", "💡")
        if c.get("reading"):
            b += heading(3, "解讀")
            b += para(c["reading"])
        if c.get("so_what"):
            b += heading(3, "所以呢")
            b += para(c["so_what"])
        if c.get("watch"):
            b += heading(3, "接下來看什麼")
            for x in L(c["watch"]):
                b += bullet(x)
        mk = c.get("markers") or []
        if mk:
            b += meta("圖上標記：" + "、".join(f"{m.get('date', '')} {m.get('label', '')}".strip()
                                              for m in mk if isinstance(m, dict)))
        if c.get("source"):
            b += meta(c["source"])
        if c.get("note"):
            b += meta(f"註：{c['note']}")
        pv = c.get("provenance") or {}
        if pv.get("computed"):
            b += meta(f"計算方式：{pv['computed']}")
        ib = pv.get("inspired_by") or {}
        if ib.get("cards"):
            b += meta("靈感來源（" + str(ib.get("source", "")) + "）：" + "；".join(ib["cards"]))
        IBK = ("source", "outlet", "publication", "who", "via", "title", "published")
        fields = [str(ib[k]) for k in IBK if ib.get(k) and not (k == "source" and ib.get("cards"))]
        if fields:
            b += meta("靈感來源：" + "｜".join(fields))
        if ib.get("url"):
            b += link_para(ib["url"], ib["url"])
        b += _leftover(ib, {"cards", "url", *IBK}, set(), 3)
        if pv.get("our_question"):
            b += meta(f"我們的問題：{pv['our_question']}")
        b += _leftover(pv, {"computed", "inspired_by", "our_question"}, set(), 3)
        b += _leftover(c, {"slot", "theme", "title", "subtitle", "takeaway", "reading", "so_what",
                           "watch", "tags", "source", "note", "provenance"}, CHART_SKIP, 3)
    ab = d.get("about") or {}
    if ab:
        b += divider()
        b += heading(1, "關於本期")
        for r in L(ab.get("run")) if isinstance(ab.get("run"), list) else [ab.get("run")]:
            if r:
                b += bullet(r)
        for q in L(ab.get("qa_dispositions")):
            b += bullet(f"**QA 判定（{q.get('category', '')}）** {q.get('key', '')}：{q.get('note', '')}")
        info = [f"{k}：{ab[k]}" for k in ("renderer_version", "rendered_at", "data_path") if ab.get(k)]
        if ab.get("upstream"):
            info.append("上游：" + "、".join(ab["upstream"]))
        if info:
            b += meta("｜".join(info))
        b += _leftover(ab, {"run", "qa_dispositions", "renderer_version", "rendered_at",
                            "data_path", "upstream"}, {"macro_release", "qa_flags"}, 2)
    b += _leftover(d, {"date", "weekday", "headline", "standfirst", "window", "charts", "about"},
                   set(), 1)
    lead = d.get("headline", "") + "\n" + d.get("standfirst", "") + "\n" + "\n".join(
        (c.get("theme", "") + " " + c.get("title", "")) for c in L(d.get("charts")))
    body = _flatten({k: v for k, v in d.items() if k != "charts"}) + "\n" + "\n".join(
        _flatten({k: v for k, v in c.items() if k not in CHART_SKIP}) for c in L(d.get("charts")))
    regions, themes = pick_tags(lead, body)
    return _props(d.get("headline", d["date"]), "每日五圖", d["date"],
                  f"{d['date']}（{d.get('weekday', '')}）", regions, themes, site), b


# --------------------------------------------------------------- podcast ----

def podcast(d: dict, repo: str, site: str):
    b: list[dict] = []
    eps = L(d.get("episodes"))
    cc = d.get("crossCut") or {}
    b += meta(f"{d.get('label', '')}｜{len(eps)} 集｜產出 {d.get('generatedAt', '')}")
    b += link_para("在原站開啟這一天", f"{site}#/{d['date']}")
    if cc:
        b += heading(1, cc.get("title") or "跨節目交叉觀察")
        b += md_blocks(cc.get("intro"))
        for p in L(cc.get("points")):
            b += heading(3, p.get("title", ""))
            b += md_blocks(p.get("body"))
        b += _leftover(cc, {"title", "intro", "points"}, set(), 2)
    ps = d.get("postscript") or {}
    if ps:
        b += heading(1, ps.get("title") or "觀察後記")
        for p in L(ps.get("paragraphs")):
            b += md_blocks(p)
        for o in L(ps.get("observations")):
            b += bullet(f"**【{o.get('status', '')}】**{o.get('text', '')}")
            if o.get("check"):
                b += para(f"　檢驗：{o['check']}", color="gray")
        b += _leftover(ps, {"title", "paragraphs", "observations"}, set(), 2)
    b += heading(1, "各集摘譯")
    for e in eps:
        b += divider()
        b += heading(2, e.get("title", ""))
        info = [x for x in (e.get("show"), e.get("published")) if x]
        b += meta("｜".join(info))
        if e.get("hosts"):
            b += meta(f"主持：{e['hosts']}")
        if e.get("guest"):
            b += meta(f"來賓：{e['guest']}")
        for m in L(e.get("meta")):
            b += meta(f"{m.get('k', '')}：{m.get('v', '')}")
        b += link_para("節目連結", e.get("url"))
        if e.get("summary"):
            b += callout(e["summary"], "🎧")
        if e.get("takeaways"):
            b += heading(3, "核心重點")
            for t in L(e["takeaways"]):
                if isinstance(t, dict):
                    lab = f"{t['label']}｜" if t.get("label") else ""
                    b += numbered(f"**{lab}{t.get('title', '')}**　{t.get('body') or t.get('detail') or ''}")
                    b += _leftover(t, {"label", "title", "body", "detail"}, set(), 3)
                else:
                    b += numbered(t)
        for s in L(e.get("sections")):
            b += heading(3, s.get("heading") or s.get("title", ""))
            for p in L(s.get("paragraphs")):
                b += md_blocks(p)
            b += _leftover(s, {"heading", "title", "paragraphs"}, set(), 3)
        if e.get("quotes"):
            b += heading(3, "金句")
            for q in L(e["quotes"]):
                rt = rich(f"「{q.get('text', '')}」—— {q.get('by', '')}")
                if q.get("original"):
                    rt += rich("\n" + q["original"], "plain", italic=True, color="gray")
                b += quote_rt(rt)
        qa = e.get("quality") or {}
        src = [f"來源：{e['source']}"] if e.get("source") else []
        if qa:
            src.append(f"品質：{qa.get('status', '')}（completeness {qa.get('completeness', '')}）")
            for k in ("speakerNote", "timestampNote"):
                if qa.get(k):
                    src.append(qa[k])
        for s in src:
            b += meta(s)
        b += _leftover(e, {"title", "show", "published", "hosts", "guest", "meta", "url", "summary",
                           "takeaways", "sections", "quotes", "quality", "source"},
                       {"id", "trackId", "showKey", "minutes", "chars", "guests", "topics"}, 3)
    b += _leftover(d, {"date", "label", "generatedAt", "crossCut", "postscript", "episodes"}, set(), 1)
    pts = L(cc.get("points"))
    head = pts[0]["title"] if pts and pts[0].get("title") else "、".join(
        dict.fromkeys(e.get("show", "") for e in eps))
    title = f"{len(eps)} 集｜{plain(head)}"
    lead = plain(_flatten(cc)) + "\n" + "\n".join(
        "、".join(L(e.get("topics")) or []) + e.get("title", "") for e in eps)
    regions, themes = pick_tags(lead, plain(_flatten(d)))
    return _props(title, "Podcast 摘譯", d["date"], d.get("label", d["date"]), regions, themes,
                  f"{site}#/{d['date']}"), b


# ----------------------------------------------------------- convergence ----

def convergence(d: dict, repo: str, site: str):
    H = "html"
    b: list[dict] = []
    b += callout(d.get("headline", ""), "🧭", H)
    rg = d.get("range") or {}
    if d.get("stamp"):
        b += meta(d["stamp"])
    b += meta(f"{d.get('label', '')}｜量化區間 {rg.get('quant', '')}｜敘事區間 {rg.get('narrative', '')}")
    b += link_para("在原站開啟這一期", f"{site}#{d['date']}")
    if d.get("coverage"):
        b += heading(2, "本期資料覆蓋")
        for c in L(d["coverage"]):
            b += bullet(f"**{c.get('k', '')}**：{c.get('v', '')}", H)
    if d.get("verdict"):
        b += heading(1, "本期判斷")
        for v in L(d["verdict"]):
            b += bullet(v, H)
    q = d.get("quant") or {}
    if q:
        b += heading(1, "量化面")
        b += para(f"**綜合分數 {q.get('composite', '')}**　{q.get('zone', '')}", H)
        if q.get("note"):
            b += para(q["note"], H)
        st = q.get("stage") or {}
        if st:
            b += bullet(f"**階段**：{st.get('current', '')}　{st.get('label', '')}（點亮 {st.get('lit', '')}）"
                        + (f"——{st['delta']}" if st.get("delta") else ""), H)
        if q.get("twHeat") not in (None, ""):
            b += bullet(f"**台股熱度**：{q['twHeat']}", H)
        qd = q.get("quadrant") or {}
        if qd:
            b += bullet(f"**象限**：{qd.get('regime', '')}（熱度 {qd.get('heat', '')}／支撐 {qd.get('support', '')}）", H)
        if q.get("dims"):
            b += heading(3, "三層分數")
            for x in L(q["dims"]):
                b += bullet(f"**{x.get('id', '')} {x.get('name', '')}**（權重 {x.get('w', '')}）"
                            f"{x.get('v', '')}，變動 {x.get('delta', '')}：{x.get('note', '')}", H)
        if q.get("triggers"):
            b += heading(3, "觸發器")
            for t in L(q["triggers"]):
                lit = "🔴 點亮" if str(t.get("state")) == "1" else "⚪ 未點亮"
                b += bullet(f"{lit}　**{t.get('name', '')}**：{t.get('value', '')}（{t.get('asof', '')}）", H)
        co = q.get("callout") or {}
        if co:
            b += callout(f"**{co.get('h', '')}**\n{co.get('body', '')}", "⚠️", H)
        b += _leftover(q, {"composite", "zone", "note", "stage", "twHeat", "quadrant", "dims",
                           "triggers", "callout"}, {"schemaVer"}, 3, H)
    for s in L(d.get("sections")):
        b += divider()
        b += heading(1, s.get("title", ""), H)
        if s.get("lede"):
            b += para(s["lede"], H, italic=True)
        for it in L(s.get("items")):
            tags = "、".join(t.get("t", "") for t in L(it.get("tags")) if isinstance(t, dict))
            b += heading(2, ("🔥 " if str(it.get("hot")).lower() == "true" else "") + it.get("title", ""), H)
            if tags:
                b += meta(tags)
            body = it.get("body")
            for p in body if isinstance(body, list) else [body]:
                if p:
                    b += para(p, H)
            if it.get("evidence"):
                b += heading(3, "證據")
                for e in L(it["evidence"]):
                    b += bullet(f"**{e.get('d', '')}｜{e.get('s', '')}**：{e.get('t', '')}", H)
            call = it.get("call") or {}
            if call:
                b += callout(f"**{call.get('h', '')}**：{call.get('body', '')}", "🎯", H)
            b += _leftover(it, {"hot", "tags", "title", "body", "evidence", "call"}, set(), 3, H)
        b += _leftover(s, {"id", "title", "lede", "items"}, set(), 2, H)
    if d.get("watch"):
        b += heading(1, "觀察清單")
        for x in L(d["watch"]):
            b += bullet(x, H)
    calls = d.get("calls") or {}
    if calls:
        b += heading(1, "預測帳本")
        if calls.get("open"):
            b += heading(2, "新開／持續中的預測")
            for c in L(calls["open"]):
                b += bullet(f"**{c.get('id', '')}**（{c.get('kind', '')}）{c.get('claim', '')}"
                            f"　裁判：{c.get('judge', '')}；期限 {c.get('deadline', '')}", H)
        if calls.get("close"):
            b += heading(2, "本期結算")
            for c in L(calls["close"]):
                b += bullet(f"**{c.get('id', '')} → {c.get('result', '')}**：{c.get('note', '')}", H)
        b += _leftover(calls, {"open", "close"}, set(), 2, H)
    if d.get("rulings"):
        b += heading(2, "裁決")
        for r in L(d["rulings"]):
            b += bullet(f"**{r.get('id', '')}　{r.get('result', '')}**：{r.get('why', '')}", H)
    if d.get("feedback"):
        b += _generic("回饋", d["feedback"], 1, H)
    if d.get("gaps"):
        b += heading(1, "缺口與限制")
        for g in L(d["gaps"]):
            b += bullet(g, H)
    ab = d.get("about") or {}
    if ab:
        b += divider()
        b += heading(1, "關於本期")
        for k, lab in (("run", "執行"), ("method", "方法")):
            if ab.get(k):
                b += para(f"**{lab}**：{ab[k]}", H)
        b += _leftover(ab, {"run", "method"}, set(), 2, H)
    b += _leftover(d, {"date", "issue", "label", "stamp", "range", "headline", "coverage", "verdict",
                       "quant", "sections", "watch", "calls", "rulings", "feedback", "gaps",
                       "about"}, {"schemaVer"}, 1, H)
    lead = plain(d.get("headline", ""), H) + "\n" + "\n".join(plain(v, H) for v in L(d.get("verdict")))
    regions, themes = pick_tags(lead, plain(_flatten(d), H))
    issue = f"第 {int(d.get('issue', 0)):03d} 期" if str(d.get("issue", "")).isdigit() else d.get("label", "")
    return _props(f"{issue}｜{plain(d.get('headline', ''), H)}", "主題匯流訊號報", d["date"],
                  issue, regions, themes, f"{site}#{d['date']}"), b


# ---------------------------------------------------------------- broker ----

def broker(d: dict, repo: str, site: str):
    b: list[dict] = []
    wk = d.get("week", "")
    rg = d.get("range") or ["", ""]
    reps = L(d.get("reports"))
    brokers = d.get("brokers") or {}
    b += meta(f"{wk}｜{rg[0]} – {rg[-1]}｜共 {d.get('reports_count', len(reps))} 份："
              + "、".join(f"{k} {v}" for k, v in brokers.items()))
    b += link_para("在原站開啟這一週", f"{site}#/w/{wk}")
    if d.get("crosscut"):
        b += heading(1, "本週交叉觀察")
        b += md_blocks(d["crosscut"], heading_base=2)
    if d.get("watch"):
        b += heading(1, "觀察清單")
        for x in L(d["watch"]):
            b += bullet(x)
    b += heading(1, "各份報告")
    for r in sorted(reps, key=lambda r: (r.get("date", ""), r.get("broker", ""))):
        b += divider()
        b += heading(2, f"{r.get('broker', '')}｜{r.get('title', '')}")
        info = [r.get("date", ""), f"{r.get('pages', '')} 頁" if r.get("pages") else ""]
        if r.get("issue") not in (None, "", "None"):
            info.append(f"期號 {r['issue']}")
        if r.get("tags"):
            info.append("、".join(r["tags"]))
        b += meta("｜".join(x for x in info if x))
        if r.get("summary"):
            b += md_blocks(r["summary"], heading_base=3)
        if r.get("stances"):
            b += heading(3, "分析師原句")
            for s in L(r["stances"]):
                rt = rich(s.get("quote_zh") or s.get("quote", ""))
                tail = []
                if s.get("theme"):
                    tail.append(s["theme"])
                if s.get("page") not in (None, "", "None"):
                    tail.append(f"p.{s['page']}")
                if s.get("label") not in (None, "", "None"):
                    tail.append(str(s["label"]))
                if s.get("quote") and s.get("quote_zh"):
                    rt += rich("\n" + s["quote"], "plain", italic=True, color="gray")
                if tail:
                    rt += rich("\n（" + "｜".join(tail) + "）", "plain", color="gray")
                b += quote_rt(rt)
        for c in L(r.get("charts")):
            if c.get("png"):
                b += image(RAW.format(repo=repo, path=f"charts/{wk}/{c['png']}"),
                           "｜".join(x for x in (c.get("title"), c.get("subtitle")) if x))
            if c.get("source"):
                b += meta(c["source"])
            names = [x.get("name") for x in L(c.get("series")) if isinstance(x, dict) and x.get("name")]
            if names:
                b += meta("圖中序列：" + "、".join(names))
            b += _leftover(c, {"png", "title", "subtitle", "source"},
                           CHART_SKIP | {"grounding", "svg", "bytes", "values", "x", "y"}, 3)
        b += _leftover(r, {"broker", "title", "date", "pages", "issue", "tags", "summary", "stances",
                           "charts"}, {"slug", "product", "title_source", "title_confident",
                                       "tier_target", "tier_band", "summary_chars"}, 3)
    if d.get("notes"):
        b += heading(1, "編輯註記")
        for n in L(d["notes"]):
            b += bullet(n)
    b += _leftover(d, {"week", "range", "reports_count", "brokers", "crosscut", "watch", "reports",
                       "notes", "date"}, {"tags", "assembled_at"}, 1)
    cross = d.get("crosscut", "") or ""
    m = re.search(r"\*\*[一二三四五六七八九十][、.．]\s*(.+?)\*\*", cross)
    head = plain(m.group(1)) if m else f"{len(reps)} 份外資報告"
    tagtext = "、".join(d.get("tags", {}).keys()) if isinstance(d.get("tags"), dict) else ""
    lead = plain(cross) + "\n" + tagtext
    regions, themes = pick_tags(lead, plain(_flatten({k: v for k, v in d.items() if k != "tags"})))
    return _props(f"{wk}｜{head}", "外資報告週摘", d.get("date") or rg[-1], wk, regions, themes,
                  f"{site}#/w/{wk}"), b


RENDERERS = {"advisory": advisory, "chart": chart, "podcast": podcast,
             "convergence": convergence, "broker": broker}
