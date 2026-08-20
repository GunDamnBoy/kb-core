#!/usr/bin/env python3
"""節目知識庫・健康檢查

把每次維護都要手動重跑的機械式檢查集中成一支腳本。
對受檢的系統只做唯讀檢查，也絕不呼叫 git（背景推送會被 .git/index.lock 擋住）。
唯一會寫的檔案是自己的 ~/.podfetch/metrics.csv（每日指標，只追加當天一列）。

用法：
    python3 ~/.podfetch/healthcheck.py

在 Cowork 的 Linux 沙箱裡跑也可以，路徑會自動偵測掛載點。
結束碼：0 = 全部 PASS／有 WARN；1 = 有 FAIL。
"""

import glob
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

TAIPEI = timezone(timedelta(hours=8))
results = []


def log(level, check, msg):
    results.append((level, check, msg))


def resolve(*candidates):
    """先找掛載點，再找家目錄。

    順序不能顛倒：在 Cowork 沙箱裡把 `podfetch.py` 匯入測試時，它的 `log()` 會在
    沙箱家目錄建出一個空的 `~/.podfetch/logs/`，若先認家目錄就會抓到那個假目錄，
    然後報出一堆「讀不到 shows.json／state.json」與錯誤的執行時刻（2026-08-08 踩過）。
    在 Mac 上沒有 `/sessions/*/mnt`，行為不變。
    """
    for base in glob.glob("/sessions/*/mnt"):
        for c in candidates:
            p = os.path.join(base, os.path.basename(c.rstrip("/")))
            if os.path.exists(p):
                return p
    for c in candidates:
        p = os.path.expanduser(c)
        if os.path.exists(p):
            return p
    return None


REPO = resolve("~/podcast-knowledge-digest")
PODFETCH = resolve("~/.podfetch")
TRANSCRIPTS = resolve("~/podcast-transcripts")
KBCORE = resolve("~/kb-core")


# ---------------------------------------------------------------- 1. 資料檔
def check_data():
    if not REPO:
        log("FAIL", "資料檔", "找不到 podcast-knowledge-digest，資料夾未連線？")
        return
    data = os.path.join(REPO, "data")
    files = sorted(glob.glob(os.path.join(data, "20*.json")))
    bad = []
    for f in files:
        try:
            json.load(open(f, encoding="utf-8"))
        except Exception as e:
            bad.append(f"{os.path.basename(f)}: {e}")
    if bad:
        log("FAIL", "資料檔", "無法解析：" + "；".join(bad))
    else:
        log("PASS", "資料檔", f"{len(files)} 個日檔全部可解析")

    idx_path = os.path.join(data, "index.json")
    try:
        idx = json.load(open(idx_path, encoding="utf-8"))
    except Exception as e:
        log("FAIL", "index.json", f"無法解析：{e}")
        return

    dates = [d["date"] for d in idx.get("days", [])]
    if dates == sorted(dates, reverse=True):
        log("PASS", "index.json 排序", f"{len(dates)} 天，由新到舊正確")
    else:
        log("FAIL", "index.json 排序", f"未由新到舊：{dates}")

    on_disk = {os.path.basename(f)[:-5] for f in files}
    missing = [d for d in dates if d not in on_disk]
    orphan = sorted(on_disk - set(dates))
    if missing:
        log("FAIL", "index.json 對應", f"days 列了但檔案不存在：{missing}")
    if orphan:
        log("WARN", "index.json 對應", f"檔案存在但沒列進 days：{orphan}")
    if not missing and not orphan:
        log("PASS", "index.json 對應", "days 與 data/ 檔案完全對應")

    # 每日集數與 shows 欄位
    for d in idx.get("days", []):
        try:
            day = json.load(open(os.path.join(data, d["date"] + ".json"), encoding="utf-8"))
        except Exception:
            continue
        actual = len(day.get("episodes", []))
        if actual != d.get("episodeCount"):
            log("WARN", "episodeCount",
                f"{d['date']}：index.json 寫 {d.get('episodeCount')}，實際 {actual} 集")


# ------------------------------------------------------------- 2. showKey CSS
def check_showkeys():
    if not REPO:
        return
    html_path = os.path.join(REPO, "index.html")
    if not os.path.exists(html_path):
        log("FAIL", "showKey", "找不到 index.html")
        return
    html = open(html_path, encoding="utf-8").read()
    bar = set(re.findall(r"\.ep\.s-([a-z0-9-]+)", html))
    badge = set(re.findall(r"\.b-([a-z0-9-]+)\{", html))
    dark = set(re.findall(r'dark"\]\s*\.b-([a-z0-9-]+)', html))

    files = sorted(glob.glob(os.path.join(REPO, "data", "20*.json")))
    used, newest_used = set(), set()
    for f in files:
        try:
            keys = {e.get("showKey") for e in json.load(open(f, encoding="utf-8")).get("episodes", [])}
        except Exception:
            continue
        used |= keys
        if f == files[-1]:
            newest_used = keys
    used.discard(None)
    newest_used.discard(None)

    # 缺 CSS 只是視覺不一致，brief 明訂功能正常 → WARN 不是 FAIL
    missing = sorted(used - bar)
    if missing:
        log("WARN", "showKey CSS", f"資料用到但沒定義色條（會走預設藍，功能正常）：{missing}")
    else:
        log("PASS", "showKey CSS", f"資料用到的 {len(used)} 個 showKey 都有色條")

    incomplete = sorted((bar - badge) | (bar - dark))
    if incomplete:
        log("WARN", "showKey CSS", f"有色條但缺徽章或深色模式：{incomplete}")

    # 與 shows.json 對齊：只檢查最新一份。歷史檔案含已移除的節目是正常的，
    # brief 明訂不要回頭改歷史資料，拿全部歷史來比會產生永久性假警報。
    if PODFETCH:
        try:
            shows = set(json.load(open(os.path.join(PODFETCH, "shows.json"), encoding="utf-8")))
            unknown = sorted(newest_used - shows)
            retired = sorted((used - newest_used) - shows)
            # **反方向**：現役節目還沒出過集數時，`used` 裡沒有它，上面那條 CSS 對帳
            # 看不見它。而「加了節目卻忘了加色」恰好就發生在還沒出集數的那段期間——
            # 等它第一次出集數，徽章當天就是沒有顏色的，而且不會有任何錯誤。
            # 2026-08-20 加 fwdguidance 時三條 CSS 全漏，這支腳本當天跑過、判 PASS。
            uncoloured = sorted(shows - bar)
            if uncoloured:
                log("WARN", "showKey CSS",
                    f"現役節目沒有色條（第一次出集數那天會沒有顏色）：{uncoloured}")
            if unknown:
                log("FAIL", "showKey 命名",
                    f"最新一份用到不在 shows.json 的鍵值（兩邊各取名字了）：{unknown}")
            else:
                log("PASS", "showKey 命名", "最新一份全部沿用 shows.json 的鍵值")
            if retired:
                log("PASS", "已移除節目", f"僅存在於歷史資料，屬預期：{retired}")
        except Exception as e:
            log("WARN", "showKey 命名", f"讀不到 shows.json：{e}")


