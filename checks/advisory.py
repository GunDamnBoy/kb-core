"""投顧知識庫的檢查。

payload 形狀（由 `tools/advisory_verify.py` 組出來，檢查本身不做 IO）：

    {"doc":     當日的 data/<date>.json,
     "prev":    前一版的 doc（沒有前一版就 None）,
     "anchors": advisory/anchors.json 讀進來的 dict,
     "now":     ISO8601}

## 數字一個都不寫在這裡

門檻全部從 `anchors` 讀。這是單錨的執行面：`anchors.json` 是唯一的家，
檢查程式是它的**讀者**而不是第二份副本。

舊系統的頭號血淚正是反過來做的——一般卡字數同時活在 brief §4、`check.py`、
排程 prompt 第 5 步，收斂只收一半，隔天照樣漂移（2026-08-17 中位 504 → 8-18 中位 441）。

## 保底卡的 `base` 欄位

2026-08-19 寫這一檔時發現的洞：BRIEF 說「保底數據卡缺席」是機械可判的當期失敗，
但當時 schema 沒有任何欄位認得出哪張是保底卡。**一條判準若在資料裡找不到對應的欄位，
它就不是機械可判的，只是看起來像。**
"""
import datetime as dt
import re

from kbcore.check import Check, fail, ok, register, skipped, warn

TPE = dt.timezone(dt.timedelta(hours=8))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 明顯不是單篇文章的路徑形態。寧可漏判也不要誤判——誤判會擋掉一張好卡，
# 而漏判只是少抓到一個壞連結，下游還有人眼。
LISTING_RE = re.compile(
    r"^/?$|/(markets|topics?|tag|tags|category|categories|section|sections|"
    r"latest|news)/?$", re.I)


def _A(p, *path):
    """從 anchors 取值。取不到就讓它 KeyError——**門檻取不到是設定壞了，不是資料壞了**，
    安靜地跳過會讓這條檢查變成永遠 PASS。"""
    cur = p["anchors"]
    for k in path:
        cur = cur[k]
    return cur


def _cards(doc):
    for sec in doc.get("sections") or []:
        for g in sec.get("groups") or []:
            for c in g.get("cards") or []:
                yield g.get("label"), c


def _is_weekend(p):
    d = dt.datetime.fromisoformat(p["doc"]["window"]["from"]).astimezone(TPE)
    return d.weekday() >= 5


def _mode(p):
    return "weekend" if _is_weekend(p) else "weekday"


# ── 1. 組名逐字相符 ──────────────────────────────────────────────────
def _group_names(p):
    """分組名對不上就沒有任何後續檢查有意義——它會讓下限比對整組落空。

    舊規格自己警告過「全形括號與頓號差一個字就會被判分組名不在表內」，
    而它自己的下限表與 QUOTA 表就有兩處對不上（2026-08-19 重寫時發現）。
    """
    known = {g["name"] for g in _A(p, "groups")}
    seen = {label for label, _ in _cards(p["doc"])}
    stray = sorted(seen - known)
    if stray:
        return fail(f"分組名不在 anchors 裡：{'、'.join(stray)} —— 逐字相符，含全形括號與頓號")
    missing = sorted(known - seen)
    if missing:
        return fail(f"{len(missing)} 組完全沒有卡片：{'、'.join(missing[:5])}")
    return ok()


register(Check(
    id="advisory.group_names",
    covers="十五組全部出現，且組名與 anchors.json 逐字相符",
    blind_to=[
        "組名對但卡片被歸錯組（機器分不出一則新聞該屬於哪一組）",
        "anchors 裡的組名本身訂錯",
    ],
    run=_group_names,
    fixture={"anchors": {"groups": [{"name": "台灣"}]},
             "doc": {"sections": [{"groups": [{"label": "臺灣", "cards": [{}]}]}]}},
    no_boundary="組名相符或不相符，逐字比對沒有中間狀態",
    suite="advisory",
))


# ── 2. 每一組達到下限 ────────────────────────────────────────────────
def _floors(p):
    mode = _mode(p)
    got = {}
    for label, _ in _cards(p["doc"]):
        got[label] = got.get(label, 0) + 1
    short = [(g["name"], got.get(g["name"], 0), g["floor"][mode])
             for g in _A(p, "groups") if got.get(g["name"], 0) < g["floor"][mode]]
    if short:
        detail = "、".join(f"{n} {c}/{f}" for n, c, f in short)
        return fail(f"{len(short)} 組低於下限（{mode}）：{detail}")
    return ok()


register(Check(
    id="advisory.group_floors",
    covers="每一組的卡片數達到它在 anchors.json 的下限（依週末模式取值）",
    blind_to=[
        "則數達標但內容注水",
        "則數達標但全部來自同一家來源",
        "某一組超收很多、掩蓋了它其實只有一個題材",
    ],
    run=_floors,
    fixture={"anchors": {"groups": [{"name": "台灣", "floor": {"weekday": 10, "weekend": 10}}]},
             "doc": {"window": {"from": "2026-08-18T07:00:00+08:00"},
                     "sections": [{"groups": [{"label": "台灣", "cards": [{}] * 9}]}]}},
    near_miss={"anchors": {"groups": [{"name": "台灣", "floor": {"weekday": 10, "weekend": 10}}]},
               "doc": {"window": {"from": "2026-08-18T07:00:00+08:00"},
                       "sections": [{"groups": [{"label": "台灣", "cards": [{}] * 10}]}]}},
    suite="advisory",
))


