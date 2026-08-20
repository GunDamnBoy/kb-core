"""Podcast 知識庫的檢查（取數層）。

payload 形狀（由 payload builder 組出來，檢查本身不做 IO）：

    {"manifest": ~/podcast-transcripts/<date>/manifest.json,
     "shows":    scripts/podcast/shows.json（showKey → meta 的 dict）,
     "anchors":  podcast/anchors.json,
     "now":      ISO8601}

## 為什麼現在只有取數層，沒有日報層

日報那一段（03:00 讀 manifest 產出當日 doc）還沒接。門檻雖然已經在
`anchors.length_tiers` 與 `per_episode` 裡，但**doc 的實際形狀還沒有一份真的樣本**。

advisory 的 XLSX 免責頁、podcast 的 Sharp Tech 預告片，兩次都是實跑那一次才長出來的。
現在憑 anchors 想像 doc 的欄位去寫檢查，寫出來的是「看起來像檢查的東西」——
它會通過 selftest，然後在第一天對著真實的 doc 全部 SKIPPED 或全部誤判。
**日報接上、有第一份真 doc 之後再寫第二組。**

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

from kbcore.check import Check, fail, ok, register, warn

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
    suite="podcast",
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
    suite="podcast",
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
    suite="podcast",
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
    suite="podcast",
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
    suite="podcast",
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
    suite="podcast",
))


# ── 7. 完整度的兩側 ──────────────────────────────────────────────────
def _completeness(p):
    """**同一個數字的兩側是兩種病，不要用同一句話描述。**

    低於下界：掉字、截斷。跳針不在這裡——它在計字前就被剔除了
    （2026-08-08 一行 28,122 個重複 token 讓完整度顯示 3.36、實際 1.10）。

    高於上界：剔除跳針之後仍然偏高，只剩一個解釋——**該節目的語速基準過期了**。
    2026-08-20 實測 iltb 是 1.57，逐字稿驗過沒有重複（最長連續同 token 只有 2、
    3-gram 分佈正常），實際約 224 字/分而 shows.json 記 140。

    所以上界該說的是「去修分母」，不是「逐字稿有問題」。
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
                    " —— 跳針已在計字前剔除，所以這是語速基準過期，去修 shows.json 的 wpm")
    return ok()


register(Check(
    id="podcast.completeness_band",
    covers="每一集的完整度落在 anchors 的 retry_below 與 completeness_high 之間；"
           "低於下界是掉字（FAIL），高於上界是語速基準過期（WARN）",
    blind_to=[
        "完整度在區間內但內容是錯的那一集",
        "字數對、順序亂（時間戳回跳全庫 32% 出現，實測後決定不加單調性檢查）",
        "**沒有 completeness 欄位的集數會被跳過**，輸出與「檢查過沒問題」相同",
        "上界被觸發時，是分母過期還是分子異常——這條只指方向，分辨要看重複度",
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
    suite="podcast",
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
    suite="podcast",
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
    suite="podcast",
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
    suite="podcast",
))
