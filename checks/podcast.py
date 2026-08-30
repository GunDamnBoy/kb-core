"""Podcast 知識庫的檢查（取數層）。

payload 形狀（由 payload builder 組出來，檢查本身不做 IO）：

    {"manifest": ~/podcast-transcripts/<date>/manifest.json,
     "shows":    scripts/podcast/shows.json（showKey → meta 的 dict）,
     "anchors":  podcast/anchors.json,
     "now":      ISO8601}

## 為什麼 suite 叫 podfetch 不叫 podcast

`podfetch` 那組回答的是「**昨晚那一輪轉錄好不好**」，不是「今天這份日報可不可以發」。
兩個問題、兩組讀者、兩個時機——前者是早上人看的，後者是 publish 的閘門。

擠在同一個 suite 裡的代價很具體：`publish.py` 用系統 id 選 suite，
它組出來的 payload 裡沒有 `manifest`，`podfetch` 那 11 條會整組 KeyError；
而為了讓它們不爆掉去塞一個 `manifest` 進發布的 payload，
等於讓發布這件事依賴一個 repo 外面的路徑。

**`podcast` 這個 suite 名留給日報層。**

## 兩組都在了

本檔現在有兩組：`suite="podfetch"`（取數層，11 條）與 `suite="podcast"`（日報層，7 條）。

> **這裡曾經有一整節叫「為什麼現在只有取數層，沒有日報層」**，理由是
> 「doc 的實際形狀還沒有一份真的樣本，憑 anchors 想像欄位寫出來的是看起來像檢查的東西」。
> **那個判斷是對的，而且它已經兌現了** —— 日報接上、有了真 doc 之後第二組才寫，
> 現在 `quotes_grounded`／`ledger_no_overdue` 這些都是對著實檔長出來的。
> **但那一節在第二組寫完之後沒有被刪，於是檔頭與檔身直接打架**：
> 照檔頭讀會得出「日報層沒有任何檢查」的結論，而 `chars_in_tier` 以下就是它。
> （**2026-08-30 訂正：這裡原本寫「第 572 行以下」，一週就漂了 12 行**——
> 08-23 同一場才訂下「四處寫死的行號已全部改成指函式名，行號會漂、名稱不會」，
> 這一處沒套用到。**訂了規則沒有全庫套用，等於只修了看得見的那幾處。**）
> 同一段還寫著「這十條」，而 `podfetch` 那組在 `no_block_repetition`（08-20 加）之後是 11 條。
> **兩處都是加了東西沒回頭改數字與敘述**，2026-08-23 訂正。

## 數字一個都不寫在這裡

門檻全部從 `anchors` 讀，跟 `checks/advisory.py` 同一條規矩。

## 已知缺口：零集無法分辨

`episodes` 是空的時候，manifest **分不出「今天真的沒有新集」與「查詢壞了」**。
2026-08-20 實測撞到：sharptech 與 fwdguidance 零產出，而 podfetch 的 log 裡
連一行都沒有——它只記總數（`找到 10 集`），不記每一檔查了什麼、回了什麼。

這個洞補不了在檢查這一層，要 podfetch 改成輸出每檔的查詢結果。
**沒有那份資料就寫不出那條檢查**，所以這裡誠實地不寫，記在 blind_to 與 CHANGELOG 裡。
"""
import datetime as dt
import re

from kbcore.check import Check, fail, ok, register, skipped, warn

FILE_ID_RE = re.compile(r"-(\d+)\.md$")
URL_ID_RE = re.compile(r"[?&]i=(\d+)")


def _A(p, *path):
    """從 anchors 取值。取不到就讓它 KeyError——**門檻取不到是設定壞了，不是資料壞了**。"""
    cur = p["anchors"]
    for k in path:
        cur = cur[k]
    return cur