# ── 3. 全站則數 ──────────────────────────────────────────────────────
def _site_total(p):
    lo, hi = _A(p, "site_total", _mode(p))
    n = sum(1 for _ in _cards(p["doc"]))
    if n < lo:
        return fail(f"全站 {n} 則，低於 {lo}")
    if n > hi:
        return warn(f"全站 {n} 則，高於 {hi} —— 加量很貴，先確認不是灌水")
    return ok()


register(Check(
    id="advisory.site_total",
    covers="全站卡片數落在 anchors.json 的 site_total 區間內",
    blind_to=[
        "總數合格但分布極不平均",
        "總數合格但其中有一批是同一篇彙整文章拆出來的",
    ],
    run=_site_total,
    fixture={"anchors": {"site_total": {"weekday": [95, 125], "weekend": [80, 125]}},
             "doc": {"window": {"from": "2026-08-18T07:00:00+08:00"},
                     "sections": [{"groups": [{"label": "x", "cards": [{}] * 94}]}]}},
    near_miss={"anchors": {"site_total": {"weekday": [95, 125], "weekend": [80, 125]}},
               "doc": {"window": {"from": "2026-08-18T07:00:00+08:00"},
                       "sections": [{"groups": [{"label": "x", "cards": [{}] * 95}]}]}},
    suite="advisory",
))


# ── 4. ts 格式與必填 ─────────────────────────────────────────────────
def _ts_wellformed(p):
    bad = []
    for label, c in _cards(p["doc"]):
        ts = c.get("ts")
        if not ts:
            bad.append(f"{c.get('title', '?')[:12]}（缺）")
            continue
        try:
            d = dt.datetime.fromisoformat(ts)
        except ValueError:
            bad.append(f"{c.get('title', '?')[:12]}（壞）")
            continue
        if d.tzinfo is None:
            bad.append(f"{c.get('title', '?')[:12]}（無時區）")
    if bad:
        return fail(f"{len(bad)} 張卡的 ts 有問題：{'、'.join(bad[:5])}")
    return ok()


register(Check(
    id="advisory.ts_wellformed",
    covers="每張卡都有可解析、帶時區的 ts",
    blind_to=[
        "ts 格式合法但換算錯了時區（+08:00 標對、值卻是當地時間）",
        "ts 是從列表頁的相對時間估出來的",
    ],
    run=_ts_wellformed,
    fixture={"doc": {"sections": [{"groups": [{"label": "x", "cards": [{"title": "無時區", "ts": "2026-08-19T10:00:00"}]}]}]}},
    no_boundary="可解析或不可解析，沒有中間狀態",
    suite="advisory",
))


# ── 5. ts 落在窗口內 ─────────────────────────────────────────────────
def _ts_in_window(p):
    w = p["doc"]["window"]
    lo, hi = dt.datetime.fromisoformat(w["from"]), dt.datetime.fromisoformat(w["to"])
    early, future = [], []
    for _, c in _cards(p["doc"]):
        try:
            t = dt.datetime.fromisoformat(c["ts"])
        except (KeyError, ValueError, TypeError):
            continue  # 交給 ts_wellformed 說話，這裡不重複報
        if t.tzinfo is None:
            continue
        if t < lo:
            early.append(c.get("title", "?")[:12])
        if t > hi:
            future.append(c.get("title", "?")[:12])
    if future:
        return fail(f"{len(future)} 張卡的 ts 晚於 window.to：{'、'.join(future[:5])}"
                    " —— 通常是時區換算錯了")
    if early:
        return fail(f"{len(early)} 張卡早於窗口起點：{'、'.join(early[:5])}")
    return ok()


register(Check(
    id="advisory.ts_in_window",
    covers="每張卡的 ts 落在 window 的兩端之間",
    blind_to=[
        "ts 在窗口內但那是轉載時間、不是原始發布時間",
        "窗口本身被設錯（起點不是前一日台北 07:00）",
    ],
    run=_ts_in_window,
    fixture={"doc": {"window": {"from": "2026-08-18T07:00:00+08:00", "to": "2026-08-19T11:00:00+08:00"},
                     "sections": [{"groups": [{"label": "x", "cards": [
                         {"title": "太早", "ts": "2026-08-18T06:59:00+08:00"}]}]}]}},
    near_miss={"doc": {"window": {"from": "2026-08-18T07:00:00+08:00", "to": "2026-08-19T11:00:00+08:00"},
                       "sections": [{"groups": [{"label": "x", "cards": [
                           {"title": "剛好", "ts": "2026-08-18T07:00:00+08:00"}]}]}]}},
    suite="advisory",
))


# ── 6. date 與 ts 的台北日期一致 ─────────────────────────────────────
def _date_ts_consistent(p):
    bad = []
    for _, c in _cards(p["doc"]):
        d, ts = c.get("date"), c.get("ts")
        if not d or not ts:
            continue
        try:
            t = dt.datetime.fromisoformat(ts).astimezone(TPE)
        except (ValueError, TypeError):
            continue
        if d.replace("/", "-") != t.date().isoformat():
            bad.append(f"{c.get('title', '?')[:10]} date={d} ts={t.date()}")
    if bad:
        return fail(f"{len(bad)} 張卡的 date 與 ts 對不上：{'；'.join(bad[:3])}")
    return ok()


