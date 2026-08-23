"""主題匯流訊號報的檢查。**payload 是一期，加上五個上游的原始資料。**

payload 形狀（由 `systems/convergence.py` 的 `build()` 組出來，檢查本身不做 IO）：

    {"draft":   單期 JSON,
     "corpora": {"adv","pod","cotd","res"} → 語料全文（缺就沒有這個鍵）,
     "bub":     監控庫的原始 data.json（**不是壓縮過的 bub.txt**）,
     "stances": 外資報告的 stances.json（選填）,
     "index":   資料 repo 的 data/index.json,
     "now":     ISO8601}

## 這一套的檢查在守什麼

其他五套守的是「自己產的東西對不對」。這一套守的是**「兩套系統之間的說法對不對得上」**，
所以它的每一條都跨庫：佐證要回查上游語料、量化數字要對回監控庫、
共振要數獨立來源、快照要跟趨勢圖的唯一資料來源逐欄等值。

## 四個聲音，門檻仍是三方

2026-08-23 加入外資報告之後，獨立來源從三個變四個：
**新聞側（投顧＋圖表計一票）／節目側／量化側／賣方側**。

**門檻沒有跟著提到四方。** 分析師寫的跟新聞報的常常是同一批事件，
四方到齊會罕見到不能用；而三方的價值本來就在「量化與敘事各自到達同一結論」。
多一個獨立來源是讓三方更容易被**驗證**，不是讓門檻更高。
"""
import datetime as dt
import html
import json
import re

from kbcore.check import Check, fail, ok, register, skipped, warn


# ── 共用 ────────────────────────────────────────────────────────────
def _d(p):
    return p.get("draft") or {}


def _secs(p):
    return _d(p).get("sections") or []


def _items(p):
    for s in _secs(p):
        for it in (s.get("items") or []):
            yield s, it


def clean(s):
    return re.sub(r"<[^>]+>", "", html.unescape(str(s))).strip()


def norm(s):
    """比對用：塌縮空白、折疊排版標點。

    跟外資報告的 `_norm` 同一個理由 —— 直引號／彎引號、各式破折號、
    標點旁多出來的空白都隨抽取器與輸入法而變，**逐字比會假性失敗，
    而假性失敗的樣子跟真的對不上一模一樣**。
    """
    t = clean(s).translate(str.maketrans({
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "−": "-", " ": " ", "　": " "}))
    return re.sub(r"\s+", " ", t).strip()


def clauses(text, min_len=8):
    """切出**所有** ≥min_len 的片段。

    **不是只取最長那一段。** 只驗最長段等於放生所有短片段裡的數字，
    而數字正是最容易抄錯的東西。
    """
    s = norm(text).split("｜")[-1]
    s = re.sub(r"^\([^)]*\)\s*", "", s)
    parts = re.split(r"[（）()【】「」，、,：:；;。]", s)
    return [x.strip() for x in parts if len(x.strip()) >= min_len]


# ── 四個聲音 ────────────────────────────────────────────────────────
# **投顧與圖表映到同一個 key，是刻意的。**
# 每日五圖的選題取自 advisory-knowledge-hub（見它自己的 about.upstream），
# 所以「投顧在講 ＋ 圖表也在畫」不構成兩個獨立來源 —— 那是同一則新聞被數兩次。
#
# **這張表寫在程式裡而不只是文件裡**，因為舊系統有兩次證明了
# 只寫在文件裡的規則會漂移（`events` 那次、樣本不足那次）。
VOICE = {
    "投顧": "narrative_adv",
    "圖表": "narrative_adv",   # ← 與投顧同一票，故意的
    "節目": "narrative_pod",
    "監控": "quant",
    "券商": "sellside",        # 2026-08-23 新增：上游是券商 PDF，與新聞不同源
}
MIN_VOICES = 3

# 章節組合：**由 `schemaVer` 決定，不是由日期決定。**
# 日期門檻是一個「記得改」的東西，而忘記改的那次不會有徵兆。
# 宣告寫在資料裡，兩個方向都擋得住：v2 卻沒有 `verdicts` → 對不上 v2 組；
# 沒宣告卻有 `verdicts` → 對不上任何舊組。
SECTION_SETS = {
    "2": ["resonance", "divergence", "verdicts", "taiwan", "charts", "single"],
    None: [["resonance", "divergence", "taiwan", "charts", "single"],   # v0.5–v1
           ["resonance", "divergence", "taiwan", "single"]],            # 第 001 期
}