def _ts(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def _eps(p):
    return p["manifest"].get("episodes") or []


def _mins(e):
    return (e.get("durationMs") or 0) / 60000


def _name(e):
    return f"{e.get('showKey')}「{(e.get('title') or '')[:32]}」"


# ── 1. manifest 的頂層形狀 ───────────────────────────────────────────
REQUIRED_TOP = ("generatedAt", "windowStartUtc", "windowEndUtc", "episodes")


def _wellformed(p):
    """頂層缺一個鍵，後面每一條檢查都會用不同的方式壞掉，而且訊息各不相同。

    先在這裡一次講清楚，比讓五條檢查各自吐一個 KeyError 有用。
    """
    m = p["manifest"]
    missing = [k for k in REQUIRED_TOP if k not in m]
    if missing:
        return fail(f"manifest 缺少頂層鍵：{'、'.join(missing)}")
    if not isinstance(m["episodes"], list):
        return fail(f"episodes 不是陣列，是 {type(m['episodes']).__name__}")
    for k in ("generatedAt", "windowStartUtc", "windowEndUtc"):
        try:
            _ts(m[k])
        except ValueError:
            return fail(f"{k} 不是可解析的時間：{m[k]!r}")
    return ok(f"{len(m['episodes'])} 集")


register(Check(
    id="podcast.manifest_wellformed",
    covers="manifest 有四個必要頂層鍵、episodes 是陣列、三個時間欄位都解析得開",
    blind_to=[
        "episodes 裡每一筆的欄位（這條只看頂層）",
        "時間解析得開但語意錯（視窗超前、視窗塌陷）——那是 window_sane 的事",
        "**episodes 是空的時候，這條會 PASS**：manifest 分不出「今天真的沒有新集」"
        "與「查詢壞了」，podfetch 目前不輸出每一檔的查詢結果",
        "manifest 寫出來了但逐字稿檔案沒有落地",
    ],
    run=_wellformed,
    fixture={"manifest": {"generatedAt": "2026-08-20T01:13:39+08:00",
                          "windowStartUtc": "2026-08-17T17:00:00Z",
                          "episodes": []}},
    near_miss={"manifest": {"generatedAt": "2026-08-20T01:13:39+08:00",
                            "windowStartUtc": "2026-08-17T17:00:00Z",
                            "windowEndUtc": "2026-08-19T17:00:00Z",
                            "episodes": []}},
    suite="podfetch",
))


# ── 2. 視窗本身合不合理 ──────────────────────────────────────────────
def _window_sane(p):
    """視窗是被寫出來的，不是被觀測到的——所以它可以指向未來，而且不會有人抗議。

    這跟 `sentinel.no_future_date` 是同一個病：時間欄位的錯誤不會讓程式壞掉，
    只會讓它抓錯一批東西然後回報成功。
    """
    m = p["manifest"]
    gen, a, b = _ts(m["generatedAt"]), _ts(m["windowStartUtc"]), _ts(m["windowEndUtc"])
    if a >= b:
        return fail(f"視窗起點 {a:%m-%d %H:%M} 不早於終點 {b:%m-%d %H:%M} —— 這一輪不可能抓到東西")
    ahead = (b - gen).total_seconds() / 60
    if ahead > 5:
        return fail(f"視窗終點比產生時間晚 {ahead:.0f} 分鐘 —— 那段時間還沒發生")
    hours = (b - a).total_seconds() / 3600
    cap = _A(p, "window", "max_lookback_hours")
    if hours > cap:
        return fail(f"視窗 {hours:.1f} 小時，超過 max_lookback_hours {cap} —— 會把舊集重收一次")
    return ok(f"{hours:.1f} 小時")


register(Check(
    id="podcast.window_sane",
    covers="視窗起點早於終點、終點不超前產生時間、長度不超過 anchors 的 max_lookback_hours",
    blind_to=[
        "視窗合理但錯過了真正的新集（視窗對，錨點抓錯）",
        "上一輪的 last_run_utc 沒有被更新，導致每天都用同一個起點",
        "視窗內確實沒有新集，與查詢根本沒送出去",
        "重疊區間（overlap_minutes）有沒有生效——這條只看兩端",
    ],
    run=_window_sane,
    fixture={"anchors": {"window": {"max_lookback_hours": 72}},
             "manifest": {"generatedAt": "2026-08-20T01:00:00+08:00",
                          "windowStartUtc": "2026-08-17T17:00:00Z",
                          "windowEndUtc": "2026-08-19T20:00:00Z"}},
    near_miss={"anchors": {"window": {"max_lookback_hours": 72}},
               "manifest": {"generatedAt": "2026-08-20T01:00:00+08:00",
                            "windowStartUtc": "2026-08-17T01:00:00+08:00",
                            "windowEndUtc": "2026-08-20T01:00:00+08:00"}},
    suite="podfetch",
))


# ── 3. 集數准入：預告片不是那一集 ────────────────────────────────────
def _admission(p):
    """**指標對這一層是瞎的，所以它必須站在指標前面。**

    2026-08-20 除名 sharptech 時定的：Sharp Tech 在 Apple 公開 feed 的每一集標題
    都帶 `(Preview)`，完整集在訂閱者私有 RSS。一支三分鐘的預告會被忠實轉寫、
    `status` 是 OK、完整度大概 100%——因為完整度量的是「轉寫得完不完整」，
    不是「這是不是那一集」。

    主判準是標題標記，時長只是第二道，而且它擋不住一支 12 分鐘的加長預告。
    """
    marks = _A(p, "episode_admission", "title_reject_markers")
    lo = _A(p, "episode_admission", "min_minutes")
    bad = []
    for e in _eps(p):
        title = e.get("title") or ""
        hit = next((m for m in marks if m.lower() in title.lower()), None)
        if hit:
            bad.append(f"{_name(e)}標題含「{hit}」")
        elif _mins(e) < lo:
            bad.append(f"{_name(e)}只有 {_mins(e):.1f} 分，低於 {lo} 分")
    if bad:
        return fail("；".join(bad[:4]) +
                    " —— 預告片會被完整轉寫、完整度照樣接近 100%，指標分不出來")
    return ok(f"{len(_eps(p))} 集都是完整集")


register(Check(
    id="podcast.episode_admission",
    covers="每一集的標題不含 anchors 的 title_reject_markers，且片長不低於 min_minutes",
    blind_to=[
        "**節目換一種標法就漏**（`Ep.0 - Coming Soon`、`Bonus`、季前預告）"
        "——這條擋的是已知的形狀，不是所有形狀",
        "一支 12 分鐘的加長預告：過得了 10 分鐘下限，標題乾淨就進得來",
        "完整集但內容是重播、精選、或上一集的延長版",
        "標題乾淨、片長正常，但音檔本身是錯的那一集",
    ],
    run=_admission,
    fixture={"anchors": {"episode_admission": {
        "title_reject_markers": ["(Preview)", "(Trailer)", "Trailer:", "預告"],
        "min_minutes": 10}},
        "manifest": {"episodes": [
            {"showKey": "sharptech", "title": "(Preview) Nvidia's Answer to Capital Constraints",
             "durationMs": 1_200_000}]}},
    near_miss={"anchors": {"episode_admission": {
        "title_reject_markers": ["(Preview)", "(Trailer)", "Trailer:", "預告"],
        "min_minutes": 10}},
        "manifest": {"episodes": [
            {"showKey": "unhedged", "title": "Does the market know anything about oil?",
             "durationMs": 630_000}]}},
    suite="podfetch",
))


# ── 4. showKey 認得出來 ──────────────────────────────────────────────
def _show_keys(p):
    """除名的節目隔天還在收，這條會叫。

    2026-08-20 除名 sharptech 之後，`shows.json` 與 `config.json` 的 show_priority
    做了雙向對帳——但**沒有任何東西在檢查「當天收進來的集數屬於還在清單裡的節目」**。
    """
    known = set(p["shows"])
    stray = sorted({e.get("showKey") for e in _eps(p)} - known)
    if stray:
        return fail(f"收到不在 shows.json 裡的 showKey：{'、'.join(str(s) for s in stray)}"
                    " —— 節目除名了但那一輪還在收，或 key 拼錯")
    return ok()


register(Check(
    id="podcast.show_keys_known",
    covers="manifest 裡每一集的 showKey 都在 shows.json 的鍵裡",
    blind_to=[
        "shows.json 有但當天零集的節目（這條只看收到的，看不見缺席的）",
        "showKey 對但 appleId 指到別的節目",
        "shows.json 與 config.json 的 show_priority 對不對得起來——那是 patch_shows.py 的事",
        "節目名稱改了但 key 沒改",
    ],
    run=_show_keys,
    fixture={"shows": {"allin": {}, "unhedged": {}},
             "manifest": {"episodes": [{"showKey": "sharptech"}]}},
    near_miss={"shows": {"allin": {}, "unhedged": {}},
               "manifest": {"episodes": [{"showKey": "allin"}]}},
    suite="podfetch",
))


# ── 5. status 的值域 ─────────────────────────────────────────────────
def _status_vocab(p):
    """值域檢查看起來多餘，直到有人用另一支程式寫 manifest。

    大小寫是真的邊界：`ok` 與 `OK` 在 JSON 裡是兩個值，而下游用 `== "OK"` 比對時，
    `ok` 會安靜地落進「不是 OK」那一側，然後被當成失敗集數捨棄。
    """
    allowed = set(_A(p, "quality", "status_values"))
    bad = [f"{_name(e)}={e.get('status')!r}" for e in _eps(p)
           if e.get("status") not in allowed]
    if bad:
        return fail(f"status 不在值域 {sorted(allowed)}：{'、'.join(bad[:4])}")
    return ok()


register(Check(
    id="podcast.status_vocabulary",
    covers="每一集的 status 落在 anchors.quality.status_values 裡（大小寫逐字相符）",
    blind_to=[
        "值在值域內但標錯了（一集其實掉了一半，卻標 OK）",
        "FAILED 與 DEGRADED 各有幾集——那是另外兩條的事",
        "status 這個欄位根本不存在的集數會被判成不在值域，訊息會說 None",
    ],
    run=_status_vocab,
    fixture={"anchors": {"quality": {"status_values": ["OK", "DEGRADED", "FAILED"]}},
             "manifest": {"episodes": [{"showKey": "allin", "title": "x", "status": "ok"}]}},
    near_miss={"anchors": {"quality": {"status_values": ["OK", "DEGRADED", "FAILED"]}},
               "manifest": {"episodes": [{"showKey": "allin", "title": "x", "status": "OK"}]}},
    suite="podfetch",
))


# ── 6. 有沒有整集失敗 ────────────────────────────────────────────────
def _no_failed(p):
    """DEGRADED 刻意不在這裡判——它的成因是完整度，家在下一條。

    同一件事被兩條檢查各判一次的代價，不是多叫一次，是**改門檻時只改到一邊**。
    """
    dead = [_name(e) for e in _eps(p) if e.get("status") == "FAILED"]
    if dead:
        return fail(f"{len(dead)} 集整集失敗：{'、'.join(dead[:4])}")
    return ok()


register(Check(
    id="podcast.no_failed_episodes",
    covers="manifest 裡沒有 status=FAILED 的集數",
    blind_to=[
        "DEGRADED 的集數——那是 completeness_band 的事，這條刻意不重複判",
        "**該收卻沒被收進 manifest 的集數**：失敗到沒有進 episodes 的，這條看不見",
        "run_budget 用完而被標 FAILED，與轉寫真的失敗，這條分不出來",
    ],
    run=_no_failed,
    fixture={"manifest": {"episodes": [
        {"showKey": "tip", "title": "x", "status": "FAILED"}]}},
    near_miss={"manifest": {"episodes": [
        {"showKey": "tip", "title": "x", "status": "DEGRADED"}]}},
    suite="podfetch",
))


# ── 7. 完整度的兩側 ──────────────────────────────────────────────────
def _completeness(p):
    """**同一個數字的兩側是兩種病，不要用同一句話描述。**

    低於下界：掉字、截斷。跳針不在這裡——它在計字前就被剔除了
    （2026-08-08 一行 28,122 個重複 token 讓完整度顯示 3.36、實際 1.10）。

    高於上界：**有兩個成因，不是一個。** 語速基準過期（分母偏小），或整段內容被複製
    （分子偏大）。2026-08-20 早上我看 iltb 的 1.57，查了連續 token 重複與 3-gram
    分佈都正常，就宣告是語速過期——**錯了**，實際是 970 token 的整段複製兩次。
    區塊重複的 3-gram 分佈本來就正常，我用測 A 的方法宣告了 B 不存在。

    而且同日的 bloomberg 8/19 完整度只有 **0.81**，一樣有區塊重播——
    **重播疊加時這個數字上升，重播覆蓋時它下降。** 所以它單獨一個指不出成因，
    要跟 `podfetch.no_block_repetition` 一起讀。
    """
    lo = _A(p, "quality", "retry_below")
    hi = _A(p, "quality", "completeness_high")
    low, high = [], []
    for e in _eps(p):
        c = e.get("completeness")
        if c is None:
            continue
        if c < lo:
            low.append(f"{_name(e)}={c:.2f}")
        elif c > hi:
            high.append(f"{_name(e)}={c:.2f}")
    if low:
        return fail(f"{len(low)} 集完整度低於 {lo}：{'、'.join(low[:4])} —— 掉字或截斷")
    if high:
        return warn(f"{len(high)} 集完整度高於 {hi}：{'、'.join(high[:4])}"
                    " —— 兩個可能的成因：語速基準過期（分母偏小）或整段內容被複製（分子偏大）。"
                    "**先看 podfetch.no_block_repetition，這個數字自己分不出來**")
    return ok()


register(Check(
    id="podcast.completeness_band",
    covers="每一集的完整度落在 anchors 的 retry_below 與 completeness_high 之間；"
           "低於下界是掉字（FAIL），高於上界是語速基準過期（WARN）",
    blind_to=[
        "完整度在區間內但內容是錯的那一集",
        "字數對、順序亂（時間戳回跳全庫 32% 出現，實測後決定不加單調性檢查）",
        "**沒有 completeness 欄位的集數會被跳過**，輸出與「檢查過沒問題」相同",
        "**上界被觸發時，是語速基準過期還是整段複製——這條分不出來**，"
        "要看 podfetch.no_block_repetition",
        "整體都偏低但每一集都還在下界之上",
    ],
    run=_completeness,
    fixture={"anchors": {"quality": {"retry_below": 0.55, "completeness_high": 1.35}},
             "manifest": {"episodes": [
                 {"showKey": "gsx", "title": "x", "completeness": 0.40},
                 {"showKey": "iltb", "title": "y", "completeness": 1.57}]}},
    near_miss={"anchors": {"quality": {"retry_below": 0.55, "completeness_high": 1.35}},
               "manifest": {"episodes": [
                   {"showKey": "gsx", "title": "x", "completeness": 0.56},
                   {"showKey": "iltb", "title": "y", "completeness": 1.34}]}},
    suite="podfetch",
))


# ── 7b. 整段內容被複製 ───────────────────────────────────────────────
def _block_repeat(p):
    """**這一條是 2026-08-20 下午由一個判斷錯誤換來的。**

    早上看到 iltb 完整度 1.57，我查了「最長連續重複同一 token」與 3-gram 分佈，
    兩者都正常，於是宣告成因是語速基準過期。錯了——實際是 970 token 的整段內容
    重播兩次。**區塊重複的 3-gram 分佈本來就正常，因為重複的是一大段連貫文字。**
    我用測 A 的方法宣告了 B 不存在。

    第二個發現更要命：bloomberg 8/19 完整度只有 **0.81**，一樣有 281 token 的區塊
    重播，而且那段重播**覆蓋掉了下一位來賓訪談的真實內容**。所以：

    **重播疊加時完整度上升，重播覆蓋時完整度下降。** `completeness_band` 只抓得到
    前一種，而後一種才是有東西真的不見了的那一種。

    偵測本身不在這裡做——檢查不做 IO。payload builder 讀逐字稿算出區塊，
    這裡只判門檻，跟 `watch.no_code_drift` 與 `code_drift()` 是同一道 seam。
    """
    lo = _A(p, "quality", "block_repeat_min_tokens")
    head = _A(p, "quality", "block_repeat_coldopen_head")
    reps = p.get("repeats")
    if reps is None:
        return fail("payload 沒有 repeats —— 偵測沒跑，而不是沒有重複")
    bad = []
    for name, blocks in sorted(reps.items()):
        for b in blocks:
            if b["tokens"] < lo:
                continue
            if b["first"] < head:
                continue  # 片頭預告：第一次出現就在開頭，稍後正片再播一次
            bad.append(f"{name} {b['tokens']} token @{b['first']}→{b['second']}")
    if bad:
        return fail(f"{len(bad)} 處整段複製：{'；'.join(bad[:3])}"
                    " —— 複製若覆蓋掉原內容，那段就真的不見了，而完整度指不出來")
    return ok()


register(Check(
    id="podfetch.no_block_repetition",
    covers="沒有超過 anchors.block_repeat_min_tokens 的整段逐字重播（片頭預告除外）",
    blind_to=[
        "**同義重述的重播**：allin 那集同一組論點講了兩次但用字不同，"
        "機械查重完全看不到，只有讀得出來",
        "重播「覆蓋」與「疊加」的差別——這條只說有重複，說不出原內容有沒有被蓋掉",
        "片頭預告的豁免會放掉真正發生在開頭前 200 token 的重播",
        "廣告與台呼低於下限所以不叫，但**一段被截短的廣告**也可能低於下限",
        "重複但兩次之間有細微差異（時間戳插入、一個字不同）會讓 shingle 斷開",
        "**同一個短句連續重複 N 次的跳針**（2026-08-23 mib：`[37:08]`–`[37:17]` 同一句 13 次、"
        "合計約 324 token，**高於下限卻仍判乾淨**）。**成因不是門檻太高，是聚合**："
        "`block_repeats()` 的合併條件 `a == cur[0] + cur[2]` 要求重複的兩端同步前進，"
        "而跳針每遇到下一個副本開頭，`seen[g]` 回傳的仍是第一份的位置、`a` 因此回捲（實測 12 筆的 `first` 全部相同、`second` 每次 +27），"
        "於是 324 token 被拆成 12 個區塊（11 個 38 token ＋ 尾段 27），逐一低於下限被濾掉。"
        "**照「門檻太高」去修會把下限調到 38，那會讓每一句廣告台詞都觸發** ——"
        "真正的修法是把 `first` 相同的區塊加總或改成計次。`quality.stutter_token_repeat`"
        "（同一 **token** 連續 20 次）也接不到，因為兩次重複之間隔著整句話",
    ],
    run=_block_repeat,
    fixture={"anchors": {"quality": {"block_repeat_min_tokens": 150,
                                     "block_repeat_coldopen_head": 200}},
             "repeats": {"iltb.md": [{"tokens": 970, "first": 7041, "second": 8000}]}},
    near_miss={"anchors": {"quality": {"block_repeat_min_tokens": 150,
                                       "block_repeat_coldopen_head": 200}},
               "repeats": {"a.md": [{"tokens": 140, "first": 3000, "second": 5000},
                                    {"tokens": 300, "first": 17, "second": 1946}]}},
    suite="podfetch",
))


# ── 8. 發布時間落在視窗內 ────────────────────────────────────────────
def _in_window(p):
    """視窗算對了、集數也收到了，但收到的是視窗外的東西——這種錯不會有人抗議。

    含下界、含上界（`overlap_minutes` 的重疊區刻意算在內）。
    """
    m = p["manifest"]
    a, b = _ts(m["windowStartUtc"]), _ts(m["windowEndUtc"])
    stray = []
    for e in _eps(p):
        r = e.get("releaseDate")
        if not r:
            continue
        t = _ts(r)
        if t < a or t > b:
            stray.append(f"{_name(e)} {t:%m-%d %H:%M}")
    if stray:
        return fail(f"{len(stray)} 集的發布時間在視窗 "
                    f"{a:%m-%d %H:%M}–{b:%m-%d %H:%M} 之外：{'、'.join(stray[:4])}")
    return ok()


register(Check(
    id="podcast.release_in_window",
    covers="每一集的 releaseDate 落在 manifest 宣告的視窗內（含兩端）",
    blind_to=[
        "視窗本身就錯的情況——那是 window_sane 的事，這條只驗兩者一致",
        "releaseDate 欄位缺席的集數會被跳過",
        "節目方事後改了發布時間",
        "**視窗內該有卻沒收到的集數**（這條只看收到的）",
    ],
    run=_in_window,
    fixture={"manifest": {"windowStartUtc": "2026-08-17T17:00:00Z",
                          "windowEndUtc": "2026-08-19T17:00:00Z",
                          "episodes": [{"showKey": "allin", "title": "x",
                                        "releaseDate": "2026-08-15T00:47:00Z"}]}},
    near_miss={"manifest": {"windowStartUtc": "2026-08-17T17:00:00Z",
                            "windowEndUtc": "2026-08-19T17:00:00Z",
                            "episodes": [{"showKey": "allin", "title": "x",
                                          "releaseDate": "2026-08-17T17:00:00Z"}]}},
    suite="podfetch",
))


# ── 9. 同源去重：必須兩個欄位同時相同 ────────────────────────────────
def _no_dupes(p):
    """**只比標題會誤判，而誤判擋掉的是一集真的內容。**

    2026-08-20 實測：JPM 的 `US Tactical Derivatives Strategy` 同一天出現兩次，
    是兩篇不同的報告。podcast 這邊同樣的形狀是週更節目的固定標題
    （`Bloomberg Surveillance TV: August 18th` 與 `August 19th` 才是不同集，
    但很多節目連日期都不放進標題）。

    所以 anchors 定的是 `require_both`：標題與片長要同時相同才算同源。
    """
    fields = _A(p, "dedup", "same_source_fields")
    both = _A(p, "dedup", "require_both")
    seen, dupes = {}, []
    for e in _eps(p):
        key = tuple(e.get(f) for f in fields) if both else (e.get(fields[0]),)
        if key in seen:
            dupes.append(_name(e))
        seen[key] = True
    if dupes:
        return fail(f"{len(dupes)} 集與前面的集數同源（{'＋'.join(fields)} 全部相同）："
                    f"{'、'.join(dupes[:4])}")
    return ok()


register(Check(
    id="podcast.no_duplicate_episodes",
    covers="沒有兩集在 anchors.dedup.same_source_fields 上全部相同",
    blind_to=[
        "同一集在兩檔節目各發一次，但標題被各自改過（同源判不出來）",
        "**內容重複但標題與片長都不同**——同一場訪談的長短版",
        "去重之後該保留哪一集（`keep_by: show_priority` 是收集端的事，這裡只驗有沒有）",
        "跨日重複：昨天收過的今天又收一次，這條只看當天這一份 manifest",
    ],
    run=_no_dupes,
    fixture={"anchors": {"dedup": {"same_source_fields": ["title", "durationMs"],
                                   "require_both": True}},
             "manifest": {"episodes": [
                 {"showKey": "oddlots", "title": "同一集", "durationMs": 2_400_000},
                 {"showKey": "oddlots", "title": "同一集", "durationMs": 2_400_000}]}},
    near_miss={"anchors": {"dedup": {"same_source_fields": ["title", "durationMs"],
                                     "require_both": True}},
               "manifest": {"episodes": [
                   {"showKey": "bloomberg", "title": "Bloomberg Surveillance TV",
                    "durationMs": 1_740_000},
                   {"showKey": "bloomberg", "title": "Bloomberg Surveillance TV",
                    "durationMs": 1_920_000}]}},
    suite="podfetch",
))


# ── 10. 檔名裡的 id 與 appleUrl 裡的 id 一致 ─────────────────────────
def _file_id(p):
    """同一個識別碼住在兩個欄位裡，那就必須驗它們一致——否則遲早會指向不同的集。

    這條抓的是「manifest 說的那個檔案，跟 appleUrl 指的不是同一集」。
    它不會讓任何程式壞掉：檔案讀得開、URL 點得進去，只是兩者對不起來。
    """
    bad = []
    for e in _eps(p):
        f, u = e.get("file") or "", e.get("appleUrl") or ""
        mf, mu = FILE_ID_RE.search(f), URL_ID_RE.search(u)
        if not f:
            bad.append(f"{_name(e)} 沒有 file 欄位")
        elif not mf:
            bad.append(f"{_name(e)} 檔名取不出 id：{f}")
        elif mu and mf.group(1) != mu.group(1):
            bad.append(f"{_name(e)} 檔名 id {mf.group(1)} ≠ URL id {mu.group(1)}")
    if bad:
        return fail("；".join(bad[:4]))
    return ok()


register(Check(
    id="podcast.file_id_matches_url",
    covers="每一集都有 file 欄位、檔名結尾取得出 id，且與 appleUrl 的 i= 參數一致",
    blind_to=[
        "**檔名的節目前綴與 showKey 對不對得起來**——這條只驗 id 那一段",
        "appleUrl 沒有 `?i=` 參數時，只驗檔名取不取得出 id，不驗一致性",
        "id 一致但檔案根本沒寫出來（檢查不做 IO，看不到檔案系統）",
        "檔案存在但內容是空的",
    ],
    run=_file_id,
    fixture={"manifest": {"episodes": [
        {"showKey": "allin", "title": "x", "file": "allin-1000783964339.md",
         "appleUrl": "https://podcasts.apple.com/us/podcast/id1502871393?i=1000784008514"}]}},
    near_miss={"manifest": {"episodes": [
        {"showKey": "allin", "title": "x", "file": "iltb-1000783964339.md",
         "appleUrl": "https://podcasts.apple.com/us/podcast/id1502871393?i=1000783964339"}]}},
    suite="podfetch",
))


# ════════════════════════════════════════════════════════════════════
# suite="podcast"｜日報層：這一份當日 doc 可不可以發布
#
# payload 由 `systems/podcast.py` 的 build() 組出來：
#   {"doc", "prev", "ledger", "quote_misses", "anchors", "now"}
#
# 這一組跟上面那組（suite="podfetch"）問的是不同的問題：
# 上面問「昨晚那一輪轉錄好不好」，這裡問「今天這份日報可不可以上線」。
# ════════════════════════════════════════════════════════════════════

def _docs(p):
    return p["doc"].get("episodes") or []


def _tier(p, minutes):
    """回傳該片長所屬層級的 (下界, 上界, 段下界, 段上界)。含下界、不含上界。"""
    for t in _A(p, "length_tiers"):
        cap = t["under_minutes"]
        if cap is None or minutes < cap:
            return t["chars"][0], t["chars"][1], t["paras"][0], t["paras"][1]
    raise KeyError("length_tiers 最後一層必須是 under_minutes: null")


# ── 11. 篇幅落在所屬層級 ─────────────────────────────────────────────
def _chars_in_tier(p):
    """BRIEF 第七節第一條當期失敗判準。

    2026-08-20 寫這條時發現的洞：**doc 裡沒有任何欄位存得下片長**——
    `published` 是「2026年8月18日｜片長 56 分鐘」這種給人讀的字串。
    層級是由片長決定的，所以這條判準當時在資料上是判不了的，只是看起來像。
    於是給每集加了 `minutes`。

    這跟投顧那次保底卡的 `base` 欄位是同一件事：**一條判準若在資料裡找不到
    對應的欄位，它就不是機械可判的。**
    """
    bad = []
    for e in _docs(p):
        m = e.get("minutes")
        if m is None:
            bad.append(f"{e.get('id')} 沒有 minutes 欄位 —— 層級判不了")
            continue
        lo, hi, plo, phi = _tier(p, m)
        n = e.get("chars") or 0
        paras = sum(len(s.get("paragraphs") or []) for s in e.get("sections") or [])
        if n > hi:
            bad.append(f"{e.get('id')} {n} 字超過上界 {hi}（{m} 分）")
        elif n < lo and not e.get("lowerBoundException"):
            bad.append(f"{e.get('id')} {n} 字低於下界 {lo} 且沒有具名的下界例外")
        elif not (plo <= paras <= phi):
            bad.append(f"{e.get('id')} {paras} 段不在 {plo}–{phi}（{m} 分）")
    if bad:
        return fail("；".join(bad[:4]))
    return ok(f"{len(_docs(p))} 集都在層級區間內")


register(Check(
    id="podcast.chars_in_tier",
    covers="每集的 chars 與段數落在片長所屬層級的區間內；低於下界要有具名的 lowerBoundException",
    blind_to=[
        "字數對但內容是注水的——**短節目硬拉長比長節目超規格更難發現**",
        "`also_top_tier_if_topics`（主題數達門檻時升到最高層）這條沒有實作，"
        "因為 doc 只帶 1–3 個受控 topics，數不到十個",
        "官方逐字稿的 10% 超規容許（`official_transcript_overrun_pct`）沒有套用，"
        "因為 doc 沒有欄位說這一集用的是哪一層退援",
        "`minutes` 本身是從 manifest 抄來的，抄錯這條看不出來",
    ],
    run=_chars_in_tier,
    fixture={"anchors": {"length_tiers": [
        {"under_minutes": 30, "chars": [2000, 3000], "paras": [10, 15]},
        {"under_minutes": None, "chars": [4000, 6500], "paras": [20, 33]}]},
        "doc": {"episodes": [{"id": "iltb-1", "minutes": 76, "chars": 6520,
                              "sections": [{"paragraphs": ["x"] * 27}]}]}},
    near_miss={"anchors": {"length_tiers": [
        {"under_minutes": 30, "chars": [2000, 3000], "paras": [10, 15]},
        {"under_minutes": None, "chars": [4000, 6500], "paras": [20, 33]}]},
        "doc": {"episodes": [{"id": "iltb-1", "minutes": 76, "chars": 6500,
                              "sections": [{"paragraphs": ["x"] * 27}]}]}},
    suite="podcast",
))


# ── 12. 受控詞表 ─────────────────────────────────────────────────────
def _topics(p):
    """自由發揮的標籤跨日對不上，等於沒有標籤。"""
    vocab = set(_A(p, "topics_vocabulary"))
    lo, hi = _A(p, "per_episode", "topics")
    bad = []
    for e in _docs(p):
        ts = e.get("topics") or []
        stray = [t for t in ts if t not in vocab]
        if stray:
            bad.append(f"{e.get('id')} 有詞表外的標籤：{'、'.join(stray)}")
        elif not (lo <= len(ts) <= hi):
            bad.append(f"{e.get('id')} 有 {len(ts)} 個 topic，不在 {lo}–{hi}")
    if bad:
        return fail("；".join(bad[:4]))
    return ok()


register(Check(
    id="podcast.topics_controlled",
    covers="每集的 topics 都在受控詞表內，數量在 anchors 的 per_episode.topics 範圍",
    blind_to=[
        "標籤在詞表內但貼錯（一集講半導體卻標成投資哲學）",
        "詞表本身涵蓋不到的題材——2026-08-20 實測 gsx 那集主體是生技醫療投資，"
        "詞表裡沒有對應項，只能選最接近的三個",
        "同一個題材跨日被標成不同的標籤",
    ],
    run=_topics,
    fixture={"anchors": {"topics_vocabulary": ["半導體", "通膨"],
                         "per_episode": {"topics": [1, 3]}},
             "doc": {"episodes": [{"id": "a-1", "topics": ["半導體", "生技醫療"]}]}},
    near_miss={"anchors": {"topics_vocabulary": ["半導體", "通膨"],
                           "per_episode": {"topics": [1, 3]}},
               "doc": {"episodes": [{"id": "a-1", "topics": ["半導體", "通膨"]}]}},
    suite="podcast",
))


# ── 13. 每集的件數 ───────────────────────────────────────────────────
def _counts(p):
    """2026-08-20 首輪就撞到：撰寫端寫了 7–8 條核心重點，而 anchors 的上界是 5。

    成因不是撰寫端貪心，是**派工單沒有把數量寫進去**——JOB.md 只給了 schema。
    這條檢查抓到的是派工的缺漏，不是內容的缺漏。

    ## 第四層的例外

    退到第四層（拿不到全文、只寫約 500 字精簡摘要）的集數，`quotes` 必須是空陣列——
    **沒有逐字稿就不寫金句**。對它套金句下界，會把一條正常的退路判成失敗，
    而 publish 是整輪一起判，所以那會擋掉當天所有集數。

    判定靠 `source` 開頭的佔位符號（家在 `anchors.dedup.placeholder_not_collected`），
    而且是**雙向**的：標了佔位就不准有金句，沒標就照常套下界。
    單向放行等於給了一個「填上這個字串就跳過檢查」的後門。
    """
    tlo, thi = _A(p, "per_episode", "takeaways")
    qlo, qhi = _A(p, "per_episode", "quotes")
    mark = _A(p, "dedup", "placeholder_not_collected")
    bad = []
    for e in _docs(p):
        nt, nq = len(e.get("takeaways") or []), len(e.get("quotes") or [])
        if not (tlo <= nt <= thi):
            bad.append(f"{e.get('id')} 核心重點 {nt} 條，不在 {tlo}–{thi}")
        # 退到第四層的集數：**沒有逐字稿就不寫金句**，所以 quotes 必須是空的。
        # 對它套下界會把一條正常的退路判成失敗，而那會擋掉整天的日報。
        if (e.get("source") or "").lstrip().startswith(mark):
            if nq:
                bad.append(f"{e.get('id')} 標了 {mark} 卻有 {nq} 條金句 —— "
                           "沒有逐字稿就不寫金句")
        elif not (qlo <= nq <= qhi):
            bad.append(f"{e.get('id')} 金句 {nq} 條，不在 {qlo}–{qhi}")
    if bad:
        return fail("；".join(bad[:4]))
    return ok()


register(Check(
    id="podcast.per_episode_counts",
    covers="每集的核心重點與金句數量落在 anchors 的 per_episode 範圍內",
    blind_to=[
        "數量對但每一條都很敷衍——`takeaway_sentences` 的句數這條沒有量",
        "核心重點有沒有真的寫進「對投資人的含義」（那是語意，機械判不了）",
        "第四層的判定只看 `source` 開頭的佔位符號 —— **退到第四層但忘了標的集數**，"
        "會被當成正常集數套下界，訊息會說「金句 0 條」而不是「忘了標退援層級」",
    ],
    run=_counts,
    fixture={"anchors": {"per_episode": {"takeaways": [3, 5], "quotes": [2, 5]},
                         "dedup": {"placeholder_not_collected": "⚠︎"}},
             "doc": {"episodes": [
                 {"id": "b-1", "source": "⚠︎ 全文摘譯待補（FT 存取失效）",
                  "takeaways": [0] * 4, "quotes": [0] * 3}]}},
    near_miss={"anchors": {"per_episode": {"takeaways": [3, 5], "quotes": [2, 5]},
                           "dedup": {"placeholder_not_collected": "⚠︎"}},
               "doc": {"episodes": [
                   {"id": "b-1", "source": "⚠︎ 全文摘譯待補（FT 存取失效）",
                    "takeaways": [0] * 4, "quotes": []}]}},
    suite="podcast",
))


# ── 14. 交叉分析 ─────────────────────────────────────────────────────
def _crosscut(p):
    n = len(_docs(p))
    need = _A(p, "per_episode", "crosscut_min_episodes")
    cc = p["doc"].get("crossCut")
    if n >= need and not (cc and (cc.get("points") or [])):
        return fail(f"當日 {n} 集達到門檻 {need}，卻沒有 crossCut —— "
                    "交叉分析是這個站跟一疊摘要的分水嶺")
    return ok()


register(Check(
    id="podcast.crosscut_present",
    covers="當日集數達到 anchors 的 crosscut_min_episodes 時，crossCut 有內容",
    blind_to=[
        "crossCut 有內容但只是並列摘要，沒有真的交叉",
        "**它引用的集數是不是當天真的有的那幾集**（`points[].episodes` 沒有回頭比對）",
        "集數未達門檻時這條永遠 PASS，包含 0 集那天",
    ],
    run=_crosscut,
    fixture={"anchors": {"per_episode": {"crosscut_min_episodes": 3}},
             "doc": {"episodes": [{}, {}, {}], "crossCut": {"points": []}}},
    near_miss={"anchors": {"per_episode": {"crosscut_min_episodes": 3}},
               "doc": {"episodes": [{}, {}], "crossCut": None}},
    suite="podcast",
))


# ── 15. 金句必須在逐字稿裡真的出現過 ─────────────────────────────────
def _quotes_grounded(p):
    """**這條是整組裡最重要的一條。**

    其他判準壞掉時，產出是缺的、空的、格式錯的——看得出來。
    金句造假的產出**讀起來比真的還通順**，而且事後回頭看也分不出來。

    `original` 這個欄位存在的唯一理由就是讓這件事變成機械可判。
    比對在 `systems/podcast.py` 做（它讀得到 repo 外面的逐字稿），這裡只判結果。
    """
    misses = p.get("quote_misses")
    if misses is None:
        return skipped("讀不到當日逐字稿，這一輪沒有比對過金句 —— "
                       "**這不等於比對過沒問題**")
    if misses:
        lines = [f"{i}／{by}：「{o}…」" for i, by, o in misses[:3]]
        return fail(f"{len(misses)} 條金句在逐字稿裡找不到：{'；'.join(lines)}")
    return ok(f"{sum(len(e.get('quotes') or []) for e in _docs(p))} 條金句全部逐字命中")


register(Check(
    id="podcast.quotes_grounded",
    covers="每一條金句的 original 都是當日逐字稿裡真的出現過的字串",
    blind_to=[
        "**中譯與原句對不對得起來**——這條只驗原句存在，不驗翻譯忠實",
        "原句存在但講者掛錯（逐字稿的講者標記本身就常錯，2026-08-20 十集皆然）",
        "原句是從廣告或台呼裡挑的",
        "逐字稿讀不到時整條 SKIPPED，那時候這個閘門是開的",
        "**比對基準只有 podfetch 稿，官方稿不在比對範圍內。** `quote_misses()` 寫死了"
        "`~/podcast-transcripts/<date>/<showKey>-<trackId>.md`，所以 A 類走第一層、"
        "用官方稿撰寫時，取自官方稿的 `original` 必然對不上（2026-08-23 latentspace 五條全 MISS）。"
        "**這條擋得住，但它擋下來的是整輪** —— 規則寫在 `preamble.md` 第三節與"
        "`DIGEST-PROMPT.md` 第 3 步：`original` 一律回 podfetch 稿挑",
        "**`trackId` 欄位缺席時整輪回 `None` → SKIPPED**，而那跟「比對過沒問題」在輸出上一樣。"
        "日期檔的欄位清單直到 2026-08-23 才把 `trackId` 寫進 `BRIEF.md` 第二節",
    ],
    run=_quotes_grounded,
    fixture={"doc": {"episodes": []},
             "quote_misses": [["iltb-1", "Ben Thompson", "this line was never said"]]},
    near_miss={"doc": {"episodes": []}, "quote_misses": []},
    suite="podcast",
))


# ── 16. 帳本有往前走 ─────────────────────────────────────────────────
def _ledger(p):
    """BRIEF 第七節第四條：**拋出去的觀察要回頭對答案。**

    這是本站跟一般摘要的分水嶺，所以它是當期失敗判準而不是加分項。
    """
    lo, hi = _A(p, "per_episode", "observations_per_day")
    date = p["doc"].get("date")
    led = p.get("ledger")
    if led is None:
        return fail("讀不到帳本 —— 觀察點沒有家，這一輪不能發")
    today = [i for i in led.get("items") or [] if i.get("date") == date]
    if not (lo <= len(today) <= hi):
        return fail(f"帳本裡當日的觀察點有 {len(today)} 條，不在 {lo}–{hi}")
    return ok(f"帳本新增 {len(today)} 條")


register(Check(
    id="podcast.ledger_advanced",
    covers="帳本裡當日新增的觀察點數量落在 anchors 的 observations_per_day 範圍",
    blind_to=[
        "**逾期未判的項目**：已於 2026-08-22 拆到 `podcast.ledger_no_overdue`，"
        "這條只管當日新增的數量。當初這裡寫「要補這個洞得先給帳本加 `due`，"
        "而歷史不改寫——只能從新項目開始帶」，實作時找到第三條路："
        "**新項目強制帶 `due` 欄位，歷史則從 text 裡的「（到期 YYYY-MM-DD）」回退解析**。"
        "那個字串本來就已經寫在多數條目裡，於是不必改寫任何一條歷史就有了即時涵蓋",
        "觀察點收得對不對（「三個月後有可能被證明是錯的嗎」是語意判準）",
        "同一個觀察點被重複收錄",
        "doc 的 postscript 與帳本檔案有沒有對上（這條只看帳本）",
    ],
    run=_ledger,
    fixture={"anchors": {"per_episode": {"observations_per_day": [2, 3]}},
             "doc": {"date": "2026-08-20"},
             "ledger": {"items": [{"date": "2026-08-19"}]}},
    near_miss={"anchors": {"per_episode": {"observations_per_day": [2, 3]}},
               "doc": {"date": "2026-08-20"},
               "ledger": {"items": [{"date": "2026-08-20"}, {"date": "2026-08-20"}]}},
    suite="podcast",
))


DUE_RE = re.compile(r"到期\s*(\d{4}-\d{2}-\d{2})")


def _due_of(item):
    """項目的到期日：優先讀 `due` 欄位，沒有就從 text 回退解析。

    **回退這條是為了不改寫歷史。** 帳本的舊條目只有 date／status／verdict，
    但其中不少在 text 結尾就寫著「（到期 2026-12-31）」——那個字串本來就在，
    解析它不需要動任何一條既有項目。新項目一律帶 `due` 欄位，
    回退路徑會隨著舊項目被判完而自然退場。
    """
    d = item.get("due")
    if d:
        return d
    m = DUE_RE.search(item.get("text") or "")
    return m.group(1) if m else None


def _overdue(p):
    """BRIEF 第七節第四條的後半：**有逾期未判的項目**。

    **為什麼不是一觸即失敗**：這條會擋住當天的發布，而被擋住的是當天的內容——
    一條三個月前的觀察沒有回訪，代價由今天的讀者付，那個賠率不對。
    所以照 MODIFY 那條「要求兩個獨立訊號同時成立才報」：
    逾期本身只是 WARN，**逾期超過 `overdue_grace_days` 才是 FAIL**。
    寬限期讓「今天剛好到期、還沒輪到回訪」與「放著不管」分得開。
    """
    grace = _A(p, "observations", "overdue_grace_days")
    today = dt.date.fromisoformat(p["doc"]["date"])
    led = p.get("ledger")
    if led is None:
        return fail("讀不到帳本 —— 觀察點沒有家，這一輪不能發")
    watching = [i for i in led.get("items") or [] if i.get("status") == "觀察中"]
    dated = [(i, _due_of(i)) for i in watching]
    over = [(i, dt.date.fromisoformat(d)) for i, d in dated if d and dt.date.fromisoformat(d) < today]
    if not over:
        n_undated = sum(1 for _, d in dated if not d)
        return ok(f"沒有逾期未判（觀察中 {len(watching)} 條，其中 {n_undated} 條沒有到期日）")
    worst = max((today - d).days for _, d in over)
    names = "、".join(i.get("id", "?") for i, _ in over[:5])
    tail = " …" if len(over) > 5 else ""
    msg = f"{len(over)} 條逾期未判（最久 {worst} 天）：{names}{tail}"
    return fail(msg + f" —— 超過 {grace} 天的寬限期") if worst > grace else warn(msg)


register(Check(
    id="podcast.ledger_no_overdue",
    covers="帳本裡沒有已過到期日卻仍是「觀察中」的項目（超過寬限期才判 FAIL）",
    blind_to=[
        "**沒有到期日的項目**：舊條目有八成（**2026-08-23 量測：64 條觀察中裡 52 條**；08-22 是 61 條裡 52 條）"
        "text 裡沒有「（到期 …）」，`due` 欄位也沒有，**這條對它們完全是瞎的**。"
        "它們只會出現在 PASS 訊息的括號裡，不會觸發任何東西——"
        "**看到綠燈不等於帳本乾淨，只代表有到期日的那些沒逾期**",
        "判決下得對不對（`status` 從觀察中改成什麼，這條不看內容）",
        "為了讓燈變綠而把項目直接改判「無法驗證」——這條擋不住，"
        "而它正是這種檢查最容易誘發的行為",
        "到期日訂得合不合理（三個月是慣例不是規則）",
        "觀察中佔比的長期趨勢——那是 healthcheck 記分板的事，這條只看逾期",
        "**寬限期那條門檻（`overdue_grace_days`）站得對不對，自檢釘不住**："
        "`near_miss` 必須落在 PASS 側，而寬限期內回的是 WARN、WARN 不是 PASS，"
        "所以自檢只驗得到「逾期／未逾期」這條邊界。寬限期改成 30 或 3，"
        "自檢照樣全綠",
    ],
    run=_overdue,
    # fixture 逾期 8 天（剛好越過 7 天寬限期）→ FAIL；near_miss 到期日就是今天 → PASS。
    # **釘住的是「逾期」那條邊界，不是寬限期那條**：near_miss 必須落在 PASS 側，
    # 而寬限期內是 WARN、WARN 不是 PASS，所以那條邊界自檢碰不到（已寫進 blind_to）。
    fixture={"anchors": {"observations": {"overdue_grace_days": 7}},
             "doc": {"date": "2026-08-22"},
             "ledger": {"items": [{"id": "a", "status": "觀察中",
                                   "text": "…（到期 2026-08-14）"}]}},
    near_miss={"anchors": {"observations": {"overdue_grace_days": 7}},
               "doc": {"date": "2026-08-22"},
               "ledger": {"items": [{"id": "a", "status": "觀察中",
                                     "text": "…（到期 2026-08-22）"}]}},
    suite="podcast",
))
