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
SYSTEMS = ("advisory", "chart", "podcast", "broker-research")


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

    base = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude"))
    if a.transcript:
        tp = os.path.expanduser(a.transcript)
    else:
        cands = glob.glob(os.path.join(base, "projects", "*", "*.jsonl"))
        if not cands:
            # **錯誤訊息要在犯錯的當下說出原因。** 文件是動手之前讀的，
            # 錯誤是動手之後讀的 —— 而「找不到檔案」跟「你在錯的機器上」
            # 在畫面上長得一模一樣。
            print(f"{base}/projects 底下找不到逐字稿。\n"
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
                  "  **這跟「這一輪沒花 token」是兩件事。**", file=sys.stderr)
            return 14
        tp = max(cands, key=os.path.getmtime)
        age = (dt.datetime.now().timestamp() - os.path.getmtime(tp)) / 60
        if age > STALE_MIN:
            print(f"最新的逐字稿是 {os.path.basename(tp)}，{age:.0f} 分鐘沒動過 —— "
                  f"**那不像是這一輪**。要就用 --transcript 明講。", file=sys.stderr)
            return 12

    until = a.until
    if a.until_receipt:
        # **界線用回執，不用猜。** publish 寫回執的時刻就是那一輪真正落地的時刻。
        rp = os.path.expanduser(f"~/outbox/{a.system}/{a.until_receipt}.receipt.json")
        if not os.path.exists(rp):
            print(f"找不到回執 {rp} —— 沒有界線就不要硬切，"
                  f"寧可印整場並在報告裡講明", file=sys.stderr)
            return 12
        try:
            at = json.load(open(rp, encoding="utf-8"))["at"]
        except Exception as e:
            print(f"回執讀不開：{e}", file=sys.stderr)
            return 12
        until = dt.datetime.fromisoformat(at).astimezone(
            dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        print(f"界線　　--until {until}（取自 {os.path.basename(rp)} 的 at={at}）")

    tot, turns, out, cr, cw, first, last = usage_of(tp, a.since, until)
    if not turns:
        print("這份逐字稿裡沒有帶用量的輪次 —— 挑錯檔了", file=sys.stderr)
        return 12

    sub_dir = os.path.join(os.path.dirname(tp),
                           os.path.basename(tp)[:-6], "subagents")
    subs = []
    for f in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl"))):
        st, sturns, *_ , sfirst, _ = usage_of(f, a.since, until)
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

    row = ",".join(str(x) for x in [
        (last or "")[:10], a.system, round(grand / 1000), turns, len(subs),
        sum(x[2] for x in subs), round(sub_tot / 1000), round(out / 1000),
        round(cr / 1000), round(cw / 1000), os.path.basename(tp)])
    hdr = ("date,system,eff_tokens_k,main_turns,subagents,agent_turns,"
           "subagent_tokens_k,out_tokens_k,cache_read_k,cache_write_k,transcript")
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