# ── 1. 結構 ─────────────────────────────────────────────────────────
REQUIRED = ("date", "issue", "label", "range", "headline", "verdict",
            "quant", "sections", "watch", "gaps", "about")


def _structure(p):
    d, bad = _d(p), []
    for k in REQUIRED:
        if k not in d:
            bad.append(f"缺頂層欄位 `{k}`")
    q = d.get("quant") or {}
    for k in ("schemaVer", "composite", "zone", "stage", "twHeat",
              "quadrant", "triggers", "dims"):
        if k not in q:
            bad.append(f"缺 `quant.{k}`")

    ver = d.get("schemaVer")
    want = SECTION_SETS.get(ver)
    ids = [s.get("id") for s in _secs(p)]
    if want is None:
        bad.append(f"不認得的 `schemaVer`：{ver!r} —— **這裡刻意不猜**")
    elif isinstance(want[0], list):
        if ids not in want:
            bad.append(f"章節 id 與順序不合規：{ids}　應為 {want[0]}（或第 001 期的 {want[1]}）")
    elif ids != want:
        bad.append(f"章節 id 與順序不合規：{ids}　應為 {want}")

    for s in _secs(p):
        if not (s.get("items") or []):
            bad.append(f"「{s.get('title', s.get('id', '?'))[:14]}」節 items 為空 —— "
                       "真的沒訊號就寫一條說明 item，**不要留空節**")
    # 值域：composite 999 不該全綠通過
    for name, v in (("composite", q.get("composite")), ("twHeat", q.get("twHeat"))):
        if isinstance(v, (int, float)) and not 0 <= v <= 100:
            bad.append(f"`quant.{name}`={v} 超出 0–100")
    for x in (q.get("dims") or []):
        if isinstance(x.get("v"), (int, float)) and not 0 <= x["v"] <= 100:
            bad.append(f"dims.{x.get('id')} v={x['v']} 超出 0–100")
    for k, v in (q.get("quadrant") or {}).items():
        if k in ("heat", "support") and isinstance(v, (int, float)) and not 0 <= v <= 100:
            bad.append(f"quadrant.{k}={v} 超出 0–100")
    if bad:
        return fail("；".join(bad[:6]) + (f"　…另外 {len(bad)-6} 項" if len(bad) > 6 else ""))
    return ok(f"{len(ids)} 節、必備欄位齊全、值域都在 0–100")


register(Check(
    id="convergence.structure",
    covers="必備頂層欄位、`quant` 必填鍵、章節 id 與順序（依 `schemaVer`）、"
           "每節至少一個 item、量化值在 0–100",
    blind_to=[
        "**item 的內容有沒有價值** —— 這條只看結構，一條「本週無」的說明 item 一樣過",
        "`headline` 與 `verdict` 是不是真的表態（規格要求表態，機器看不出來）",
        "章節組合表本身訂得對不對 —— 它只驗資料合不合表",
        "**新增一種 `schemaVer` 而忘記加進 `SECTION_SETS`** —— 那會被判成不認得而 FAIL，"
        "方向是對的，但錯誤訊息會指向資料而不是這張表",
    ],
    run=_structure,
    fixture={"draft": {"date": "2026-08-16", "sections": [{"id": "resonance", "items": []}]}},
    # **near_miss 要真的長得像一期**，不能用 `{k: 1 for k in REQUIRED}` 充數 ——
    # 那樣 `dims` 會變成不可迭代的 `1`，檢查在 near_miss 上直接爆掉，
    # 而「爆掉」與「不通過」在自檢眼裡是同一件事：這條檢查因此**永遠不會 PASS**。
    # 2026-08-23 自檢當場抓到，這正是 fixture／near_miss 機制存在的理由。
    near_miss={"draft": {
        "date": "2026-08-16", "issue": 3, "label": "第 003 期", "range": {},
        "headline": "h", "verdict": ["a", "b", "c"], "watch": [], "gaps": ["g"],
        "about": {},
        "quant": {"schemaVer": "v2", "composite": 66.6, "zone": "z",
                  "stage": {"current": 2.6}, "twHeat": 57.3,
                  "quadrant": {"heat": 68.0, "support": 63.9},
                  "triggers": [], "dims": [{"id": "L1", "v": 61.2}]},
        "sections": [{"id": i, "items": [{"title": "x"}]}
                     for i in SECTION_SETS[None][0]]}},
    suite="convergence",
))


