"""外資報告資料庫的檢查。**這一批是一週的量，所以 payload 是整批不是單份。**

payload 形狀（由 `tools/research_verify.py` 組出來，檢查本身不做 IO）：

    {"docs":    [scripts/research/extract.py 的輸出, ...]（整批）,
     "anchors": research/anchors.json,
     "now":     ISO8601}

## 為什麼是整批

去重與 slug 唯一性是**跨檔**的問題，單份看不出來：同一份報告用兩個檔名各抽一次，
每一份自己都完全合格。週頻的產出本來就是一批，形狀跟著問題走。

## 這一套沒有註冊成 `System`

`System` 有五個必填欄位，其中 `index_entry`／`index_meta`／`staged_paths` 全是為
**發布**設計的，而這一套刻意不發布（原文逐頁蓋有可追溯到個人的浮水印）。
`kbcore/system.py` 自己寫著「沒有預設值是刻意的 —— 給預設等於讓下一套系統
安靜地繼承錯的形狀」。填三個假的 callable 只為了形狀一致，正是它在防的事。
哪天衍生層真的要發布，那時才註冊，而且那時 `staged_paths` 會有真的答案。
"""
import datetime as dt
import re

from kbcore.check import Check, fail, ok, register, skipped, warn


def _A(p, *path):
    """取不到就 KeyError —— **門檻取不到是設定壞了，不是資料壞了。**"""
    cur = p["anchors"]
    for k in path:
        cur = cur[k]
    return cur


def _docs(p):
    return p.get("docs") or []


def _name(d):
    return (d.get("slug") or d.get("source_file") or "?")[:44]


# ── 1. PII 與追蹤碼有沒有殘留 ────────────────────────────────────────
LEAK = {
    "信箱": re.compile(r"[\w.+-]+@[\w.-]+\.\w{2,}"),
    "反寫信箱": re.compile(r"[A-Z]{2}\.[A-Z]{3}\.[A-Z]+@\d+"),
    "追蹤雜湊": re.compile(r"\b[0-9a-f]{32}\b"),
    "exclusive": re.compile(r"exclusive use of|evisulcxe", re.I),
    "prepared-for": re.compile(r"Prepared for\s+[A-Z]|deraperP"),
}


def _no_pii(p):
    """**這一條是整套系統裡唯一不能只靠人記得的規則。**

    報告逐頁蓋有個人化浮水印，內含收件人的公司信箱與逐份追蹤雜湊。剃除寫在
    抽取層的第一步，但**「有一個剃除步驟」與「它真的剃乾淨了」是兩件事** ——
    而剃漏的樣子是一份看起來完全正常的中間檔。所以這裡不信任上游，重掃一次。
    """
    bad = []
    for d in _docs(p):
        blob = (d.get("page_one") or "") + "\n" + "\n".join(d.get("body") or [])
        hits = {k: len(rx.findall(blob)) for k, rx in LEAK.items()}
        hits = {k: v for k, v in hits.items() if v}
        if hits:
            bad.append(f"{_name(d)} {hits}")
    if bad:
        return fail("；".join(bad) + " —— **抽取層沒剃乾淨**。"
                    "這些字串一旦寫進任何檔案就收不回來，處置是修抽取層之後整批重抽，"
                    "不是在下游過濾")
    return ok(f"{len(_docs(p))} 份，PII 與追蹤碼零殘留")


register(Check(
    id="research.no_pii",
    covers="抽出來的 page_one 與 body 裡沒有信箱、反寫信箱、32 位追蹤雜湊、"
           "`exclusive use of`、`Prepared for` 的任何殘留",
    blind_to=[
        "**表格裡的殘留** —— 這條只掃 page_one 與 body，`tables` 沒掃",
        "**沒見過的浮水印形態** —— 換一家券商、換一種蓋法，這五條規則一條都不會響",
        "分析師姓名（電話與信箱剃掉了，人名留著；`anchors.known_limits` 有記）",
        "原始 PDF 本身（它照樣帶著浮水印，那是刻意的：原文不進版控）",
    ],
    run=_no_pii,
    fixture={"anchors": {}, "docs": [{"slug": "x", "page_one": "For the exclusive use of a@b.com",
                                      "body": []}]},
    near_miss={"anchors": {}, "docs": [{"slug": "x", "page_one": "Citi's take on rates", "body": []}]},
    suite="research",
))


