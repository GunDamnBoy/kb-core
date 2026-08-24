#!/usr/bin/env python3
"""子代理帳：**那一輪的錢花在哪一個子代理身上，以及花成什麼形狀。**

## 為什麼需要這一支

`usage_report.py` 回答「這一輪多少錢」，`usage.csv` 回答「哪一套比較貴」。
2026-08-24 回填之後兩個問題都有答案了，而答案指向同一個地方：
**advisory 每輪 24k–32k、每天都跑、七成在子代理**（五天佔比 68–73%，幾乎不動）。

但「七成在子代理」還不是一個可以動手的東西。要動手得知道：
是**一個**子代理很貴，還是**十二個**都中等？貴在讀還是貴在寫？
派工單多大？——這一支回答那些。

## 它看的是形狀，不只是總數

每個子代理拆成兩個比值：

- `讀佔比` ＝ 重讀×0.1 ÷ 有效總額。**高的那些是「context 一直被重讀」**，
  對策是把輸入變小（分層取材、先摘要再細讀）。
- `寫佔比` ＝ 產出×5 ÷ 有效總額。**高的那些是「真的在生成很多字」**，
  對策是砍產出規格或合併子代理，把輸入變小沒有用。

**兩種貴法的修法相反，而總數看起來一模一樣。**

## 派工單也印出來

每個子代理的第一則 user 訊息就是它的派工單。派工單的長度本身是成本
（它進了那個子代理的每一輪 context），而**內容決定它要跑幾輪**。
截斷到一行只是為了對照，要細看就去讀那個 jsonl。
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from usage_report import W, eff, rows, usage_of, _norm_iso            # noqa: E402
from usage_gaps import TPE                                            # noqa: E402
from usage_scan import (repo_by_outbox, commit_on_date, window_to,    # noqa: E402
                        index_transcripts, pick)
from usage_report import OUTBOX_DIR                                   # noqa: E402


def assignment(path: str, limit: int = 90) -> str:
    """子代理的派工單 —— 它的第一則 user 訊息，壓成一行。"""
    for d in rows(path):
        if d.get("type") != "user":
            continue
        c = (d.get("message") or {}).get("content")
        if isinstance(c, list):
            c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
        if not isinstance(c, str) or not c.strip():
            continue
        s = " ".join(c.split())
        return s[:limit] + ("…" if len(s) > limit else "")
    return "（讀不到派工單）"


def breakdown(main_tp: str, since, until):
    """回 `[(名稱, 有效, 輪數, 產出, 重讀, 寫入, 派工單)]`，由貴到便宜。"""
    sub_dir = os.path.join(os.path.dirname(main_tp),
                           os.path.basename(main_tp)[:-6], "subagents")
    out = []
    for f in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl"))):
        tot, turns, o, cr, cw, *_ = usage_of(f, since, until)
        if turns:
            out.append((os.path.basename(f)[6:23], tot, turns, o, cr, cw,
                        assignment(f)))
    return sorted(out, key=lambda x: -x[1])


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("system")
    ap.add_argument("--date", default=None, help="預設是台北的昨天")
    ap.add_argument("--transcript", default=None,
                    help="直接指定主逐字稿；不給就照 usage_scan 那一套自己找")
    ap.add_argument("--outbox", default="~/outbox")
    ap.add_argument("--sessions",
                    default="~/Library/Application Support/Claude/local-agent-mode-sessions")
    ap.add_argument("--launchd", default=os.path.join(os.path.dirname(HERE), "launchd"))
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12

    date = a.date or (dt.datetime.now(TPE).date() - dt.timedelta(days=1)).isoformat()
    outbox = os.path.expanduser(a.outbox)
    sub = OUTBOX_DIR.get(a.system) or ""
    until = None

    if a.transcript:
        tp = os.path.expanduser(a.transcript)
    else:
        marker = os.path.join("outbox", sub, f"{date}.draft.json")
        hits = index_transcripts(os.path.expanduser(a.sessions), {date: {marker}})
        tp, why = pick(hits, date, marker)
        if tp is None:
            print(f"找不到唯一的逐字稿 —— {why}", file=sys.stderr)
            return 12

    repo = repo_by_outbox(a.launchd).get(os.path.normpath(os.path.join(outbox, sub)))
    if repo:
        rel = f"data/{date}.json"
        at, h = commit_on_date(repo, rel, date)
        if at:
            until = window_to(repo, rel, h) or at

    # **界線要正規化成與逐字稿同一種格式（UTC、`Z`）再用。**
    # `usage_of()` 做的是字串比較，而日檔的 `window.to` 是台北位移
    # （`2026-08-24T09:41:00+08:00`）—— 直接丟進去比，字串序上它幾乎大於
    # 當天所有 UTC 時戳，**界線等於整整鬆了八小時、而畫面上完全看不出來**。
    # 2026-08-24 首跑就踩到：主線被算成 33,068k，而同一輪切對界線是 8,373k。
    # `usage_report.py` 早就有這道正規化，這一支當初沒接上 —— 同一個坑的第二次。
    raw_until = until
    if until:
        until = _norm_iso(until)
    tot, turns, o, cr, cw, first, last = usage_of(tp, None, until)
    subs = breakdown(tp, None, until)          # until 已正規化
    sub_tot = sum(x[1] for x in subs)
    grand = tot + sub_tot

    print(f"{a.system} {date}")
    print(f"逐字稿　{os.path.basename(tp)}")
    print(f"上界　　{raw_until or '（沒切，數字含後面的維護對話）'}"
          + (f"　→　{until}" if raw_until and until != raw_until else ""))
    print(f"合計　　{grand/1000:,.0f}k　＝　主線 {tot/1000:,.0f}k"
          f"（{tot/grand*100:.0f}%）＋ 子代理 {sub_tot/1000:,.0f}k"
          f"（{sub_tot/grand*100:.0f}%）")
    print()
    print(f"{'子代理':18}{'有效':>9}{'佔子代理':>9}{'輪':>5}{'每輪':>8}"
          f"{'讀佔比':>8}{'寫佔比':>8}")
    print("─" * 68)
    for name, t, n, o2, cr2, cw2 in ((s[0], s[1], s[2], s[3], s[4], s[5]) for s in subs):
        rd = cr2 * W["cr"] / t * 100 if t else 0
        wr = o2 * W["out"] / t * 100 if t else 0
        print(f"{name:18}{t/1000:>8,.0f}k{t/sub_tot*100:>8.0f}%{n:>5}"
              f"{t/n/1000:>7,.0f}k{rd:>7.0f}%{wr:>7.0f}%")
    print()
    for name, t, n, *_rest in subs:
        print(f"  {name}  {_rest[-1]}")
    print()
    top = subs[:3]
    if top:
        share = sum(x[1] for x in top) / sub_tot * 100
        print(f"**最貴的 3 個吃掉子代理成本的 {share:.0f}%**"
              f"（共 {sum(x[2] for x in top)} 輪）。")
    print("讀佔比高＝context 一直被重讀，對策是把輸入變小；"
          "寫佔比高＝真的在生成很多字，把輸入變小沒有用。"
          "**兩種貴法的修法相反，而總數看起來一模一樣。**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