def _norm(t):
    """比對用的正規化：只留英數、轉小寫。

    名稱在不同文件裡寫法本來就不同——`shows.json` 是 `MacroVoices`、
    brief 寫 `Macro Voices`；`All-In Podcast` 在 README 是 `All-In`。
    **逐字比對會把這些判成缺漏**，而一條天天誤報的檢查等於沒有檢查。
    """
    return re.sub(r"[^a-z0-9]", "", t.lower())


def check_show_names_in_docs():
    """每一檔現役節目，在 brief 與 README 裡都要找得到。

    `MAINTENANCE.md` 第 5 節那張「新增一檔節目」的八步驟清單早就存在，
    第 1 步是 brief、第 5 步是 README。**它失敗過兩次，兩次同一種**：
    08-10 加 TIP 漏了 README（登記簿有紀錄），08-20 加 fwdguidance 漏了 brief。
    清單沒有錯，錯的是「靠人記得走完清單」這件事本身，所以這裡把它變成機械檢查。

    **只做一個方向。** 反方向（文件裡還留著已除役的節目）試過，
    分不出「變更紀錄裡提到 BG2」與「現況清單忘了刪 BG2」——
    前者是對的、後者是錯的，而兩者在文字上一模一樣。
    一條永遠會響的檢查會讓人不再讀它，比沒有更糟。除役後的文件清理留給第 5 節的人工步驟。
    """
    if not (PODFETCH and REPO):
        log("WARN", "節目在文件裡", "有一邊不在（沙箱通常如此），跳過")
        return
    try:
        shows = json.load(open(os.path.join(PODFETCH, "shows.json"), encoding="utf-8"))
    except Exception as e:
        log("FAIL", "節目在文件裡", f"讀不到 shows.json：{e}")
        return
    docs = {}
    for fn in ("AGENT_BRIEF.md", "README.md"):
        try:
            docs[fn] = _norm(open(os.path.join(REPO, fn), encoding="utf-8").read())
        except Exception as e:
            log("FAIL", "節目在文件裡", f"讀不到 {fn}：{e}")
            return
    bad = []
    for key, v in sorted(shows.items()):
        name = (v.get("name") or "").strip()
        if not name:
            bad.append(f"{key} 在 shows.json 沒有 name")
            continue
        n = _norm(name)
        # `All-In Podcast` 在 README 只寫 `All-In`，所以尾綴 podcast 要能省略。
        forms = {n, re.sub(r"(the)?podcast$", "", n)} - {""}
        miss = [fn for fn, t in docs.items()
                if not any(f in t for f in forms)]
        if miss:
            bad.append(f"{name}（{key}）沒出現在 " + "、".join(miss))
    if bad:
        # WARN 不是 FAIL：日報照樣跑得完，只是那一檔沒有取得方式的說明。
        log("WARN", "節目在文件裡", "；".join(bad)
            + " —— 見 MAINTENANCE.md 第 5 節的八步驟")
    else:
        log("PASS", "節目在文件裡", f"{len(shows)} 檔在 brief 與 README 都找得到")


def check_shows_sync():
    """`shows.json` 有**兩份**，這條是唯一在對它們帳的地方。

    podfetch 執行時讀的是 `~/.podfetch/shows.json`（見 podfetch.py 的 SHOWS_PATH）；
    版控的那份在 `kb-core/scripts/podcast/shows.json`，`patch_shows.py` 負責同步。
    **兩份不同步的樣子是「什麼都沒發生」**——版控那份加了一檔節目，podfetch 照舊
    不去抓它，日報少一檔，而所有檢查都是綠的，因為每一條都只讀得到其中一份。

    2026-08-20 我拿版控那份算出「21 檔現役」並據此判 fwdguidance 缺 CSS——
    **那個結論的前提是兩份一樣，而當時沒有任何東西在保證這件事。**
    """
    if not (PODFETCH and KBCORE):
        log("WARN", "shows.json 兩份", "有一邊不在（沙箱通常如此），跳過對帳")
        return
    a = os.path.join(PODFETCH, "shows.json")
    b = os.path.join(KBCORE, "scripts", "podcast", "shows.json")
    try:
        run = json.load(open(a, encoding="utf-8"))
        vcs = json.load(open(b, encoding="utf-8"))
    except Exception as e:
        log("FAIL", "shows.json 兩份", f"讀不到其中一份：{e}")
        return
    only_run = sorted(set(run) - set(vcs))
    only_vcs = sorted(set(vcs) - set(run))
    if only_run or only_vcs:
        log("FAIL", "shows.json 兩份",
            f"鍵值不一致——只在執行檔：{only_run}／只在版控：{only_vcs}"
            "（podfetch 讀的是執行檔那一份，版控那份不影響它抓什麼）")
        return
    diff = sorted(k for k in run if run[k] != vcs[k])
    if diff:
        log("WARN", "shows.json 兩份",
            f"鍵值相同但內容有差（wpm／優先序之類）：{diff}")
    else:
        log("PASS", "shows.json 兩份", f"{len(run)} 檔，執行檔與版控完全一致")