# ── 2. 券商與日期認出來了嗎 ──────────────────────────────────────────
def _identified(p):
    lo = _A(p, "brokers", "min_hits")
    margin = _A(p, "brokers", "min_margin")
    bad, thin = [], []
    for d in _docs(p):
        if not d.get("broker"):
            bad.append(f"{_name(d)} 認不出券商 {d.get('broker_tally')}")
        if not d.get("date"):
            bad.append(f"{_name(d)} 認不出日期")
        t = d.get("broker_tally") or {}
        if d.get("broker") and len(t) > 1:
            vals = sorted(t.values(), reverse=True)
            if vals[0] < vals[1] * margin * 2:
                thin.append(f"{_name(d)} {t}")
    if bad:
        return fail("；".join(bad) + f" —— 門檻是至少 {lo} 次且為第二名的 {margin} 倍")
    if thin:
        return warn("；".join(thin) + " —— **差距只勉強過門檻**。"
                    "報告會互相引用，差距本身就是證據；快貼到線上時要人看一眼")
    return ok(f"{len(_docs(p))} 份全部認出券商與日期")


register(Check(
    id="research.identified",
    covers="每一份都認得出券商與日期，且券商計次滿足 anchors.brokers 的 min_hits 與 min_margin",
    blind_to=[
        "**認錯**（計次最高的不一定是發行者）—— 這條只問「有沒有認出來」，不問「認得對不對」",
        "**沒登記的券商** —— 不在 roster 裡的一律計 0，於是整份判「認不出」，而不是「這是新的一家」",
        "日期認出來但認的是引用文獻的日期",
        "產品線（從檔名取，沒有任何驗證）",
    ],
    run=_identified,
    fixture={"anchors": {"brokers": {"min_hits": 3, "min_margin": 3}},
             "docs": [{"slug": "x", "broker": None, "date": "2026-08-20", "broker_tally": {"A": 1}}]},
    near_miss={"anchors": {"brokers": {"min_hits": 3, "min_margin": 3}},
               "docs": [{"slug": "x", "broker": "A", "date": "2026-08-20",
                         "broker_tally": {"A": 40, "B": 0}}]},
    suite="research",
))


# ── 3. 剃掉的份量有沒有失控 ──────────────────────────────────────────
def _strip_bounded(p):
    hi = _A(p, "extract", "strip_warn_pct")
    stop = _A(p, "extract", "strip_fail_pct")
    over, warned = [], []
    for d in _docs(p):
        r = d.get("strip_report") or {}
        pct = r.get("removed_pct")
        if pct is None:
            continue
        (over if pct >= stop else warned if pct >= hi else []).append(f"{_name(d)} {pct}%")
    if over:
        return fail("；".join(over) + f" —— 超過 {stop}%，**剃太多與文件本來就乾淨，"
                    "輸出長得一模一樣**，要人看剃掉的是什麼")
    if warned:
        return warn("；".join(warned) + f" —— 超過 {hi}%")
    return ok("剃除份量都在範圍內")


register(Check(
    id="research.strip_bounded",
    covers="每一份被剃掉的頁首頁尾行數佔比落在 anchors.extract 的兩道門檻內",
    blind_to=[
        "**剃錯但份量正常** —— 剃掉 1% 的正文跟剃掉 1% 的頁首，這條分不出來",
        "浮水印剃了幾處（那個數字有記，但沒有門檻——形態太隨券商而異）",
        "整份都沒剃到（0% 也在範圍內，而那可能代表偵測失效）",
    ],
    run=_strip_bounded,
    fixture={"anchors": {"extract": {"strip_warn_pct": 8, "strip_fail_pct": 15}},
             "docs": [{"slug": "x", "strip_report": {"removed_pct": 22.0}}]},
    near_miss={"anchors": {"extract": {"strip_warn_pct": 8, "strip_fail_pct": 15}},
               "docs": [{"slug": "x", "strip_report": {"removed_pct": 2.1}}]},
    suite="research",
))


# ── 4. 自報頁數對得上抽到的頁數 ──────────────────────────────────────
def _page_count(p):
    pairs = [(d, d.get("claimed_pages")) for d in _docs(p)]
    have = [(d, c) for d, c in pairs if c]
    if not have:
        return skipped("這一批沒有任何一份自報頁數（只有花旗提供）—— "
                       "**跟「比對過、都對」是兩件事**")
    bad = [f"{_name(d)} 自報 {c} ≠ 抽到 {d.get('pages')}" for d, c in have
           if c != d.get("pages")]
    if bad:
        return fail("；".join(bad) + " —— 抽取器漏頁或檔案不完整")
    return ok(f"{len(have)}/{len(pairs)} 份有自報頁數，全部相符")


