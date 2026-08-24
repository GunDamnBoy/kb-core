#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""這一場對話到現在花了多少，以及**現在切一場划不划算**。只讀不寫。

用法：
    python3 tools/session_cost.py [--transcript FILE] [--next 100]

## 為什麼需要這一支

2026-08-23 拿一場真實逐字稿量出來的形狀：

    輪次區段        每輪平均 context
      1– 56              103k
    281–336              367k
    505–560              555k

**context 是累積的** —— 每一個工具結果都留在窗口裡，之後每一輪都要重讀它。
所以同樣 56 輪，最後那段比第一段貴 5.5 倍，而重讀佔原始 token 的 97.8%。

成本函數是「context 隨輪次成長」的積分，不是「產出多少字」。
這件事的操作含義是：**同樣的工作拆成兩場，成本不是打對折，是省四成以上**，
因為你砍掉的是最貴的那一半。

而排程執行本來就不長（chart 179 輪、podcast 89 輪），
**長的是維護對話**（實測一場 567 輪、187M，等於五天的 chart）。
所以這條規則的對象是坐在這裡的人，不是排程代理 ——
而「覺得有點長了就切」不可操作，要有一個當場算得出來的數字。

## 它算什麼

拿最近 N 輪的實際單輪成本、與開場 N 輪的實際單輪成本，
對「再做 M 輪」做兩個估算：留在這裡，或現在新開一場。
**成長率用這一場自己的資料擬合**，不是套用別場的常數。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.usage_report import pick_transcript  # noqa: E402

WIN = 20          # 取樣窗口：開場與當下各取這麼多輪
ADVISE_TURNS = 200  # 超過這個輪次就值得認真考慮切；理由見 report()


def turns_of(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            u = (d.get("message") or {}).get("usage")
            if not u:
                continue
            out.append((u.get("cache_read_input_tokens", 0),
                        u.get("cache_creation_input_tokens", 0),
                        u.get("output_tokens", 0)))
    return out


def report(rows, nxt):
    n = len(rows)
    cr = [r[0] for r in rows]
    tot_cr, tot_cw, tot_out = (sum(r[i] for r in rows) for i in range(3))
    raw = tot_cr + tot_cw + tot_out
    print(f"# 這一場：{n} 輪")
    print(f"　原始 token {raw/1e6:.1f}M　（重讀 {tot_cr/1e6:.1f}M ＝ {tot_cr/max(1,raw):.1%}、"
          f"寫入 {tot_cw/1e3:.0f}k、產出 {tot_out/1e3:.0f}k）\n")

    if n < WIN * 3:
        print(f"　輪次還少（不到 {WIN*3}），成長趨勢看不出來，先繼續。")
        return 0

    open_avg = sum(cr[:WIN]) / WIN
    now_avg = sum(cr[-WIN:]) / WIN
    # 每多一輪，單輪成本增加多少（用整場的線性斜率，單位 token/輪）
    slope = (now_avg - open_avg) / max(1, n - WIN)

    print("## 每輪的 context 怎麼長")
    k = max(1, n // 8)
    for i in range(0, n, k):
        seg = cr[i:i + k]
        if len(seg) < max(3, k // 2):
            continue
        avg = sum(seg) / len(seg)
        bar = "█" * max(1, round(avg / max(now_avg, 1) * 34))
        print(f"　{i+1:>4}–{min(i+k, n):<5}{avg/1000:>7,.0f}k  {bar}")
    print(f"\n　開場 {WIN} 輪平均 {open_avg/1000:,.0f}k　→　最近 {WIN} 輪平均 "
          f"{now_avg/1000:,.0f}k　（**{now_avg/max(1,open_avg):.1f} 倍**）")
    print(f"　每多做一輪，之後每一輪就多 {slope:,.0f} token\n")

    # ── 再做 nxt 輪：留在這裡 vs 現在新開一場 ──────────────
    stay = sum(now_avg + slope * i for i in range(1, nxt + 1))
    fresh = sum(open_avg + slope * i for i in range(1, nxt + 1))
    print(f"## 再做 {nxt} 輪的話")
    print(f"　留在這一場　≈ {stay/1e6:>5.1f}M")
    print(f"　現在新開一場 ≈ {fresh/1e6:>5.1f}M　"
          f"（**省 {1-fresh/max(1,stay):.0%}**，{(stay-fresh)/1e6:.1f}M）")
    print("　新開一場的代價是把脈絡重講一次 —— 那大概幾輪、幾萬 token，"
          "**跟上面那個數字比一比就知道值不值**。\n")

    if n >= ADVISE_TURNS and fresh < stay * 0.75:
        print(f"**建議切。** 已經 {n} 輪，接下來每一輪都比開場貴 "
              f"{now_avg/max(1,open_avg):.1f} 倍，而切的成本是固定的、只付一次。")
    elif n >= ADVISE_TURNS:
        print(f"已經 {n} 輪，但成長還平緩（{now_avg/max(1,open_avg):.1f} 倍），"
              "切不切都可以。")
    else:
        print(f"還在 {n} 輪，先繼續。過 {ADVISE_TURNS} 輪再回來看一次。")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--next", type=int, default=100, help="打算再做幾輪（預設 100）")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv[1:])
    if a.help or unknown:
        print(__doc__)
        return 0 if a.help else 12
    tp, err, code = pick_transcript(a.transcript)
    if tp is None:
        print(err, file=sys.stderr)
        return code
    rows = turns_of(tp)
    if not rows:
        print(f"{os.path.basename(tp)} 裡沒有帶 usage 的輪次 —— "
              "**那跟「沒花 token」是兩件事**，多半是挑錯檔。", file=sys.stderr)
        return 12
    print(f"（逐字稿 {os.path.basename(tp)}）\n")
    return report(rows, a.next)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
