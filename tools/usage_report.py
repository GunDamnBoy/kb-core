#!/usr/bin/env python3
"""量這一輪花了多少 token。**這支只讀不寫**（除了 `--append` 指定的那個檔）。

用法：usage_report.py <系統 id> [--transcript FILE] [--append CSV]
                        [--since ISO8601] [--until ISO8601] [--until-receipt DATE]

## 一個工作階段可能不只裝一件事

Cowork 的排程與事後的維護對話**會共用同一份逐字稿**——2026-08-23 實測，同一個
`.jsonl` 前段是 03:07 的日報、後段是 08:40 起的維護。整份掃完得到 30,744k，
而日報那一輪其實是 **6,611k**，**高估 4.6 倍**。
所以切界線不是選配：`--since` 切掉前面、`--until` 切掉後面，
`--until-receipt <DATE>` 直接拿 `~/outbox/<系統>/<DATE>.receipt.json` 的 `at` 當界線
——那是那一輪真正落地的時刻，比任何自述都可靠。

## 為什麼要有它

`podcast/metrics-columns.md` 對那四欄的來源寫得很誠實：**「人工，抄自當輪用量回顧」**。
那是**自述**——代理回報它認為自己用了多少，然後有人抄進 CSV。
這一套一路的紀律是「自述不能當證據」，而用量是最容易自述錯的東西之一：
代理看不到自己的 usage 欄位，只能估。

這支改成**讀逐字稿算**。同一件事，換成量測。

## 「有效 token」的權重只有一個家

重讀 ×0.1、寫入 ×2、產出 ×5、新輸入 ×1。四套系統共用這一組，
不然「這一輪比上一輪貴」會變成「兩邊用了不同的尺」。

## 它挑哪一份逐字稿

沒給 `--transcript` 就挑**最後修改時間最新**的那一份，並且**把挑到的檔案、
輪次與時間範圍印出來**——挑錯逐字稿與挑對的，輸出的數字都很合理，
差別只有印出來的那幾行看得出來。太舊的直接拒絕，不猜。
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import json
import os
import sys

W = {"inp": 1.0, "out": 5.0, "cw": 2.0, "cr": 0.1}
STALE_MIN = 90          # 最新逐字稿超過這麼久沒動，就不是「這一輪」
# **值域擋在這裡。** 打錯一個字（`podcasts`、`research`）不會有任何徵兆，
# 而那一列會變成一套從此只有一列的「系統」，永遠不會被拿來比較。
# 2026-08-23 由四套擴到七套。**沒有登記的系統跑不了這支**，而那正是
# `metrics/usage.csv` 到那天只有三列的原因之一：bubble／convergence／houseview
# 的 run skill 根本沒有這一步，就算有也會被這個值域擋下來。
SYSTEMS = ("advisory", "chart", "podcast", "broker-research",
           "bubble", "convergence", "houseview")
# **系統 id 不等於 outbox 目錄名。** `--until-receipt` 要去 `~/outbox/<目錄>/` 找回執，
# 而 broker-research 在 outbox 底下叫 `research`。
# 2026-08-23 實測：不做這層對照，`broker-research --until-receipt` 一律 exit 12，
# **而它正是四套裡最需要切界線的那一套**（08-22 那一輪 43,339k／617 輪）。
#
# **`""` 與「不在表裡」是兩件事，不要用真假值判。** 2026-08-24 之前這裡沒有
# advisory，於是它被歸進「沒有回執可用」而只能 `--since`——但 advisory 的回執
# 一直都在，只是在 **outbox 根目錄**（`~/outbox/<DATE>.receipt.json`），
# 不像其他六套有自己的子目錄。`""` 表示「有回執、在根目錄」，
# 鍵不存在才表示「這一套沒有回執」。呼叫端因此要用 `is None` 判，不能用 `if not sub`。
OUTBOX_DIR = {"advisory": "", "podcast": "podcast", "chart": "chart",
              "broker-research": "research", "bubble": "bubble",
              "convergence": "convergence", "houseview": "houseview"}


def pick_transcript(explicit=None):
    """挑一份逐字稿。回 `(path, err, code)`；path 是 None 就照 err／code 收工。

    **這段抽出來是為了讓 `session_cost.py` 用同一份。** 兩邊各自寫一次的話，
    下面那段錯誤訊息（它記著「Cowork 的逐字稿在 Mac 上、不在沙箱」這個訂正）
    只會有一邊是對的 —— 而那正是 2026-08-23 在 payload 上剛發生過的事。
    """
    base = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude"))
    if explicit:
        return os.path.expanduser(explicit), None, 0
    cands = glob.glob(os.path.join(base, "projects", "*", "*.jsonl"))
    if not cands:
        # **錯誤訊息要在犯錯的當下說出原因。** 文件是動手之前讀的，
        # 錯誤是動手之後讀的 —— 而「找不到檔案」跟「你在錯的機器上」
        # 在畫面上長得一模一樣。
        return None, (
            f"{base}/projects 底下找不到逐字稿。\n"
            "  **先確認 CLAUDE_CONFIG_DIR 指對地方。** 不同執行環境不一樣：\n"
            "  · Claude Code／雲端容器：預設的 `~/.claude` 通常就對\n"
            "  · **Cowork：逐字稿在 Mac 上**，要指到某一場的 `.claude`——\n"
            "      BASE=$(ls -dt \"$HOME/Library/Application Support/Claude/"
            "local-agent-mode-sessions\"/*/*/local_*/.claude | head -1)\n"
            "      CLAUDE_CONFIG_DIR=\"$BASE\" python3 …\n"
            "    **Cowork 的沙箱那一側看不到它，也掛不上**（掛載會被明文拒絕），\n"
            "    所以這支在 Cowork 要在 Mac 的終端機跑。\n"
            "  （2026-08-23 訂正：這裡原本寫「逐字稿只存在於雲端那一側、"
            "在 Mac 上跑一定失敗」——**那是錯的，剛好講反**。）\n"
            "  **這跟「這一輪沒花 token」是兩件事。**"), 14
    tp = max(cands, key=os.path.getmtime)
    age = (dt.datetime.now().timestamp() - os.path.getmtime(tp)) / 60
    if age > STALE_MIN:
        return None, (f"最新的逐字稿是 {os.path.basename(tp)}，{age:.0f} 分鐘沒動過 —— "
                      "**那不像是這一輪**。要就用 --transcript 明講。"), 12
    return tp, None, 0


def eff(u):
    return (u.get("input_tokens", 0) * W["inp"]
            + u.get("output_tokens", 0) * W["out"]
            + u.get("cache_creation_input_tokens", 0) * W["cw"]
            + u.get("cache_read_input_tokens", 0) * W["cr"])


def rows(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except ValueError:
                    pass


def _norm_iso(s):
    """把使用者或回執給的 ISO8601 正規化成與逐字稿同一種格式（UTC、`Z` 結尾）。

    **為什麼一定要正規化**：`usage_of()` 做的是字串比較，而字串序只有在同格式下
    才等於時間序。台北位移的 `2026-08-23T11:41:10+08:00` 與逐字稿的
    `2026-08-23T03:41:10.000Z` 指同一刻，字串比起來卻是前者大——**界線會失效**。

    naive（沒有位移）一律當 UTC，**不吃本機時區**：2026-08-23 實測，
    吃 `$TZ` 會讓同一份回執在 Mac（Asia/Taipei）與 CI（UTC）算出差 8 小時的界線。
    `Z` 結尾在 Python 3.10 的 `fromisoformat` 會直接 ValueError，先換掉。
    """
    s = str(s).strip().replace("Z", "+00:00")
    # **純日期要明確擋掉。** `fromisoformat("2026-08-23")` 會成功並變成當天 00:00，
    # 於是界線看起來生效、實際上把整場切光——2026-08-23 實測就是這樣，
    # 而 docstring 已經寫了「純日期不接受」。**文件說不接受、程式接受，
    # 比兩邊都沒寫更糟**：讀文件的人以為有守衛。
    if "T" not in s:
        raise ValueError(f"{s!r} 只有日期沒有時間 —— 界線必須帶時間，"
                         "例如 2026-08-23T04:00:00Z")
    d = dt.datetime.fromisoformat(s)          # 其餘格式不對就讓它丟 ValueError
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def span(first, last):
    """把主線的第一筆與最後一筆換成 `(started_at, ended_at, minutes)`。

    **這一欄問的是「這一輪實際在動多久」，不是「界線給了多久」。**
    界線是輪次宣告的（sidecar 的 `since`／`until`），跨距是逐字稿量到的 ——
    兩者差多少本身就是資訊：輪次早收工，或界線切得太鬆。

    格式是 UTC 的 `Z`，與逐字稿同一種 —— **CSV 裡不混時區**。
    `date` 欄是台北那一天，這兩欄是 UTC 的時刻，看起來會對不上八小時，
    那是預期的：2026-08-24 的 advisory 從台北 07:35 起跑，UTC 是前一天 23:35。

    只用主線。子代理跑在主線等待的那段裡面，**它們的時間戳不會把跨距撐大**，
    而多讀十幾個檔只為了求一個幾乎相同的 min/max 不划算。

    拿不到時間戳就回三個空字串 —— **空的比 0 誠實**，`0.0` 分鐘看起來像量到了。
    """
    if not first or not last:
        return "", "", ""
    try:
        f = dt.datetime.fromisoformat(str(first).replace("Z", "+00:00"))
        l = dt.datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return "", "", ""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (f.astimezone(dt.timezone.utc).strftime(fmt),
            l.astimezone(dt.timezone.utc).strftime(fmt),
            round((l - f).total_seconds() / 60, 1))


def usage_of(path, since=None, until=None):
    """回傳 (有效 token, 輪次, 產出, 重讀, 寫入, 最早, 最晚)。

    `since`／`until` 都是 ISO8601 字串，直接做字串比較——**這是刻意的**：
    逐字稿裡的 `timestamp` 一律是 `...Z` 的 UTC ISO8601，同格式下字串序等於時間序，
    不必解析就不會有時區解析錯誤。**但也因此傳進來的界線必須是同一種格式**，
    所以 `--until-receipt` 會把回執的 `at` 正規化成 UTC 的 `Z` 形式再用。
    """
    tot = turns = out = cr = cw = 0
    first = last = None
    for d in rows(path):
        ts = d.get("timestamp") or ""
        if since and ts and ts < since:
            continue
        if until and ts and ts >= until:
            continue
        if ts:
            first = first or ts
            last = ts
        if d.get("type") != "assistant":
            continue
        u = (d.get("message") or {}).get("usage") or {}
        if not u:
            continue
        tot += eff(u)
        turns += 1
        out += u.get("output_tokens", 0)
        cr += u.get("cache_read_input_tokens", 0)
        cw += u.get("cache_creation_input_tokens", 0)
    return tot, turns, out, cr, cw, first, last


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("system", choices=SYSTEMS)
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--append", default=None)
    ap.add_argument("--since", default=None,
                    help="只算這個時間點之後的輪次（ISO8601）。同一個工作階段跑了"
                         "不只一件事時用它切開。")
    ap.add_argument("--until", default=None,
                    help="只算這個時間點之前的輪次（ISO8601）。與 --since 成對，"
                         "把一個工作階段裡的某一段切出來。")
    ap.add_argument("--until-receipt", metavar="DATE", default=None,
                    help="用 ~/outbox/<系統>/<DATE>.receipt.json 的 `at` 當 --until。"
                         "那是那一輪真正落地的時刻，比任何自述都可靠。")
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12

    tp, err, code = pick_transcript(a.transcript)
    if tp is None:
        print(err, file=sys.stderr)
        return code

    # **`--since` 與 `--until` 走同一段正規化，這是 2026-08-24 補的。**
    # 在那之前只有 `--until` 有，而 `--since` 原樣進了字串比較 ——
    # 於是 `--since 2026-08-24T07:35:00+08:00`（台北位移）拿去跟逐字稿的
    # `2026-08-24T01:44:00.000Z` 比，字串序上前者比較大，**整場被切光**。
    # 那一段註解就寫在下面幾行，說的是同一件事，只是當時只套用在一個旗標上 ——
    # **同一個坑修一半，比沒修更難發現**，因為文件會說「界線已經處理過了」。
    # 這一條在自動化之後更要緊：`kbusage.sh` 帶進來的 `since` 由輪次寫在 sidecar 裡，
    # 而輪次寫的是台北時刻。
    since = a.since
    if since:
        try:
            since = _norm_iso(since)
        except ValueError as e:
            print(f"--since 解析不了：{e}\n"
                  "  要 ISO8601，例如 2026-08-23T04:00:00Z 或 2026-08-23T12:00:00+08:00。"
                  "\n  **純日期（2026-08-23）不接受** —— 它沒有時間，切出來的界線是任意的。",
                  file=sys.stderr)
            return 12

    until = a.until
    if until:
        # **界線是字串比較，所以格式不對不會報錯、只會安靜不切。**
        # 2026-08-23 實測：傳台北位移（`...+08:00`）或純日期（`2026-08-23`）
        # 都會讓界線完全失效，而輸出印的是整場、exit 0 ——
        # **「切過了」與「沒切」在畫面上長得一樣**，正是這套系統反覆記的那種失效。
        # 所以在這裡正規化成與逐字稿同一種格式（UTC、`Z` 結尾），對不上就擋下。
        try:
            until = _norm_iso(until)
        except ValueError as e:
            print(f"--until 解析不了：{e}\n"
                  "  要 ISO8601，例如 2026-08-23T04:00:00Z 或 2026-08-23T12:00:00+08:00。"
                  "\n  **純日期（2026-08-23）不接受** —— 它沒有時間，切出來的界線是任意的。",
                  file=sys.stderr)
            return 12
    if a.until_receipt:
        if a.until:
            print("--until 與 --until-receipt 同時給了，**以回執為準**"
                  f"（忽略 --until {a.until}）", file=sys.stderr)
        # **界線用回執，不用猜。** publish 寫回執的時刻就是那一輪真正落地的時刻。
        sub = OUTBOX_DIR.get(a.system)
        if sub is None:
            print(f"{a.system} 沒有回執，用不了 --until-receipt；"
                  "改用 --until 明講界線", file=sys.stderr)
            return 12
        # `sub` 是 `""` 時回執在 outbox 根目錄（advisory 就是這一種）。
        rp = os.path.expanduser(
            os.path.join("~/outbox", sub, f"{a.until_receipt}.receipt.json"))
        if not os.path.exists(rp):
            print(f"找不到回執 {rp} —— 沒有界線就不要硬切，"
                  f"寧可印整場並在報告裡講明", file=sys.stderr)
            return 12
        try:
            at = json.load(open(rp, encoding="utf-8"))["at"]
            until = _norm_iso(at)
        except Exception as e:
            print(f"回執的 at 讀不開或解析不了：{e}", file=sys.stderr)
            return 12
        print(f"界線　　--until {until}（取自 {os.path.basename(rp)} 的 at={at}）")

    tot, turns, out, cr, cw, first, last = usage_of(tp, since, until)
    if not turns:
        bounds = "／".join(x for x in (f"--since {since}" if since else "",
                                       f"--until {until}" if until else "") if x)
        why = f"界線把它切光了（{bounds}）" if bounds else "挑錯檔了"
        print(f"這份逐字稿裡沒有帶用量的輪次 —— {why}", file=sys.stderr)
        return 12

    sub_dir = os.path.join(os.path.dirname(tp),
                           os.path.basename(tp)[:-6], "subagents")
    subs = []
    for f in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl"))):
        st, sturns, *_ , sfirst, _ = usage_of(f, since, until)
        if sturns:
            subs.append((os.path.basename(f)[6:23], st, sturns))

    sub_tot = sum(x[1] for x in subs)
    grand = tot + sub_tot

    print(f"逐字稿　{tp}")
    print(f"　　　　{first} → {last}")
    print(f"主線　　{turns} 輪　有效 {tot:,.0f}")
    print(f"子代理　{len(subs)} 個　{sum(x[2] for x in subs)} 輪　有效 {sub_tot:,.0f}")
    if subs:
        print("　　　　" + "、".join(
            f"{i}:{t/1000:.0f}k/{n}" for i, t, n in
            sorted(subs, key=lambda x: -x[1])[:10]))
    print(f"**合計有效 {grand:,.0f}**"
          f"（產出 {out:,} ×5、重讀 {cr:,} ×0.1、寫入 {cw:,} ×2）")

    # **CSV 要帶「這個數字能不能信」，不只帶數字。**
    # 沒切界線的一輪，數字本身完全合理（型別對、量級也像），只是它量的可能是
    # 一整場維護對話 —— 2026-08-22 的 broker-research 就是這樣進去的：
    # 43,339k／617 輪，而那份逐字稿同時裝著整場維護。
    # 有了這一欄，下一個拿 CSV 做決定的人不必去比對 transcript 才知道該不該用。
    bounded = "yes" if (since or a.until or a.until_receipt) else "no"
    if bounded == "no":
        print("\n⚠︎ **這一輪沒有切界線**（沒給 --since／--until／--until-receipt）——"
              "若這份逐字稿同時裝了維護對話，算出來的是兩者之和。"
              "CSV 的 `bounded` 欄會記成 no。")
    started_at, ended_at, minutes = span(first, last)
    row = ",".join(str(x) for x in [
        (last or "")[:10], a.system, started_at, ended_at, minutes,
        round(grand / 1000), turns, len(subs),
        sum(x[2] for x in subs), round(sub_tot / 1000), round(out / 1000),
        round(cr / 1000), round(cw / 1000), bounded, os.path.basename(tp)])
    hdr = ("date,system,started_at,ended_at,minutes,"
           "eff_tokens_k,main_turns,subagents,agent_turns,"
           "subagent_tokens_k,out_tokens_k,cache_read_k,cache_write_k,bounded,transcript")
    print("\n把下面這一行 append 到 kb-core/metrics/usage.csv：")
    print(row)

    if a.append:
        p = os.path.expanduser(a.append)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8") as f:
            if new:
                f.write(hdr + "\n")
            f.write(row + "\n")
        print(f"→ 已寫入 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
