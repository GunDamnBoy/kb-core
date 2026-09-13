#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日五圖 · 第 1 步的盤點表。**這支只讀不寫。**

用法：
    python3 scripts/chart/prep_chart.py [YYYY-MM-DD]

## 為什麼有這一支

第 1 步的完成條件本來就寫得很清楚：「手上有一張表 —— 今天是星期幾、
該出哪一條軌道、預抓涵蓋到哪些序列、以及上游今天給了什麼題材。」

**那張表是確定性的，不需要代理逐份讀檔去湊。** 而代價很具體：
上游投顧的當日 JSON 是 **11 萬字元（約 77k token）**，整份讀進來之後，
**後面每一輪都要重讀它一次**。2026-08-23 量到 chart 一輪 179 輪、
重讀 36.7M —— 光那一份就佔了三分之一上下。

這支把它壓成「群組｜tag｜標題」的清單：87 張 card、3.9k 字元，**28 倍**。
選定五個題目之後再去讀那五張的全文（`--card N`），是分層取材，
與 `prep_hv.py` 對每日五圖做的事同一招。

## 它不做的事

**不判斷、不選題、不取數。** 它只把四份輸入攤成一張表。
選哪五個題目、theme 撞不撞、素材夠不夠 —— 那些是第 2 步，是判斷。

