#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一輪的主線拆開：context 是誰撐起來的、寫入快取集中在哪裡。**這支只讀不寫。**

用法：
    python3 tools/turn_breakdown.py --transcript FILE [--since ISO8601] [--until ISO8601]
                                    [--top 20]

## 為什麼要有這一支

`usage_report.py` 回答「這一輪花了多少」，`session_cost.py` 回答「現在切一場划不划算」。
**兩支都答不出「錢花在哪一份資料上」** —— 而那正是決定要優化哪一步的時候要問的。

2026-08-24 advisory 那一輪量出 46,079k，其中主線重讀 110,720k（原始）佔 24%、
寫入快取 4,908k（原始 ×2）佔 21%。要判斷「把上游那份 1.8MB 擋在 context 外」
值不值得做，得先知道那 110,720k 裡面到底是什麼。
**不然就是在優化我們假設的那一塊，不是量出來大的那一塊。**

## 它怎麼歸因

context 是累積的：一個工具結果進來之後，**後面每一輪都要重讀它一次**。
所以一份資料的真正成本不是它的大小，是「大小 × 它之後還有幾輪」。
早進來的大東西，比晚進來的同樣大的東西貴得多。

這支就照這個排序，並且印出**歸因涵蓋率** —— 把算出來的常駐成本換算後
跟實際重讀總量比。涵蓋率低就代表 context 的大頭不是工具結果
（多半是系統提示與工具清單，podcast 2026-08-21 那份分析量到 14.6%），
**那時候要修的就不是取材方式**。

## 它不做的事

**不判斷、不建議、不碰子代理。** 子代理各自是獨立對話，
它們的帳在 `usage_report.py` 已經分開列了。這支只看主線。