# ── 2. index 快照逐欄對帳 ───────────────────────────────────────────
def _index_snapshot(p):
    """**趨勢圖的唯一資料來源就是這一份快照。**

    舊系統的頭號隱性事故：快照漏一欄，趨勢圖少一個點，**頁面不會報錯**，
    而歷史永不改寫 —— 那個缺口會永遠留在線上。所以這裡逐欄等值比，
    不是「欄位存在就算」。
    """
    d = _d(p)
    idx = p.get("index") or {}
    days = idx.get("days")
    if days is None:
        return fail("`index.json` 沒有 `days` —— **舊版用的是 `issues`**，"
                    "而 `tools/publish.py`／`verify_site_index.py`／哨兵全部走 `days`。"
                    "要先跑索引鍵遷移")
    me = next((x for x in days if x.get("date") == d.get("date")), None)
    if me is None:
        return skipped("索引裡還沒有本期 —— 發布時由 `publish.py` 寫入，這裡跳過")
    import systems.convergence as sysconv
    want = sysconv.index_entry(d)
    bad = [f"`{k}`：索引 {me.get(k)!r} ≠ 應為 {v!r}"
           for k, v in want.items() if k != "errata" and me.get(k) != v]
    if bad:
        return fail("；".join(bad[:5]) + " —— **趨勢圖讀的就是這一份**")
    return ok(f"快照 {len(want)} 欄與本期逐欄相符")


register(Check(
    id="convergence.index_snapshot",
    covers="`index.json` 本期那一筆的每一欄，與單期 JSON 算出來的值逐欄相等",
    blind_to=[
        "**索引裡還沒有本期的輪次**（回 SKIPPED）—— 那是發布前的正常狀態",
        "更舊的幾期被悄悄改過 —— 這條只看本期那一筆",
        "快照的欄位選得對不對（`index_entry` 決定要帶哪幾欄，這條只驗它帶的那些對不對）",
    ],
    run=_index_snapshot,
    fixture={"draft": {"date": "2026-08-16", "quant": {"composite": 66.6}},
             "index": {"days": [{"date": "2026-08-16", "composite": 11.1}]}},
    no_boundary="逐欄等值比對，沒有門檻——相等或不相等，沒有中間狀態",
    suite="convergence",
))


# ── 3. evidence[].s 是封閉集合 ──────────────────────────────────────
def _evidence_source(p):
    """`s` 打錯字會讓 `VOICE.get()` 回 None 而**靜靜地少一票**，
    而下游的錯誤訊息還會誤導成「來源不夠獨立」。先把非法值擋下來。
    """
    bad, n = set(), 0
    for _, it in _items(p):
        for e in (it.get("evidence") or []):
            n += 1
            if e.get("s") not in VOICE:
                bad.add(str(e.get("s")))
    if bad:
        return fail(f"`evidence[].s` 有非法值 {sorted(bad)} —— "
                    f"合法值只有 {sorted(VOICE)}")
    return ok(f"{n} 條佐證的來源都在合法集合裡（{len(VOICE)} 個值、{len(set(VOICE.values()))} 個獨立聲音）")


register(Check(
    id="convergence.evidence_source",
    covers="每一條 `evidence[].s` 都在五個合法值裡（監控／投顧／節目／圖表／券商）",
    blind_to=[
        "**標成合法但標錯家** —— 「這句其實是節目說的卻標成投顧」由 "
        "`evidence_grounded` 的逐來源回查抓，不是這條",
        "`list[]` 裡的 `src` —— 那是自由文字，不受這個集合約束",
    ],
    run=_evidence_source,
    fixture={"draft": {"sections": [{"id": "resonance", "items": [
        {"evidence": [{"s": "圖表庫"}]}]}]}},
    no_boundary="集合成員判定，沒有門檻",
    suite="convergence",
))