register(Check(
    id="research.page_count",
    covers="有自報頁數的報告，抽到的頁數與它相符",
    blind_to=[
        "**沒有自報頁數的券商**（高盛、野村）—— 回 SKIPPED 不是 PASS",
        "頁數對但某一頁抽出來是空的",
        "自報的那個數字本身就是錯的",
    ],
    run=_page_count,
    fixture={"anchors": {}, "docs": [{"slug": "x", "claimed_pages": 26, "pages": 27}]},
    near_miss={"anchors": {}, "docs": [{"slug": "x", "claimed_pages": 26, "pages": 26}]},
    suite="research",
))


# ── 5. 第一頁撐不撐得起「立場」 ──────────────────────────────────────
def _page_one(p):
    lo = _A(p, "page_one_is_the_thesis", "min_visible_chars")
    bad = []
    for d in _docs(p):
        n = len(re.sub(r"\s+", " ", d.get("page_one") or "").strip())
        if n < lo:
            bad.append(f"{_name(d)} 塌縮空白後只有 {n} 字元")
    if bad:
        return fail("；".join(bad) + f" —— 不足 {lo}，"
                    "**第一頁是這一套的主要輸入**，它薄了下游全部跟著薄")
    return ok("每一份的第一頁都有足夠內容")


register(Check(
    id="research.page_one_substantial",
    covers="每一份的 page_one 塌縮空白後不少於 anchors 的 min_visible_chars",
    blind_to=[
        "**字數夠但講的不是立場** —— 封面頁、目錄頁一樣有字",
        "第一頁被右欄污染（分析師欄插進主張裡，`known_limits` 有記）",
        "第一頁很短但立場其實寫在第二頁",
    ],
    run=_page_one,
    fixture={"anchors": {"page_one_is_the_thesis": {"min_visible_chars": 400}},
             "docs": [{"slug": "x", "page_one": "短"}]},
    near_miss={"anchors": {"page_one_is_the_thesis": {"min_visible_chars": 400}},
               "docs": [{"slug": "x", "page_one": "字" * 400}]},
    suite="research",
))


# ── 6. 同一份有沒有被收兩次 ──────────────────────────────────────────
def _dupes(p):
    by_slug, by_sha = {}, {}
    for d in _docs(p):
        by_slug.setdefault(d.get("slug"), []).append(d.get("source_file"))
        by_sha.setdefault(d.get("sha256"), []).append(d.get("source_file"))
    ds = {k: v for k, v in by_slug.items() if len(v) > 1}
    dh = {k[:8]: v for k, v in by_sha.items() if k and len(v) > 1}
    if dh:
        # 兩種成因，訊息要分得出來：來源檔名相同 ＝ 同一份輸入被抽了兩次
        # （多半是 slug 規則改過、舊輸出成了孤兒）；來源檔名不同 ＝ 真的收了兩份一樣的檔。
        same_src = {k: v for k, v in dh.items() if len(set(v)) == 1}
        diff_src = {k: v for k, v in dh.items() if len(set(v)) > 1}
        msg = []
        if same_src:
            msg.append(f"同一份輸入產生了兩個輸出：{same_src} —— "
                       "**slug 規則改過，舊的那個是孤兒**，用 extract.py --prune 清掉")
        if diff_src:
            msg.append(f"兩個不同檔名、內容一樣：{diff_src}")
        return fail("；".join(msg))
    if ds:
        return fail(f"slug 撞號：{ds} —— 同一天同一家同一個產品線，"
                    "**但內容不同**。可能是早晚兩版，需要在 slug 裡加區別")
    return ok(f"{len(by_slug)} 份，slug 與 sha256 都唯一")


register(Check(
    id="research.no_duplicates",
    covers="這一批之內 slug 與 sha256 都唯一",
    blind_to=[
        "**跨批重複** —— 上週已經收過的這一批又收一次，這條看不到（它只看眼前這批）",
        "同一份報告的修訂版（內容不同、sha 不同、slug 也可能不同）",
        "檔名正規化之前就已經是兩份的情況",
    ],
    run=_dupes,
    fixture={"anchors": {}, "docs": [{"slug": "a", "sha256": "ff", "source_file": "1.pdf"},
                                     {"slug": "a", "sha256": "ee", "source_file": "2.pdf"}]},
    near_miss={"anchors": {}, "docs": [{"slug": "a", "sha256": "ff", "source_file": "1.pdf"},
                                       {"slug": "b", "sha256": "ee", "source_file": "2.pdf"}]},
    suite="research",
))


# ── 7. 立場的原句要在報告裡找得到 ────────────────────────────────────
def _norm(s):
    """比對用：塌縮空白。抽取器對空白的處理不同，逐字比會假性失敗。"""
    return re.sub(r"\s+", " ", s or "").strip()