字元數是**量**出來的；token 是**估**的（照這套系統慣用的繁中 1.1 字元／token），
所有估算值一律標 `~`。
"""
import argparse
import datetime as dt
import json
import os
import sys

# **一個比值不夠。** 繁中約 1.1 字元／token，而 JSON 與英文約 3.5 —— 差三倍。
# 工具結果兩種都有，所以估算一律給區間，不給單一數字：
# 用單一比值算出來的涵蓋率會精確得像量出來的，而它不是。
CPT_LO, CPT_HI = 1.1, 3.5


def rows(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except ValueError:
                    pass


def norm(s):
    s = str(s).strip().replace("Z", "+00:00")
    if "T" not in s:
        raise ValueError(f"{s!r} 只有日期沒有時間 —— 界線必須帶時間")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def blocks(msg):
    c = (msg or {}).get("content")
    return c if isinstance(c, list) else []


def label_of(name, inp):
    """一句話認出這是哪一次呼叫。認不出就回工具名 —— **不要編**。"""
    if not isinstance(inp, dict):
        return ""
    for k in ("file_path", "path", "url", "notebook_path"):
        if inp.get(k):
            return str(inp[k])
    for k in ("command", "pattern", "query", "prompt", "description"):
        if inp.get(k):
            return " ".join(str(inp[k]).split())[:70]
    return ""


def human(n):
    return f"{n:,}"


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args(argv[1:])
    if a.help or not a.transcript:
        print(__doc__)
        return 0 if a.help else 12

    path = os.path.expanduser(a.transcript)
    since = norm(a.since) if a.since else None
    until = norm(a.until) if a.until else None

    turns = []          # 每個 assistant 輪次：(ts, cr, cw, inp, out)
    tools = {}          # tool_use_id -> (name, label)
    results = []        # (chars, turn_index_when_it_arrived, name, label)
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
        t = d.get("type")
        msg = d.get("message") or {}
        if t == "assistant":
            for b in blocks(msg):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools[b.get("id")] = (b.get("name", "?"),
                                          label_of(b.get("name"), b.get("input")))
            u = msg.get("usage") or {}
            if u:
                turns.append((ts,
                              u.get("cache_read_input_tokens", 0),
                              u.get("cache_creation_input_tokens", 0),
                              u.get("input_tokens", 0),
                              u.get("output_tokens", 0)))
        elif t == "user":
            for b in blocks(msg):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    n = len(c if isinstance(c, str)
                            else json.dumps(c, ensure_ascii=False))
                    nm, lb = tools.get(b.get("tool_use_id"), ("（對不到呼叫）", ""))
                    results.append((n, len(turns), nm, lb))

    if not turns:
        print("這個範圍內沒有帶 usage 的 assistant 輪次 —— 界線可能切錯了",
              file=sys.stderr)
        return 12

    N = len(turns)
    CR = sum(t[1] for t in turns)
    CW = sum(t[2] for t in turns)
    print(f"# 主線拆解　{os.path.basename(path)}")
    print(f"範圍 {first} → {last}")
    print(f"主線 {N} 輪　重讀 {human(CR)}　寫入 {human(CW)}"
          f"　產出 {human(sum(t[4] for t in turns))}\n")

    # ── 一、context 曲線 ────────────────────────────────────────
    print("## 一、context 曲線（每輪 cache_read + cache_creation）\n")
    print("　輪次區段        每輪平均 context      該段重讀      佔重讀")
    seg = max(1, N // 8)
    for s in range(0, N, seg):
        part = turns[s:s + seg]
        ctx = sum(t[1] + t[2] for t in part) / len(part)
        cr = sum(t[1] for t in part)
        print(f"　{s+1:>4}–{s+len(part):<4}      {ctx/1000:>10,.0f}k"
              f"      {cr/1000:>9,.0f}k      {cr/max(1,CR)*100:>5.1f}%")
    print("\n　**context 是累積的** —— 同樣輪數，後段比前段貴。\n")

    # ── 二、寫入快取 ────────────────────────────────────────────
    print("## 二、寫入快取集中在哪裡（寫入算 ×2，是四種裡最貴的一把尺）\n")
    gaps = []
    for i, t in enumerate(turns):
        g = None
        if i and t[0] and turns[i - 1][0]:
            try:
                g = (dt.datetime.fromisoformat(t[0].replace("Z", "+00:00"))
                     - dt.datetime.fromisoformat(turns[i - 1][0].replace("Z", "+00:00"))
                     ).total_seconds()
            except ValueError:
                g = None
        gaps.append(g)
    # **不要固定取前 15。** 寫入大多是均勻的小額時，前 15 名全是同一個數字，
    # 看起來像「集中」其實只是排序的假象。改成只列明顯高於中位數的那幾輪。
    ws = sorted(t[2] for t in turns)
    med = ws[len(ws) // 2] or 1
    top = [i for i in sorted(range(N), key=lambda i: turns[i][2], reverse=True)[:15]
           if turns[i][2] > med * 2]
    if not top:
        print(f"　沒有任何一輪的寫入超過中位數（{human(med)}）的兩倍 —— "
              "**寫入是均勻攤開的，不是集中在某幾輪**")
    else:
        print("　  輪次   時刻(UTC)         寫入        距上一輪    當輪 context")
    for i in sorted(top):
        ts = (turns[i][0] or "")[11:19]
        g = gaps[i]
        gs = "（第一輪）" if g is None else f"{g:>8.0f} 秒"
        print(f"　{i+1:>6}   {ts}      {turns[i][2]:>9,}   {gs}"
              f"   {(turns[i][1]+turns[i][2])/1000:>9,.0f}k")
    tw = sum(turns[i][2] for i in top)
    if top:
        print(f"\n　這 {len(top)} 輪合計 {human(tw)}，佔全部寫入的 {tw/max(1,CW)*100:.1f}%"
              f"（中位數 {human(med)}）")
    for lim in (60, 300):
        idx = [i for i in range(N) if gaps[i] is not None and gaps[i] > lim]
        w = sum(turns[i][2] for i in idx)
        print(f"　距上一輪超過 {lim:>3} 秒的：{len(idx):>3} 輪，"
              f"寫入 {human(w)}（佔 {w/max(1,CW)*100:.1f}%）")
    print("\n　**這裡只給相關，不給因果。** 間隔長而寫入大，可能是快取過期整包重寫，"
          "\n　也可能只是那一輪剛好塞進很多新內容 —— 要分辨得看第三節那些東西何時進來。\n")

    # ── 三、context 裡最大的常駐項目 ────────────────────────────
    print("## 三、誰撐起了 context（工具結果，按「大小 × 之後還有幾輪」排序）\n")
    scored = [(n * max(0, N - k), n, k, nm, lb) for n, k, nm, lb in results]
    scored.sort(reverse=True)
    print("　  常駐成本      大小(字元)   第幾輪進來   之後   工具")
    for cost, n, k, nm, lb in scored[:a.top]:
        print(f"　{cost/1e6:>10,.1f}M   {n:>10,}   {k:>8}   {N-k:>5}   {nm}")
        if lb:
            print(f"　             {lb}")
    tot_chars = sum(n for n, _, _, _ in results)
    tot_cost = sum(s[0] for s in scored)
    hi, lo = tot_cost / CPT_LO, tot_cost / CPT_HI      # 比值小 → token 多
    print(f"\n　工具結果 {len(results)} 筆，合計 {human(tot_chars)} 字元（量）")
    print(f"　常駐成本 {tot_cost/1e6:,.0f}M 字元（量）"
          f" ≈ ~{lo/1e6:,.1f}–{hi/1e6:,.1f}M token（估，比值 {CPT_HI}–{CPT_LO}）")
    print(f"　實際重讀 {CR/1e6:,.1f}M token（量）")
    print(f"　**歸因涵蓋率 ~{lo/max(1,CR)*100:.0f}–{hi/max(1,CR)*100:.0f}%**")
    # **殘留假設會壞掉。** 這個模型假設東西進了 context 就一直在，
    # 而 context 被壓縮（compaction）過就不是這樣——那時候常駐成本會高估。
    drops = [i for i in range(1, N)
             if turns[i][1] < turns[i - 1][1] * 0.7 and turns[i - 1][1] > 50000]
    if drops:
        print(f"\n　⚠︎ **偵測到 {len(drops)} 次 context 大幅回落**"
              f"（第 {'、'.join(str(i+1) for i in drops[:6])}"
              f"{' 等' if len(drops) > 6 else ''} 輪）——"
              "\n　　context 被壓縮過，「進來就一直在」的殘留假設在那之後不成立，"
              "\n　　**常駐成本是高估的**。排序仍然可用，絕對值不要拿去做預算。")
    if lo > CR:
        print("\n　⚠︎ **涵蓋率下界就超過 100%** —— 殘留假設不成立"
              "（多半是上面那個回落，或這一輪的內容偏英文／JSON 而比值取低了）。"
              "\n　　**此時只讀排序，不要讀絕對值。**")
    print("\n　涵蓋率高 → context 的大頭是工具結果，改取材方式有效。"
          "\n　涵蓋率低 → 大頭是系統提示與工具清單那類每輪固定成本，"
          "**那時候要修的不是取材方式**。")
    print("\n**這支不判斷、不建議。**")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
