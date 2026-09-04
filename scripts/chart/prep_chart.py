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
WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ZH = ["一", "二", "三", "四", "五", "六", "日"]


def sib(name):
    p = os.path.join(SIB, name)
    return p if os.path.isdir(p) else os.path.expanduser("~/" + name)


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
    """
    F = (anchors or {}).get("freshness") or {}
    weekly_ids = F.get("weekly_release_series") or {}
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
        if last.endswith("-01"):                          # 月頻以每月 1 號標記
            n, unit = gap // 30, "期（月頻）"
            hi, lo = F.get("monthly_fail_periods", 3), F.get("monthly_warn_periods", 2)
        elif sid in weekly_ids:
            n, unit = gap // 7, "期（週頻發布）"
            hi, lo = F.get("weekly_fail_periods", 3), F.get("weekly_warn_periods", 2)
        else:
            if trading_on:
                n, unit = _weekdays_after(ld, now), "個交易日"
            else:
                n, unit = gap, "個日曆日"
            hi, lo = F.get("daily_fail_days", 5), F.get("daily_warn_days", 2)
        if n >= hi:
            bad.append((s, f"落後 {n} {unit}，≥ 硬失敗門檻 {hi}"))
        elif n >= lo:
            warn.append((s, f"落後 {n} {unit}，≥ 警示門檻 {lo}"))
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
    """`_dead()` 的回歸。**四個案例對應它的四條出口**，不連外、不讀預抓狀態檔。

    第 4 條是這支自檢真正的理由：「今天沒抓它」**不可以**被讀成復活，
    否則預抓清單一改，這裡就會噴一堆假的好消息 —— 而假的好消息會讓人把登錄拿掉。
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
    print("selftest-offline 全部通過 ✓" if ok else "★ selftest-offline 有錯")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest-offline" in sys.argv[1:]:
        sys.exit(selftest_offline())
    sys.exit(main(sys.argv))
