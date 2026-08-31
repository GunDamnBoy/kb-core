"""外資報告資料庫的檢查。**這一批是一週的量，所以 payload 是整批不是單份。**

payload 形狀（由 `tools/research_verify.py` 組出來，檢查本身不做 IO）：

    {"docs":    [scripts/research/extract.py 的輸出, ...]（整批）,
     "anchors": research/anchors.json,
     "now":     ISO8601}

## 為什麼是整批

去重與 slug 唯一性是**跨檔**的問題，單份看不出來：同一份報告用兩個檔名各抽一次，
每一份自己都完全合格。週頻的產出本來就是一批，形狀跟著問題走。

## 註冊成 `System` 是 2026-08-21 才發生的事

原本刻意不註冊：`index_entry`／`index_meta`／`staged_paths` 全是為發布設計的，
而這一套不發布。當時寫著「哪天衍生層真的要發布，那時才註冊，
**而且那時 `staged_paths` 會有真的答案**」—— 那天就是同一天下午。

**界線沒有移動：發布的是衍生層（精華、原句、標籤、重製圖），
原文與抽取文字仍然永不進任何 repo。** 那條界線是結構性的，不是 `.gitignore`。

於是 `systems/research.py` 的 `build()` 要去 repo 以外讀抽取文字 ——
那是這五套裡唯一一個這樣的 payload，理由與它最危險的失效模式都寫在那個檔頭。
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


def _parts(d):
    """一份報告**全部**的抽取文字：第一頁 ＋ 內文 ＋ 表格列。

    這個函式存在，是因為同一個「報告內容有哪些」的定義原本散在三條檢查裡，
    而**三條各自答錯了不同的部分**：

    - `chart_grounded` 2026-08-21 首輪就撞上（花旗那張圖的數字全在第 11 頁表格裡，
      16 條 grounding 全部找不到），當場補了表格。
    - `stance_grounded` 的 `blind_to` **宣稱**掃了表格，程式沒有 ——
      文件與程式各說各話，而它會製造**假性 FAIL**：一句只出現在表格裡的原句
      被判沒憑據，撰寫者只能把那筆立場刪掉或改寫。**看起來像撰寫者偷懶。**
    - `no_pii` 誠實地在 `blind_to` 記著沒掃表格 —— 誠實，但那是唯一一條
      不能靠人記得的規則，浮水印蓋在哪裡不由我們決定。

    一個定義三個家，於是每個家各壞一次、而且壞法都不一樣。現在只有一個家。

    **回的是原始片段，不是塌縮過的字串** —— `no_pii` 的信箱與雜湊正則要靠標點，
    而 `_norm` 會折疊標點。要比對的那兩條自己再 `_norm`。
    """
    parts = [d.get("page_one") or ""] + list(d.get("body") or [])
    for t in (d.get("tables") or []):
        for row in t.get("rows") or []:
            parts.append(" ".join(str(c) for c in row))
    return parts


def _all_text(d):
    """一份抽取結果裡**任何會被存下來的文字**，包含 `page_one_columns`。

    **這跟 `_parts()` 刻意不一樣，而差異不是疏漏。** 兩者回答兩個不同的問題：

    - `_parts()` 問「分析師寫過這句話嗎」（grounding）。`page_one_columns` 是
      `page_one` 的重排版 —— 同樣的內容換個版面，收進來只會**重複計算同一個乾草堆**。
    - `_all_text()` 問「這個檔裡還有沒有殘留」（PII）。這時**每一個會被寫進檔案的
      欄位都算數**，包括重排版，因為浮水印不挑欄位。

    2026-08-23：`page_one_columns` 是第三個繞過浮水印剃除的表示法，
    而 `no_pii` 當時掃的是 `_parts()`，連看都沒看到它。
    **兩個函式共用一個定義，就是這個漏洞當初的成因。**
    """
    return _parts(d) + [d.get("page_one_columns") or ""]


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
        hits = {k: len(rx.findall("\n".join(_all_text(d)))) for k, rx in LEAK.items()}
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
    covers="抽出來的 page_one、body、tables 與 page_one_columns 裡沒有信箱、反寫信箱、"
           "32 位追蹤雜湊、`exclusive use of`、`Prepared for` 的任何殘留",
    blind_to=[
        "**表格的欄位錯位** —— 掃得到表格文字，但抽取器把一格拆成兩格時，"
        "一個被劈開的信箱這五條正則一條都不會響",
        "**沒見過的浮水印形態** —— 換一家券商、換一種蓋法，這五條規則一條都不會響",
        "**下一個新增的表示法** —— 這條掃的是 `_all_text()` 列出的欄位。"
        "2026-08-23 之前它漏掉 `tables` 與 `page_one_columns` 兩個，"
        "而兩者都是後來才加進抽取結果的。**新增欄位時沒有東西會提醒你回來改這裡**",
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
def visible_len(s):
    """`page_one` 塌縮空白之後還剩幾個字元。**這條規則的家在這裡。**

    2026-08-31 起 `extract.py` 的逐檔退路也用它 —— 那支要判「主抽取器是不是
    把第一頁抽成空的」，判準必須跟這條檢查**逐字相同**。
    兩個長得很像的實作，會在某一天給出不同的答案，而那天沒有人會發現。
    （`check_part.py` 借用 `_norm` 是同一條理由。）
    """
    return len(re.sub(r"\s+", " ", s or "").strip())


def _page_one(p):
    lo = _A(p, "page_one_is_the_thesis", "min_visible_chars")
    bad = []
    for d in _docs(p):
        n = visible_len(d.get("page_one"))
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
    # 註：**真正的撞號這條看不到**，理由寫在下面的 blind_to。守衛在 extract.py。
    return ok(f"{len(by_slug)} 份，slug 與 sha256 都唯一")


register(Check(
    id="research.no_duplicates",
    covers="這一批之內 slug 與 sha256 都唯一",
    blind_to=[
        "**同一輪裡真的撞號的那兩份** —— 這條讀的是 `extracted/`，而覆蓋發生在它執行之前：到它看的時候兩份已經變成一份，`by_slug` 只有一個值。**它量的是撞號之後的狀態，而證據那時已經被刪掉了。**真正的守衛在 `extract.py` 的寫檔前（2026-08-23 加），這條只抓得到「兩份都寫出來了但 slug 一樣」這種不會發生的情況",
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
# 排版標點的等價類。撰寫者用直引號打字、PDF 裡是彎引號，這是字形差異不是內容差異，
# 跟空白同一類：不折疊就會出現「原句明明在報告裡、機械比對卻說找不到」的假性失敗。
_PUNCT = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                        "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " "})


# 抽取器會在標點前後多塞一個空白（pdftotext 實測：`remain on hold .`）。
# 跟彎引號同一類 —— **字形差異，不是內容差異**。
# 2026-08-22：整批換抽取器之後，野村那句立場就只差這一個空白而對不上，
# 而它讀起來跟原句一模一樣。
_SP_BEFORE = re.compile(r"\s+([.,;:!?%)\]}])")
_SP_AFTER = re.compile(r"([(\[{])\s+")


def _norm(s):
    """比對用：塌縮空白、折疊排版標點、拿掉標點旁邊多出來的空白。

    三者都隨抽取器與輸入法而變，逐字比會假性失敗 ——
    **而假性失敗的樣子跟真的對不上一模一樣**。
    """
    t = re.sub(r"\s+", " ", (s or "").translate(_PUNCT)).strip()
    return _SP_AFTER.sub(r"\1", _SP_BEFORE.sub(r"\1", t))


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
    text = {d.get("slug"): _norm("\n".join(_parts(d))) for d in _docs(p)}
    miss, orphan = [], []
    for r in digest.get("reports") or []:
      for s in r.get("stances") or []:
        slug, q = r.get("slug"), _norm(s.get("quote"))
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
    n = sum(len(r.get("stances") or []) for r in digest.get("reports") or [])
    return ok(f"{n} 筆立場的原句全部對得上")


register(Check(
    id="research.stance_grounded",
    covers="digest 裡每一筆 stance 的 quote 都能在該報告的抽取文字裡逐字找到（塌縮空白後）",
    blind_to=[
        "**只跑入庫的輪次整條跳過**（回 SKIPPED，不是 PASS）",
        "**原句對得上但中譯是錯的** —— `quote_zh` 沒有任何驗證",
        "**原句對得上但斷章取義** —— 前後文翻轉語意，機械比對看不到",
        "`crosscut` 那一段（那裡本來就是我們的話，不受這條約束）",
        "**圖說與座標軸文字** —— 掃 page_one、body 與 tables，圖片裡的文字抽不出來所以掃不到",
        "**乾草堆變大帶來的巧合命中** —— 2026-08-23 把表格收進來之後，"
        "一句很短的原句可能剛好等於某個表格欄位的文字。這是刻意收下的代價："
        "少掉的假性 FAIL（只出現在表格裡的真原句）比多出來的巧合命中值錢",
    ],
    run=_stance_grounded,
    fixture={"anchors": {}, "docs": [{"slug": "a", "page_one": "growth is slowing", "body": []}],
             "digest": {"reports": [{"slug": "a", "stances": [{"quote": "we see a recession"}]}]}},
    near_miss={"anchors": {}, "docs": [{"slug": "a", "page_one": "growth  is   slowing", "body": []}],
               "digest": {"reports": [{"slug": "a", "stances": [{"quote": "growth is slowing"}]}]}},
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
    bad = sorted({s.get("theme") for r in (digest.get("reports") or [])
                  for s in (r.get("stances") or []) if s.get("theme") not in names})
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
             "digest": {"reports": [{"stances": [{"theme": "隨便一個不存在的組"}]}]}},
    near_miss={"anchors": {}, "advisory_anchors": {"groups": [{"name": "央行、利率與匯率"}]},
               "digest": {"reports": [{"stances": [{"theme": "央行、利率與匯率"}]}]}},
    suite="research",
))


# ── 9. 精華篇幅落在該層的區間 ────────────────────────────────────────
def _summary_len(p):
    """**不對稱：低於下界 FAIL、高於上界 WARN。**

    太短代表精華沒撐起報告，讀者還是得回去翻原文 —— 那是目的失效。
    太長只是成本與可讀性，內容本身沒有錯。
    而且「短報告硬拉長」比「長報告超規格」嚴重 —— **注水的字比缺的字更難發現。**
    """
    digest = p.get("digest")
    if digest is None:
        return skipped("這一輪沒有第 2 層產出")
    thin, fat = [], []
    for r in digest.get("reports") or []:
        n, band = r.get("summary_chars"), r.get("tier_band")
        if n is None or not band:
            continue
        if n < band[0]:
            thin.append(f"{r.get('slug','?')[:38]} {n} < {band[0]}")
        elif n > band[1]:
            fat.append(f"{r.get('slug','?')[:38]} {n} > {band[1]}")
    if thin:
        return fail("；".join(thin) + " —— **不足下界**。素材真的撐不起就要在回報裡具名，"
                    "而不是交一份讀者還得回去翻原文的精華")
    if fat:
        return warn("；".join(fat) + " —— 超出上界。內容沒有錯，但成本與可讀性要看一眼；"
                    "**連續幾期同一類報告都超出，代表該調的是門檻不是撰寫者**")
    return ok(f"{len(digest.get('reports') or [])} 份的篇幅都落在該層區間內")


register(Check(
    id="research.summary_length",
    covers="每份精華的 summary_chars 落在該頁數層的區間（anchors.summary_tiers）",
    blind_to=[
        "**字數對但內容空洞** —— 這條只量長度，不看它有沒有回答「主張、憑什麼、哪裡可能錯」",
        "分層界線本身訂得對不對（11／31 頁是首批七份的分布，估的）",
        "`summary_chars` 是組檔程式算的；撰寫者自報的數字不進來",
        "只跑入庫的輪次（SKIPPED）",
    ],
    run=_summary_len,
    fixture={"anchors": {}, "digest": {"reports": [{"slug": "x", "summary_chars": 900,
                                                    "tier_band": [2600, 3400]}]}},
    near_miss={"anchors": {}, "digest": {"reports": [{"slug": "x", "summary_chars": 2600,
                                                      "tier_band": [2600, 3400]}]}},
    suite="research",
))


# ── 10. 圖裡的數字有出處 ─────────────────────────────────────────────
def _chart_grounded(p):
    """圖表繼承 `stance_grounded` 的同一條紀律。

    **自動解表格那條路之所以被否掉，理由就在這裡**：解出來的數字沒有可回溯的出處，
    錯了看起來跟對的一樣。從內文取數則每個數字都指得出原句，於是可驗證。
    """
    digest = p.get("digest")
    if digest is None:
        return skipped("這一輪沒有第 2 層產出")
    lo, hi = _A(p, "charts", "per_report")
    # 「報告內容有哪些」的定義在 `_parts()`，三條檢查共用一個家（見那裡的檔頭）。
    # 這條是最早發現表格不能漏的：2026-08-21 首輪，花旗那張央行利率圖的數字
    # 全部來自第 11 頁的表格，於是 16 條 grounding 全部找不到。
    text = {d.get("slug"): _norm("\n".join(_parts(d))) for d in _docs(p)}
    miss, over, nogr, err = [], [], [], []
    for r in digest.get("reports") or []:
        cs = r.get("charts") or []
        if not (lo <= len(cs) <= hi):
            over.append(f"{r.get('slug','?')[:34]} {len(cs)} 張")
        for c in cs:
            if c.get("render_error"):
                err.append(f"{c.get('title','?')[:24]}：{c['render_error'][:48]}")
            g = c.get("grounding") or []
            if not g:
                nogr.append(f"{r.get('slug','?')[:34]}／{c.get('title','?')[:22]}")
                continue
            body = text.get(r.get("slug"), "")
            for frag in g:
                if _norm(frag) not in body:
                    miss.append(f"{c.get('title','?')[:22]}：「{_norm(frag)[:30]}…」")
    if err:
        return fail("；".join(err) + " —— 圖渲染失敗，**規格與繪圖引擎對不上**")
    if nogr:
        return fail("；".join(nogr) + " —— **沒有 grounding 的圖不得發布**。"
                    "數字沒有出處，錯了看起來跟對的一樣")
    if miss:
        return fail("；".join(miss[:5]) + f"（共 {len(miss)} 條）"
                    " —— **圖裡的數字在報告裡找不到**")
    if over:
        return fail("；".join(over) + f" —— 每份 {lo}–{hi} 張")
    n = sum(len(r.get("charts") or []) for r in digest.get("reports") or [])
    return ok(f"{n} 張圖的數字全部有出處且渲染成功")


register(Check(
    id="research.chart_grounded",
    covers="每張重製圖的張數在 anchors.charts.per_report 內、有 grounding、"
           "每條 grounding 都能在該報告的抽取文字裡逐字找到，且沒有渲染失敗",
    blind_to=[
        "**grounding 對得上但圖畫錯** —— 原句有那個數字，不代表它被放進正確的類別",
        "**圖表選型是否恰當** —— 用長條圖畫時間序列這條看不出來",
        "數字對但單位或量級標錯",
        "圖裡有出處、但那個出處在報告裡是被作者否定的說法",
        "**標點形態被折疊** —— 直引號與彎引號、各式破折號、以及標點旁多出來的空白，都視為同一個字（見 `_norm`，刻意）",
        "只跑入庫的輪次（SKIPPED）",
    ],
    run=_chart_grounded,
    fixture={"anchors": {"charts": {"per_report": [0, 3]}},
             "docs": [{"slug": "a", "page_one": "share rose to 42%", "body": []}],
             "digest": {"reports": [{"slug": "a", "charts": [
                 {"title": "t", "grounding": ["share rose to 99%"]}]}]}},
    near_miss={"anchors": {"charts": {"per_report": [0, 3]}},
               "docs": [{"slug": "a", "page_one": "share  rose   to 42% by 4Q\u201927", "body": []}],
               "digest": {"reports": [{"slug": "a", "charts": [
                   {"title": "t", "grounding": ["share rose to 42% by 4Q'27"]}]}]}},
    suite="research",
))


# ── 11. 報告層標籤：數量、字形、值域（值域尚未開啟）─────────────────
def _tags_wellformed(p):
    """標籤是**網站上找東西的那條軸**，所以它壞掉的樣子是「找不到」，不是「錯」。

    找不到跟沒有長得一模一樣，而且沒有人會來回報 —— 所以這條在發布前就要擋。

    `anchors.tags.vocab` 是 `null` 時**不驗值域**（前幾期刻意讓撰寫者自由下，
    累積後再合併成受控詞表）。那不是這條檢查偷懶，是詞表要從真實內容長出來；
    詞表一填進去，值域這一段就自動開始驗。
    """
    digest = p.get("digest")
    if digest is None:
        return skipped("這一輪沒有第 2 層產出（只跑了入庫）—— "
                       "**跟「比對過、都對」是兩件事**")
    T = _A(p, "tags")
    lo, hi = T["per_report"]
    vocab = T.get("vocab")
    cnt, form, oov = [], [], []
    seen = {}
    for r in digest.get("reports") or []:
        tags = r.get("tags") or []
        slug = r.get("slug", "?")
        if not lo <= len(tags) <= hi:
            cnt.append(f"{slug[:34]} {len(tags)} 個")
        for t in tags:
            t = (t or "").strip()
            # 空白與標點是「這是一句話不是一個名字」最便宜的訊號。
            if not t or len(t) > 12 or re.search(r"[\s，。、；：,.;:!?！？]", t):
                form.append(f"{slug[:24]}：「{t[:16]}」")
            if vocab and t not in vocab:
                oov.append(t)
            seen[t] = seen.get(t, 0) + 1
    if cnt:
        return fail("；".join(cnt[:5]) + f" —— 每份要 {lo}–{hi} 個。"
                    "**標籤太少的那份在網站上會跟誰都連不起來**，而它看起來很正常")
    if form:
        return fail("；".join(form[:5]) + " —— 標籤是**名詞不是句子**："
                    "不帶空白標點、不超過 12 字。帶了方向的標籤會在立場反轉時變成錯的，"
                    "而它看起來還是一個好好的標籤")
    if oov:
        return fail(f"不在受控詞表裡：{sorted(set(oov))[:6]} —— "
                    "詞表的家在 `anchors.tags.vocab`")
    n = len(seen)
    once = sum(1 for v in seen.values() if v == 1)
    msg = f"{len(digest.get('reports') or [])} 份、{n} 個相異標籤"
    if vocab is None:
        msg += "（詞表尚未訂，值域這一段沒驗）"
    # 全部只出現一次 = 沒有任何一份連得到另一份，那時標籤等於沒有作用。
    if n and once == n and n > 3:
        return warn(msg + f"，但 {n} 個**全部只出現一次** —— "
                    "標籤的用途是把報告連起來，全不重複等於這一期誰也連不到誰")
    return ok(msg)


register(Check(
    id="research.tags_wellformed",
    covers="digest 裡每份報告的 tags 數量在 anchors.tags.per_report 內、"
           "每個標籤是不含空白標點且不超過 12 字的短詞；"
           "`anchors.tags.vocab` 非 null 時另驗值域",
    blind_to=[
        "**標籤下得對不對** —— 這條只驗數量與字形，不驗它是否真的描述了這份報告",
        "**同義詞分裂** —— 「資料中心」與「數據中心」在這裡是兩個合格的標籤"
        "（詞表訂了以後才擋得住）",
        "四類（地區／資產／主題／政策）有沒有各取一個 —— 那是取樣方向不是硬規則",
        "跨期的標籤漂移（這條只看眼前這一期）",
        "只跑入庫的輪次（SKIPPED）",
    ],
    run=_tags_wellformed,
    fixture={"anchors": {"tags": {"per_report": [3, 6], "vocab": None}},
             "digest": {"reports": [{"slug": "a", "tags": ["聯準會", "原油"]}]}},
    near_miss={"anchors": {"tags": {"per_report": [3, 6], "vocab": None}},
               "digest": {"reports": [{"slug": "a", "tags": ["聯準會", "原油", "美國"]},
                                      {"slug": "b", "tags": ["聯準會", "日本", "公債"]}]}},
    suite="research",
))


# ── 12. 圖檔真的在資料 repo 裡 ──────────────────────────────────────
def _chart_files_present(p):
    """**這條擋的是「每一個訊號都說成功，而讀者拿到 404」。**

    `chart_grounded` 驗的是圖裡的數字有沒有出處 —— 那是內容。
    這條驗的是那個檔案到底在不在該在的地方 —— 那是**低一階、但獨立**的維度，
    而 2026-08-21 每日五圖那次證明了：內容全綠不代表檔案推得出去。

    圖由 `assemble.py` 複製進 repo，它跑在 Cowork 的掛載視角下；
    資料夾沒接上那一步就做不到，而發布這條線完全不受影響 ——
    JSON 照上線、網站照更新、回執照寫 exit 0。
    """
    files = p.get("chart_files")
    if files is None:
        return skipped("payload 沒帶 chart_files —— 這一輪沒有資料 repo 可看"
                       "（`research_verify` 走的就是這條路）。"
                       "**跟「檔案都在」是兩件事**")
    digest = p.get("digest")
    if digest is None:
        return skipped("這一輪沒有第 2 層產出（只跑了入庫）")
    want = [(r.get("slug", "?"), c[k]) for r in digest.get("reports") or []
            for c in (r.get("charts") or []) for k in ("png", "svg") if c.get(k)]
    if not want:
        return ok("這一期沒有重製圖 —— 0 張是允許的")
    miss = [f"{s[:26]}／{n}" for s, n in want if files.get(n) is None]
    if miss:
        return fail("；".join(miss[:5]) + f"（共 {len(miss)} 個）—— "
                    "**digest 指名的圖檔不在資料 repo 裡**。"
                    "發布不會因此失敗，網站也會照常更新，讀者拿到的是 404。"
                    "多半是 `~/broker-research-digest` 沒接上 Cowork，"
                    "`assemble.py` 那一步做不到")
    empty = [f"{s[:26]}／{n}" for s, n in want if files.get(n) == 0]
    if empty:
        return fail("；".join(empty[:5]) + " —— 檔案在但是 0 位元組。"
                    "**這跟「沒複製進來」是兩件事**：那是渲染壞了")
    return ok(f"{len(want)} 個圖檔都在 repo 裡（"
              f"{sum(files[n] for _, n in want) // 1024:,} KB）")


register(Check(
    id="research.chart_files_present",
    covers="digest 裡每張圖宣稱的 png／svg 都在資料 repo 的 charts/<週次>/ 底下且非空",
    blind_to=[
        "**檔案在本機但沒進版控** —— 這條看檔案系統，看不見 git；"
        "那一格由 publish 步驟 4b 的對帳負責",
        "圖檔在但畫的是錯的資料（那是 `chart_grounded` 的事，且它也只驗數字有出處）",
        "PNG 大小正常但內容是一張空白圖",
        "**沒有資料 repo 的輪次整條跳過**（SKIPPED，不是 PASS）—— "
        "`research_verify` 永遠走這一條",
        "上一期的圖不見了（這條只看眼前這一期宣稱的檔）",
    ],
    run=_chart_files_present,
    fixture={"anchors": {}, "chart_files": {"a-1.png": 100, "a-1.svg": None},
             "digest": {"reports": [{"slug": "a", "charts": [
                 {"png": "a-1.png", "svg": "a-1.svg"}]}]}},
    near_miss={"anchors": {}, "chart_files": {"a-1.png": 100, "a-1.svg": 40},
               "digest": {"reports": [{"slug": "a", "charts": [
                   {"png": "a-1.png", "svg": "a-1.svg"}]}]}},
    suite="research",
))


# ── 13. 立場帳本：到期就要有人回頭判 ────────────────────────────────
def _ledger_no_overdue(p):
    """**這條是這個庫從「讀物」變回「證據」的那一根線。**

    使用者當初要的是「未來驗證用」。而一筆記下來的立場，如果沒有任何機制
    在三個月後叫人回頭判，那它跟一段讀過就算的文字沒有差別 ——
    **而兩者在檔案裡長得一模一樣。**

    形狀直接沿用 podcast 的 `ledger_no_overdue`（那套已經跑得好好的），
    只有寬限期不同：週頻的東西逾期一週只代表一次機會沒做，日頻的代表七次。
    **門檻要跟節奏走。**
    """
    led = p.get("ledger")
    if led is None:
        return skipped("payload 沒帶帳本 —— 這一輪沒有資料 repo 可看。"
                       "**跟「都判完了」是兩件事**")
    O = _A(p, "observations")
    grace, vocab = O["overdue_grace_days"], O["status_vocab"]
    now = dt.date.fromisoformat((p.get("now") or "")[:10]) if p.get("now") else None
    if now is None:
        return skipped("payload 沒帶 now")
    items = led.get("items") or []
    if not items:
        return ok("帳本是空的 —— 還沒有立場入帳")
    bad = [i for i in items if i.get("status") not in vocab]
    if bad:
        return fail(f"{len(bad)} 筆的 status 不在受控詞表裡："
                    f"{sorted({i.get('status') for i in bad})[:4]} —— 值域的家在 "
                    "`anchors.observations.status_vocab`，**跟 podcast 共用一套**")
    over = []
    for i in items:
        if i.get("status") != vocab[0] or not i.get("due"):
            continue
        try:
            d = (now - dt.date.fromisoformat(i["due"])).days
        except ValueError:
            continue
        if d > 0:
            over.append((d, i))
    if not over:
        watching = sum(1 for i in items if i.get("status") == vocab[0])
        judged = len(items) - watching
        return ok(f"{len(items)} 筆立場，觀察中 {watching}、已判 {judged}，沒有逾期")
    over.sort(reverse=True, key=lambda x: x[0])
    worst = over[0][0]
    names = "、".join(i["id"][:34] for _, i in over[:3])
    tail = f"…共 {len(over)} 筆" if len(over) > 3 else ""
    msg = f"{len(over)} 筆逾期未判（最久 {worst} 天）：{names}{tail}"
    return (fail(msg + f" —— 超過 {grace} 天的寬限期。"
                 "**放著不判，這個庫就只是一堆讀過的字**")
            if worst > grace else warn(msg))


register(Check(
    id="research.ledger_no_overdue",
    covers="`data/stances.json` 裡沒有已過到期日、卻仍是「觀察中」的立場"
           "（超過 anchors.observations.overdue_grace_days 才判 FAIL）；"
           "且每筆的 status 都在受控詞表裡",
    blind_to=[
        "**判決下得對不對** —— 這條只看有沒有人判，不看判得準不準",
        "**為了讓燈變綠而全部改判「無法驗證」** —— 擋不住，"
        "而那正是這種檢查最容易誘發的行為",
        "到期日訂得合不合理（報告日期 + 3 個月是慣例不是規則）",
        "同一份報告的多筆立場其實該一起判",
        "**沒有資料 repo 的輪次整條跳過**（SKIPPED，不是 PASS）",
    ],
    run=_ledger_no_overdue,
    fixture={"anchors": {"observations": {"overdue_grace_days": 14,
                                          "status_vocab": ["觀察中", "應驗"]}},
             "now": "2026-12-31T00:00:00Z",
             "ledger": {"items": [{"id": "a", "status": "觀察中", "due": "2026-09-01"}]}},
    near_miss={"anchors": {"observations": {"overdue_grace_days": 14,
                                            "status_vocab": ["觀察中", "應驗"]}},
               "now": "2026-09-01T00:00:00Z",
               "ledger": {"items": [{"id": "a", "status": "觀察中", "due": "2026-12-01"}]}},
    suite="research",
))


# ── 14. 圖表規格填在該填的欄位裡 ────────────────────────────────────
def _chart_spec_wellformed(p):
    """**每一種圖型的資料住在自己的欄位裡，不是統一用 `series`。**

    2026-08-22 實測到的失效：野村那張 `waterfall` 的數字被寫進 `groups`
    （那是 `grouped_bar` 的欄位），而 `_draw_waterfall` 讀的是 `vals` ——
    於是它 zip 一個空陣列、**一根柱子都沒畫、沒有丟任何例外**、
    PNG 正常寫出、`chart_files_present` 看到 109 KB 判過。

    > **守衛量的是「檔案在不在、有多大」，比它宣稱保護的東西（圖上有沒有東西）低一階。**

    值域的家在 `chart/anchors.json` 的 `kinds` —— 那張表 2026-08-20 就是為了
    同一個問題建的（「這張表不存在的時候，`series` 是空的看起來就像資料掉了」）。
    這裡讀它，不抄它。
    """
    digest = p.get("digest")
    if digest is None:
        return skipped("這一輪沒有第 2 層產出（只跑了入庫）")
    ca = p.get("chart_anchors")
    if not ca or "kinds" not in ca:
        return fail("payload 沒帶每日五圖的 anchors —— **圖型與欄位的對照表的家在那裡**，"
                    "拿不到就沒有資格判")
    K = ca["kinds"]
    known = {k: v for k, v in K.items() if isinstance(v, dict) and "data" in v}
    bad = []
    n = 0
    for r in digest.get("reports") or []:
        for c in r.get("charts") or []:
            n += 1
            kind, title = c.get("kind"), (c.get("title") or "?")[:20]
            if kind not in known:
                bad.append(f"{title}：`kind` 是「{kind}」，不在 {sorted(known)}")
                continue
            for fld in known[kind]["data"]:
                v = c.get(fld)
                if not v:
                    bad.append(f"{title}：`{kind}` 要 `{fld}`，而它是空的 —— "
                               f"**這張會畫成空白圖而且不丟例外**")
            # 類別軸圖型：每一組的長度要跟 cats 對得上（ECharts 按位置貼，錯位不報錯）
            for g in c.get("groups") or []:
                if len(g.get("values") or []) != len(c.get("cats") or []):
                    bad.append(f"{title}：組「{g.get('name','?')[:14]}」有 "
                               f"{len(g.get('values') or [])} 個值，"
                               f"而 `cats` 有 {len(c.get('cats') or [])} 個 —— **會整條位移**")
    if bad:
        return fail("；".join(bad[:4]) + (f"（共 {len(bad)} 項）" if len(bad) > 4 else ""))
    return ok(f"{n} 張圖的資料都填在該填的欄位裡" if n else "這一期沒有重製圖")


register(Check(
    id="research.chart_spec_wellformed",
    covers="每張圖的 `kind` 在 chart/anchors.json 的 kinds 表裡，"
           "且該圖型宣告的每個 data 欄位都非空；類別軸圖型每組的值數等於 cats 數",
    blind_to=[
        "**欄位填了但數字是錯的** —— 這條只驗形狀，數字對不對是 `chart_grounded` 的事",
        "選型恰不恰當（用長條圖畫時間序列這條看不出來）",
        "`optional` 欄位漏填造成的降級（例如 waterfall 沒給 `total_label`）",
        "渲染時才會炸的東西（那是 `chart_files_present` 與 `chart_grounded` 的 render_error）",
        "只跑入庫的輪次（SKIPPED）",
    ],
    run=_chart_spec_wellformed,
    fixture={"anchors": {},
             "chart_anchors": {"kinds": {"waterfall": {"data": ["cats", "vals"]}}},
             "digest": {"reports": [{"charts": [
                 {"kind": "waterfall", "title": "t", "cats": ["a"],
                  "groups": [{"name": "g", "values": [1]}]}]}]}},
    near_miss={"anchors": {},
               "chart_anchors": {"kinds": {"waterfall": {"data": ["cats", "vals"]}}},
               "digest": {"reports": [{"charts": [
                   {"kind": "waterfall", "title": "t", "cats": ["a"], "vals": [1]}]}]}},
    suite="research",
))


# ── 15. 這一批是不是同一支抽取器抽的 ────────────────────────────────
def _one_engine(p):
    """**兩軌對同一份 PDF 可能給不同答案。**

    `pdftotext` 與 `pdfplumber` 對旋轉文字、欄位分隔、空白的處理都不同 ——
    2026-08-21 的浮水印剃除與券商辨識就是在這個差異上壞過一次
    （沙箱 7/7、發布機 6/7）。

    混軌的一批，**每一份自己都完全合格**，但跨份的比較不再成立：
    「這家的頁首剃得比較乾淨」可能只是它被另一支抽的。
    而這件事在產出上完全看不出來 —— 十八份摘要讀起來一樣正常。

    這條不驗「兩軌會不會給一樣的答案」（那要雙倍抽取，成本在 anchors 裡有記），
    只驗**這一批有沒有混軌**。前者是抽驗，後者是每一輪都該成立的前提。
    """
    docs = _docs(p)
    if not docs:
        return skipped("這一輪沒有抽取結果")
    by = {}
    for d in docs:
        by.setdefault(d.get("engine") or "（沒記）", []).append(d.get("slug", "?"))
    if len(by) == 1:
        eng = next(iter(by))
        if eng == "（沒記）":
            return fail("整批都沒有記 `engine` —— **抽取器是誰抽的都不知道，"
                        "就沒有資格說這一批可以互相比較**")
        return ok(f"{len(docs)} 份全部由 {eng} 抽")
    lines = [f"{e}（{len(v)} 份：{v[0][:30]}…）" for e, v in sorted(by.items())]
    return warn("；".join(lines) + " —— **這一批是混軌抽的**。"
                "每一份自己都合格，但跨份的比較不再成立；"
                "要比較之前整批用同一支重抽（`extract.py --force`）")


register(Check(
    id="research.one_engine",
    covers="這一批抽取結果全部由同一支抽取器產生，且每一份都記了 engine",
    blind_to=[
        "**兩軌對同一份檔會不會給出不同答案** —— 這條只看有沒有混軌，"
        "不看兩軌一不一致。後者要雙倍抽取，形態是抽驗不是常設",
        "同一支抽取器的不同版本（`engine` 只記名字不記版本）",
        "整批用同一支、但那一支對這幾份就是抽得不好",
        "只跑第 2 層而沒有重抽的輪次（docs 沿用上一輪的）",
        "**刻意的混軌與手滑的混軌** —— 2026-08-31 起 `extract.py` 有逐檔退路"
        "（主抽取器把第一頁抽成空的時換下一支），換過軌的那一份帶著 "
        "`engine_fallback` 欄位，而這條只數 `engine` 有幾種、不看那個欄位。"
        "**要分辨哪一種，看 `extract.py` 印的那份具名清單。**",
    ],
    run=_one_engine,
    fixture={"anchors": {},
             "docs": [{"slug": "a", "engine": "pdftotext"},
                      {"slug": "b", "engine": "pdfplumber"}]},
    near_miss={"anchors": {},
               "docs": [{"slug": "a", "engine": "pdftotext"},
                        {"slug": "b", "engine": "pdftotext"}]},
    suite="research",
))


# ── 16. 標題是不是報告的真實標題 ────────────────────────────────────
def _title_resolved(p):
    """**這一條擋的是「檔名冒充標題」。**

    2026-08-23 之前，`title` 是檔名去副檔名。它壞成三種樣子，而只有一種看得見：

    - 野村五份的檔名是流水號（`1317180`）—— **會被看見**，而且是被回報的那一種。
    - GS 的檔名被下載端截在 128 字元 —— 尾巴斷掉，讀起來仍然像個標題。
    - 花旗的檔名只有系列名（`Oil Monitor`）—— **完全看不出來**，
      而真正的標題是「Oil Monitor: At visible draw rates, when do we…」。

    第三種是這條存在的理由。前兩種遲早有人回報，第三種**永遠不會有人回報**，
    因為它看起來就是一個好標題。所以判準不是「標題看起來對不對」，
    是**「它是從哪裡來的」** —— 那是唯一一個機器分得出來的維度。

    `title_source == "filename"` ＝ `title.py` 的對照表裡沒有這家券商的取法，
    或者兩個來源對不起來。兩種情況都該在發布前被看到。
    """
    docs = _docs(p)
    if not docs:
        return skipped("這一輪沒有抽取結果")
    miss = [d for d in docs if not d.get("title_source")]
    if miss:
        return fail(f"**{len(miss)} 份沒有 `title_source`** —— "
                    f"{[_name(d) for d in miss][:4]}。"
                    "抽取層比 `title.py` 舊，標題可能是檔名而沒有人知道")
    fn = [d for d in docs if d["title_source"] == "filename"]
    if fn:
        return fail(f"**{len(fn)} 份的標題還是檔名**："
                    + "；".join(f"{_name(d)}（{d.get('title_note') or '沒說原因'}）"
                               for d in fn[:4])
                    + "。新券商要先量過第一頁與 `/Title`，再加進 `title.py` 的對照表")
    weak = [d for d in docs if not d.get("title_confident")]
    by = {}
    for d in docs:
        by[d["title_source"]] = by.get(d["title_source"], 0) + 1
    line = "、".join(f"{k} {v} 份" for k, v in sorted(by.items()))
    if weak:
        return warn(f"{line}；**{len(weak)} 份取到了但不確定完整**："
                    + "；".join(f"{_name(d)}（{d.get('title_note')}）" for d in weak[:3]))
    return ok(f"{len(docs)} 份都取到真實標題（{line}）")


register(Check(
    id="research.title_resolved",
    covers="每一份的標題都不是檔名，且來源有記錄（`title_source`／`title_confident`）",
    blind_to=[
        "**取到的標題對不對** —— 這條只看它從哪裡來。內容要對，"
        "得跑 `title.py --selftest`（對著人工讀出來的 `title_fixture.json`）",
        "`pdf_meta` 被截在 139 字元而第一頁補得回來的那種：那會標成 `page_one` 且可信，"
        "這條看不出補過",
        "已經發布出去的舊標題 —— 這條只看眼前這一批（舊的由 `backfill_titles.py` 一次性處理）",
        "同一家券商換了排版：對照表照樣會回一個標題，只是可能是錯的那一段",
    ],
    run=_title_resolved,
    fixture={"anchors": {}, "docs": [
        {"slug": "a", "title_source": "filename", "title_confident": False,
         "title_note": "沒有 'Barclays' 的取法"}]},
    near_miss={"anchors": {}, "docs": [
        {"slug": "a", "title_source": "pdf_meta", "title_confident": True}]},
    suite="research",
))
