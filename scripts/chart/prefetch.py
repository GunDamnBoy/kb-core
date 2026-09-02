# -*- coding: utf-8 -*-
"""
prefetch.py — 在「網路通得出去的那台機器」上預抓序列，寫進 data/series 快取。

【為什麼需要這支】
2026-08-06 起，執行輪次所在的沙箱對外連線被出口代理擋掉（FRED／Yahoo／證交所
一律 Tunnel 403，只有 pypi 通）。**連續九天每一輪都靠瀏覽器同源備援取數**，
而那條路需要有 Chrome 執行個體在線 —— 2026-08-14 11:30 那輪剛好沒有，整輪沒有產出。

問題不在那天失敗，**在前八天的成功**：每天都「降級但成功」，於是一個持續九天的
結構性故障從來沒有被當成故障。**降級若每天都成功，就不會有人把它升級成問題。**

這支的角色是把取數移回網路正常的本機（使用者的 Mac），由 launchd 每天在
執行輪次之前跑一次，把常用序列寫進快取。執行輪次讀快取即可，
**不再依賴沙箱網路，也不再依賴 Chrome 有沒有開著。**

【明確的限制 —— 不要誤以為它解決了全部】
只預抓「核心清單 ∪ 近 14 天用過的序列」。當天臨時想到的新序列它抓不到，
那種情況仍要走瀏覽器備援。**它把常態變成不需要人，不是把例外也變成不需要人。**

用法：
    python3 ~/kb-core/scripts/chart/prefetch.py              預抓並寫快取
    python3 ~/kb-core/scripts/chart/prefetch.py --list       只印出這次會抓哪些，不連外
    python3 ~/kb-core/scripts/chart/prefetch.py --quiet      只印摘要（launchd 用）
    python3 ~/kb-core/scripts/chart/prefetch.py --history            末日歷史有幾輪，不連外
    python3 ~/kb-core/scripts/chart/prefetch.py --history DCOILBRENTEU  某條的末日怎麼跳

狀態會寫進 data/_prefetch_status.json，執行輪次與 `chart.prefetch_fresh` 靠它判斷
快取是不是新鮮、有沒有哪幾條沒抓到。**沒有狀態檔＝預抓沒跑，不是「都成功」。**
"""
from __future__ import annotations
import json, os, sys, time, datetime, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()
STATUS = os.path.join(REPO, "data", "_prefetch_status.json")
# **狀態檔每天被覆寫，所以「某條序列的末日多久跳一次」沒有任何資料可以回答。**
# 這是 2026-09-01 才發現的空白：那一輪要判 `DCOILBRENTEU` 究竟是週頻發布
# 還是單純停更，翻遍手上的東西只湊得出三筆觀測（兩份舊日檔加當天的狀態檔），
# 而那三筆剛好互相矛盾（08-27 只落後 2 個交易日，不像週頻）。
# `anchors.freshness.weekly_release_source` 當初為 H.10 那兩條解這題時，
# 靠的是連續兩天手動比對；**同一個問題再問一次，手上仍然沒有帳。**
# 所以這裡留一本 append-only 的帳：每輪一行，之後要判任何序列的發布節奏都查它。
# 刻意**沒有任何檢查在讀它** —— 它是量測，不是閘門；等資料夠了再決定要不要改門檻。
HISTORY = os.path.join(REPO, "data", "_prefetch_history.jsonl")
RECENT_DAYS = 14

# 核心清單：即使近期沒用到也維持新鮮的序列。
# 挑選依據是「軌道輪盤五條軌道各自的骨幹」＋三大數據，
# 這些是不論當天選什麼題目都很可能需要的。
CORE = [
    # 利率與匯率
    "DGS2", "DGS10", "DGS30", "^TNX", "^TYX", "^IRX", "JPY=X", "DTWEXBGS",
    # 信用與風險偏好
    "BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A3HYC", "BAMLH0A1HYBB", "^VIX",
    # 美股與 AI 半導體
    "^GSPC", "^SOX", "^IXIC",
    # 台股與資金流
    "^TWII", "2330.TW", "2317.TW",
    # 原物料與能源
    "BZ=F", "GLD", "HG=F", "XLE",
    # 三大月度數據
    "CPIAUCSL", "CPILFESL", "PAYEMS", "PCEPI", "PCEPILFE",
    # 指數與期貨的 ETF 代理（見 fetch.PROXY）。**以自己的代號預抓，不冒充原標的**——
    # 要用就在 series_spec 明寫，並依 brief §3.2 在 note 標明「ETF 非指數」。
    "SOXQ", "FEZ", "CPER",
]