# ── 4. 共振的來源獨立性 ─────────────────────────────────────────────
def _resonance_independent(p):
    bad = []
    for s, it in _items(p):
        if s.get("id") != "resonance":
            continue
        tags = " ".join(t.get("t", "") for t in (it.get("tags") or []))
        if "共振" not in tags:
            continue
        voices = {VOICE.get(e.get("s")) for e in (it.get("evidence") or [])} - {None}
        if len(voices) < MIN_VOICES:
            srcs = sorted({e.get("s") for e in (it.get("evidence") or [])} - {None})
            bad.append(f"{clean(it.get('title', '(無標題)'))[:34]}｜來源 {srcs} → "
                       f"只有 {len(voices)} 個獨立聲音")
    if bad:
        return fail(f"{len(bad)} 條標為「共振」的 item 不到 {MIN_VOICES} 個獨立來源："
                    + "；".join(bad[:3])
                    + " —— **投顧與圖表計為同一票**（圖表的選題取自投顧庫）")
    n = sum(1 for s, it in _items(p) if s.get("id") == "resonance")
    return ok(f"共振節 {n} 條 item，獨立來源都達 {MIN_VOICES} 個以上")


register(Check(
    id="convergence.resonance_independent",
    covers="`resonance` 節裡標了「共振」的 item，佐證要來自至少三個獨立聲音；"
           "投顧與圖表映到同一個聲音",
    blind_to=[
        "**沒標「共振」tag 的 item** —— 這條靠 tag 認，不標就不驗。"
        "把共振寫進 `divergence` 節也繞得過去",
        "**三個聲音但講的其實不是同一件事** —— 機器數的是來源，不是語意",
        "**弱同源** —— 監控庫的每週質化覆核用 WebSearch 打分，有可能搜到券商報告的轉述。"
        "那是偶發、非結構性的重疊，處置是寫進 `gaps`，這條看不到",
    ],
    run=_resonance_independent,
    fixture={"draft": {"sections": [{"id": "resonance", "items": [
        {"title": "t", "tags": [{"t": "共振"}],
         "evidence": [{"s": "投顧"}, {"s": "圖表"}]}]}]}},
    near_miss={"draft": {"sections": [{"id": "resonance", "items": [
        {"title": "t", "tags": [{"t": "共振"}],
         "evidence": [{"s": "投顧"}, {"s": "圖表"}, {"s": "節目"}, {"s": "監控"}]}]}]}},
    suite="convergence",
))


# ── 5. 敘事佐證逐來源逐字回查 ───────────────────────────────────────
SRC_CORPUS = {"投顧": "adv", "節目": "pod", "圖表": "cotd", "券商": "res"}


def _evidence_grounded(p):
    corp = p.get("corpora")
    if not corp:
        return skipped("這一輪沒有語料 —— **跟「回查過、都對」是兩件事**。"
                       "離線稽核走這條；發布時 `build()` 會先 raise")
    bad, n = [], 0
    for _, it in _items(p):
        for e in (it.get("evidence") or []):
            src = e.get("s")
            key = SRC_CORPUS.get(src)
            if not key:
                continue          # 監控側走 quant_grounded，不在這裡驗
            hay = norm(corp.get(key, ""))
            n += 1
            for frag in clauses(e.get("t", "")):
                if frag not in hay:
                    # **逐來源比對**：標錯 s 時要說得出「在別的來源找得到」
                    elsewhere = [s2 for s2, k2 in SRC_CORPUS.items()
                                 if k2 != key and frag in norm(corp.get(k2, ""))]
                    why = f"（在{'／'.join(elsewhere)}找得到 —— **`s` 標錯家**）" if elsewhere else ""
                    bad.append(f"[{src}] 「{frag[:26]}…」{why}")
    if bad:
        return fail(f"{len(bad)} 個片段在宣稱的來源裡找不到：" + "；".join(bad[:4])
                    + " —— 沒有原句的判斷要歸到 `crosscut`／自己的話，不要標成佐證")
    return ok(f"{n} 條敘事佐證的每一個片段都在宣稱的來源裡逐字找得到")