`_macro_release.json` **整份原樣印出**（含 `checked_at` 與可能的 `error`），
因為 SKILL 明寫要整份搬進 `about.macro_release`，而且它只有幾百位元組。
**「偵測失敗」與「今天沒發布」是兩件事，而空的 items 與「沒發布」在下游長得一樣。**
"""
import argparse
import datetime as dt
import json
import os
import sys

TPE = dt.timezone(dt.timedelta(hours=8))
# 路徑從自己的位置推，不猜 `~`。這支住在 <某處>/kb-core/scripts/chart/，
# 其他 repo 是 kb-core 的兄弟 —— Mac 本機與 Cowork 工作區同一條規則。
# （2026-08-23 這個坑在 houseview_weekly.py 上踩過一次。）
KBCORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIB = os.path.dirname(KBCORE)
sys.path.insert(0, KBCORE)
from kbcore.series import is_monthly  # noqa: E402
WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ZH = ["一", "二", "三", "四", "五", "六", "日"]


def sib(name):
    p = os.path.join(SIB, name)
    return p if os.path.isdir(p) else os.path.expanduser("~/" + name)


def _failure_streaks(pre, anchors):
    """今天失敗的每一條，各自**連續失敗了幾輪**。回一串要印的行。

    ## 為什麼要有

    2026-09-10 那一期的執行報告寫著「`^GSPC` 429 **連續第五天**」——
    而那個「第五天」是執行者翻前幾期的報告數出來的，**不在任何程式的輸出裡**。
    prep 只印一個「失敗 1」，連是哪一條都沒說。

    這正是 `anchors.data_paths.streak_note` 記過的形狀：
    **降級若每天都成功，就不會有人把它升級成問題。** `^GSPC` 每天被 FRED 的
    `SP500` 與 ETF 代理 `SOXQ` 接住，於是一個持續五天的結構性故障，
    每天都長得像「今天有一條小失敗」。

    **帳早就在了，缺的只是讀者**：`_prefetch_history.jsonl` 從 2026-09-01 起
    每輪記一行，裡面就有 `failed`。這支把它讀出來數連續幾輪。

    門檻 `anchors.prefetch.failure_streak_warn` —— **這裡不抄數字**。
    """
    failed = pre.get("failed") or {}
    if not failed:
        return []
    hi = ((anchors or {}).get("prefetch") or {}).get("failure_streak_warn") or 3
    rows = []
    try:
        path = os.path.join(sib("chart-of-the-day"), "data", "_prefetch_history.jsonl")
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass                 # 壞行跳過，不讓一行壞掉整本帳讀不出來
    except Exception:                        # noqa: BLE001
        rows = []                            # 沒有帳就只印今天這一次，不要靜靜不印
    since = rows[0].get("run", "")[:10] if rows else ""
    out = [f"　**取數失敗 {len(failed)} 條**（連續輪數取自 `_prefetch_history.jsonl`，"
           f"帳從 {since or '—'} 起）："]
    for sid in sorted(failed):
        streak = 0
        for r in reversed(rows):
            if sid in (r.get("failed") or []):
                streak += 1
            else:
                break
        # **數到帳的第一行就停了＝這是下界，不是答案。** 帳從 2026-09-01 才開始記，
        # 在那之前失敗了幾輪這裡答不出來 —— 而「10」與「至少 10」是兩個不同的陳述。
        floor = "（帳只到這裡，所以這是**下界**）" if rows and streak == len(rows) else ""
        if streak >= hi:
            head = (f"**連續 {streak} 輪**{floor} —— 已達 {hi} 輪門檻。"
                    "每天都被代理接住不代表它好了：照 `anchors.data_paths.streak_note`，"
                    "在 `about.run` 具名寫一句，並判斷要不要改登錄")
        elif streak:
            head = f"連續 {streak} 輪{floor}"
        else:
            head = "（帳上查不到連續紀錄——今天第一次失敗，或那幾輪根本沒跑）"
        out.append(f"　　{sid:<14}{head}")
        out.append(f"　　　　{str(failed[sid]).splitlines()[0][:100]}")
    return out


def _cadence(s):
    """這條序列是不是月頻。回 `(monthly, how)`，`how` 是這個答案哪來的。

    **`how` 是這個函式存在的一半理由。** 2026-09-10 那次之所以難看見，
    正是因為判定與判定的來源在畫面上長得一樣 —— 一個猜出來的「月頻」
    跟一個量出來的「月頻」印出來一模一樣。所以來源要跟著答案一起走。

    · `status` —— 預抓在取數當下量的（`prefetch.py` 寫進狀態檔的 `monthly`）
    · `cache`  —— 回頭讀 `data/series/<id>.csv` 的整條日期
    · `unknown`—— 兩條都拿不到，**當日頻**（嚴的那把尺）

    判準本身在 `kbcore/series.is_monthly`，**這裡不另寫一份**。
    """
    if isinstance(s.get("monthly"), bool):
        return s["monthly"], "status"
    sid = s.get("id")
    if sid:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import fetch as _F
            d, _v = _F.read_cache(_F.cache_path(sid))
            if d:
                return is_monthly(d), "cache"
        # **`SystemExit` 要一起接。** `fetch.py` 在 import 時就呼叫 `_repo.repo()`，
        # 沒有 `CHART_REPO` 時它 `sys.exit()` —— 那是 `_repo` 刻意的「大聲失敗」，
        # 對它的呼叫者是對的，對這裡不是：這裡問的是「有沒有快取可讀」，
        # 答案「沒有」不該讓整支程式停下來（`selftest_offline` 就在這個情境裡跑）。
        except (Exception, SystemExit):                  # noqa: BLE001
            pass                                         # 讀不到快取不是錯誤，往下走
    return False, "unknown"


def _kind_variety(anchors, today, n=14):
    """近 n 期用過哪些非折線圖型、各自上一次是哪一天。回一串要印的行。

    ## 為什麼要有（2026-09-13）

    `anchors.diversity.min_non_line_per_day` 是「每期至少一張非折線」，
    2026-08-09 立的，理由是前五期 25 張圖有 24 張是 timeseries。
    2026-09-13 回頭量近 14 期：規則**天天都滿足**，而 19 張非折線圖
    只有兩種圖型（`grouped_bar` 12、`scatter` 6，加上當期）；
    `range_area` 上一次是 08-30、`waterfall` 08-27，
    `heatmap`／`gauge`／`stacked_bar`／`pct_stacked_bar` 一次都沒有。

    **規則沒有失效，是它想防的事換了一個形狀回來** —— 從「五張都是折線」
    變成「那一張永遠是同一種」。`chart.diversity` 的 blind_to 裡逐字寫著
    「同一種非折線圖型連續用了一個月」，它現在成真了。

    ## 為什麼是量測、而且放在 prep 而不是 checks

    放進檢查就得決定「幾種算夠」，而那個數字沒有人量得出來 ——
    當天每個題目真的都適合長條圖時，硬換圖型比重複更糟
    （`anchors.diversity.source` 自己就是這麼寫的）。
    所以它不擋任何東西，只在**選題發生之前**把事實擺在桌上：
    `scan_moves` 的註解那句「**掃到什麼才會想到什麼**」對圖型一樣成立。

    **它看不到的**：index 的 `kinds` 是逐日去重的，所以同一天用了兩張
    `grouped_bar` 在這裡只算一次；2026-08-20 之前的 entry 沒有 `kinds`
    （那批寫的是 `slots`），整筆跳過而不是當成零。
    """
    line_kinds = set((anchors.get("diversity") or {}).get("line_kinds") or ["timeseries"])
    # **認「有 `data` 欄位的那些鍵」，不認「不是底線開頭的鍵」。**
    # 第一版用後者，於是 `range_area_is_heavy`（一段散文）被當成一種圖型，
    # 印進了「一次都沒出現」那一行 —— **一個不存在的圖型，看起來跟真的一樣。**
    # `anchors.kinds` 裡圖型與說明是混住的，唯一分得開的特徵就是 `data`。
    known = [k for k, v in (anchors.get("kinds") or {}).items()
             if isinstance(v, dict) and v.get("data")]
    idx, _e = load(os.path.join(sib("chart-of-the-day"), "data", "index.json"), "index.json")
    days = [x for x in ((idx or {}).get("days") or []) if x.get("date", "") < today]
    days = [x for x in days if isinstance(x.get("kinds"), list)][:n]
    if not days:
        return ["**圖型多樣性**：index 讀不到或沒有帶 `kinds` 的 entry —— 這一輪沒有量到"]
    last_seen, counts = {}, {}
    for x in days:                                   # index 是由新到舊
        for k in x["kinds"]:
            if k in line_kinds:
                continue
            counts[k] = counts.get(k, 0) + 1
            last_seen.setdefault(k, x["date"])
    used = "、".join(f"{k} {counts[k]} 期（上次 {last_seen[k]}）"
                     for k in sorted(counts, key=lambda z: -counts[z]))
    never = [k for k in known if k not in line_kinds and k not in counts]
    out = [f"**圖型多樣性**（近 {len(days)} 期，量測不是閘門）：非折線用過 {len(counts)} 種 —— {used}"]
    if never:
        out.append(f"　這 {len(never)} 種 {n} 期內一次都沒出現：{'、'.join(never)}"
                   "　—— **不是要你今天硬用一種**（硬塞比重複更糟），"
                   "是提醒「每期至少一張非折線」正在窄化成「每期至少一張同一種」")
    return out


def _stale(ser, anchors, today):
    """把預抓涵蓋的序列照**各自的**門檻分成硬失敗與警示兩堆。回 (bad, warn)。

    ## 為什麼不是「末日最舊的五條」

    舊寫法是 `sorted(ser, key=last)[:5]`，**按字串排序的原始日期**。
    2026-08-30 實測它的後果：印出來的五條是 `2382.TW`（06-30）與四條月頻
    FRED 序列（CPIAUCSL／CPILFESL／PAYEMS／PCEPI，全部 07-01）——
    **那四條對月頻門檻完全正常**，卻把真正硬失敗的 `^TWOII`（07-17、落後 44 天）
    擠到第六名，於是它**一次都沒有被印出來**。
    不是「沒有標示出來」，是根本沒出現在畫面上。

    同一天還有第二條同樣安靜的：`2382.TW` 出現了，但它跟旁邊四條月頻序列
    **長得一模一樣**（都只是一行 `last=`），讀的人分不出誰正常誰壞掉。

    門檻一律從 `anchors.freshness` 讀，日／週／月三套各自判 —— **這裡不抄數字**。
    日頻的交易日換算直接用 `checks.chart._weekdays_after`，
    **不在這裡再寫一份**：兩份實作遲早會漂，而漂的那天 prep 與檢查會給出不同答案。

    ## 月頻怎麼判（2026-09-10 訂正）

    原本是 `last.endswith("-01")` —— **只看末日那一筆**。
    任何日頻序列每個月都會有一天剛好落在 1 號，那一天它的門檻會從
    「5 個交易日」鬆成「3 期（約 90 天）」，而畫面上完全看不出來。

    2026-09-10 真的發作：`DCOILBRENTEU` 末日 2026-09-01、落後 7 個交易日，
    `9 // 30 = 0` 期 —— **它在硬失敗與警示兩堆裡都沒有出現**。
    那一輪的軌道圖因此改了題，而 `chart_verify` 是全綠的。

    現在的來源優先序，**兩條都看得到整條日期，不再靠猜**：

    1. 預抓寫進狀態檔的 `monthly` 欄（`prefetch.py` 在取數當下量的）。
    2. 狀態檔沒有那個欄位（舊檔）就回頭讀 `data/series/<id>.csv` 的整條日期。

    兩條都拿不到就**當日頻**並在說明裡標 `頻率未知`。
    這是刻意的不對稱：判錯成月頻會讓門檻鬆 30 倍、而且安靜，
    判錯成日頻只會多響一次警示。
    """
    F = (anchors or {}).get("freshness") or {}
    weekly_ids = F.get("weekly_release_series") or {}
    # **逐條的生效日優先於全域那一個**（2026-09-13）。理由與讀法在
    # `anchors.freshness.weekly_release_series_from_source`，**這裡不抄第二份**。
    # 這一支與 `checks/chart.py` 的 `_freshness` 是同一條規則的兩個讀者，
    # 兩邊要同時改 —— 只改一邊的話，prep 說「不能用」而檢查說 PASS，
    # 而那一天沒有任何東西會說是哪一邊變了。
    weekly_since = F.get("weekly_release_series_from") or {}
    weekly_global = F.get("weekly_release_from") or "9999-12-31"
    try:
        sys.path.insert(0, KBCORE)
        from checks.chart import _weekdays_after
    except Exception:                                    # noqa: BLE001
        _weekdays_after = None
    trading_on = bool(F.get("daily_counts_trading_days")) and \
        today >= (F.get("trading_days_from") or "9999-12-31") and _weekdays_after
    bad, warn = [], []
    now = dt.date.fromisoformat(today)
    for s in ser:
        last = str(s.get("last") or "")
        if len(last) < 10:
            continue
        try:
            ld = dt.date.fromisoformat(last[:10])
        except ValueError:
            continue
        gap = (now - ld).days
        sid = s.get("id")
        monthly, how = _cadence(s)
        if monthly:
            n, unit = gap // 30, "期（月頻）"
            hi, lo = F.get("monthly_fail_periods", 3), F.get("monthly_warn_periods", 2)
        elif sid in weekly_ids and today >= (weekly_since.get(sid) or weekly_global):
            n, unit = gap // 7, "期（週頻發布）"
            hi, lo = F.get("weekly_fail_periods", 3), F.get("weekly_warn_periods", 2)
        else:
            if trading_on:
                n, unit = _weekdays_after(ld, now), "個交易日"
            else:
                n, unit = gap, "個日曆日"
            hi, lo = F.get("daily_fail_days", 5), F.get("daily_warn_days", 2)
        tail = "　頻率未知，照日頻判" if how == "unknown" else ""
        if n >= hi:
            bad.append((s, f"落後 {n} {unit}，≥ 硬失敗門檻 {hi}{tail}"))
        elif n >= lo:
            warn.append((s, f"落後 {n} {unit}，≥ 警示門檻 {lo}{tail}"))
    bad.sort(key=lambda t: str(t[0].get("last")))
    warn.sort(key=lambda t: str(t[0].get("last")))
    return bad, warn


def _dead(bad, anchors, ser):
    """把硬失敗那一堆拆成「已登錄的長期失效」與「新的」，並抓出復活的。

    回 `(dead, fresh_bad, revived)`：
      · `dead`      —— 在 `anchors.dead_series` 裡、且末日仍在登錄的那一天：一行帶過
      · `fresh_bad` —— 沒有登錄過的硬失敗：**這才是要凸顯的那些**
      · `revived`   —— 登錄過但末日已經越過 `revive_if_last_after`：要求把登錄拿掉

    ## 為什麼要拆

    2026-09-04 之前每一輪的執行報告都在重寫同一段 `^TWOII` 的降級說明，
    而那條序列從 2026-07-17 起就沒有更新 —— **它是持續的缺口，不是當日事件**。
    代價是新的降級被它淹掉：那一期 `^GSPC` 的 429 就排在它後面。

    ## 為什麼一定要有 `revived`

    **一條「不用再報」的登錄就是一條會藏住復活的登錄。** 反向那一半必須跟登錄同時存在，
    否則哪天櫃買指數回來了，這裡會照舊印「已登錄失效」而沒有人會去查。
    這是 `handshake.failed_empty_means` 那次學到的：一格只寫了「有東西＝壞了」、
    沒寫「空的不代表好」，讀的人就要自己把兩段接起來才看得見。
    """
    reg = {k: v for k, v in ((anchors or {}).get("dead_series") or {}).items()
           if isinstance(v, dict)}
    dead, fresh_bad, revived = [], [], []
    for s, why in bad:
        r = reg.get(s.get("id"))
        if r is None:
            fresh_bad.append((s, why))
            continue
        after = str(r.get("revive_if_last_after") or "")
        if after and str(s.get("last") or "") > after:
            revived.append((s, r))
        else:
            dead.append((s, r, why))
    # 登錄過、今天**有被抓到**、但連硬失敗都沒進 —— 那也是復活，而且更安靜：
    # 它不在 `bad` 裡，所以上面那個迴圈根本走不到它。
    # **條件是它出現在今天的涵蓋清單裡**：只是「今天沒抓它」不算復活，
    # 否則預抓清單一改，這裡就會噴一堆假的好消息。
    in_bad = {s.get("id") for s, _ in bad}
    fetched = {s.get("id") for s in (ser or [])}
    for sid, r in reg.items():
        if r.get("revive_if_last_after") and sid in fetched and sid not in in_bad:
            got = next((s for s in ser if s.get("id") == sid), {"id": sid})
            revived.append((got, r))
    return dead, fresh_bad, revived


def load(path, what):
    """讀不到就說出來並回 None。**讀不到與「裡面是空的」是兩件事。**"""
    if not os.path.exists(path):
        return None, f"{what} 不在：{path}"
    try:
        return json.load(open(path, encoding="utf-8")), None
    except Exception as e:
        return None, f"{what} 讀不開：{type(e).__name__}: {e}"


def topics(adv):
    """把上游的 card 攤成一行一條。

    **形狀不對就說出來，不要靜靜跳過。** `prep_hv.py` 2026-08-23 踩過：
    `sections` 是 list 不是 dict，而它的 isinstance 判斷讓整節無聲消失，
    輸出仍然看起來完整。這裡每一層都回報遇到的實際型別。
    """
    out, notes = [], []
    secs = adv.get("sections")
    if not isinstance(secs, list):
        return [], [f"sections 不是 list，是 {type(secs).__name__} —— 上游形狀變了"]
    for si, s in enumerate(secs):
        gs = s.get("groups")
        if not isinstance(gs, list):
            notes.append(f"第 {si+1} 節「{s.get('title','?')}」的 groups 是 "
                         f"{type(gs).__name__}，跳過這一節")
            continue
        for g in gs:
            for c in g.get("cards") or []:
                out.append({
                    "group": g.get("label", "?"), "tag": c.get("tag", ""),
                    "title": c.get("title") or c.get("head") or "",
                    "date": c.get("date", ""), "tone": c.get("tone", ""),
                    "deep": bool(c.get("deep")), "src": c.get("src", "")})
    return out, notes


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--card", type=int, default=None,
                    help="印出第 N 張 card 的全文（選定題目之後才用）")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args(argv[1:])
    if a.help:
        print(__doc__)
        return 0

    day = a.date or dt.datetime.now(TPE).date().isoformat()
    d = dt.date.fromisoformat(day)
    anchors, e1 = load(os.path.join(KBCORE, "chart", "anchors.json"), "chart/anchors.json")
    if anchors is None:
        print(e1, file=sys.stderr)
        return 12
    adv, e_adv = load(os.path.join(sib("advisory-rewrite"), "data", f"{day}.json"),
                      "上游投顧當日 JSON")
    pre, e_pre = load(os.path.join(sib("chart-of-the-day"), "data", "_prefetch_status.json"),
                      "預抓狀態檔")
    mac, e_mac = load(os.path.join(sib("chart-of-the-day"), "data", "_macro_release.json"),
                      "三大數據發布偵測")

    if a.card is not None:
        if adv is None:
            print(e_adv, file=sys.stderr)
            return 12
        cards = []
        for s in adv.get("sections") or []:
            for g in s.get("groups") or []:
                cards += (g.get("cards") or [])
        if not 1 <= a.card <= len(cards):
            print(f"--card 要在 1..{len(cards)}", file=sys.stderr)
            return 12
        print(json.dumps(cards[a.card - 1], ensure_ascii=False, indent=1))
        return 0

    print(f"# 每日五圖 · 開工盤點　{day}（星期{ZH[d.weekday()]}）\n")

    # ── 軌道 ──────────────────────────────────────────────
    T = anchors.get("tracks") or {}
    wk = WD[d.weekday()]
    if d.weekday() >= 5:
        prev = (d - dt.timedelta(days=1)).isoformat()
        pdat, _ = load(os.path.join(sib("chart-of-the-day"), "data", f"{prev}.json"), "前一日")
        used = ""
        for c in ((pdat or {}).get("charts") or []):
            if "軌道圖" in str(c.get("slot", "")):
                used = str(c.get("slot", ""))
        print(f"**軌道**：週末 → {T.get('weekend_mode','週線複查')}　"
              f"（標籤格式 `{T.get('weekend_slot_label','')}`）")
        print(f"　昨天（{prev}）用的是：{used or '（讀不到前一日，要人工確認）'}")
        if T.get("weekend_distinct_days"):
            print("　**週六與週日不得挑同一條** —— 上面那一條今天不能再用")
    else:
        print(f"**軌道**：{T.get(wk, '（anchors.tracks 裡沒有這一天）')}（{wk} 綁死，不是輪流）")
    S = anchors.get("structure") or {}
    print(f"**版位**：{'／'.join(S.get('slots') or [])}"
          f"　theme 不得重複＝{S.get('theme_unique_within_day')}\n")
    for line in _kind_variety(anchors, day):
        print(line)
    print()

    # ── 預抓 ──────────────────────────────────────────────
    print("## 預抓")
    if pre is None:
        print(f"　**{e_pre}** —— 沒有狀態檔＝預抓沒跑，"
              "**不是「可能沒跑」**；`about.data_path` 不可宣稱 prefetch")
    else:
        vh = ((anchors.get("prefetch") or {}).get("status_valid_hours")) or 30
        fin = pre.get("finished") or pre.get("started") or ""
        age = None
        try:
            age = (dt.datetime.now(TPE) - dt.datetime.fromisoformat(fin)).total_seconds() / 3600
        except Exception:
            pass
        mark = "逾期" if (age is not None and age > vh) else "有效"
        print(f"　{fin}　{'%.1f 小時前' % age if age is not None else '（時間讀不出來）'}"
              f"　門檻 {vh}h → **{mark}**")
        print(f"　{pre.get('ok','?')}/{pre.get('requested','?')} 條成功　"
              f"失敗 {len(pre.get('failed') or {})}　跳過 {len(pre.get('skipped') or {})}")
        for line in _failure_streaks(pre, anchors):
            print(line)
        # **哨兵單獨一行，而且只有轉綠時才要處置。**（2026-09-13 加）
        # 在此之前它躲在 `failed` 裡，於是它每天都被 `_failure_streaks` 報成
        # 「取數失敗 1 條、連續 N 輪」—— 那條計數器是拿來抓結構性故障的，
        # 而一個依設計每天都會紅的東西把它整條佔滿了。現在分開：
        # **紅是預期值，不必處置；綠才是新聞。**
        can = pre.get("canary") or {}
        if can.get("id"):
            if can.get("red"):
                print(f"　哨兵 {can['id']}（裸客戶端）：紅 —— 預期值，Yahoo 仍要求握手，"
                      "**不必在 `about.run` 寫它**")
            else:
                print(f"　**哨兵 {can['id']} 轉綠了** —— Yahoo 可能不再要求握手，"
                      "回頭檢討 `anchors.rate_limits.handshake_allowlist` 是否還需要，"
                      "並在 `about.run` 寫一句")
        hs = (pre.get("handshake") or {}).get("failed") or []
        if hs:
            print(f"　**握手失敗**：{'、'.join(hs)} —— 這幾條今天退回代理或改題，"
                  "並在 `about.run` 說明")
        ser = pre.get("series") or []
        if ser:
            bad, warn = _stale(ser, anchors, day)
            dead, fresh_bad, revived = _dead(bad, anchors, ser)
            print(f"　涵蓋 {len(ser)} 條，其中 **{len(bad)} 條硬失敗**"
                  f"（{len(fresh_bad)} 條新的、{len(dead)} 條已登錄長期失效）、{len(warn)} 條警示")
            # **復活排最前面，因為它是唯一一種「登錄本身該被改掉」的訊號。**
            for s, r in revived:
                print(f"　　**登錄的失效序列復活了**　{s.get('id','?')}"
                      f"（{r.get('label','')}）last={s.get('last','?')}，"
                      f"已越過登錄的 {r.get('revive_if_last_after')} —— "
                      "回頭把 `anchors.dead_series` 那一格拿掉，並在 `about.run` 寫一句")
            # 新的硬失敗逐條列，**這是這一段存在的理由**：它們在 `ok` 清單裡，
            # 不列出來就跟正常的序列長得一模一樣。
            for s, why in fresh_bad:
                print(f"　　**不能用**　{s.get('id','?'):<14}n={s.get('n','?'):<6}"
                      f"last={s.get('last','?')}　{why}")
            # 已登錄的一行帶過。**門檻沒有放寬**：用它出圖照樣會被
            # `chart.series_freshness` 判 FAIL，這裡只是不再每輪佔掉一段。
            for s, r, why in dead:
                print(f"　　（已登錄失效，不必在 about.run 重寫）　{s.get('id','?')}"
                      f"（{r.get('label','')}）last={s.get('last','?')}　{why}"
                      f"　登錄於 {r.get('registered','?')}")
            # 警示只給摘要。**逐條列會反過來蓋掉硬失敗**——2026-08-30 實測，
            # 那天警示有 32 條（多數只是日曆日在週末必然落後 2–3 天），
            # 三條真的不能用的被埋在中間。
            if warn:
                byday = {}
                for s, _why in warn:
                    byday.setdefault(str(s.get("last")), []).append(str(s.get("id")))
                print(f"　　警示 {len(warn)} 條（要在 subtitle 或 note 寫出基準日）：")
                for k in sorted(byday):
                    ids = byday[k]
                    head = "、".join(ids[:6]) + (f" 等 {len(ids)} 條" if len(ids) > 6 else "")
                    print(f"　　　末日 {k}：{head}")
            if not bad and not warn:
                print("　　（沒有任何一條落後到警示以上）")
    print()

    # ── 三大數據：整份原樣 ────────────────────────────────
    print("## 三大數據發布偵測（整份原樣，直接搬進 `about.macro_release`）")
    print("```json")
    print(json.dumps(mac, ensure_ascii=False, indent=1) if mac is not None else f"// {e_mac}")
    print("```")
    if mac is not None and mac.get("error"):
        print("**帶 error** —— 檢查會判 SKIPPED 並把錯誤說出來。"
              "「偵測失敗」與「今天沒發布」是兩件事，不要自己去問 FRED。")
    print()

    # ── 上游題材 ──────────────────────────────────────────
    print("## 上游題材")
    if adv is None:
        wait = (anchors.get("schedule") or {}).get("upstream_wait_minutes", 15)
        print(f"　**{e_adv}**")
        print(f"　上游還沒好就等 {wait} 分鐘；仍無則用前一日並在 `about.run` 註明。")
        print("　**不要改讀別的目錄** —— 舊 checkout 讀起來不會報錯，只會安靜拿到舊題材。")
        return 0
    tp, notes = topics(adv)
    for n in notes:
        print(f"　⚠︎ {n}")
    raw = len(json.dumps(adv, ensure_ascii=False))
    print(f"　{len(tp)} 條（上游整份 {raw:,} 字元，這裡只列標題）")
    print(f"　`{os.path.basename(sys.argv[0])} {day} --card N` 印第 N 張的全文\n")
    cur = None
    for i, t in enumerate(tp, 1):
        if t["group"] != cur:
            cur = t["group"]
            print(f"　── {cur}")
        flag = "★" if t["deep"] else " "
        stale = "" if t["date"] == day else f"（{t['date']}）"
        print(f"　{i:>3}{flag} [{t['tag']}] {t['title']}{stale}")
    dig = sum(len(f"{t['group']}{t['tag']}{t['title']}") for t in tp)
    print(f"\n　（標題合計約 {dig:,} 字元，壓縮 {raw/max(1,dig):.0f}×；"
          "★＝上游標為深度。**選題是第 2 步，這支不選**）")
    return 0


def selftest_offline() -> int:
    """`_dead()` 與 `_stale()` 頻率判定的回歸。不連外、不讀預抓狀態檔。

    第 4 條是這支自檢當初的理由：「今天沒抓它」**不可以**被讀成復活，
    否則預抓清單一改，這裡就會噴一堆假的好消息 —— 而假的好消息會讓人把登錄拿掉。

    2026-09-10 加上頻率那一組。**在那之前這支自檢自己就活在那個歧義裡** ——
    五個案例裡有兩個的 `last` 是 `-01` 結尾（`2026-06-01`、`2026-08-01`），
    於是它們一直是以「月頻」的門檻在跑，而案例的期望值剛好兩種判法都成立。
    **一個回歸測試如果它的案例對缺陷不敏感，它就只是在陪跑。**
    """
    a = {"freshness": {"daily_fail_days": 5, "daily_warn_days": 2,
                       "daily_counts_trading_days": True,
                       "trading_days_from": "2026-08-31"},
         "dead_series": {"^X": {"label": "測試", "registered": "2026-09-04",
                                "revive_if_last_after": "2026-07-17"}}}
    day, ok = "2026-09-04", True

    def run(ser):
        bad, _w = _stale(ser, a, day)
        return _dead(bad, a, ser)

    cases = [
        ("登錄過且末日沒動 → dead 1／fresh 0／revived 0",
         [{"id": "^X", "last": "2026-07-17"}], (1, 0, 0)),
        ("沒登錄的硬失敗 → dead 0／fresh 1／revived 0",
         [{"id": "^NEW", "last": "2026-06-01"}], (0, 1, 0)),
        ("登錄過但末日往前動（仍硬失敗）→ revived 1",
         [{"id": "^X", "last": "2026-08-01"}], (0, 0, 1)),
        ("登錄過且完全恢復（連硬失敗都沒進）→ revived 1",
         [{"id": "^X", "last": "2026-09-03"}], (0, 0, 1)),
        ("**今天沒抓它 → 一律不算復活**",
         [{"id": "^OTHER", "last": "2026-09-03"}], (0, 0, 0)),
    ]
    for label, ser, want in cases:
        got = tuple(len(x) for x in run(ser))
        if got != want:
            print(f"✗ {label}：得到 {got}、應為 {want}")
            ok = False

    # ── 頻率判定（2026-09-10 加）──────────────────────────────────
    # **三個案例的 `last` 完全相同，只有頻率不同，而期望值相反。**
    # 這正是缺陷的形狀：`2026-09-01` 這一天，日頻已經落後 7 個交易日、
    # 而月頻是 `9 // 30 = 0` 期。舊寫法只看末日字串，兩者分不開。
    day2 = "2026-09-10"
    freq_cases = [
        ("日頻末日落在 1 號 → 硬失敗（這是 2026-09-10 的 DCOILBRENTEU）",
         {"id": "^D", "last": "2026-09-01", "monthly": False}, "bad"),
        ("月頻末日落在 1 號 → 兩堆都不進",
         {"id": "^M", "last": "2026-09-01", "monthly": True}, "none"),
        ("**狀態檔沒有 monthly、快取也讀不到 → 當日頻**（嚴的那把尺）",
         {"id": "^UNKNOWN-SERIES", "last": "2026-09-01"}, "bad"),
    ]
    for label, s, want in freq_cases:
        bad, wrn = _stale([s], a, day2)
        got = "bad" if bad else "warn" if wrn else "none"
        if got != want:
            print(f"✗ {label}：得到 {got}、應為 {want}")
            ok = False
    # `_cadence` 的來源標示：答案與答案的出處要一起走，見那支的病歷。
    for s, want in [({"id": "^A", "monthly": True}, "status"),
                    ({"id": "^UNKNOWN-SERIES"}, "unknown")]:
        if _cadence(s)[1] != want:
            print(f"✗ _cadence 來源：{s} 得到 {_cadence(s)[1]}、應為 {want}")
            ok = False

    print("selftest-offline 全部通過 ✓" if ok else "★ selftest-offline 有錯")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest-offline" in sys.argv[1:]:
        sys.exit(selftest_offline())
    sys.exit(main(sys.argv))