# 走握手客戶端的那幾條（清單的家在 `anchors.rate_limits.handshake_allowlist`）。
# **在這裡展開成核心清單的一部分**，理由是：不預抓它們，握手那條路就只有在
# 執行輪次臨時用到時才會被走到，而**那時候壞掉才發現，已經來不及改題**。
# 每天抓一次，等於每天替那條路做一次體檢；壞了會落在 status 的 failed，看得見。
CORE += [i for i in F.handshake_allowlist() if i not in CORE]

# Yahoo 代號的 FRED 等價序列。
# 2026-08-14 首跑實測 Yahoo 整批 429、FRED 13/13 全通（API key 正常）。
# **這不是「繞過 Yahoo」，是改用有文件、有認證的官方 API** —— brief §3.1 本來就偏好那條。
# 代價寫在 brief §3.2：**FRED 的日頻序列比 Yahoo 慢一個交易日**，
# 所以「講當日事件反應」的圖仍應優先用 Yahoo；這裡預抓只是確保 Yahoo 不通時有底。
FRED_EQUIV = {
    "^VIX": "VIXCLS", "^GSPC": "SP500", "^IXIC": "NASDAQCOM",
    "^IRX": "DTB3", "^TNX": "DGS10", "^TYX": "DGS30",
    "JPY=X": "DEXJPUS", "^N225": "NIKKEI225", "BZ=F": "DCOILBRENTEU",
}


def _handshake_stale(ok: list) -> list:
    """走握手、取數成功、但末日已過硬失敗門檻的那幾條。

    **為什麼要有這一格**：`handshake.failed` 只由「取數有沒有拋錯」推出來，
    而 `^TWOII` 的失效方式是**取得到、只是來源停止更新**（2026-08-29 起
    末日凍在 2026-07-17）。它因此落在 `ok`，`failed` 是空的 —— 而
    「`failed` 空」讀起來就像「那條路是好的」。
    `anchors.rate_limits.handshake_allowlist` 早就把這件事寫下來，
    連「它從 2026-08-29 起會變安靜」都預測到了；**預測寫在文件裡，而狀態檔沒有跟上。**

    **這是量測不是閘門**（同 2026-09-01 那本 `_prefetch_history.jsonl` 的理由）：
    不改任何門檻、不擋任何產出，只是把安靜的那一半寫出來。
    `prep_chart._stale()` 每一輪本來就會把它印成「不能用」，那一段仍然是主要的出口；
    這一格補的是**狀態檔自己**的可讀性 —— 讀狀態檔的人不會同時在看 prep 的輸出。

    判定整段委外給 `prep_chart._stale()`：門檻、日／週／月三套、交易日換算全部在那裡。
    **在這裡再寫一份就是漂移**，而漂的那天兩邊會對同一條序列給出不同答案。
    取不到就回空 list 並印一行 —— **記帳失敗不可以擋住預抓**。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from prep_chart import _stale
        allow = set(F.handshake_allowlist())
        rows = [s for s in ok if s.get("id") in allow]
        bad, _warn = _stale(rows, F.anchors(), datetime.date.today().isoformat())
        return [{"id": s.get("id"), "last": s.get("last"), "why": why} for s, why in bad]
    except Exception as e:                               # noqa: BLE001
        print(f"  ⚠ 握手停滯清單算不出來（不影響預抓）：{e}", file=sys.stderr)
        return []


def recent_ids(days: int = RECENT_DAYS) -> list:
    """近 N 期實際用過的序列 id。

    **清單自己維護自己**：任何被用過一次的序列會在接下來 N 天保持新鮮，
    之後自然淘汰。硬寫死一份清單一定會爛掉，因為選題每天都在變。
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    ids = set()
    for p in sorted(glob.glob(os.path.join(REPO, "data", "20*.json"))):
        day = os.path.basename(p)[:10]
        if day < cutoff:
            continue
        try:
            doc = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for ch in doc.get("charts", []):
            for s in ch.get("series_spec") or []:
                if s.get("id"):
                    ids.add(s["id"])
    return sorted(ids)