register(Check(
    id="convergence.evidence_grounded",
    covers="每一條敘事佐證（投顧／節目／圖表／券商）的**所有**片段，"
           "都能在它宣稱的那一份語料裡逐字找到",
    blind_to=[
        "**沒有語料的輪次整條跳過**（SKIPPED，不是 PASS）",
        "**逐字對得上但斷章取義** —— 前後文翻轉語意，機械比對看不到",
        "**中譯是錯的** —— `quote_zh` 沒有任何驗證",
        "語料本身被截斷掉的那一段 —— 摘要層有字數上限，被截掉的原句會變成假 FAIL",
        "監控側的佐證（那是 `quant_grounded` 的事）",
    ],
    run=_evidence_grounded,
    fixture={"draft": {"sections": [{"id": "resonance", "items": [
        {"evidence": [{"s": "投顧", "t": "這句話語料裡完全沒有出現過"}]}]}]},
        "corpora": {"adv": "別的內容", "pod": "", "cotd": "", "res": ""}},
    near_miss={"draft": {"sections": [{"id": "resonance", "items": [
        {"evidence": [{"s": "投顧", "t": "信用利差正在收斂"}]}]}]},
        "corpora": {"adv": "本週  信用利差正在收斂  而股市沒動", "pod": "", "cotd": "", "res": ""}},
    suite="convergence",
))


# ── 6. 量化佐證：欄位存在、且不得取自 events ────────────────────────
CODE_RX = re.compile(r"<code>([a-z0-9_]+)</code>")


def _quant_grounded(p):
    bub = p.get("bub")
    if not bub:
        return skipped("這一輪沒有監控庫快照 —— 跟「對過、都對」是兩件事")
    legal = {i.get("id") for i in (bub.get("indicators") or [])}
    legal |= {t.get("id") for t in (bub.get("triggers") or [])}
    legal |= set((bub.get("dims") or {}).keys())
    legal |= {i.get("id") for i in ((bub.get("tw") or {}).get("items") or [])}
    legal |= {"composite", "twHeat", "stage", "quadrant"}
    ev_txt = [e.get("t", "") for _, it in _items(p) for e in (it.get("evidence") or [])
              if e.get("s") == "監控"]
    bad, unmarked = [], 0
    for t in ev_txt:
        ids = CODE_RX.findall(t)
        if not ids:
            unmarked += 1
            continue
        for i in ids:
            if i not in legal:
                bad.append(f"`{i}` 不是監控庫的合法欄位名")
    # events 同源：`events` 本身就是 Google News，拿它當量化證據
    # 等於把投顧側的新聞當成量化側的第二票。**那是假共振。**
    evt = {norm(e.get("t", "")) for e in (bub.get("events") or [])}
    leaked = [t[:30] for t in ev_txt
              if any(norm(t) and norm(t) in x for x in evt)]
    if leaked:
        bad.append(f"{len(leaked)} 條量化佐證取自 `events`（同源）：{leaked[:2]}")
    if bad:
        return fail("；".join(bad[:5]))
    if unmarked:
        return warn(f"{len(ev_txt)} 條量化佐證裡有 {unmarked} 條沒有用 `<code>` 標欄位名 —— "
                    "**檢查對那幾條形同空轉**")
    return ok(f"{len(ev_txt)} 條量化佐證的欄位名都合法，且沒有取自 `events`")


register(Check(
    id="convergence.quant_grounded",
    covers="監控側佐證用 `<code>` 標的欄位名確實存在於監控庫，且佐證沒有取自 `events`",
    blind_to=[
        "**沒有監控庫快照的輪次整條跳過**（SKIPPED，不是 PASS）",
        "**沒包 `<code>` 的那幾條** —— 出 WARN 不出 FAIL，因為純中文描述門檻"
        "（「高收益債利差偏低」）在語法上無法與正常敘述區分",
        "**欄位名合法但數字抄錯** —— 那是 `quant_reconcile` 的事",
        "`events` 的比對是逐句包含，改寫過的引用抓不到",
    ],
    run=_quant_grounded,
    fixture={"draft": {"sections": [{"id": "divergence", "items": [
        {"evidence": [{"s": "監控", "t": "指標 <code>nosuchid</code> 走闊"}]}]}]},
        "bub": {"indicators": [{"id": "hyoas"}]}},
    near_miss={"draft": {"sections": [{"id": "divergence", "items": [
        {"evidence": [{"s": "監控", "t": "指標 <code>hyoas</code> 走闊"}]}]}]},
        "bub": {"indicators": [{"id": "hyoas"}]}},
    suite="convergence",
))


