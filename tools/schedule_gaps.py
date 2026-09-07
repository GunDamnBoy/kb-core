#!/usr/bin/env python3
"""排程哨兵：**該跑的那一輪，到底有沒有跑。**

## 它問的是 `usage_gaps.py` 上面那一層

`usage_gaps.py` 問「**有回執**卻沒有 usage 列」——它拿回執在不在當成「那天跑了」，
這是刻意的，因為用節奏推算會天天誤報。但那個設計有一個它自己講明的前提：
**它只看得到「跑過的輪次」**。輪次根本沒被觸發時，回執不在，
`usage_gaps` 判定「那天沒跑，不是缺口」而回 0 —— 一聲都不會出。

2026-09-07 就是這個形狀：`advisory-daily-0730`（07:35）與 `bubble-weekly-0900`（09:04）
兩支都沒有產出任何東西，而**七支哨兵、兩個發布器、三份 log 全部安靜**。
那天被發現的唯一原因，是人自己在早上注意到儀表板沒更新。

## ⚠️ 不要讀排程器的 `lastRunAt`，它會少報

寫這一支的第一版本來要比對桌面排程器自述的 `lastRunAt`。**當天的實測否定了那個做法**：

    2026-09-07 11:30  chart-daily-1130 觸發
    2026-09-07 11:59  ~/outbox/chart/2026-09-07.receipt.json  exit 0  commit 676da60
    2026-09-07 12:00  ~/outbox/chart/2026-09-07-run-report.md
    2026-09-07 13:2x  排程器自述 lastRunAt 仍是 2026-09-06T03:31:18Z

**一輪確實跑完、發布成功、留下回執與報告，而 `lastRunAt` 沒有動。**
拿它當判準會把「跑了」讀成「沒跑」——那正是這一天稍早已經犯過一次的錯。
同一天還量到 `nextRunAt` 是**派工當下**就往前推進的，不是跑完才推，
所以「`nextRunAt` 跳過去了」也不代表那一輪被丟掉。

**排程器的自述欄位一個都不能當證據。這一支只讀產出檔。**

## 哨兵不能依賴它要監視的那個東西

這一支跑在 launchd 上，不是桌面排程器上。2026-09-07 那天 launchd 全綠
（保底層 07:20 有跑、三個 publish 迴圈都在寫 log），而桌面排程器漏了兩支——
**如果哨兵也掛在桌面排程器上，它會跟著一起安靜。**

## 節奏表是排程器 cron 的鏡像，這是刻意接受的代價

`SCHEDULE` 裡的時刻與星期，是 `~/Claude/Scheduled/` 那邊 cron 的第二份拷貝，
**而這個 repo 的其他地方一律禁止第二份拷貝**。這裡破例，理由是上一段：
哨兵去讀被監視對象的設定，就等於把兩者的存活綁在一起。

**代價要講清楚**：排程改了而這裡沒跟上，這一支會誤報或漏報，而且不會有東西叫。
所以改排程時要一起改這裡——這件事寫進 `skills/maintain/SKILL.md` 的排程那一節。
**誤報一次就沒有人看了**，這是 `usage_gaps` 的 plist 註解裡已經寫過的話。

## 它不補，只報

跟 `usage_gaps.py` 同一條規矩。它不去啟動任何排程、不寫任何系統的資料，
只讀檔並寫一份 `~/.kbusage/schedule-gaps.md`。

## 它看不到的（blind_to）

- **morning-brief**：產出是「本機存檔 ＋ 更新 artifact」，不走 `~/outbox` 也沒有回執，
  **這一支判不了它**。2026-09-07 那天它同樣沒有產出，而這裡查不出來。
- **跑了但內容是錯的**：回執在、exit 0，這一支就算它跑了。內容對不對是各套自己的驗證程式的事。
- **跑了但被 park**：`auto_publish.py`（bubble）park 掉的草稿不會留下當日回執，
  這一支會判成「沒跑」。兩者的處置不同，**看到 bubble 有缺口時要先去看 `~/outbox/bubble/*.parked`**。
- **同一天跑了兩次**：只看有沒有，不看幾次。
- **排程被停用**：`enabled: false` 的排程不該被算成缺口，而這一支讀不到 enabled。
  停用一支排程時要一起把它從 `SCHEDULE` 拿掉。
- **這一支自己沒跑**：launchd 掛了就沒有人在看它。`com.kenny.kbwatch` 管 plist 的存活。

## 退出碼

0 = 沒有缺口；12 = 有缺口；14 = 環境問題（`~/outbox` 讀不到）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usage_report import OUTBOX_DIR  # noqa: E402

# 輪次的「日期」是**台北那一天**。寫死是刻意的，理由與 usage_gaps.py 同一條：
# 吃 $TZ 會讓同一支腳本在別的環境算出別的「昨天」。
TPE = dt.timezone(dt.timedelta(hours=8))

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.receipt\.json$")

# ---------------------------------------------------------------------------
# 節奏表：桌面排程器 cron 的鏡像（見上面的說明，這是刻意的第二份拷貝）
#
#   dow    ── None 表示每天；否則是 Python 的 weekday()（週一 = 0）
#   at     ── 排定時刻（台北，時, 分）。取 cron 的值，不含 jitter。
#   grace  ── 從排定時刻起算，允許多久之後才看得到產出（分鐘）。
#             這是「那一輪要跑多久」而不是「排程器慢多久」——
#             advisory 一輪約 1.5–2 小時，所以它的餘裕最大。
#             實測值：advisory 09-06 那輪 07:35→09:28（113 分）、
#             09-07 人工補跑 08:41→10:41（120 分）；chart 09-07 11:30→11:59（29 分）；
#             podcast 09-07 03:07→03:30（23 分）、09-03 那輪到 06:16（189 分，最慢的一次）。
# ---------------------------------------------------------------------------
SCHEDULE = {
    "advisory":        {"dow": None, "at": (7, 30),  "grace": 180},
    "podcast":         {"dow": None, "at": (3, 0),   "grace": 240},
    "chart":           {"dow": None, "at": (11, 30), "grace": 90},
    "bubble":          {"dow": 0,    "at": (9, 0),   "grace": 180},
    "convergence":     {"dow": 0,    "at": (15, 0),  "grace": 180},
    "broker-research": {"dow": 6,    "at": (23, 0),  "grace": 240},
    "houseview":       {"dow": 4,    "at": (16, 30), "grace": 180},
}


def due_date(system: str, now: dt.datetime):
    """回「現在最近一次**應該已經產出**的那一天」，還沒到就回 None。

    判準是**排定時刻 ＋ grace 已經過去**，不是「排定時刻過去了」——
    否則每天 11:31 都會對 chart 誤報一次，而那一輪要跑到 11:59。
    """
    spec = SCHEDULE[system]
    hh, mm = spec["at"]
    grace = dt.timedelta(minutes=spec["grace"])
    for back in range(0, 15):
        day = (now - dt.timedelta(days=back)).date()
        if spec["dow"] is not None and day.weekday() != spec["dow"]:
            continue
        fire = dt.datetime.combine(day, dt.time(hh, mm), tzinfo=TPE)
        if fire + grace <= now:
            return day
    return None


def latest_receipt(outbox: str, system: str):
    """那一套最新一份回執的日期（`datetime.date`），一份都沒有就回 None。

    **advisory 的回執在 outbox 根目錄**（`OUTBOX_DIR` 給 `""`），其餘六套各有子目錄。
    這一層對照從 `usage_report` import，不在這裡抄第二份。
    """
    sub = OUTBOX_DIR.get(system)
    if sub is None:
        return None
    d = os.path.join(outbox, sub) if sub else outbox
    dates = []
    for p in glob.glob(os.path.join(d, "*.receipt.json")):
        m = DATE_RE.search(os.path.basename(p))
        if m:
            try:
                dates.append(dt.date.fromisoformat(m.group(1)))
            except ValueError:
                pass
    return max(dates) if dates else None


def parked(outbox: str, system: str):
    """那一套有沒有被 park 的草稿。**「沒跑」與「跑了但被閘門擋下」處置不同。**"""
    sub = OUTBOX_DIR.get(system)
    if sub is None:
        return []
    d = os.path.join(outbox, sub) if sub else outbox
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(d, "*.parked")))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outbox", default=os.path.expanduser("~/outbox"))
    ap.add_argument("--report", default=os.path.expanduser("~/.kbusage/schedule-gaps.md"))
    ap.add_argument("--now", help="覆寫「現在」（ISO8601，測試用）")
    args = ap.parse_args()

    if not os.path.isdir(args.outbox):
        print(f"讀不到 outbox：{args.outbox}", file=sys.stderr)
        return 14

    now = dt.datetime.fromisoformat(args.now).astimezone(TPE) if args.now \
        else dt.datetime.now(TPE)

    lines, gaps = [], []
    for system in sorted(SCHEDULE):
        due = due_date(system, now)
        newest = latest_receipt(args.outbox, system)
        park = parked(args.outbox, system)
        if due is None:
            lines.append(f"⏳ {system:<16} 這一輪還沒到（或還在 grace 內）")
            continue
        newest_s = newest.isoformat() if newest else "（一份回執都沒有）"
        if newest and newest >= due:
            lines.append(f"✅ {system:<16} 應有 {due}，最新 {newest_s}")
        elif park:
            lines.append(f"⚠︎ {system:<16} 應有 {due}，最新 {newest_s}"
                         f"　**有被 park 的草稿**：{', '.join(park)}")
            gaps.append(system)
        else:
            lines.append(f"❌ {system:<16} 應有 {due}，最新 {newest_s}")
            gaps.append(system)

    head = [f"# 排程缺口　{now.strftime('%Y-%m-%d %H:%M')} 台北", ""]
    tail = ["",
            "**這一支只讀產出檔，不讀排程器的 `lastRunAt`** —— 2026-09-07 實測那個欄位會少報"
            "（chart 跑完、發布成功、回執 exit 0，而 `lastRunAt` 沒動）。",
            "**它不補，只報。** morning-brief 不走 outbox、沒有回執，這一支判不了它。",
            "❌ 之後要先去看那一套的 `~/outbox/<目錄>/publish.log` 與 `*.parked`。"]
    body = "\n".join(head + lines + tail) + "\n"

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(body)
    print(body, end="")
    if gaps:
        print(f"\n有缺口：{', '.join(gaps)}", file=sys.stderr)
        return 12
    return 0


if __name__ == "__main__":
    sys.exit(main())