register(Check(
    id="advisory.date_ts_consistent",
    covers="每張卡的 date 等於它 ts 的台北日期",
    blind_to=["兩者一致但都錯"],
    run=_date_ts_consistent,
    fixture={"doc": {"sections": [{"groups": [{"label": "x", "cards": [
        {"title": "對不上", "date": "2026/08/19", "ts": "2026-08-18T10:00:00+08:00"}]}]}]}},
    no_boundary="日期相等或不相等，沒有中間狀態",
    suite="advisory",
))


# ── 7. 跨版去重 ──────────────────────────────────────────────────────
def _cross_version_dupe(p):
    """跨版去重是 24 小時窗口的執行面。少了它，窗口就只是一句宣告——而且沒有人會發現。"""
    prev = p.get("prev")
    if prev is None:
        return skipped("沒有前一版，第一天無從比較")
    exempt = set(_A(p, "dedup_exempt"))
    old = {c.get("url") for _, c in _cards(prev) if c.get("url")}
    dupe = [c.get("url") for _, c in _cards(p["doc"])
            if c.get("url") in old and c.get("url") not in exempt]
    if dupe:
        return fail(f"{len(dupe)} 張卡與前一版共用原文連結：{dupe[0]} …"
                    " —— 每一張卡都該是今天新採的")
    return ok()


register(Check(
    id="advisory.cross_version_dedup",
    covers="沒有任何卡片與前一版共用原文連結（豁免清單在 anchors 的 dedup_exempt）",
    blind_to=[
        "連結不同但講的是同一件事（改寫過的同一篇）",
        "與前兩版重複（只比前一版）",
        "同一版內部重複",
    ],
    run=_cross_version_dupe,
    fixture={"anchors": {"dedup_exempt": []},
             "prev": {"sections": [{"groups": [{"label": "x", "cards": [{"url": "https://a/1"}]}]}]},
             "doc": {"sections": [{"groups": [{"label": "x", "cards": [{"url": "https://a/1"}]}]}]}},
    no_boundary="連結相同或不同，集合比對沒有中間狀態",
    suite="advisory",
))


# ── 8. url 是單篇文章 ────────────────────────────────────────────────
def _url_is_article(p):
    """讀者隔天點進去要看得到卡片描述的那件事。列表頁、指數頁做不到這件事。

    2026-08-02、08-03 兩版都出現 `bloomberg.com/markets/stocks` 被當成原文連結——
    那是即時指數頁，隔天點進去看到的是完全不同的內容，**等於沒有出處**。
    """
    bad = []
    for _, c in _cards(p["doc"]):
        u = c.get("url") or ""
        m = re.match(r"^https?://[^/]+(/.*)?$", u)
        if not m:
            bad.append(u or "（空）")
            continue
        path = m.group(1) or "/"
        if LISTING_RE.match(path):
            bad.append(u)
    if bad:
        return fail(f"{len(bad)} 張卡的 url 看起來是列表頁或首頁：{'、'.join(bad[:3])}")
    return ok()


register(Check(
    id="advisory.url_is_article",
    covers="每張卡的 url 是單篇文章的永久連結，不是列表頁、指數頁或首頁",
    blind_to=[
        "路徑看起來像文章但其實是列表（形態判斷只認得明顯的那幾種）",
        "是單篇文章但連到錯的那一篇",
        "連結今天有效、下個月失效",
    ],
    run=_url_is_article,
    fixture={"doc": {"sections": [{"groups": [{"label": "x", "cards": [
        {"url": "https://www.bloomberg.com/markets"}]}]}]}},
    near_miss={"doc": {"sections": [{"groups": [{"label": "x", "cards": [
        {"url": "https://www.bloomberg.com/markets/stocks/2026-08-19-abc"}]}]}]}},
    suite="advisory",
))


# ── 9. 保底數據卡 ────────────────────────────────────────────────────
def _base_cards(p):
    need = set(_A(p, "base_card_groups"))
    got = {label for label, c in _cards(p["doc"]) if c.get("base")}
    missing = sorted(need - got)
    if missing:
        return fail(f"{'、'.join(missing)} 沒有標 base 的保底數據卡 ——"
                    " 保底卡的價值在跨期序列，缺一天就是序列斷點")
    return ok()


register(Check(
    id="advisory.base_cards",
    covers="anchors 的 base_card_groups 每一組都有至少一張 base:true 的卡",
    blind_to=[
        "有標 base 但數字沒更新（跟昨天一樣）",
        "有標 base 但那是新聞不是數據",
        "標了 base 的卡缺少跨期比較（只有當日值、沒有變動幅度）",
    ],
    run=_base_cards,
    fixture={"anchors": {"base_card_groups": ["信用債", "黃金"]},
             "doc": {"sections": [{"groups": [{"label": "信用債", "cards": [{"base": True}]}]}]}},
    no_boundary="有或沒有，不是連續量",
    suite="advisory",
))