# ── 7. 量化對帳：現值與變動 vs history，不跨改版 ────────────────────
def _quant_reconcile(p):
    """**基準必須與現值同架構。**

    監控庫 2026-08-04 由 v1 六維（`D1`–`D6`）改成 v2 三層（`L1`/`L2`/`L3`），
    兩者分群邏輯根本不同。**禁止互相映射** —— 硬接起來就是假的趨勢，
    而跨期趨勢正是這一套相對於「翻舊文章」的唯一差異。

    另一個容易寫錯的地方：變動是對**現值**算的，不是對 `history` 最後一筆。
    監控庫盤後更新時 `history` 會落後頂層一格。
    """
    bub, d = p.get("bub"), _d(p)
    if not bub:
        return skipped("這一輪沒有監控庫快照")
    q = d.get("quant") or {}
    bad = []
    top = bub.get("dims") or {}
    for x in (q.get("dims") or []):
        i = x.get("id")
        if i in top and x.get("v") != top[i]:
            bad.append(f"dims.{i} 期刊 {x.get('v')} ≠ 監控庫 {top[i]}")
    for k, mine, theirs in (("composite", q.get("composite"), bub.get("composite")),
                            ("twHeat", q.get("twHeat"), (bub.get("tw") or {}).get("heat"))):
        if theirs is not None and mine != theirs:
            bad.append(f"{k} 期刊 {mine} ≠ 監控庫 {theirs}")
    # 觸發器：條數與 id 以監控庫為準，**不要挑** —— 沒亮的那幾條本身就是資訊
    mine = {t.get("id"): t.get("state") for t in (q.get("triggers") or [])}
    theirs = {t.get("id"): t.get("state") for t in (bub.get("triggers") or [])}
    if set(mine) != set(theirs):
        miss, extra = sorted(set(theirs) - set(mine)), sorted(set(mine) - set(theirs))
        bad.append(f"觸發器對不上 —— 少了 {miss}、多了 {extra}。"
                   "**條數與 id 以監控庫為準，不要挑**")
    else:
        for i in mine:
            if bool(mine[i]) != bool(theirs[i]):
                bad.append(f"觸發器 `{i}` state 期刊 {mine[i]} ≠ 監控庫 {theirs[i]}")
    # 基準同架構
    hist = bub.get("history") or []
    keys = {x.get("id") for x in (q.get("dims") or [])}
    same = [h for h in hist if set((h.get("dims") or {}).keys()) == keys]
    if keys and not same:
        bad.append(f"`history` 裡找不到與現值同架構（{sorted(keys)}）的基準 —— "
                   "**禁止把 v1 的 D1–D6 映射到 v2 的 L1–L3**")
    if bad:
        return fail("；".join(bad[:5]))
    return ok(f"dims／composite／twHeat／觸發器 {len(theirs)} 條與監控庫逐欄相符")


register(Check(
    id="convergence.quant_reconcile",
    covers="`quant` 抄寫的欄位與監控庫逐欄等值；觸發器 id 集合與 state 相符；"
           "`history` 裡有與現值同架構的基準",
    blind_to=[
        "**沒有監控庫快照的輪次整條跳過**（SKIPPED，不是 PASS）",
        "**「本期變動」那個數字算得對不對** —— 這條只驗基準存在且同架構，不重算差值",
        "監控庫自己算錯的情況 —— 這條以它為準",
        "`stage.lit` 的兩種算法落差（骨架 truthy 計數 vs 上游 note 的 0.5 累加）—— "
        "**機制不同，不是誰算錯**",
    ],
    run=_quant_reconcile,
    fixture={"draft": {"quant": {"composite": 11.1, "dims": [], "triggers": []}},
             "bub": {"composite": 66.6, "dims": {}, "triggers": [], "history": []}},
    near_miss={"draft": {"quant": {"composite": 66.6, "dims": [], "triggers": []}},
               "bub": {"composite": 66.6, "dims": {}, "triggers": [], "history": []}},
    suite="convergence",
))