def _stance_grounded(p):
    """**這是這一套唯一的防線。**

    另外三套的產出都能回頭跟來源比對（逐字稿、序列、新聞連結）。這一套不行 ——
    原文不進版控，所以未來的人手上只有我們寫的東西。原句因此是硬性的：
    它讓「這是分析師說的」與「這是我們的歸納」永遠分得開。

    比對用子字串包含、不用整行相等 —— 跟 podcast 的 `quotes_grounded` 同一個理由：
    抽取層會重排空白，整行比對會把完整的句子誤判成對不上。
    """
    digest = p.get("digest")
    if digest is None:
        return skipped("這一輪沒有第 2 層產出（只跑了入庫）—— "
                       "**跟「比對過、都對」是兩件事**")
    text = {d.get("slug"): _norm((d.get("page_one") or "") + "\n" + "\n".join(d.get("body") or []))
            for d in _docs(p)}
    miss, orphan = [], []
    for s in digest.get("stances") or []:
        slug, q = s.get("slug"), _norm(s.get("quote"))
        if slug not in text:
            orphan.append(f"{slug} 不在這一批抽取結果裡")
        elif not q:
            miss.append(f"{slug} 的 quote 是空的")
        elif q not in text[slug]:
            miss.append(f"{slug}：「{q[:34]}…」")
    if orphan:
        return fail("；".join(orphan) + " —— 引用了不存在的報告")
    if miss:
        return fail("；".join(miss) + " —— **原句在報告裡找不到**。"
                    "沒有原句的判斷要歸到 crosscut，那裡本來就是我們的話")
    n = len(digest.get("stances") or [])
    return ok(f"{n} 筆立場的原句全部對得上")


register(Check(
    id="research.stance_grounded",
    covers="digest 裡每一筆 stance 的 quote 都能在該報告的抽取文字裡逐字找到（塌縮空白後）",
    blind_to=[
        "**只跑入庫的輪次整條跳過**（回 SKIPPED，不是 PASS）",
        "**原句對得上但中譯是錯的** —— `quote_zh` 沒有任何驗證",
        "**原句對得上但斷章取義** —— 前後文翻轉語意，機械比對看不到",
        "`crosscut` 那一段（那裡本來就是我們的話，不受這條約束）",
        "原句出自表格或圖說（只掃 page_one 與 body）",
    ],
    run=_stance_grounded,
    fixture={"anchors": {}, "docs": [{"slug": "a", "page_one": "growth is slowing", "body": []}],
             "digest": {"stances": [{"slug": "a", "quote": "we see a recession"}]}},
    near_miss={"anchors": {}, "docs": [{"slug": "a", "page_one": "growth  is   slowing", "body": []}],
               "digest": {"stances": [{"slug": "a", "quote": "growth is slowing"}]}},
    suite="research",
))


# ── 8. 主題在投顧的值域裡 ────────────────────────────────────────────
def _theme_domain(p):
    digest = p.get("digest")
    if digest is None:
        return skipped("這一輪沒有第 2 層產出")
    adv = p.get("advisory_anchors")
    if not adv:
        return fail("payload 沒帶投顧的 anchors —— **值域的家在那裡**，"
                    "拿不到就沒有資格判 theme")
    names = {g.get("name") for g in (adv.get("groups") or [])}
    bad = sorted({s.get("theme") for s in (digest.get("stances") or [])
                  if s.get("theme") not in names})
    if bad:
        return fail(f"theme 不在投顧的十五組裡：{bad} —— "
                    "**值域只有一個家**，要加組名去投顧那邊加")
    return ok(f"全部落在 {len(names)} 組值域內")


register(Check(
    id="research.theme_in_domain",
    covers="digest 裡每一筆 stance 的 theme 都在 advisory/anchors.json 的 groups 裡",
    blind_to=[
        "**分對組但分錯地方** —— 這條只驗值域，不驗分類正確",
        "只跑入庫的輪次（SKIPPED）",
        "同一份報告被拆成多筆立場、而它們該是同一組",
    ],
    run=_theme_domain,
    fixture={"anchors": {}, "advisory_anchors": {"groups": [{"name": "央行、利率與匯率"}]},
             "digest": {"stances": [{"theme": "隨便一個不存在的組"}]}},
    near_miss={"anchors": {}, "advisory_anchors": {"groups": [{"name": "央行、利率與匯率"}]},
               "digest": {"stances": [{"theme": "央行、利率與匯率"}]}},
    suite="research",
))