def targets() -> list:
    seen, out = set(), []
    base = CORE + recent_ids()
    # 用到的 Yahoo 代號若有 FRED 等價序列，兩個都抓——Yahoo 不通時才有替代品可用
    base += [FRED_EQUIV[i] for i in base if i in FRED_EQUIV]
    for i in base:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


MACRO = os.path.join(REPO, "data", "_macro_release.json")


def _write_macro_release() -> None:
    """三大月度數據的發布偵測 —— **跑在有網路的這一側**。

    `anchors.structure.release_day.detection` 一直寫著「偵測需要網路、判定不需要，
    把兩者分開」，但偵測從來沒有搬過來：執行輪次在沙箱，FRED 是 Tunnel 403，
    於是每一輪都用 web_fetch 人工重建三筆 last_updated。
    2026-08-22 那輪三筆裡有一筆（PCE）根本沒重新量，只沿用前一天的值 ——
    **每天都做得到的人工重建，會在某一天悄悄少做一筆，而輸出長得一模一樣。**

    這裡失敗不影響預抓本身（序列已經寫好了），但**要留下具名的錯誤**：
    寫一個帶 `error` 的檔，比不寫檔好 —— 不寫檔跟「今天沒發布」在下游長得一樣。
    """
    now = datetime.datetime.now().astimezone()
    try:
        import macro_release as MR
        items = MR.check()
        doc = {"checked_at": now.isoformat(timespec="seconds"),
               "host": os.uname().nodename, "source": "macro_release.check()",
               "items": items}
        print("三大數據偵測：" + "、".join(
            f"{r['kind']}{'（今日發布）' if r.get('fresh') else ''}" for r in items))
    except Exception as e:
        doc = {"checked_at": now.isoformat(timespec="seconds"),
               "host": os.uname().nodename, "source": "macro_release.check()",
               "error": f"{type(e).__name__}: {e}"[:300], "items": []}
        print(f"三大數據偵測失敗（不影響序列預抓）：{doc['error'].splitlines()[0][:110]}")
    with open(MACRO, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def _append_history(status: dict) -> None:
    """把這一輪每條序列的末日 append 一行到 `HISTORY`。

    **一行一輪，不是一行一序列**：47 條壓成一個物件約 1.5 KB，
    而 `data/` 是整個目錄進版控的，append-only 的一行是這裡能產生的最小 diff
    （`_prefetch_status.json` 每天是整檔重寫）。

    **寫失敗不可以擋住預抓。** 這是一本帳，不是產出的一部分 ——
    2026-08-12 的教訓反過來也成立：把記錄失敗算成執行失敗，
    會讓一件無關的小事變成當天沒有序列可用。所以吞掉例外、只印一行。
    """
    try:
        row = {
            "run": status["finished"],
            "host": status.get("host"),
            "ok": status.get("ok"),
            "requested": status.get("requested"),
            # 只留 id → 末日。點數在狀態檔裡，這本帳要回答的是「末日多久跳一次」。
            "last": {s["id"]: s["last"] for s in status.get("series") or []},
            "failed": sorted(status.get("failed") or {}),
            "skipped": sorted(status.get("skipped") or {}),
        }
        with open(HISTORY, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:                                   # noqa: BLE001
        print(f"  ⚠ 末日歷史沒寫成（{type(e).__name__}: {e}）——預抓本身不受影響")


def _show_history(sid: str | None) -> int:
    """讀 `HISTORY`，印某條序列的末日隨每輪怎麼跳。**離線，不連外。**

    這是這本帳唯一的讀者。沒有它，帳會變成「有人記得去 `grep` 才有用的東西」——
    而 `anchors` 裡已經有兩條規則是「先量再改」，兩次都卡在沒有現成的查法。

    看的是 `末日跳動間隔`：日頻發布每輪都會跳（週末除外），
    週頻發布會連續幾輪不動然後跳一整週。**兩者在單一輪次看起來一模一樣。**
    """
    if not os.path.exists(HISTORY):
        print(f"還沒有末日歷史（{HISTORY}）——它從 2026-09-01 那一版起才開始記，"
              "第一輪之前沒有帳是預期的，不是壞掉。")
        return 0
    rows = []
    with open(HISTORY, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass                       # 壞行跳過，不讓一行壞掉整本帳讀不出來
    if not sid:
        n = len(rows)
        span = f"{rows[0]['run'][:10]} 至 {rows[-1]['run'][:10]}" if rows else "—"
        print(f"末日歷史：{n} 輪（{span}）｜{HISTORY}")
        print("加序列代號看它的末日怎麼跳，例如："
              "python3 ~/kb-core/scripts/chart/prefetch.py --history DCOILBRENTEU")
        return 0
    print(f"{sid} 的末日歷史（{len(rows)} 輪）｜{HISTORY}")
    prev, stuck = None, 0
    for r in rows:
        last = (r.get("last") or {}).get(sid)
        if last is None:
            state = "✗ 那一輪沒抓到" + (" (failed)" if sid in (r.get("failed") or [])
                                    else " (skipped)" if sid in (r.get("skipped") or [])
                                    else "")
        elif prev is None:
            state = "首筆"
        elif last == prev:
            stuck += 1
            state = f"沒動（連續 {stuck} 輪）"
        else:
            state = f"跳 {(dt_date(last) - dt_date(prev)).days} 天"
            stuck = 0
        print(f"  輪次 {r['run'][:16]}  末日 {last or '—':<12} {state}")
        if last:
            prev = last
    return 0


def dt_date(s: str):
    return datetime.date.fromisoformat(s)


def main(argv):
    quiet = "--quiet" in argv
    ids = targets()

    if "--list" in argv:
        print(f"這次會抓 {len(ids)} 條（核心 {len(CORE)} ＋ 近 {RECENT_DAYS} 天用過）：")
        for i in ids:
            print(f"  {i}")
        return 0

    if "--history" in argv:
        k = argv.index("--history")
        return _show_history(argv[k + 1] if len(argv) > k + 1 else None)

    started = datetime.datetime.now().astimezone()
    ok, failed, skipped = [], {}, {}
    # 熔斷：同一個來源連續 N 次被限流就停止再試它。
    # 2026-08-14 首跑實測：13 個 Yahoo 代號各退避 20＋40 秒後仍 429，白耗約 13 分鐘。
    # **規格說「429 是等不是繞」，但對一個明確說「不」的站台連敲 13 次不是等，是敲。**
    # 熔斷後其餘同來源標的記為 skipped（不是 failed）——它們沒被試過，不該算失敗。
    BREAK_AFTER = 3
    streak = {"yahoo": 0, "fred": 0, "tiingo": 0, "tw": 0}

    # 已知被擋的來源每天只試一條當哨兵（canary）。
    # **全部不試就再也不會發現它恢復了；全部都試就每天白耗好幾分鐘。**
    # 選最有代表性的那條：^GSPC 是最常用、也最能代表 Yahoo 整體狀態的標的。
    #
    # **2026-08-22 起這條哨兵問的是一個更小的問題**：它用的是裸客戶端，
    # 所以它答的是「裸客戶端通不通」，不是「Yahoo 通不通」——同日實測，
    # 同機同 IP 的握手客戶端拿得到資料。若 Yahoo 從此要求握手，
    # **它會永遠紅，而永遠紅的訊號跟沒有訊號一樣**。
    # 留著它是因為它仍答得出一件事：Yahoo 哪天不再要求握手（它會轉綠）。
    # 真正在替握手那條路做體檢的，是 CORE 裡那幾條允許清單的代號。
    CANARY = "^GSPC"
    canary_done = False

    for i, ident in enumerate(ids, 1):
        if ident in F.BLOCKED and not (ident == CANARY and not canary_done):
            skipped[ident] = f"來源已知被擋，改用 {F.BLOCKED[ident]}（brief §3.2）"
            if not quiet:
                print(f"  [{i}/{len(ids)}] {ident:<16} — 略過（已知被擋，用 {F.BLOCKED[ident]}）")
            continue
        if ident == CANARY:
            canary_done = True
        src = F.route_of(ident)
        if streak.get(src, 0) >= BREAK_AFTER:
            skipped[ident] = f"{src} 連續 {BREAK_AFTER} 次被限流，本輪不再嘗試"
            if not quiet:
                print(f"  [{i}/{len(ids)}] {ident:<16} — 跳過（{src} 已熔斷）")
            continue
        try:
            # use_cache=False：預抓的重點就是刷新，讀快取等於什麼都沒做
            s = F.get(ident, use_cache=False)
            last = s["d"][-1] if s.get("d") else "?"
            ok.append({"id": ident, "n": len(s.get("d") or []), "last": last})
            streak[src] = 0
            if ident in F.BLOCKED:
                print(f"  ★ {ident} 又通了——Yahoo 可能已解除封鎖，"
                      f"請重新評估 brief §3.2 的替代方案是否仍必要")
            if not quiet:
                print(f"  [{i}/{len(ids)}] {ident:<16} {len(s.get('d') or []):>5} 點，末日 {last}")
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"[:200]
            failed[ident] = msg
            if "429" in msg or "Too Many Requests" in msg:
                streak[src] = streak.get(src, 0) + 1
            if not quiet:
                print(f"  [{i}/{len(ids)}] {ident:<16} ✗ {msg.splitlines()[0][:110]}")
        time.sleep(1.0)          # 逐標的間隔，見 brief §3.2

    status = {
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "host": os.uname().nodename,
        "requested": len(ids),
        "ok": len(ok),
        "failed": failed,
        "skipped": skipped,
        "series": ok,
        "canary": {
            "id": CANARY, "client": "bare",
            "means": "裸客戶端通不通，不是 Yahoo 通不通。紅＝維持現狀（2026-08-22 起的已知值）；"
                     "綠＝Yahoo 不再要求握手，此時應回頭檢討 handshake_allowlist 是否還需要",
            "red": CANARY in failed,
        },
        "handshake": {
            "ids": list(F.handshake_allowlist()),
            "failed": [i for i in F.handshake_allowlist() if i in failed],
            "stale": _handshake_stale(ok),
            "means": "走握手客戶端的那幾條。**這裡有東西就是那條路壞了**（多半是 yfinance "
                     "又被 Yahoo 改壞），當日該圖要退回代理或改題並在 note 說明",
            "failed_empty_means": "**`failed` 是空的不代表那條路是好的。** 它只由「取數有沒有拋錯」"
                     "推出來，所以「握手成功、但來源已經停止更新」會落進 `ok`，在這一格完全看不到。"
                     "`^TWOII` 就是這個形狀：2026-08-29 之前沒裝 yfinance 時它每天落在 `failed`，"
                     "是大聲的失敗；裝了之後它落進 `ok`，涵蓋率看起來還變好了，"
                     "**而它依然過不了 freshness 的硬失敗門檻**。所以另外看 `stale`。",
            "stale_means": "走握手且**末日已過 freshness 硬失敗門檻**的那幾條 —— "
                     "取得到但不能用。**這是量測不是閘門**：預抓照樣算它成功、"
                     "涵蓋率照樣算它一條，只是這裡把「安靜的那一半」寫出來。"
                     "門檻與交易日換算都走 `prep_chart._stale()`，**這裡不抄數字也不另寫一份**。",
        },
    }
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)

    _append_history(status)
    _write_macro_release()

    # **兩種「未嘗試」的成因不同，混在一起講會讓人以為今天出了 11 個問題。**
    _n_blocked = sum(1 for v in skipped.values() if "已知被擋" in v)
    _n_break = len(skipped) - _n_blocked
    print(f"預抓完成：{len(ok)}/{len(ids)} 成功"
          + (f"，{len(failed)} 條失敗：{', '.join(list(failed)[:6])}" if failed else "")
          + (f"，{_n_blocked} 條來源已知被擋（用替代品）" if _n_blocked else "")
          + (f"，{_n_break} 條因熔斷未嘗試" if _n_break else ""))
    # 全部失敗＝網路整條不通，要讓 launchd 的錯誤日誌看得出來
    return 1 if not ok else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