# ── 10. watchReview 有回答 ───────────────────────────────────────────
def _watch_review(p):
    """拋出去的預測要回頭對答案——這是本站與一般新聞摘要的分水嶺。

    「全部未決」在資料上跟「有認真判」長得一樣，所以它要被具名擋下來。
    """
    # 第一天沒有前一版，就沒有任何 watch 可以回顧。**這是具名的「跑不了」，
    # 不是 PASS 也不是 FAIL** —— 判成 PASS 會讓「認真回顧了」與「沒東西可回顧」
    # 長得一樣；判成 FAIL 會讓第一天永遠發不出去。
    if p.get("prev") is None:
        return skipped("第一天沒有前一版的 watch 可回顧")
    wr = (p["doc"].get("overview") or {}).get("watchReview")
    if wr is None:
        return fail("沒有 watchReview —— 拋出去的預測要回頭對答案")
    if not wr:
        return fail("watchReview 是空的")
    allowed = set(_A(p, "fixed_structure", "watch_review_verdicts"))
    verdicts = [x.get("verdict") for x in wr]
    strays = sorted({v for v in verdicts if v not in allowed})
    if strays:
        return fail(f"verdict 值域外：{'、'.join(map(str, strays))}")
    undecided = [v for v in verdicts if v == "未決"]
    if len(undecided) == len(verdicts):
        return fail(f"{len(verdicts)} 條全部「未決」—— 整天都未決等於沒有回答")
    return ok()


register(Check(
    id="advisory.watch_review",
    covers="watchReview 存在、verdict 在值域內、且不是整批未決",
    blind_to=[
        "有判但判得敷衍",
        "只回顧了容易判的那幾條、避開難的",
        "回顧的不是前幾天真的丟出去的那些 watch",
        "第一天整條檢查跳過——那天的 watchReview 品質沒有任何機制看著",
    ],
    run=_watch_review,
    fixture={"anchors": {"fixed_structure": {"watch_review_verdicts": ["應驗", "落空", "未決"]}},
             "prev": {}, "doc": {"overview": {"watchReview": [{"verdict": "未決"},
                                                              {"verdict": "未決"}]}}},
    near_miss={"anchors": {"fixed_structure": {"watch_review_verdicts": ["應驗", "落空", "未決"]}},
               "prev": {}, "doc": {"overview": {"watchReview": [{"verdict": "未決"},
                                                                {"verdict": "應驗"}]}}},
    suite="advisory",
))


# ── 11. 三分鐘總覽的固定結構 ─────────────────────────────────────────
def _fixed_structure(p):
    fs, ov = _A(p, "fixed_structure"), p["doc"].get("overview") or {}
    bad = []
    for key, want in (("snap", "snap_cells"), ("focus", "focus_cards"),
                      ("takeaways", "takeaways"), ("pulse", "pulse_entries")):
        n = len(ov.get(key) or [])
        if n != fs[want]:
            bad.append(f"{key} {n}（應為 {fs[want]}）")
    keys = [x.get("k") for x in (ov.get("pulse") or [])]
    if keys and keys != fs["pulse_keys"]:
        bad.append(f"pulse 鍵名或順序不符：{keys}")
    # `dir` 與卡片的 `tone` 共用同一個值域（見 anchors 的 _pulse_dir_shares_tone）。
    # 先前這裡沒有驗過 dir —— 值域寫在 anchors 但沒有讀者，等於沒有訂。
    tones = _A(p, "card_vocab", "tone")
    off = [f"{x.get('k')}＝{x.get('dir')!r}" for x in (ov.get("pulse") or [])
           if x.get("dir") not in tones]
    if off:
        bad.append(f"pulse 的 dir 不在值域 {tones}：{'、'.join(off)}")
    lvl = (ov.get("thermo") or {}).get("level")
    if not (isinstance(lvl, str) and lvl.isdigit() and 0 <= int(lvl) <= 100):
        bad.append(f"thermo.level 不是 0–100 的整數字串：{lvl!r}")
    if bad:
        return fail("；".join(bad))
    return ok()


register(Check(
    id="advisory.fixed_structure",
    covers="snap／focus／takeaways／pulse 的數量、pulse 的鍵名順序、thermo.level 的形態",
    blind_to=[
        "數量對但內容空洞",
        "thermo 是合法整數但與當天實況無關",
        "pulse 的 dir 天天翻轉",
    ],
    run=_fixed_structure,
    fixture={"anchors": {"card_vocab": {"tone": ["偏多", "中性", "偏空"]},
                         "fixed_structure": {"snap_cells": 6, "focus_cards": 4, "takeaways": 7,
                                             "pulse_entries": 5, "pulse_keys": []}},
             "doc": {"overview": {"thermo": {"level": "偏熱"}}}},
    no_boundary="數量與形態是離散的；thermo 的 0–100 邊界由值域比對涵蓋",
    suite="advisory",
))


