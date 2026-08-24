#!/usr/bin/env python3
"""缺列哨兵：**前一天有跑的系統，usage.csv 上是不是都有那一列。**

## 它不量，它只問「有沒有」

量測的執行者是 `com.kenny.kbusage`（撿 sidecar、跑 `usage_report.py`）。
這一支不重做那件事，它問的是上一層的問題：**那一輪根本沒進到量測流程，
會發生什麼事？** 答案是「什麼都不會發生」—— sidecar 沒被寫出來的話，
`kbusage` 的迴圈是空的、不寫日誌、退出 0，而 CSV 少一列沒有任何徵兆。

`metrics/usage.csv` 到 2026-08-24 為止只有三列、而每天都在跑的 advisory
一列都沒有，就是這個形狀。**補一個執行者解掉了「沒人記得跑」，
但沒解掉「沒人記得接線」** —— 七套裡只有 advisory 的 run skill 寫 sidecar。

## 「那天有沒有跑」不用猜，回執說了算

`~/outbox/<目錄>/<日期>.receipt.json` 是 publish 寫的。它在，就代表那一套
那一天真的產出過東西。**這比用節奏推算可靠**：convergence 是週報、
houseview 是手動啟動，用「每天都該有一列」去判會天天誤報。

回執同時帶 `exit`。**publish 失敗的那一輪沒有列是合理的**，
所以那種情況印 ⚠︎ 不印 ❌ —— 哨兵誤報一次，下一次就沒人看了。

## 值域與目錄對照從 `usage_report` import，不抄

`SYSTEMS` 與 `OUTBOX_DIR`（`broker-research` 在 outbox 底下叫 `research`、
advisory 的回執在根目錄）只有一個家。這一條是這套系統反覆踩出來的：
**同一段話存在兩個地方，就是兩個會各自過期的地方。**

## 退出碼

0 = 沒有缺口（含「那天誰都沒跑」）；12 = 有缺口；14 = 環境問題（讀不到 CSV）。
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usage_report import SYSTEMS, OUTBOX_DIR       # noqa: E402

# 輪次的「日期」是**台北那一天**，不是 UTC 那一天，也不是這台機器的 $TZ。
# 寫死是刻意的：這七套都在台北時間跑，而吃 $TZ 會讓同一支腳本在 CI 上算出別的昨天。
TPE = dt.timezone(dt.timedelta(hours=8))


def receipt_path(outbox: str, system: str, date: str):
    """那一套那一天的回執路徑；這一套沒有回執（不在 `OUTBOX_DIR` 裡）就回 None。

    **`""` 與「不在表裡」是兩件事**：advisory 的回執在 outbox 根目錄，
    所以它的值是 `""`；鍵不存在才表示這一套沒有回執。呼叫端要用 `is None` 判。
    """
    sub = OUTBOX_DIR.get(system)
    if sub is None:
        return None
    return os.path.join(outbox, sub, f"{date}.receipt.json")


def has_row(csv: str, system: str, date: str) -> bool:
    """CSV 上有沒有那一天那一套。**前後各補一個換行再比**，
    否則 `chart` 會被 `broker-research,` 之類的字串前綴誤傷（同理日期）。

    抽成函式是因為 `usage_scan.py` 也要問同一個問題 ——
    **同一個判斷散在兩支工具裡，就是兩個會各自漂的判斷。**
    """
    try:
        body = open(csv, encoding="utf-8").read()
    except OSError:
        return False
    return f"\n{date},{system}," in "\n" + body


def state(outbox: str, system: str, date: str, row_exists: bool):
    """回 `(記號, 說明)`。記號只有四種：✅ 有列、⏳ 排隊中、⚠︎ 不算缺口、❌ 缺口。"""
    receipt = receipt_path(outbox, system, date)
    if receipt is None:
        return "⚠︎", "這一套沒有回執，哨兵判不了"
    d = os.path.dirname(receipt)
    if not os.path.exists(receipt):
        return None, None                      # 那天沒跑，不是缺口
    try:
        doc = json.load(open(receipt, encoding="utf-8"))
        code = doc.get("exit")
    except Exception as e:
        doc, code = {}, f"讀不開（{type(e).__name__}）"

    # **不是每一份回執都代表「那天跑了一輪」。**
    # `tools/publish.py` 的回執帶 `draft`（它是為某一份草稿寫的）；
    # 而 `tools/houseview_weekly.py` 寫的是**整合檢查**回執，帶的是 `system`／`stamp`。
    # 2026-08-24 實測：houseview 因此被判成缺口，而它那天根本沒有產出過一期 ——
    # **哨兵誤報一次之後就沒有人看了**，所以這裡用資料本身分辨，不是把 houseview 寫死。
    if doc and "draft" not in doc:
        return "⚠︎", ("這一份不是發布回執（沒有 `draft` 欄，看起來是整合檢查回執）"
                      " —— 判不了那天有沒有跑一輪")
    if row_exists:
        return "✅", f"有列（回執 exit={code}）"
    if isinstance(code, int) and code != 0:
        # **失敗的那一輪沒有列是合理的。** 它沒交出草稿，也就沒有可切的上界。
        return "⚠︎", f"那一輪 publish 失敗（exit={code}），沒有列是合理的"

    sc = os.path.join(d, f"{date}.usage.json")
    if os.path.exists(sc):
        return "⏳", ("sidecar 還在（`%s`）—— kbusage 撿過但沒成功，"
                      "原因在 ~/.kbusage/kbusage.log" % sc)
    for suffix, why in ((".usage.json.bad", "sidecar 欄位不合格，已被搬成 .bad"),
                        (".usage.json.failed", "sidecar 逾期仍失敗，已被搬成 .failed")):
        if os.path.exists(os.path.join(d, date + suffix)):
            return "❌", why + "（這一列要人來補）"
    # 沒有 sidecar、也沒有壞掉的 sidecar —— **那一輪根本沒寫**。
    #
    # **原因有兩種，而它們在 outbox 上長得一模一樣**，所以這裡不要只講其中一種：
    # 2026-08-24 實測，advisory 的正本（`kb-core/skills/advisory/SKILL.md`，389 行）
    # 有這一步，而每天 07:30 真的在跑的那一份 —— 帳號 skill `advisory-daily`，
    # 138 行、`updatedAt` 停在 08-19 —— 整份 grep 不到「用量」兩個字。
    # **正本接上了不等於部署的那份接上了。**
    return "❌", ("那一輪沒寫 sidecar。**正本沒接上這一步**，"
                  "或**正本接上了但部署的那份副本沒跟上**（帳號 skill 與排程 prompt "
                  "都是 kb-core 的副本，要手動重新部署）")


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--date", default=None,
                    help="要查的那一天（YYYY-MM-DD）。預設是**台北的昨天**。")
    ap.add_argument("--csv", default="~/kb-core/metrics/usage.csv")
    ap.add_argument("--outbox", default="~/outbox")
    ap.add_argument("--report", default="~/.kbusage/gaps.md")
    ap.add_argument("--log", default="~/.kbusage/kbusage.log",
                    help="有缺口時附一行到這裡。**沒缺口不寫** —— 與 kbusage.sh "
                         "同一個紀律：每天一行「一切正常」會把日誌洗掉。")
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12

    date = a.date or (dt.datetime.now(TPE).date() - dt.timedelta(days=1)).isoformat()
    csv = os.path.expanduser(a.csv)
    outbox = os.path.expanduser(a.outbox)

    if not os.path.exists(csv):
        print(f"讀不到 {csv} —— 這是環境問題，不是「沒有缺口」", file=sys.stderr)
        return 14
    # **⏳ 是不是缺口，取決於查的是哪一天。** 剛寫出來的 sidecar 本來就還沒被撿；
    # 但**昨天**的 sidecar 還在，代表它已經被每 10 分鐘重試了一整天還是沒成功 ——
    # 那不是排隊，是卡住。`kbusage.sh` 要拖到 STALE_DAYS=2 才會搬成 `.failed`，
    # 中間那一天沒有任何人會發現，這一支補的就是那一天。
    today = dt.datetime.now(TPE).date().isoformat()
    past = date < today

    lines, gaps, ran = [], 0, 0
    for s in SYSTEMS:
        mark, why = state(outbox, s, date, has_row(csv, s, date))
        if mark is None:
            continue
        ran += 1
        if mark == "❌" or (mark == "⏳" and past):
            gaps += 1
            if mark == "⏳":
                why += "。**這是昨天的 sidecar，已經重試一整天了**"
        lines.append(f"- {mark} `{s}` {why}")

    head = f"# 用量缺列哨兵 · {date}（台北）"
    if not ran:
        lines = [f"- 這一天七套都沒有回執 —— **沒有東西跑過，不是缺口**"]
    out = "\n".join([head, ""] + lines + [
        "", f"查的是 `{csv}`，回執在 `{outbox}`。",
        "**哨兵只報，不補。** 估一個數字填進去，CSV 就再也分不出哪幾列可以信。",
    ])
    print(out)

    rp = os.path.expanduser(a.report)
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    open(rp, "w", encoding="utf-8").write(out + "\n")

    if gaps:
        stamp = dt.datetime.now(TPE).strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.expanduser(a.log), "a", encoding="utf-8") as f:
            f.write(f"{stamp} 缺列哨兵 {date}：{gaps} 個缺口，明細在 {rp}\n")
    return 12 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