# ---------------------------------------------------------------- 3. podfetch
def check_podfetch():
    if not PODFETCH:
        log("WARN", "podfetch", "~/.podfetch 未連線，跳過管線檢查")
        return

    logs = sorted(glob.glob(os.path.join(PODFETCH, "logs", "20*.log")))
    if not logs:
        log("FAIL", "podfetch 日誌", "logs/ 裡沒有任何日誌")
        return
    latest = logs[-1]
    name = os.path.basename(latest)[:-4]
    body = open(latest, encoding="utf-8", errors="replace").read()
    head = body.split("\n", 1)[0] if body else ""

    today = datetime.now(TAIPEI).date().isoformat()
    if name != today:
        log("WARN", "podfetch 日誌", f"最新日誌是 {name}，今天是 {today}（今天還沒跑？）")

    # **不能只看第一行（2026-08-10 修）**：log 按日期附加，維護時 00:xx 手動跑過
    # 一次，正常的 01:00 排程執行就會被第一行蓋住，這裡會誤報 FAIL 並把人引去
    # 查 plist——巡檢指錯方向比沒有巡檢更貴。每次「執行」的標記是「視窗：」那
    # 一行（每次 main() 都會印），掃全檔收集所有執行的起始時刻再判斷。
    runs = re.findall(r"^\[(\d{2}):(\d{2})[^\]]*\] 視窗：", body, re.M)
    m = re.match(r"\[(\d{2}):(\d{2})", head)
    ontime = [(h, mi) for h, mi in runs if h == "01"] or \
             ([(m.group(1), m.group(2))] if m and m.group(1) == "01" else [])
    # 判斷順序：掃全檔的結果優先於「第一行長怎樣」——第一行可能是手動執行或雜訊
    if ontime:
        h, mi = ontime[0]
        extra = ("" if len(runs) <= 1
                 else f"（本日共 {len(runs)} 次執行，含手動；已認 01:{mi} 那次）")
        log("PASS", "podfetch 時刻", f"{name} 於 {h}:{mi} 準時執行{extra}")
    elif not m:
        log("WARN", "podfetch 時刻", f"{name} 開頭沒有時間戳：{head[:60]}")
    else:
        sec = head[m.end():m.end() + 3]
        punctual = sec.startswith(":0") and sec[2:3] in ("0", "1", "2")
        hint = (f"（{m.group(1)}:{m.group(2)}{sec} 是「整點加一兩秒」，"
                f"這是 StartCalendarInterval 準時觸發的特徵，優先懷疑 plist 的時刻值）"
                if punctual else "")
        log("FAIL", "podfetch 時刻",
            f"{name} 於 {m.group(1)}:{m.group(2)} 執行，不是 01:00——日報可能搶在它前面。{hint}"
            f"依序查三項，三項都要看完，不要查到一項就收手："
            f"(1) plist 的 StartCalendarInterval 應為 Hour=1（最便宜也最確定，先查這項）"
            f"(2) `pmset -g custom` 的 AC Power 段 sleep 應為 0（主要保障）"
            f"(3) `pmset -g sched` 應有 00:55 排定喚醒（後備）。"
            f"注意：先查到的值若今天被人改過，它只能證明現在、不能證明事發當時。")

    if "沒有新集數。" in body:
        log("PASS", "podfetch 結果", f"{name} 為 0 集，正常結束（不會建立目錄，屬預期）")
    elif "完成：" in body:
        log("PASS", "podfetch 結果", f"{name} " + body.strip().rsplit("]", 1)[-1].strip()[:60])
    else:
        log("WARN", "podfetch 結果", f"{name} 結尾非正常收束：…{body.strip()[-80:]}")

    try:
        st = json.load(open(os.path.join(PODFETCH, "state.json"), encoding="utf-8"))
        last = datetime.fromisoformat(st["last_run_utc"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        # 2026-08-16：`last_run_utc` 從此不再等於「podfetch 上次跑的時刻」——
        # 0 集那天 podfetch 正常執行但**刻意不推進**它（防止暫時性失效變成永久缺口）。
        # 所以一個真 0 集的週末就會讓這個數字自然長到 50 小時以上，舊的 30 小時門檻
        # 會對完全正常的系統報 WARN。**「podfetch 今天有沒有跑」由上面的日誌檢查回答，
        # 這裡只回答「視窗起點離現在多遠」**——兩件事已經分家，門檻也要跟著分家。
        # 取 96 小時：連三天 0 集（週末＋一個假日）仍在容忍內，再久就值得看一眼。
        stale_h = 96
        lvl = "PASS" if age < stale_h else "WARN"
        note = ("（0 集日不推進，這個數字不等於「上次執行時刻」）"
                if age >= 30 else "")
        log(lvl, "podfetch state",
            f"last_run_utc {st['last_run_utc']}（視窗起點，{age:.1f} 小時前）{note}；"
            f"model_pool 剩 {len(st.get('model_pool', []))} 個模型")
    except Exception as e:
        log("WARN", "podfetch state", f"讀不到 state.json：{e}")


# ------------------------------------------------------------- 4. 逐字稿品質
def check_transcripts():
    if not TRANSCRIPTS:
        log("WARN", "逐字稿", "~/podcast-transcripts 未連線，跳過")
        return
    dirs = sorted(d for d in glob.glob(os.path.join(TRANSCRIPTS, "20*")) if os.path.isdir(d))
    if not dirs:
        log("WARN", "逐字稿", "沒有任何日期目錄（可能連續 0 集）")
        return
    latest = dirs[-1]
    try:
        m = json.load(open(os.path.join(latest, "manifest.json"), encoding="utf-8"))
    except Exception as e:
        log("WARN", "逐字稿", f"{os.path.basename(latest)} 讀不到 manifest：{e}")
        return
    eps = m["episodes"] if isinstance(m, dict) and "episodes" in m else m
    counts = {}
    for e in eps:
        counts[e.get("status", "?")] = counts.get(e.get("status", "?"), 0) + 1
    desc = "／".join(f"{k} {v}" for k, v in sorted(counts.items()))
    lvl = "FAIL" if counts.get("FAILED") else ("WARN" if counts.get("DEGRADED") else "PASS")
    tail = ""
    if counts.get("FAILED"):
        tail = "；未完成的集數不推進 last_run_utc，下次執行會自動重抓"
    log(lvl, "逐字稿品質", f"{os.path.basename(latest)}：{len(eps)} 集（{desc}）{tail}")


# ------------------------------------------------- 4B. 待補回的佔位集數
def check_pending():
    """最新資料檔裡 source 以 ⚠︎ 開頭的集數＝當時沒拿到全文。
    podfetch 重抓成功後必須重寫這些集，去重規則不可把它們當成已收錄。"""
    if not REPO:
        return
    files = sorted(glob.glob(os.path.join(REPO, "data", "20*.json")))
    if not files:
        return
    try:
        d = json.load(open(files[-1], encoding="utf-8"))
    except Exception:
        return
    pending = [e for e in d.get("episodes", []) if str(e.get("source", "")).startswith("⚠︎")]
    name = os.path.basename(files[-1])[:-5]
    if pending:
        titles = "；".join(e.get("title", "?")[:26] for e in pending)
        log("WARN", "待補全文",
            f"{name} 有 {len(pending)} 集只有佔位（{titles}）。"
            f"下次若抓到全文要**重寫**這幾集，不要被去重擋掉")
    else:
        log("PASS", "待補全文", f"{name} 沒有 ⚠︎ 佔位集數")


# ------------------------------------------- 4.5 觀察點記分板（2026-08-16 新增）
OBS_STATUS = {"觀察中", "應驗", "部分應驗", "落空", "無法驗證"}


def check_observations():
    """brief 第 4 節說「每天要動三個檔」，observations.json 是第三個，先前沒有任何把關。

    **這裡只擋住其中一種失效態：「有產出卻沒回訪」（`updated` 落後於最新日檔）。**
    另一種——**回訪了但只附加不改判**——本檔量得到卻刻意不報警（見下），
    所以「加了這個檢查就都擋住了」是錯的認知。2026-08-16 複驗時實測：當天新增 3 條、
    改判 0 條，本檢查照樣回 PASS。

    **這裡刻意只用一個訊號，沒有照 MODIFY.md 的「兩個獨立訊號同時成立」。**
    那條規則針對的是單獨看必然有雜訊的啟發式訊號（大間隙佔比、泛稱佔比那一類）。
    這裡比的是兩個 ISO 日期字串，沒有雜訊來源：有日檔就代表那天有集數、有後記，
    `updated` 就該跟著動。**0 集日不產日檔，所以真 0 集不會誤報**——這正是護欄所在。

    **積壓數字只印不報警。** 47/56 卡在「觀察中」是現況，算不算問題要人看；
    讓它變成每天都亮的 WARN，只會被當成背景噪音（同「完整度 1.2–1.3 變常態」的教訓）。
    """
    if not REPO:
        return
    path = os.path.join(REPO, "data", "observations.json")
    if not os.path.exists(path):
        log("WARN", "觀察點記分板",
            "找不到 data/observations.json——brief 第 4 節列為每天要動的三個檔之一")
        return
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        log("FAIL", "觀察點記分板", f"解析失敗：{type(e).__name__}: {e}")
        return

    items = d.get("items") or []
    updated = str(d.get("updated") or "")
    files = sorted(glob.glob(os.path.join(REPO, "data", "20*.json")))
    latest = os.path.basename(files[-1])[:-5] if files else ""

    open_items = [i for i in items if i.get("status") == "觀察中"]
    judged = [i for i in items if i.get("verdictDate")]
    bad = sorted({str(i.get("status")) for i in items if i.get("status") not in OBS_STATUS})
    oldest = min((i.get("date", "") for i in open_items), default="")
    age = ""
    if oldest:
        try:
            n = (datetime.now(TAIPEI).date()
                 - datetime.strptime(oldest, "%Y-%m-%d").date()).days
            age = f"，最舊觀察中 {oldest}（{n} 天）"
        except Exception:
            pass
    stats = f"觀察中 {len(open_items)}／已判 {len(judged)}／共 {len(items)}{age}"

    # **不要用 elif 鏈**：2026-08-16 複驗實測，非法 status 會把「落後 15 天」整條蓋掉——
    # 次要的資料衛生檢查排在主要目的（回訪把關）前面，等於用小問題遮住大問題。
    problems = []
    if not files:
        problems.append("data/ 底下沒有任何日檔，這次等於什麼都沒驗到")
    elif not updated:
        problems.append("缺 updated 欄位，無法判斷有沒有回訪")
    elif latest > updated:
        problems.append(f"最新日檔是 {latest}，記分板的 updated 停在 {updated}"
                        f"——**那天有產出卻沒回訪**（brief 第 4 節：每天要動三個檔）")
    if bad:
        problems.append(f"status 出現合法值域外的值 {bad}"
                        f"（只能是 觀察中／應驗／部分應驗／落空／無法驗證）")
    if problems:
        log("WARN", "觀察點記分板", "；".join(problems) + f"。{stats}")
    else:
        log("PASS", "觀察點記分板",
            f"updated {updated} 與最新日檔 {latest} 同步。{stats}")


# ------------------------------------------------------------- 5. 推送鏈（唯讀）
def check_push():
    if not REPO:
        return
    def read(p):
        try:
            return open(os.path.join(REPO, p), encoding="utf-8").read().strip()
        except Exception:
            return None
    def packed(refname):
        # git gc 之後 loose ref 檔會消失、進 .git/packed-refs——沒有這個 fallback，
        # gc 一跑這項檢查就變成每天假 WARN（2026-08-10 補）。
        # **loose 永遠優先**：packed-refs 可能是舊快照，順序反了會把「已同步」
        # 誤報成「落後」。
        body = read(".git/packed-refs")
        if not body:
            return None
        for line in body.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == refname:
                return parts[0]
        return None

    local = read(".git/refs/heads/main") or packed("refs/heads/main")
    origin = (read(".git/refs/remotes/origin/main")
              or packed("refs/remotes/origin/main"))
    if not local or not origin:
        log("WARN", "推送鏈", "讀不到 refs（loose 與 packed-refs 都沒有；"
                          "不要用 git 指令補查，改看 .git/logs/）")
    elif local == origin:
        log("PASS", "推送鏈", f"local 與 origin 同雜湊 {local[:7]}")
    else:
        log("WARN", "推送鏈",
            f"local {local[:7]} 領先 origin {origin[:7]}——dashpush 每 180 秒推一次，稍等再看")


# --------------------------------------------------- 6. brief 內部一致性
CONFIG_KEYS = ["segment_seconds", "max_chunk_mb", "min_request_interval_seconds",
               "max_output_tokens", "default_window_hours", "max_lookback_hours",
               "flash_slots", "lite_slots", "overload_cooldown_seconds",
               "episode_budget_seconds", "run_budget_seconds",
               "stale_feed_hours"]


def check_brief():
    if not REPO or not PODFETCH:
        return
    brief_path = os.path.join(REPO, "AGENT_BRIEF.md")
    try:
        brief = open(brief_path, encoding="utf-8").read()
        cfg = json.load(open(os.path.join(PODFETCH, "config.json"), encoding="utf-8"))
    except Exception as e:
        log("WARN", "brief 一致性", f"讀不到 brief 或 config.json：{e}")
        return

    bad, missing = [], []
    for k in CONFIG_KEYS:
        if k not in cfg:
            continue
        found = {int(v) for v in re.findall(rf"{re.escape(k)}`?[：:\s]+`?(\d+)", brief)}
        if not found:
            # brief 提到這個鍵但寫成「`key` 秒（現為 300）」這種正則吃不到的句型，
            # 或根本沒寫。舊版直接 continue，於是靜默跳過卻仍回報「N 個都對得上」
            # ——檢查數與實查數脫鉤（2026-08-09 子代理抓到 episode_budget_seconds）。
            missing.append(k)
            continue
        if int(cfg[k]) not in found:
            bad.append(f"{k}：brief 寫 {sorted(found)}，config.json 是 {cfg[k]}")
    if bad:
        log("FAIL", "brief vs config", "；".join(bad))
    elif missing:
        log("WARN", "brief vs config",
            "%d/%d 個對得上；brief 裡找不到可比對的數值：%s（請寫成 `key: 值` 的形式）"
            % (len(CONFIG_KEYS) - len(missing), len(CONFIG_KEYS), "、".join(missing)))
    else:
        log("PASS", "brief vs config", f"檢查的 {len(CONFIG_KEYS)} 個設定值都對得上")

    # 節目數量：brief 宣稱 vs shows.json 實際
    try:
        shows = json.load(open(os.path.join(PODFETCH, "shows.json"), encoding="utf-8"))
        claimed = {int(n) for n in re.findall(r"(\d+)\s*檔", brief)}
        if not claimed:
            # **沒有可比的東西 ≠ 比過了沒問題。** 2026-08-20 把 brief 裡寫死的
            # 檔數與鍵值清單全部拿掉（一個檔案、一行指令的東西不值得抄第二份），
            # 於是這條沒有輸入了。原本的 else 會照樣印「brief 與 shows.json 一致
            # （21 檔）」——**一句它其實沒有驗過的話**，而且還帶著一個看起來像
            # 佐證的數字。這正是它要抓的那種錯，只是發生在它自己身上。
            log("SKIP", "節目數量", f"brief 已不再宣稱檔數（刻意），無從比對；"
                                    f"shows.json 現有 {len(shows)} 檔")
        elif len(shows) not in claimed:
            log("WARN", "節目數量", f"brief 提到 {sorted(claimed)} 檔，shows.json 有 {len(shows)} 檔")
        else:
            log("PASS", "節目數量", f"brief 與 shows.json 一致（{len(shows)} 檔）")
    except Exception:
        pass


# ------------------------------------------------------- 5B. 線上是否真的更新
def check_live():
    """比對線上 index.json 與本地。

    2026-08-07 教訓：推送鏈檢查（local == origin）報 PASS，但網站停在前一天——
    完整的鏈是「寫檔 → commit → push → Actions → Pages」，前三段對不代表最後
    一段有跑。這正是 08-03 auto-push 事故的同一個教訓往下游挪了一格。
    """
    if not REPO:
        return
    try:
        local = json.load(open(os.path.join(REPO, "data", "index.json"), encoding="utf-8"))
    except Exception:
        return
    url = ("https://gundamnboy.github.io/podcast-knowledge-digest/data/index.json"
           "?cb=%s" % datetime.now(TAIPEI).strftime("%Y%m%d%H%M%S"))
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=20) as r:
            live = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log("WARN", "線上狀態", "連不到 GitHub Pages（%s）——沙箱通常會擋，"
            "請在 Mac 上跑一次確認" % type(e).__name__)
        return

    ld, lv = local.get("updatedLabel"), live.get("updatedLabel")
    lday = (local.get("days") or [{}])[0].get("date")
    vday = (live.get("days") or [{}])[0].get("date")
    if ld == lv and lday == vday:
        log("PASS", "線上狀態", "線上與本地一致（%s，days[0]=%s）" % (lv, vday))
    else:
        log("FAIL", "線上狀態",
            "**線上落後本地**：線上 %s／days[0]=%s，本地 %s／days[0]=%s。"
            "推送鏈若為 PASS，卡點就在 GitHub Actions／Pages 部署端——去看 Actions 分頁的執行紀錄"
            % (lv, vday, ld, lday))


# ----------------------------------------------------- 6. 每日指標（唯一會寫檔的一項）
METRICS = ["date", "episodes", "ok", "degraded", "failed", "transcript_kb",
           "output_json_kb", "brief_kb", "skill_kb", "segments_done",
           "podfetch_minutes", "speaker_flags",
           "eff_tokens_k", "subagents", "agent_turns", "subagent_tokens_k"]
# `subagent_tokens_k`（2026-08-17 新增）＝子代理部分的加權 token。
# **為什麼要單獨存**：`eff_tokens_k` 是整場工作階段，裡面混了固定開銷（指示、盤點、
# 組檔、上線驗證）與一次性的維護動作（例如「幫我分析用量」本身就佔了 08-17 的 14.2%）。
# 拿它除以集數會得到不可比的數字——08-17 表面每集 985K、是 08-14 的 3.5 倍，
# 但其中 2.1 倍來自逐字稿變長（116 KB/集 vs 55），其餘來自固定成本攤到 3 集而非 12 集。
# **08-17 的子代理每 KB ＝ 1582÷349 ＝ 4.53，這是第一個實測值；08-14 沒有這一欄，
# 無法直接比較**（用 eff_tokens_k 反推要先減掉一個估來的固定成本，減多少決定結論方向，
# 所以不做）。**真正的比較從 08-17 之後才開始有基礎。** 08-15 也踩過同類的坑（事故維護成本混入）。
# **要看效率就看 `subagent_tokens_k ÷ transcript_kb`**，那才是紀律真正管得到的部分。
# 第 5.5 步的探測腳本本來就會印「子代理加權 NNNNK」，先前只是沒存下來。


TOKEN_NOTE = ""   # 量測失敗的原因，由 measure_session_tokens 填，「每日指標」那行印出


def measure_session_tokens(day):
    """量測當日排程執行的加權 token 用量。

    2026-08-09 加入。動機：08-08 changelog 寫「粗估降 60–75%」，**那是估算不是量測**
    ——當時沒有任何一天的實際數字可比，所以那句宣稱到今天仍無法驗證。

    加權方式與 Claude 的計價結構一致：cache 重讀 0.1x、cache 寫入 2x、產出 5x。
    回傳 (加權token千, 子代理數, 子代理總回合數)；讀不到就回 ("","","")。

    **2026-08-10 修：初版只找 `~/.claude/projects`，那是 Claude Code CLI 的路徑，
    而每日排程跑在 Cowork，transcript 在 `$TMPDIR/claude-hostloop-plugins/<hash>/projects/`
    底下。** 結果這一欄連續兩天都是空的——**加了量測卻沒量到，比沒加更糟，因為
    metrics.csv 看起來已經在收集基線了。** 現在同時搜尋多個候選根目錄。
    根目錄含隨機 hash、會隨版本變動，所以用 glob 而不是寫死。

    沙箱讀不到實機路徑時仍會留空，不報錯——量測失敗不該讓巡檢變紅。**但要把
    失敗原因寫進 TOKEN_NOTE 讓「每日指標」那行印出來**：08-09 到 08-10 連兩天
    留空而沒人發現，正是因為留空是靜默的。**靜默的失敗會被當成還沒有資料。**
    """
    global TOKEN_NOTE
    # 2026-08-14 起直接短路。**但 2026-08-16 把當初的結論修窄了，措辭跟著改：**
    # 已確認的只有「從別的工作階段讀不到」——08-16 實測 /sessions/ 下 70 多個其他
    # 工作階段全部 Permission denied，而排程執行的沙箱隨執行結束銷毀，事後救不回來。
    # **「排程在它自己的沙箱裡有沒有 transcript」從來沒有人驗證過**（五次嘗試都是
    # 從外面找）。SKILL.md 第 5.5 步已加入自我探測，答案會出現在每天回報第 16 項。
    # 在那之前這裡不做任何搜尋——從這支腳本的位置，怎麼找都是找不到的。
    TOKEN_NOTE = ("這四欄由維護者人工填入：從別場工作階段讀不到排程的 transcript，"
                  "且排程沙箱隨執行結束銷毀、事後救不回（08-16 的三欄已永久遺失）。"
                  "**數字改從當日回報第 16 項抄**——SKILL.md 第 5.5 步會讓排程量測自己並"
                  "印出這四個值（標明為下限）；若回報寫「PROBE=找不到」，才是真正確認"
                  "排程不留 transcript")
    return "", "", ""

    roots, tried = [], []
    for pat in (
            # **2026-08-14 用 find 實地定位出來的真實路徑**，不要再改成猜的。
            # Cowork 排程的 transcript 在：
            #   ~/Library/Application Support/Claude/local-agent-mode-sessions/
            #     <帳號>/<工作區>/local_<階段>/.claude/projects/<專案>/<uuid>.jsonl
            # 子代理在同層的 <uuid>/subagents/agent-*.jsonl（掃描邏輯本來就對得上）。
            # 前兩次分別猜成 `~/.claude/projects` 與 `$TMPDIR/claude-hostloop-plugins/`，
            # 都錯，`eff_tokens_k` 因此連續五天空白。
            os.path.expanduser("~/Library/Application Support/Claude/"
                               "local-agent-mode-sessions/*/*/*/.claude/projects"),
            os.path.expanduser("~/.claude/projects"),
            os.path.join(tempfile.gettempdir(), "claude-hostloop-plugins", "*", "projects"),
            "/var/folders/*/*/T/claude-hostloop-plugins/*/projects"):
        tried.append(pat)
        roots += [p for p in ([pat] if os.path.isdir(pat) else glob.glob(pat))
                  if os.path.isdir(p)]
    roots = sorted(set(os.path.realpath(p) for p in roots))
    if not roots:
        TOKEN_NOTE = ("token 量測：找不到任何 transcript 根目錄（試過 %d 個樣式）"
                      % len(tried))
        return "", "", ""

    def eff(u):
        return (u.get("input_tokens", 0)
                + 0.1 * u.get("cache_read_input_tokens", 0)
                + 2.0 * u.get("cache_creation_input_tokens", 0)
                + 5.0 * u.get("output_tokens", 0))

    def scan(path):
        tot = 0.0
        turns = 0
        try:
            for line in open(path, encoding="utf-8", errors="replace"):
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "assistant":
                    continue
                u = (d.get("message") or {}).get("usage")
                if not u:
                    continue
                tot += eff(u)
                turns += 1
        except Exception:
            return 0.0, 0
        return tot, turns

    # 找當天「排程執行」那個 session。**不能只挑當天最大的那個**——維護用的互動
    # 對話往往比排程執行大得多（08-09 的互動對話是排程的數倍），挑錯就等於量錯。
    #
    # **2026-08-14 改用內容特徵，不用 mtime 窗口。** 原本只認 02:30–06:00 之間
    # 修改的檔案，實測 70 個 transcript 沒有一個落在窗口內——mtime 是「最後一次
    # 寫入」，桌面 App 之後重開或續讀同一個 session 都會把它往後推。**時間是外部
    # 條件，內容才是這個檔案是什麼的證據。**
    # 排程 prompt 開頭那句話只會出現在排程執行的 transcript 裡，拿它當指紋。
    day_start = datetime.fromisoformat(day + "T00:00:00").replace(tzinfo=TAIPEI)
    lo = day_start + timedelta(hours=2, minutes=30)
    hi = day_start + timedelta(hours=6)
    MARK = "節目知識庫（Podcast Knowledge Digest）的每日產出"

    def is_scheduled_run(path):
        """這個 transcript 是不是 `day` 那天的排程執行？

        兩個條件都要成立：①開頭 256 KB 內含排程 prompt 的指紋；②檔案裡第一筆
        帶 `timestamp` 的紀錄落在 `day`（台北）。用**檔內時間**而不是 mtime。
        """
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                head = fh.read(262144)
        except Exception:
            return False
        if MARK not in head:
            return False
        for line in head.splitlines():
            try:
                ts = json.loads(line).get("timestamp")
            except Exception:
                continue
            if not ts:
                continue
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
            return t.astimezone(TAIPEI).date().isoformat() == day
        return False

    best = None
    files = []
    for root in roots:
        # 有些版本是 projects/<專案>/<uuid>.jsonl，有些多包一層，所以兩種深度都收。
        files += glob.glob(os.path.join(root, "*", "*.jsonl"))
        files += glob.glob(os.path.join(root, "*", "*", "*.jsonl"))
    files = sorted(set(files))
    if not files:
        TOKEN_NOTE = ("token 量測：根目錄有 %d 個但底下沒有 .jsonl（%s）"
                      % (len(roots), roots[0]))
        return "", "", ""
    cand = [f for f in files if is_scheduled_run(f)]
    if not cand:
        # 指紋找不到就退回舊的 mtime 窗口——排程 prompt 改寫時指紋會失效，
        # 那時至少還有一條路，而且訊息會講明是走了哪一條。
        cand = []
        for f in files:
            try:
                mt = datetime.fromtimestamp(os.path.getmtime(f), TAIPEI)
            except Exception:
                continue
            if lo <= mt < hi:
                cand.append(f)
        if cand:
            TOKEN_NOTE = "（指紋比對失敗，退回 mtime 窗口；排程 prompt 是不是改過了？）"
    for f in cand:
        sub = os.path.join(f[:-6], "subagents")
        n_sub = len(glob.glob(os.path.join(sub, "*.jsonl"))) if os.path.isdir(sub) else 0
        main_tot, _ = scan(f)
        if best is None or main_tot > best[0]:
            best = (main_tot, f, sub, n_sub)
    if not best:
        # 指紋與 mtime 兩條路都沒找到。印出最接近的幾個 mtime，
        # 讓維護時一眼看出是「判別法設錯」還是「排程根本不在這裡留紀錄」。
        stamps = []
        for x in files:
            try:
                stamps.append((datetime.fromtimestamp(os.path.getmtime(x), TAIPEI), x))
            except OSError:
                continue        # 檔案可能在 glob 之後被清掉；同函式前面已這樣防過
        near = sorted(stamps)[-3:]
        TOKEN_NOTE = ("token 量測：%d 個 transcript 都認不出是 %s 的排程執行"
                      "（指紋與 02:30–06:00 窗口都沒中）；最近三筆 mtime %s"
                      % (len(files), day,
                         "、".join(t.strftime("%m-%d %H:%M") for t, _ in near)
                         or "（都讀不到 mtime）"))
        return "", "", ""

    main_tot, chosen, sub, n_sub = best
    sub_tot = 0.0
    sub_turns = 0
    for s in glob.glob(os.path.join(sub, "*.jsonl")):
        t, n = scan(s)
        sub_tot += t
        sub_turns += n
    total = round((main_tot + sub_tot) / 1000)
    if total <= 0:
        # **0 也是失敗，不要當成量到了。** 檔案在窗口內但沒有任何帶 usage 的
        # assistant 行（格式改版、檔案被截斷、選到的是空 session）都會走到這裡。
        # 若照樣回傳 0，「每日指標」會印 PASS「加權 token 0K」——那就是把
        # 「留空看起來像還沒有資料」換成「0 看起來像量到了」，同一個失效換件衣服。
        TOKEN_NOTE = ("token 量測：選中 %s 但算出 0，該檔沒有帶 usage 的 assistant 行"
                      % os.path.basename(chosen))
        return "", "", ""
    return total, n_sub, sub_turns


def build_metric_row(day, is_today):
    """組出某一天的指標列。`day` 是 YYYY-MM-DD（台北）。

    2026-08-14 從 collect_metrics 拆出來，讓它能用在**任何一天**而不只是今天——
    metrics.csv 原本只在「跑 healthcheck 的當天」寫入，沒跑維護的日子就沒有那一列
    （08-13 就這樣缺了）。**一份有洞的基線在做趨勢比較時會安靜地誤導人。**
    """
    row = {k: "" for k in METRICS}
    row["date"] = day

    # 逐字稿：集數、狀態分布、總字數、講者訊號數
    if TRANSCRIPTS:
        d = os.path.join(TRANSCRIPTS, day)
        if os.path.isdir(d):
            try:
                m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
                eps = m["episodes"] if isinstance(m, dict) and "episodes" in m else m
                row["episodes"] = len(eps)
                for k in ("ok", "degraded", "failed"):
                    row[k] = sum(1 for e in eps if (e.get("status") or "").lower() == k)
                row["speaker_flags"] = sum(1 for e in eps if e.get("speakerNotes"))
                row["podfetch_minutes"] = round(
                    sum(e.get("durationMs", 0) for e in eps) / 60000.0)
            except Exception:
                pass
            kb = sum(os.path.getsize(f) for f in glob.glob(os.path.join(d, "*.md")))
            row["transcript_kb"] = round(kb / 1024)

    # 產出與規格檔大小。**brief／SKILL 的大小只有「今天」量得準**——它們是當下的
    # 檔案，回填舊日期時填今天的值會是假的，所以回填列一律留空。
    if REPO:
        p = os.path.join(REPO, "data", day + ".json")
        if os.path.exists(p):
            row["output_json_kb"] = round(os.path.getsize(p) / 1024)
        if is_today:
            b = os.path.join(REPO, "AGENT_BRIEF.md")
            if os.path.exists(b):
                row["brief_kb"] = round(os.path.getsize(b) / 1024)
    if is_today:
        # **這一欄在 Cowork 沙箱裡永遠是空的**（沙箱看不到 `~/Documents/`），
        # 而維護幾乎都在沙箱裡跑——所以 metrics.csv 的 skill_kb 至今一列都沒有值。
        # 要它有值就得在 Mac 的終端機直接跑 healthcheck。刻意不改成從別處猜，
        # 空值至少誠實；填一個猜來的大小會讓這一欄看起來有在追蹤。
        sk = os.path.expanduser(
            "~/Documents/Claude/Scheduled/podcast-digest-daily/SKILL.md")
        if os.path.exists(sk):
            row["skill_kb"] = round(os.path.getsize(sk) / 1024)

    # podfetch 當日完成段數（日誌裡每段完成一行）
    lp = os.path.join(PODFETCH, "logs", day + ".log")
    if os.path.exists(lp):
        body = open(lp, encoding="utf-8", errors="replace").read()
        # 2026-08-10 改名：這個數字是「完成的段數」，不是 API 請求數——重試、探測、
        # 過載嘗試都不在裡面，快取段也不在。08-05 實測請求數是段數的 2.5 倍。
        # 舊名 podfetch_requests 會讓人拿它估 RPD 消耗而系統性低估。
        row["segments_done"] = len(re.findall(r"段完成", body))

    global TOKEN_NOTE
    keep = TOKEN_NOTE
    # **這三欄不再自動量測（2026-08-14 定案）。** 2026-08-09 加入時假設排程執行會在
    # 本機留下 transcript，猜了三次路徑、又改過一次判別法，最後用 grep 掃遍
    # `~/Library/Application Support/Claude` 才確認：**`local-agent-mode-sessions/`
    # 底下只有互動式對話，排程執行根本不在本機留紀錄。** 四次修正全都建立在一個
    # 從沒被驗證的前提上。
    #
    # 但資料一直都在——每天的 token 分析報告有，只是機器讀不到。所以改成
    # **維護時人工填入**：這裡只負責「不要把既有的值洗掉」。
    row["eff_tokens_k"], row["subagents"], row["agent_turns"] = \
        measure_session_tokens(day)
    if not is_today:
        # 回填舊日期時 measure_session_tokens 也會寫 TOKEN_NOTE，把「今天為什麼
        # 量不到」的訊息蓋成某個回填日的原因——訊息還在，但指錯日子。
        TOKEN_NOTE = keep
    return row


def collect_metrics():
    """累積每日指標到 ~/.podfetch/metrics.csv。

    2026-08-08 加入。動機：當天做了一次大幅 token 優化，卻**只能估算**降幅，
    因為從來沒有量測過任何一天的實際數字。沒有基線，下一次優化仍然只能猜。
    同一天重跑會覆寫該日那一列，不重複累積。

    2026-08-14：**同時回填 metrics.csv 缺漏的日子**。有 `data/YYYY-MM-DD.json`
    或逐字稿目錄、卻沒有對應列的日期一律補上——沒跑維護的日子原本就沒有紀錄。
    """
    if not PODFETCH:
        return
    today = datetime.now(TAIPEI).date().isoformat()
    row = build_metric_row(today, True)

    path = os.path.join(PODFETCH, "metrics.csv")
    rows, seen = [], False
    if os.path.exists(path):
        for i, line in enumerate(open(path, encoding="utf-8")):
            line = line.rstrip("\n")
            if i == 0 or not line:
                continue
            if line.split(",")[0] == today:      # 同日覆寫，不重複累積
                seen = True
                # **但人工填的 token 三欄要留著**，否則每跑一次 healthcheck 就洗掉一次。
                old = line.split(",")
                for k in ("eff_tokens_k", "subagents", "agent_turns",
                          "subagent_tokens_k"):
                    i2 = METRICS.index(k)
                    if i2 < len(old) and old[i2] and not row[k]:
                        row[k] = old[i2]
                continue
            # 舊列可能少欄（METRICS 擴充過）。**補到與表頭等長再存回**，
            # 否則表頭 15 欄、歷史列 12 欄，整份檔案就無法按欄名解析——
            # 而這份檔案存在的唯一目的就是當可解析的基線（2026-08-09 修）。
            cells = line.split(",")
            if len(cells) < len(METRICS):
                cells += [""] * (len(METRICS) - len(cells))
            rows.append(",".join(cells[:len(METRICS)]))
    rows.append(",".join(str(row[k]) for k in METRICS))

    # 回填缺漏的日子。來源是「有產出或有逐字稿」的日期，兩邊聯集。
    have = {r.split(",")[0] for r in rows}
    known = set()
    if REPO:
        known |= {os.path.basename(f)[:-5]
                  for f in glob.glob(os.path.join(REPO, "data", "20*-*-*.json"))}
    if TRANSCRIPTS:
        known |= {os.path.basename(d) for d in glob.glob(os.path.join(TRANSCRIPTS, "20*-*-*"))
                  if os.path.isdir(d)}
    filled = sorted(d for d in known - have if len(d) == 10 and d <= today)
    for d in filled:
        r = build_metric_row(d, False)
        rows.append(",".join(str(r[k]) for k in METRICS))
    rows.sort()
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(",".join(METRICS) + "\n" + "\n".join(rows) + "\n")
        base = ("已%s %s（%s 集／逐字稿 %s KB／產出 %s KB）→ metrics.csv 共 %d 天%s"
                % ("更新" if seen else "記錄", today, row["episodes"] or "?",
                   row["transcript_kb"] or "?", row["output_json_kb"] or "?",
                   len(rows),
                   "；回填 %d 天（%s）" % (len(filled), "、".join(filled)) if filled else ""))
        # **四個 token 欄要一起看，不能只看 eff_tokens_k**（2026-08-17 修）。
        # `subagent_tokens_k` 是 08-17 新增的效率分母，而 `measure_session_tokens()`
        # 不產生它、只能人工從回報第 16 項抄。舊寫法只在 eff_tokens_k 為空時出聲，
        # 而第 5.5 步探測成功後 eff_tokens_k 一定有值 → **這則提示從此不會再出現，
        # 新欄會安靜地永遠留空**，而留空看起來像「還沒有資料」不像「壞了」——
        # 那正是 08-09／08-10 連兩天沒人發現的同一種失效。
        miss = [k for k in ("eff_tokens_k", "subagents", "agent_turns",
                            "subagent_tokens_k") if row[k] == ""]
        if not miss:
            log("PASS", "每日指標",
                base + "；加權 token %sK（子代理 %sK／%s 個）" %
                (row["eff_tokens_k"], row["subagent_tokens_k"], row["subagents"]))
        elif row["eff_tokens_k"] != "":
            log("WARN", "每日指標",
                base + "；加權 token %sK。**但還缺 %s**——回報第 16 項的探測會印"
                "「子代理加權 NNNNK」，抄進 `subagent_tokens_k`。"
                "**效率要看 `subagent_tokens_k ÷ transcript_kb`**，"
                "`eff_tokens_k ÷ 集數` 混了固定開銷與一次性維護動作、不可比。"
                % (row["eff_tokens_k"], "／".join(miss)))
        else:
            # **量測失敗一定要說出來。** 08-09 到 08-10 連兩天留空沒人發現，
            # 就是因為留空看起來像「還沒有資料」而不是「壞了」。
            log("WARN", "每日指標",
                base + "。**今日的 eff_tokens_k 還沒填**——"
                "從當日 token 分析報告抄進 metrics.csv 對應欄位（加權總量千位、"
                "子代理數、子代理總回合數、**子代理加權千位**）。" + (TOKEN_NOTE or ""))
    except Exception as e:
        log("WARN", "每日指標", "寫不進 metrics.csv：%s" % e)


def main():
    for fn in (check_data, check_showkeys, check_shows_sync,
               check_show_names_in_docs, check_podfetch,
               check_transcripts, check_pending, check_observations,
               check_push, check_live, check_brief, collect_metrics):
        try:
            fn()
        except Exception as e:
            log("FAIL", fn.__name__, f"檢查本身出錯：{type(e).__name__}: {e}")

    width = max(len(c) for _, c, _ in results) if results else 10
    # SKIP 要跟 PASS 分開列。**「這條沒得判」與「這條判過沒問題」是兩件事**，
    # 而把前者印成後者，正是這支腳本存在的理由的反面。
    icon = {"PASS": "✓", "WARN": "!", "FAIL": "✗", "SKIP": "–"}
    print(f"節目知識庫健康檢查　{datetime.now(TAIPEI):%Y-%m-%d %H:%M}（台北）")
    print(f"repo={REPO}\npodfetch={PODFETCH}\ntranscripts={TRANSCRIPTS}")
    print("-" * 72)
    for lvl, check, msg in results:
        print(f"{icon[lvl]} {lvl:<4} {check:<{width}}  {msg}")
    print("-" * 72)
    tally = {k: sum(1 for l, _, _ in results if l == k)
             for k in ("PASS", "WARN", "FAIL", "SKIP")}
    line = f"PASS {tally['PASS']}　WARN {tally['WARN']}　FAIL {tally['FAIL']}"
    if tally["SKIP"]:
        line += f"　SKIP {tally['SKIP']}"
    print(line)
    return 1 if tally["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