# ── 12. 卡片長度（只警告，不擋） ─────────────────────────────────────
def _lengths(p):
    """字數是品質指標不是正確性指標——**為了湊字數注水比超標更糟**，所以它只警告。

    但它要印出中位數與分布，因為 2026-08-17 的字數事故正是靠中位數才看見的
    （平均值被少數長卡拉高，看起來正常）。
    """
    L = _A(p, "lengths")
    reg, deep = [], []
    for _, c in _cards(p["doc"]):
        n = len(c.get("body") or "") + sum(len(b) for b in (c.get("bullets") or []))
        (deep if c.get("deep") else reg).append(n)
    if not reg and not deep:
        return skipped("沒有卡片可量")
    msgs = []
    for name, xs, lo_hi in (("一般卡", reg, L["regular_card"]), ("深度卡", deep, L["deep_card"])):
        if not xs:
            continue
        xs = sorted(xs)
        med = xs[len(xs) // 2]
        under = sum(1 for x in xs if x < lo_hi[0])
        over = sum(1 for x in xs if x > lo_hi[1])
        msgs.append(f"{name} {len(xs)} 張、中位 {med}、低於下限 {under}、高於上限 {over}")
    detail = "；".join(msgs)
    n_deep = len(deep)
    lo, hi = L["deep_card_count"]
    if not (lo <= n_deep <= hi):
        return warn(f"{detail}；深度卡 {n_deep} 張不在 {lo}–{hi}")
    if any("低於下限 0" not in m and "低於下限" in m and
           int(m.split("低於下限 ")[1].split("、")[0]) > 0 for m in msgs):
        return warn(detail)
    return ok(detail)


register(Check(
    id="advisory.card_lengths",
    covers="一般卡與深度卡的長度分布、深度卡張數（只警告，不影響退出碼）",
    blind_to=[
        "字數合格但內容是注水",
        "中位數合格但分布有雙峰",
        "深度卡張數合格但都集中在同一組",
    ],
    run=_lengths,
    fixture={"anchors": {"lengths": {"regular_card": [550, 900], "deep_card": [900, 1300],
                                     "deep_card_count": [6, 8]}},
             "doc": {"sections": [{"groups": [{"label": "x", "cards": [
                 {"body": "字" * 100, "bullets": []}]}]}]}},
    no_boundary="它刻意只回 WARN／PASS，邊界的意義在印出來的分布而不在門檻",
    suite="advisory",
))


# ── 13. index entry 的來源欄位 ───────────────────────────────────────
def _index_source(p):
    """index.json 是系統的跨日記憶；這條檢查看的是「當日的 doc 供不供得出它」。

    2026-08-19 首日 publish 只把 date 與 file 寫進 index，那五個跨日欄位全空，
    而**當天沒有任何檢查會叫**——`watch_review` 在沒有前一版時是 SKIPPED，
    其餘檢查都只看 doc 不看 index。洞要到第二天讀不到前一版的 watch 才會爆。

    所以這條檢查刻意擺在「來源」而不是「產物」：index 由 publish 寫，
    但它寫得出什麼完全取決於 doc 帶不帶得動。**擋在來源比擋在產物早一步。**
    """
    doc = p["doc"]
    bad = []
    for k in ("weekday", "stamp", "headline"):
        if not (doc.get(k) or "").strip():
            bad.append(f"{k} 空白")
    if not isinstance(doc.get("cards"), int) or doc.get("cards", 0) <= 0:
        bad.append(f"cards 不是正整數：{doc.get('cards')!r}")

    threaded = [c for _, c in _cards(doc) if c.get("thread")]
    lo, hi = _A(p, "lengths", "threaded_cards_per_day")
    if not threaded:
        bad.append("沒有任何卡帶 thread —— 明天沒有 thread 可沿用")
    elif not (lo <= len(threaded) <= hi):
        bad.append(f"帶 thread 的卡 {len(threaded)} 張，不在 {lo}–{hi}")

    for k in ("watch", "pulse", "snap"):
        if not ((doc.get("overview") or {}).get(k) or []):
            bad.append(f"overview.{k} 是空的")
    if bad:
        return fail("；".join(bad))
    return ok(f"index 可帶齊 11 欄；thread {len(threaded)} 張")


register(Check(
    id="advisory.index_entry_source",
    covers="當日 doc 供得出完整 index entry 的所有欄位（weekday／stamp／headline／"
           "cards／thermo／threads／watch／pulse／snap），且帶 thread 的卡片數在 anchors 區間內",
    blind_to=[
        "publish 實際寫進 index.json 的內容（這條只看來源，不看產物）",
        "欄位有值但值是錯的（headline 與當天實況無關、thread 名稱亂取）",
        "thread 名稱與前幾天不一致，導致跨日串不起來",
        "index.json 裡既有的舊 entry 是否也完整",
    ],
    run=_index_source,
    fixture={"anchors": {"lengths": {"threaded_cards_per_day": [3, 6]}},
             "doc": {"weekday": "", "stamp": "s", "headline": "h", "cards": 1,
                     "overview": {"watch": [1], "pulse": [1], "snap": [1]},
                     "sections": [{"groups": [{"label": "x", "cards": [
                         {"thread": "t"}, {"thread": "t"}, {"thread": "t"}]}]}]}},
    near_miss={"anchors": {"lengths": {"threaded_cards_per_day": [3, 6]}},
               "doc": {"weekday": "星期三", "stamp": "s", "headline": "h", "cards": 1,
                       "overview": {"watch": [1], "pulse": [1], "snap": [1]},
                       "sections": [{"groups": [{"label": "x", "cards": [
                           {"thread": "t"}, {"thread": "t"}, {"thread": "t"}]}]}]}},
    suite="advisory",
))


# ── 14. 卡片值域與形狀 ───────────────────────────────────────────────
def _card_vocab(p):
    """tone／tagcls 的值域，以及 body 必須是字串。

    2026-08-19 把舊站 18 天歷史接進 index 時才發現這件事：舊站的 tone 存的是
    CSS class（`t-red`／`t-orange`）、tagcls 存 `hot`／`warn`，而重寫版存語意值。
    **兩種形狀在同一個 index 底下並存，外殼一定會有一邊渲染不出來。**

    `body` 那一項是其中最危險的：舊站深度卡的 body 是字串陣列、一般卡是字串。
    照著其中一種寫的渲染邏輯，碰到另一種不會報錯，只會**安靜地整段掉**——
    這正是 anchors 裡「可以被算出來的數字不要存」同一個家族的錯誤：
    可以被推導的呈現方式不要存進資料。
    """
    tones = set(_A(p, "card_vocab", "tone"))
    clss = set(_A(p, "card_vocab", "tagcls"))
    bad_tone, bad_cls, bad_body, bad_src = [], [], [], []
    for _, c in _cards(p["doc"]):
        t = c.get("title", "?")[:10]
        if c.get("tone") not in tones:
            bad_tone.append(f"{t}={c.get('tone')!r}")
        if c.get("tagcls") not in clss:
            bad_cls.append(f"{t}={c.get('tagcls')!r}")
        if not isinstance(c.get("body"), str):
            bad_body.append(f"{t}={type(c.get('body')).__name__}")
        if not (c.get("src") or "").strip():
            bad_src.append(t)
    msgs = []
    if bad_tone:
        msgs.append(f"{len(bad_tone)} 張 tone 不在值域：{'、'.join(bad_tone[:3])}")
    if bad_cls:
        msgs.append(f"{len(bad_cls)} 張 tagcls 不在值域：{'、'.join(bad_cls[:3])}")
    if bad_body:
        msgs.append(f"{len(bad_body)} 張 body 不是字串：{'、'.join(bad_body[:3])}")
    if bad_src:
        msgs.append(f"{len(bad_src)} 張 src 空白：{'、'.join(bad_src[:3])}")
    if msgs:
        return fail("；".join(msgs))
    return ok()


register(Check(
    id="advisory.card_vocab",
    covers="每張卡的 tone 與 tagcls 落在 anchors.card_vocab 的值域內、body 是字串（不是陣列）、src 非空",
    blind_to=[
        "值在值域內但用錯了（一則利多的卡標成偏空）",
        "src 非空但寫的是除名來源——來源清單的家在 preamble，這裡刻意不抄第二份",
        "已發布的舊日期檔（檢查只跑當日的 doc）",
        "外殼實際怎麼把語意映射成顏色",
    ],
    run=_card_vocab,
    fixture={"anchors": {"card_vocab": {"tone": ["偏多", "中性", "偏空"],
                                        "tagcls": ["t-mkt"]}},
             "doc": {"sections": [{"groups": [{"label": "x", "cards": [
                 {"title": "舊站樣式", "tone": "t-red", "tagcls": "hot",
                  "body": ["段一", "段二"], "src": "bbg"}]}]}]}},
    near_miss={"anchors": {"card_vocab": {"tone": ["偏多", "中性", "偏空"],
                                          "tagcls": ["t-mkt"]}},
               "doc": {"sections": [{"groups": [{"label": "x", "cards": [
                   {"title": "新版樣式", "tone": "偏空", "tagcls": "t-mkt",
                    "body": "字串", "src": "Bloomberg"}]}]}]}},
    suite="advisory",
))


# ── 15. 派工表本身 ───────────────────────────────────────────────────
def _dispatch(p):
    groups = _A(p, "groups")
    roster = _A(p, "collectors", "roster")
    batches = _A(p, "collectors", "batches")
    bad = []

    # ①每一組、兩種模式，都要有人負責。**素材從來不缺，缺的是有人負責。**
    for g in groups:
        for mode in ("weekday", "weekend"):
            own = (g.get("owners") or {}).get(mode)
            if not own:
                bad.append(f"{g['name']} 的 {mode} 沒有指派")
                continue
            unknown = sorted(set(own) - set(roster))
            if unknown:
                bad.append(f"{g['name']}／{mode} 指給了不存在的採集員 {unknown}")
            # ②指派的則數要加總成配額。配額與下限的差額是汰除餘裕，
            #   加總對不上就代表餘裕被默默改掉了。
            s, q = sum(own.values()), g["quota"][mode]
            if s != q:
                bad.append(f"{g['name']}／{mode} 指派合計 {s} ≠ 配額 {q}")

    # ③每個採集員恰好在一個批次裡。漏掉的那個永遠不會被派出去，
    #   而它負責的組會在盤點缺口時才浮出來——那時已經是補位輪的成本了。
    flat = [c for b in batches for c in b]
    dupe = sorted({c for c in flat if flat.count(c) > 1})
    if dupe:
        bad.append(f"採集員出現在一個以上的批次：{dupe}")
    missing = sorted(set(roster) - set(flat))
    if missing:
        bad.append(f"採集員不在任何批次裡：{missing}")
    ghost = sorted(set(flat) - set(roster))
    if ghost:
        bad.append(f"批次裡有不存在的採集員：{ghost}")

    # ④**一家來源只能屬於一個採集員。** 這條才是並行安全的實際依據：
    #   單來源 15 篇的上限與「不要同時打同一家」，只有在獨佔時守得住。
    home = {}
    for cid, c in roster.items():
        for s in c.get("sources") or []:
            if s in home:
                bad.append(f"來源「{s}」同時屬於 {home[s]} 與 {cid}")
            home[s] = cid
    naked = sorted(cid for cid, c in roster.items() if not (c.get("sources") or []))
    if naked:
        bad.append(f"採集員沒有任何來源：{naked}")

    if bad:
        return fail("；".join(bad))
    sizes = "＋".join(str(len(b)) for b in batches)
    return ok(f"{len(roster)} 個採集員、{sizes} 兩批、{len(home)} 家來源各有唯一歸屬")


register(Check(
    id="advisory.dispatch_wellformed",
    covers="anchors 的派工表自洽：十五組兩種模式都有人負責且合計等於配額、"
           "每個採集員恰好在一個批次、每一家來源只屬於一個採集員",
    blind_to=[
        "**指派了但那個人當天沒跑**——這條驗的是表，不是執行",
        "數字加得起來但分派得不合理（把台灣 12 則指給只讀 Bloomberg 的人）",
        "來源獨佔了，但兩個採集員讀同一家的**不同子網域**（newsletter.semianalysis.com vs semianalysis.com）",
        "批次大小對分頁池是否真的安全——4 這個數字的依據在 anchors 的 _batches_source，這裡不驗它",
        "採集員實際交回幾則（那是 group_floors 與當期失敗判準的事）",
        "來源清單有沒有跟 preamble 第六節同步——來源的家在 preamble，這裡只驗歸屬唯一",
    ],
    run=_dispatch,
    fixture={"anchors": {
        "groups": [{"name": "央行、利率與匯率", "quota": {"weekday": 9, "weekend": 9},
                    "owners": {"weekday": {"A": 5, "C": 4}}}],
        "collectors": {"batches": [["A"], ["C"]],
                       "roster": {"A": {"sources": ["Bloomberg"]},
                                  "C": {"sources": ["Nikkei Asia"]}}}}},
    near_miss={"anchors": {
        "groups": [{"name": "央行、利率與匯率", "quota": {"weekday": 9, "weekend": 9},
                    "owners": {"weekday": {"A": 5, "C": 4},
                               "weekend": {"A": 5, "C": 4}}}],
        "collectors": {"batches": [["A"], ["C"]],
                       "roster": {"A": {"sources": ["Bloomberg"]},
                                  "C": {"sources": ["Nikkei Asia"]}}}}},
    suite="advisory",
))


# ── 16. 三分鐘總覽的第二層 ───────────────────────────────────────────
def _overview_prose(p):
    ov = p["doc"].get("overview") or {}
    lo, hi = _A(p, "overview_prose", "pulse_note_chars")
    tlo, thi = _A(p, "overview_prose", "thermo_note_chars")
    ratio = _A(p, "overview_prose", "takeaway_bold_ratio_min")
    tk_min = _A(p, "overview_prose", "takeaway_chars_min")

    # ── 缺席是錯誤 ──
    bad = []
    naked = [x.get("k") for x in (ov.get("pulse") or []) if not (x.get("note") or "").strip()]
    if naked:
        bad.append(f"{len(naked)} 筆 pulse 沒有 note：{'、'.join(str(k) for k in naked)}")
    # watchReview 有兩種方言：舊制 t＝原文／note＝回顧，重寫後 w＝原文／t＝回顧。
    # 這裡只問「兩層都在嗎」，不強迫哪一種欄位名——歷史封存不改。
    thin = []
    for w in ov.get("watchReview") or []:
        orig = w.get("w") or (w.get("t") if w.get("note") else None)
        review = w.get("t") if w.get("w") else w.get("note")
        if not (orig or "").strip() or not (review or "").strip():
            thin.append(str(w.get("d") or "?"))
    if thin:
        bad.append(f"{len(thin)} 筆 watchReview 只有一層（原文或回顧缺一）：{'、'.join(thin[:4])}")
    if bad:
        return fail("；".join(bad))

    # ── 偏薄是警告。為了湊字數注水比偏短更糟，所以這裡不擋發布。 ──
    warns = []
    over = [x.get("k") for x in (ov.get("pulse") or [])
            if not (lo <= len((x.get("note") or "").strip()) <= hi)]
    if over:
        warns.append(f"{len(over)} 筆 pulse note 不在 {lo}–{hi} 字：{'、'.join(str(k) for k in over)}")
    tn = ((ov.get("thermo") or {}).get("note") or "").strip()
    if not (tlo <= len(tn) <= thi):
        warns.append(f"thermo.note {len(tn)} 字，不在 {tlo}–{thi}")
    tks = [t if isinstance(t, str) else "" for t in (ov.get("takeaways") or [])]
    if tks:
        nb = sum(("<b>" in t or "<strong>" in t) for t in tks)
        if nb / len(tks) < ratio:
            warns.append(f"{nb}/{len(tks)} 條 takeaway 有粗體導言（應 ≥{ratio:.0%}）")
        short = sum(len(t) < tk_min for t in tks)
        if short:
            warns.append(f"{short} 條 takeaway 短於 {tk_min} 字")
    if warns:
        return warn("；".join(warns))
    return ok()


register(Check(
    id="advisory.overview_prose",
    covers="三分鐘總覽的第二層：pulse 每筆有 note、watchReview 兩層俱在（缺就擋）；"
           "note 字數、thermo.note 長度、takeaway 粗體導言比例（偏薄只警告）",
    blind_to=[
        "**兩層都在但下層是上層的換句話說**——字數與粗體都合格，內容卻沒有多說任何事",
        "粗體導言裡沒有硬數字（只驗有沒有標籤，不驗裡面是什麼）",
        "thermo.note 長度合格但沒有跟前一版比較",
        "pulse 的 dir 與 note 互相矛盾",
        "watchReview 的回顧寫了但與 verdict 對不上",
        "已發布的舊日期檔（檢查只跑當日的 doc）",
    ],
    run=_overview_prose,
    fixture={"anchors": {"overview_prose": {
                "pulse_note_chars": [8, 40], "thermo_note_chars": [80, 320],
                "takeaway_bold_ratio_min": 0.7, "takeaway_chars_min": 100}},
             "doc": {"overview": {"pulse": [{"k": "美股", "dir": "中性"}]}}},
    near_miss={"anchors": {"overview_prose": {
                "pulse_note_chars": [8, 40], "thermo_note_chars": [80, 320],
                "takeaway_bold_ratio_min": 0.7, "takeaway_chars_min": 100}},
               "doc": {"overview": {
                   "pulse": [{"k": "美股", "dir": "中性", "note": "指數收黑但半導體獨強，分化而非轉弱"}],
                   "thermo": {"note": "比" + "昨" * 100},
                   "takeaways": ["<b>導言</b>" + "說" * 100],
                   "watchReview": [{"d": "2026-08-19", "w": "原文", "t": "回顧"}]}}},
    suite="advisory",
))


# ── 17. 窗口本身 ─────────────────────────────────────────────────────
def _window(p):
    """**其他每一條窗口相關的檢查都拿這個窗口當基準，所以它自己要先被驗過。**

    `ts_in_window` 問「卡片落在窗口裡嗎」、`_mode` 問「起點那天是不是週末」——
    兩者都對 `window` 照單全收。起點寫錯不會讓任何一條變紅，
    只會**安靜地換掉整輪的收錄門檻與下限表**。
    """
    doc = p["doc"]
    w = doc.get("window") or {}
    if not (w.get("from") and w.get("to")):
        return fail("window 缺 from 或 to —— 沒有窗口就沒有收錄門檻")
    hour = _A(p, "window", "from_hour_taipei")
    off = _A(p, "window", "from_day_offset")
    lo_h, hi_h = _A(p, "window", "length_hours")
    ov_lo, ov_hi = _A(p, "window", "overlap_hours")

    fr = dt.datetime.fromisoformat(w["from"]).astimezone(TPE)
    to = dt.datetime.fromisoformat(w["to"]).astimezone(TPE)
    bad = []
    if (fr.hour, fr.minute, fr.second) != (hour, 0, 0):
        bad.append(f"起點是台北 {fr:%H:%M:%S}，應為 {hour:02d}:00:00")
    want = dt.date.fromisoformat(doc["date"]) + dt.timedelta(days=off)
    if fr.date() != want:
        bad.append(f"起點日期 {fr.date()}，依 date {doc['date']} 與偏移 {off} 應為 {want}")
    if to <= fr:
        bad.append(f"終點 {to} 不晚於起點 {fr}")
    if to.date() != dt.date.fromisoformat(doc["date"]):
        bad.append(f"終點的台北日期 {to.date()} 不是 date {doc['date']}")

    prev = p.get("prev")
    pw = (prev or {}).get("window") or {}
    ov = None
    if pw.get("to"):
        ov = (dt.datetime.fromisoformat(pw["to"]).astimezone(TPE) - fr).total_seconds() / 3600
        if ov < ov_lo:
            # 負的重疊 ＝ 兩個窗口之間有斷口，那一段的素材**永久掉單**，
            # 而且不會有任何一張卡看起來不對。
            bad.append(f"與前一版的窗口有 {-ov:.1f} 小時斷口 —— 那一段永久掉單")
    if bad:
        return fail("；".join(bad))

    warns = []
    ln = (to - fr).total_seconds() / 3600
    if not (lo_h <= ln <= hi_h):
        warns.append(f"窗口長 {ln:.1f} 小時，不在 {lo_h}–{hi_h} —— "
                     "多半代表這一輪開跑時間偏離常態，跨日比較會失真")
    if ov is not None and ov > ov_hi:
        warns.append(f"與前一版重疊 {ov:.1f} 小時，超過 {ov_hi}")
    if warns:
        return warn("；".join(warns))
    return ok(f"起點台北 {fr:%m-%d %H:%M}、長 {ln:.1f} 小時"
              + (f"、與前版重疊 {ov:.1f} 小時" if ov is not None else ""))


register(Check(
    id="advisory.window_wellformed",
    covers="window 自己：起點的時刻與日偏移符合 anchors、終點晚於起點且落在當日、"
           "與前一版沒有斷口（缺就擋）；窗口長度與重疊超出實測帶（只警告）",
    blind_to=[
        "**起點形式正確但那天根本不該跑**（例如整輪重跑時 to 用了舊時刻）",
        "窗口對，但卡片的 ts 是轉載時間而非原始發布時間",
        "前一版自己的窗口就是錯的——這條只比兩者的接縫",
        "斷口為零但前一版根本沒收到那段素材（重疊只保證有機會，不保證有讀）",
        "已發布的舊日期檔（檢查只跑當日的 doc）",
    ],
    run=_window,
    fixture={"anchors": {"window": {"from_hour_taipei": 7, "from_day_offset": -1,
                                    "length_hours": [24, 30], "overlap_hours": [0, 6]}},
             "doc": {"date": "2026-08-20",
                     "window": {"from": "2026-08-19T09:00:00+08:00",
                                "to": "2026-08-20T11:00:00+08:00"}}},
    near_miss={"anchors": {"window": {"from_hour_taipei": 7, "from_day_offset": -1,
                                      "length_hours": [24, 30], "overlap_hours": [0, 6]}},
               "doc": {"date": "2026-08-20",
                       "window": {"from": "2026-08-19T07:00:00+08:00",
                                  "to": "2026-08-20T11:00:00+08:00"}}},
    suite="advisory",
))