# ── 8. watch 綁 trigger id ──────────────────────────────────────────
def _watch_bound(p):
    bub = p.get("bub")
    if not bub:
        return skipped("這一輪沒有監控庫快照")
    trig = {t.get("id") for t in (bub.get("triggers") or [])}
    ind = {i.get("id") for i in (bub.get("indicators") or [])}
    ws = _d(p).get("watch") or []
    bad = []
    for w in ws:
        t = w if isinstance(w, str) else json.dumps(w, ensure_ascii=False)
        for i in CODE_RX.findall(t):
            if i in trig:
                continue
            if i in ind:
                # **標成合法的 indicator id 是最危險的那一種**：
                # `ccc` 本身合法，過度標記檢查會放它過，而下一期沒東西可驗收。
                bad.append(f"`{i}` 是 indicator 不是 trigger —— "
                           f"是不是想標 {sorted(x for x in trig if x.startswith(i))[:1] or '對應的 trigger'}？")
            else:
                bad.append(f"`{i}` 既不是 trigger 也不是 indicator")
    if bad:
        return fail("；".join(bad[:4]))
    marked = sum(1 for w in ws if CODE_RX.search(
        w if isinstance(w, str) else json.dumps(w, ensure_ascii=False)))
    if ws and not marked:
        return warn(f"{len(ws)} 條 watch **一條都沒有綁 trigger id** —— "
                    "純中文描述門檻的條目機器擋不了，下一期會沒有東西可以驗收")
    return ok(f"{len(ws)} 條 watch，{marked} 條綁了正確的 trigger id")


register(Check(
    id="convergence.watch_bound",
    covers="`watch` 裡用 `<code>` 標的 id 確實是 trigger（不是 indicator、不是打錯字）",
    blind_to=[
        "**沒有監控庫快照的輪次整條跳過**（SKIPPED，不是 PASS）",
        "**整條用中文描述門檻、明文裡根本沒有 id** —— 出 WARN 不出 FAIL，"
        "因為「這條該不該綁 trigger」機器判不了",
        "綁對了 id 但門檻描述與 trigger 的定義不一致",
    ],
    run=_watch_bound,
    fixture={"draft": {"watch": ["殖利率破 5%（<code>ccc</code>）"]},
             "bub": {"triggers": [{"id": "ccc12"}], "indicators": [{"id": "ccc"}]}},
    near_miss={"draft": {"watch": ["信用轉弱（<code>ccc12</code>）"]},
               "bub": {"triggers": [{"id": "ccc12"}], "indicators": [{"id": "ccc"}]}},
    suite="convergence",
))


# ── 9. gaps 每期都要有 ──────────────────────────────────────────────
def _gaps_present(p):
    """**這一套順便是另外五套的健康度哨兵。**

    `gaps` 空著跟「五庫都很健康」長得一模一樣，而後者幾乎不可能為真
    （五庫的日期本來就不會對齊）。所以空陣列判 FAIL：真的沒缺口就寫一條說明。
    """
    g = _d(p).get("gaps")
    if g is None:
        return fail("缺 `gaps` 欄位 —— 這一套順便是另外五套的健康度哨兵")
    if not g:
        return fail("`gaps` 是空的 —— **空著跟「五庫都很健康」長得一模一樣**，"
                    "而五庫的日期本來就不會對齊。真的沒缺口就寫一條說明")
    return ok(f"{len(g)} 條資料缺口")


register(Check(
    id="convergence.gaps_present",
    covers="`gaps` 存在且非空",
    blind_to=[
        "**寫了但寫得敷衍** —— 這條只數條數",
        "**該查而沒查的那幾項** —— 五項清單（缺天／各庫 index 過期／指標 asof 落後／"
        "卡片數異常／qa_flags）在 brief 裡，這條看不出漏了哪一項",
    ],
    run=_gaps_present,
    fixture={"draft": {"gaps": []}},
    near_miss={"draft": {"gaps": ["投顧庫 8/20 缺天"]}},
    suite="convergence",
))
