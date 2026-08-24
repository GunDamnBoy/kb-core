#!/usr/bin/env python3
"""一個子代理的 context 裡裝了什麼，以及**每一樣東西被重讀了幾次**。

## 為什麼要有這一支

`subagent_report.py` 量到 advisory 的採集員每一輪重讀約 100k、而且
**68 輪到 188 輪之間每輪成本是平的**——所以那不是「context 一路長大」，
是「一份大約固定的 context 被重讀一百多次」。

已知的那一塊是 `preamble.md`（34k 字元）。**剩下的看不到。**
而看不到就只能猜，猜錯的下場已經有前例：`prep_chart.py` 砍掉 11 萬字元的上游
JSON，帳上一點都沒動。

## 它排序的不是大小，是「重讀成本」

**大小 × 之後還有幾輪。** 這是這支工具唯一的主張：

一份 34k 的檔案在第 3 輪讀進來、後面還有 185 輪，它被重讀 185 次；
同樣 34k 在第 180 輪才進來，只被重讀 8 次。**兩者大小一樣，成本差 23 倍，
而任何按大小排序的清單會把它們排在一起。**

所以早進來的大東西是首要目標，而「晚一點再讀」本身就是一種優化 ——
`prep_chart` 的分層取材其實就是這一招，只是當時沒有這個排序來確認該砍哪一份。

## 它的自我檢查

最後會把「模型算出來的重讀總量」與「逐字稿實際量到的 cache_read」並排。
**同一個數量級才代表這個模型抓對了形狀**；差一個數量級就是這支工具在說故事，
那時候不要拿它做決定。字元換 token 的除數是粗估（中英混排取 3），
所以要看的是數量級與排序，不是小數點。
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
from usage_report import rows, usage_of, _norm_iso, OUTBOX_DIR       # noqa: E402
from usage_gaps import TPE                                           # noqa: E402
from usage_scan import (repo_by_outbox, commit_on_date, window_to,   # noqa: E402
                        index_transcripts, pick)

# 2026-08-24 移除了字元換 token 的係數：**不估了，改用量到的 cache_read 增量**。


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    out = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_result":
            c = b.get("content")
            out.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
        elif b.get("type") == "text":
            out.append(b.get("text", ""))
    return "".join(out)


LABEL_LEN = 40      # 由 --label-len 覆寫


def label_of(name: str, inp: dict) -> str:
    """工具呼叫的標籤。**指令要看得到全文才知道那一筆是什麼東西** ——
    2026-08-24 chart 的第一名是一筆 78.5k 的 `mcp__workspace__bash`，
    而截在 40 字元只看得到 `ls -la /sessions/…/mn`，看不出它列的是哪個目錄。
    """
    if not isinstance(inp, dict):
        return name
    for k in ("file_path", "path", "url", "notebook_path"):
        if inp.get(k):
            v = str(inp[k])
            return f"{name} {os.path.basename(v) if '/' in v else v}"
    if inp.get("command"):
        return f"{name} {' '.join(str(inp['command']).split())[:LABEL_LEN]}"
    if inp.get("pattern"):
        return f"{name} {inp['pattern']}"
    return name


def profile(path: str, until, warmup: int = 5):
    """回 `(項目, 總輪數, 量到的重讀總量)`。項目 = (重讀成本, token, 第幾輪, 標籤)。

    **不估 token，用量到的。** 每一則 assistant 訊息都帶 `cache_read_input_tokens`
    —— 那是那一輪實際重讀了多少 token。所以：

        第 i 輪的增量  d_i = c_i − c_(i−1)
        那一批東西的重讀成本 = d_i × (總輪數 − i + 1)

    而 `Σ c_i`（量到的重讀總量）恆等於 `Σ d_i × (總輪數 − i + 1)`，
    **所以歸因加總與量測值完全相等，不是「同一個數量級」**。
    2026-08-24 第一版是用字元數×係數去估的，比值 0.30 —— 漏了模型自己的輸出、
    系統提示與工具定義，而那三項都是真的成本。**估的東西不用調係數，要換掉。**

    第 1 輪的 `c_1` 是**基線**：系統提示＋工具定義＋派工單。它沒有對應的工具結果，
    所以單獨列出來 —— 它也是唯一一項「每一輪都在付、而且從第一輪就開始付」的東西。

    增量為負代表 context 被壓縮過或快取沒中；那一輪不歸因，並在最後報幾次。
    """
    seq = [d for d in rows(path)
           if not (until and (d.get("timestamp") or "") >= until)]

    turns = []          # [(輪號, cache_read)]
    pending, since_last, items, drops = {}, [], [], 0
    for d in seq:
        msg = d.get("message") or {}
        if d.get("type") == "assistant":
            for b in (msg.get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    pending[b.get("id")] = label_of(b.get("name", "?"), b.get("input"))
            u = msg.get("usage")
            if u:
                turns.append((len(turns) + 1, u.get("cache_read_input_tokens", 0)))
                items.append((len(turns), list(since_last)))
                since_last = []
        elif d.get("type") == "user":
            content = msg.get("content")
            size = len(text_of(content))
            if not size:
                continue
            lbl = "（派工單）"
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        lbl = pending.get(b.get("tool_use_id"), "（工具結果）")
                        break
            since_last.append((lbl, size))

    total = len(turns)
    if not total:
        return [], 0, 0
    measured = sum(c for _, c in turns)

    # **每一輪的重讀 = 那一輪還活在 context 裡的每一項的當下大小之和。**
    # 所以逐輪把「還活著的項目」加總，加總值恆等於量到的 `Σ c_i` ——
    # 這不是估計，是把同一個數字換一個維度切開。
    #
    # `cache_read` 掉下來時（context 被壓縮、或快取沒中）代表有東西離開了。
    # **第一版在這裡直接跳過那幾輪，於是歸因總和比量測值高了穩定的 18%** ——
    # 跳過減少只會讓帳變大，而且大得很一致，看起來就像「模型差一點點」。
    # 現在改成按比例縮小所有還活著的項目：**哪一項離開是猜的，但總量是準的**，
    # 而我們要的排序靠的是總量。
    live, cost, order, prev, drops = {}, {}, [], 0, 0
    for (i, c), (_, batch) in zip(turns, items):
        d = c - prev
        if i <= warmup:
            # **開場那幾輪不逐筆歸因。** 這一段的增量是快取暖機 ——
            # 系統提示、工具定義、派工單本來就在 context 裡，只是還沒被算成重讀。
            # 掛到「那一輪剛好跑的工具」上會產生看起來精確、實際上錯的標籤。
            k = (1, f"（開場第 1–{warmup} 輪：系統提示＋工具定義＋派工單＋環境探測"
                    f" —— 這一段分不出誰是誰）")
            live[k] = live.get(k, 0) + max(0, d if i > 1 else c)
            if k not in order:
                order.append(k)
        elif d > 0:
            chars = sum(x[1] for x in batch)
            if chars:
                for n, (lbl, sz) in enumerate(batch):
                    k = (i, lbl, n)
                    live[k] = live.get(k, 0) + d * sz / chars
                    if k not in order:
                        order.append(k)
            else:
                k = (i, "（模型自己的輸出）")
                live[k] = live.get(k, 0) + d
                if k not in order:
                    order.append(k)
        elif d < 0 and prev > 0:
            drops += 1
            f = c / prev
            for k in live:
                live[k] *= f
        prev = c
        for k, v in live.items():
            cost[k] = cost.get(k, 0) + v

    out = [(cost[k], live.get(k, 0), k[0], k[1]) for k in order]
    # **掉下來的輪數當註腳印，不要當成一個項目** —— 它會混進分類彙總，
    # 而分類鍵取的是標籤第一個詞，於是表格裡會冒出一行「（有」。
    profile.drops = drops
    return sorted(out, key=lambda x: -x[0]), total, measured


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("system")
    ap.add_argument("--date", default=None)
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--top", type=int, default=1, help="剖析最貴的前幾個子代理")
    ap.add_argument("--main", action="store_true",
                    help="改成剖析**主線**而不是子代理。**零子代理的系統只能用這個** —— "
                         "chart 沒有任何子代理，它的成本 59% 是主線的重讀"
                         "（08-24：eff 4,874k、cache_read 28,666k），而那在子代理清單裡"
                         "一列都不會出現。")
    ap.add_argument("--rows", type=int, default=12, help="每個子代理列出前幾項")
    ap.add_argument("--warmup", type=int, default=5, metavar="N",
                    help="把前 N 輪併成一個「開場」項目，**不逐筆歸因**。"
                         "開場那幾輪的 cache_read 成長是快取暖機（系統提示與工具定義"
                         "本來就在 context 裡，只是還沒被算成重讀），"
                         "逐筆歸因會把它掛到那一輪剛好跑的工具上 —— "
                         "2026-08-24 實測：convergence 一個 `date; ls` 被算成 5.6M。"
                         "設 0 關掉這個合併（想看原始歸因時用）。")
    ap.add_argument("--label-len", type=int, default=40,
                    help="指令標籤截斷長度。查大回傳值是什麼時開大一點（例如 160）。")
    ap.add_argument("--outbox", default="~/outbox")
    ap.add_argument("--sessions",
                    default="~/Library/Application Support/Claude/local-agent-mode-sessions")
    ap.add_argument("--launchd", default=os.path.join(os.path.dirname(HERE), "launchd"))
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12

    global LABEL_LEN
    LABEL_LEN = a.label_len
    date = a.date or (dt.datetime.now(TPE).date() - dt.timedelta(days=1)).isoformat()
    sub = OUTBOX_DIR.get(a.system) or ""
    if a.transcript:
        tp = os.path.expanduser(a.transcript)
    else:
        marker = os.path.join("outbox", sub, f"{date}.draft.json")
        hits = index_transcripts(os.path.expanduser(a.sessions), {date: {marker}})
        tp, why = pick(hits, date, marker)
        if tp is None:
            print(f"找不到唯一的逐字稿 —— {why}", file=sys.stderr)
            return 12

    until = None
    repo = repo_by_outbox(a.launchd).get(
        os.path.normpath(os.path.join(os.path.expanduser(a.outbox), sub)))
    if repo:
        rel = f"data/{date}.json"
        at, h = commit_on_date(repo, rel, date)
        if at:
            until = _norm_iso(window_to(repo, rel, h) or at)

    if a.main:
        tot, turns, _o, cr, *_ = usage_of(tp, None, until)
        agents = [(tot, cr, tp)] if turns else []
    else:
        sub_dir = os.path.join(os.path.dirname(tp),
                               os.path.basename(tp)[:-6], "subagents")
        agents = []
        for f in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl"))):
            tot, turns, _o, cr, *_ = usage_of(f, None, until)
            if turns:
                agents.append((tot, cr, f))
        agents.sort(key=lambda x: -x[0])
    if not agents:
        print("沒有帶用量的輪次 —— 界線把它切光了，或挑錯檔了", file=sys.stderr)
        return 12

    print(f"{a.system} {date}　上界 {until or '（沒切）'}")
    for tot, cr, f in agents[:a.top]:
        items, total, measured = profile(f, until, a.warmup)
        model = sum(x[0] for x in items)
        who = "主線" if a.main else f"子代理 {os.path.basename(f)[6:23]}"
        print(f"\n{who}　{total} 輪　有效 {tot/1000:,.0f}k")
        print(f"{'重讀成本':>10}{'進來時':>9}{'第幾輪':>7}  來源")
        print("─" * 66)
        for cost, size, turn, lbl in items[:a.rows]:
            print(f"{cost/1e6:>9.1f}M{size/1000:>8.1f}k{turn:>7}  {lbl}")
        rest = items[a.rows:]
        if rest:
            print(f"{sum(x[0] for x in rest)/1e6:>9.1f}M"
                  f"{sum(x[1] for x in rest)/1000:>8.1f}k{'':>7}  其餘 {len(rest)} 項")
        # **逐項排序回答「哪一份最貴」，分類彙總回答「錢在哪一類」。**
        # 30 篇各 3k 的頁面在逐項清單裡每一筆都很小、看起來無關緊要，
        # 加起來卻可能跟 preamble 同一個量級 —— 只看逐項會漏掉這種形狀。
        cat = {}
        for cost, size, _t, lbl in items:
            # 括號開頭的是我們自己的分類標籤（開場、模型自己的輸出），整串當一類；
            # 其餘取第一個詞＝工具名。**取第一個詞會把「（開場第 1–5 輪…）」切成「（開場第」。**
            k = lbl if lbl.startswith("（") else (lbl.split()[0] if lbl.split() else lbl)
            c = cat.setdefault(k, [0, 0, 0])
            c[0] += cost; c[1] += size; c[2] += 1
        print(f"\n{'重讀成本':>10}{'進來時':>9}{'筆數':>7}  分類")
        print("─" * 66)
        for k, (cost, size, n) in sorted(cat.items(), key=lambda x: -x[1][0]):
            print(f"{cost/1e6:>9.1f}M{size/1000:>8.1f}k{n:>7}  {k}")
        if getattr(profile, "drops", 0):
            print(f"\n  註：有 {profile.drops} 輪的 cache_read 掉下來過"
                  f"（context 被壓縮或快取沒中），已把當時還活著的項目按比例縮小 ——"
                  f"**哪一項離開是猜的，總量是準的**。")
        print(f"\n  歸因加總　　　　{model/1e6:,.1f}M token")
        print(f"  量到的 cache_read {measured/1e6:,.1f}M token")
        ratio = model / measured if measured else 0
        verdict = ("**歸因與量測相等** —— 這兩個數字本來就恆等，"
                   "對不上就是有輪次被壓縮過（見下）"
                   if 0.98 <= ratio <= 1.02 else
                   "**對不上 —— 有輪次的 cache_read 掉下來過（context 被壓縮或快取沒中）**")
        print(f"  比值 {ratio:.2f} —— {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
