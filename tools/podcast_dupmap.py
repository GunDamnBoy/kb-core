#!/usr/bin/env python3
"""把整段複製的 token 位置換算成撰寫 subagent 能定位的時間戳區間。

用法：podcast_dupmap.py <逐字稿根目錄> [日期 YYYY-MM-DD]

    podcast_dupmap.py ~/podcast-transcripts
    podcast_dupmap.py ~/podcast-transcripts 2026-08-22

## 為什麼需要這一支

`podcast_verify.py` 的 `podfetch.no_block_repetition` 會告訴你「這一集有整段複製」，
manifest 的 `warnings` 也會，但兩者給的都是 **token 位置**（「第 1533 → 第 3791 個字」）。
撰寫 subagent 手上只有一份帶時間戳的逐字稿，**拿 token 位置在裡面定位不了**。

`DIGEST-PROMPT.md` 第 3 步要求派工單「具名告訴那一集的 subagent」複製位置。
2026-08-22 那一輪為了做到這件事，主代理臨時寫了一支腳本做換算 —— 寫在 `/tmp`，
跑完就沒了，**隔天那條規則會退回成不可執行**。
一個每天都要用、卻每天都要重寫的換算，就該是一支工具。

## 它比那支臨時腳本多做的一件事：先分段

臨時腳本把整份逐字稿當成單一時間軸，於是把 macrovoices 的
「29:13 之後全是重貼」推論成「實質內容只到 28:44」，**並把這個結論寫進了派工單**。
實際上該檔在第一段轉錄之後還有數段各自從 00:00 重新計時的獨立轉錄，內容全新，
是 subagent 逐行核對後推翻了主代理。同一天 oddlots 也是同一形態
（三段轉錄在交界處重置，複本各帶矛盾的時間戳）。

**所以時間戳重置點要先找出來，區間一律標明屬於第幾段。**
跨段比較時間戳是沒有意義的。

## 它刻意不做的事

- **不判定「這一集能不能寫到下界」。** 它只輸出覆蓋率與區塊位置。
  篇幅結論由讀完素材的 subagent 自己下 —— 派工單預告下界例外會誘導它少寫。
- **不改任何檔案、不讀 `.md` 以外的東西。** 逐字稿在 repo 外面，這支程式不改變那件事。
- **不重寫偵測邏輯。** 區塊偵測用 `kbcore.transcript.significant_repeats`，
  與 podfetch、`podcast_verify.py` 是同一份實作。**雙軌漂移是這套系統最常見的缺陷。**
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore.transcript import (  # noqa: E402
    cycle_repeats, significant_repeats, tokens_with_lines,
)

TPE = dt.timezone(dt.timedelta(hours=8))


def _hms(sec):
    if sec is None:
        return "??:??"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def segments(stamps, drop):
    """找時間戳重置點，回傳每一段的起始行號。

    重置的判準是「後一個有時間戳的行，秒數比前一個低超過 `drop`」。
    門檻的家在 anchors 的 `quality.segment_reset_drop_seconds`，這裡不寫死。
    """
    starts, prev = [0], None
    for j, s in enumerate(stamps):
        if s is None:
            continue
        if prev is not None and prev - s > drop:
            starts.append(j)
        prev = s
    return starts


def _seg_of(starts, line):
    n = 0
    for i, st in enumerate(starts):
        if line >= st:
            n = i
    return n + 1


def analyse(path, k, min_tokens, coldopen, drop, cyc=None):
    text = path.read_text(encoding="utf-8")
    toks, owners, stamps = tokens_with_lines(text)
    reps = significant_repeats(text, k, min_tokens, coldopen)
    starts = segments(stamps, drop)

    def ts_at(i):
        """第 i 個 token 所在行往回找最近的時間戳。"""
        j = owners[i] if i < len(owners) else owners[-1]
        while j >= 0 and stamps[j] is None:
            j -= 1
        return stamps[j] if j >= 0 else None

    blocks, covered = [], set()
    for r in reps:
        n, a, b = r["tokens"], r["first"], r["second"]
        covered.update(range(b, min(b + n, len(toks))))
        blocks.append({
            "tokens": n,
            "first_seg": _seg_of(starts, owners[a]),
            "first_from": ts_at(a), "first_to": ts_at(min(a + n - 1, len(toks) - 1)),
            "dup_seg": _seg_of(starts, owners[b]),
            "dup_from": ts_at(b), "dup_to": ts_at(min(b + n - 1, len(toks) - 1)),
            "snippet": " ".join(toks[a:a + 14]),
        })
    cycles, cyc_cov = [], set()
    if cyc:
        for c in cycle_repeats(text, k, coldopen, cyc["min_copies"],
                               cyc["min_distinct"], cyc["min_group_covered"]):
            for a, b in c["spans"]:
                cyc_cov.update(range(a, min(b, len(toks))))
            # **逐份印，不要印頭尾的凸包。** 初版取 `spans[0][0]`–`spans[-1][1]`，
            # 副本分散在全集時那個區間會橫跨整集 —— 08-23 mib 實測印出 21 分鐘，
            # 而實際重複只有 63 token。**派工單叫 subagent 把印出來的區間當缺漏，
            # 所以印錯區間＝叫他丟掉乾淨內容。**
            ranges = []
            for a, b in c["spans"]:
                hi = min(b - 1, len(toks) - 1)
                t0, t1 = ts_at(a), ts_at(hi)
                # 時間戳在該區段回跳時，起點會晚於終點（iltb 實測 1:18:59–1:18:55）。
                # 照原樣印會給出一個「結束早於開始」的區間，所以排序並標記。
                flip = (t0 is not None and t1 is not None and t1 < t0)
                if flip:
                    t0, t1 = t1, t0
                ranges.append({"seg": _seg_of(starts, owners[a]),
                               "from": t0, "to": t1, "flip": flip,
                               "tokens": b - a})
            cycles.append({
                "copies": c["copies"], "covered": c["covered"],
                "unit_tokens": max(r["tokens"] for r in ranges),
                "ranges": ranges,
                "snippet": " ".join(toks[c["first"]:c["first"] + 14]),
            })
    return {
        "total_tokens": len(toks),
        "covered": len(covered),
        "coverage": (len(covered) / len(toks)) if toks else 0.0,
        "segments": len(starts),
        "seg_starts": [(_seg_of(starts, s), s) for s in starts],
        "blocks": sorted(blocks, key=lambda x: (x["dup_seg"], x["dup_from"] or 0)),
        "cycles": sorted(cycles, key=lambda x: -x["covered"]),
        "cycle_coverage": (len(cyc_cov) / len(toks)) if toks else 0.0,
    }


def main(argv) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2

    root = Path(argv[1]).expanduser()
    date = argv[2] if len(argv) == 3 else dt.datetime.now(TPE).strftime("%Y-%m-%d")
    day = root / date
    mf = day / "manifest.json"
    if not mf.exists():
        print(f"讀不到 {mf} —— 這與「今天沒有節目」不是同一件事，先確認 podfetch 跑了沒有")
        return 2

    anchors = json.loads((ROOT / "podcast" / "anchors.json").read_text(encoding="utf-8"))
    q = anchors["quality"]
    k = q["block_repeat_shingle"]
    min_tokens = q["block_repeat_min_tokens"]
    coldopen = q["block_repeat_coldopen_head"]
    drop = q["segment_reset_drop_seconds"]
    tiers = q["block_repeat_coverage_tiers"]
    cyc = {"min_copies": q["cycle_min_copies"],
           "min_distinct": q["cycle_min_distinct_tokens"],
           "min_coverage": q["cycle_min_coverage"],
           "min_covered_tokens": q["cycle_min_covered_tokens"],
           "min_group_covered": q["cycle_min_group_covered"]}

    eps = json.loads(mf.read_text(encoding="utf-8"))["episodes"]
    print(f"{date}｜{len(eps)} 集｜整段複製定位"
          f"（{k}-gram、下限 {min_tokens} token、cold-open 豁免前 {coldopen}）")
    print("=" * 74)

    dirty = 0
    for e in eps:
        path = day / e["file"]
        if not path.exists():
            print(f"\n{e['file']}　⚠︎ 檔案不存在（manifest 寫了但沒落地）")
            dirty += 1
            continue
        r = analyse(path, k, min_tokens, coldopen, drop, cyc)
        head = f"\n{e['showKey']}｜{e['title'][:46]}"
        # **兩個觸發條件是 OR，不是 AND，而那是量出來的。** 比例對長集數不利：
        # 09-17 的 iltb 有一組 134 token 的內容塊循環三輪、369 token 被蓋掉，
        # 但全集 12,753 token，算出來只有 2.89% —— **卡在 3% 門檻下 0.11 個百分點**，
        # 而那一集是當天人工逐行核對過的真陽性。同樣 369 token 落在一集 3,000 token
        # 的短節目上就是 12%。所以補一條絕對量下限。
        cyc_tokens = round(r["cycle_coverage"] * r["total_tokens"])
        has_cyc = bool(r["cycles"]) and (
            r["cycle_coverage"] >= cyc["min_coverage"]
            or cyc_tokens >= cyc["min_covered_tokens"])
        if not r["blocks"] and not has_cyc:
            print(f"{head}\n  乾淨（{r['total_tokens']:,} token，{r['segments']} 段）"
                  f"——整段複製與循環重複兩種都沒觸發")
            continue
        dirty += 1
        print(head)
        print(f"  {r['segments']} 段轉錄"
              + ("（時間戳有重置，**區間不可跨段比較**）" if r["segments"] > 1 else ""))
        if has_cyc:
            print(f"  ◆ 循環重複　覆蓋 {r['cycle_coverage']:.0%}"
                  f"（{len(r['cycles'])} 組）——**這一種 `podcast_verify.py` 看不到**")
            for i, c in enumerate(r["cycles"], 1):
                print(f"    ~{i:<2} 單元 {c['unit_tokens']:>4} tok × {c['copies']} 份"
                      f"　共蓋掉 {c['covered']:,} token")
                for rg in c["ranges"][:4]:
                    flag = "　⚠時間戳在此回跳" if rg["flip"] else ""
                    print(f"        [段{rg['seg']} {_hms(rg['from'])}–{_hms(rg['to'])}]"
                          f" {rg['tokens']:>4} tok{flag}")
                if len(c["ranges"]) > 4:
                    print(f"        …另有 {len(c['ranges']) - 4} 份，"
                          f"區間從略（份數已列在上面）")
                print(f"        «{c['snippet']}…»")
            print("    → 這幾個區間照缺漏處理，不要據它生成內容；"
                  "回報要寫出時間戳區間、週期與次數")
        if not r["blocks"]:
            print("  整段複製：無")
            continue
        cov = r["coverage"]
        # **這三個字串會被原樣貼進派工單，所以它們只描述事實、不下篇幅結論。**
        # 「覆蓋率高的集數可以額外授權 subagent 自行判定下界例外」是給主代理的話，
        # 印在最後的總結那一行 —— 印在這裡會連同集數一起被貼過去，
        # 那就正好違反 anchors 那條「不要在派工單裡預告它會觸發」。
        level = ("高（>%d%%）" % (tiers["brief"] * 100)) if cov > tiers["brief"] \
            else ("中（%d–%d%%）" % (tiers["note"] * 100, tiers["brief"] * 100)) if cov > tiers["note"] \
            else "低（<%d%%）" % (tiers["note"] * 100)
        print(f"  ◆ 整段複製　覆蓋 {r['covered']:,}／{r['total_tokens']:,} token"
              f"（{cov:.0%}）　嚴重度：{level}")
        print(f"  {len(r['blocks'])} 個區塊：")
        for i, b in enumerate(r["blocks"], 1):
            print(f"    #{i:<2} {b['tokens']:>4} tok　"
                  f"原始 [段{b['first_seg']} {_hms(b['first_from'])}–{_hms(b['first_to'])}]"
                  f"　→　重複於 [段{b['dup_seg']} {_hms(b['dup_from'])}–{_hms(b['dup_to'])}]")
            print(f"        «{b['snippet']}…»")
        segs = {b["dup_seg"] for b in r["blocks"]}
        clean = [n for n, _ in r["seg_starts"] if n not in segs]
        if clean:
            print(f"  ✓ 第 {'、'.join(map(str, clean))} 段沒有複製 ——"
                  f" **不要因為某一段髒就判定整集內容不足**")

    print("\n" + "=" * 74)
    print(f"{dirty}／{len(eps)} 集有整段複製或循環重複。"
          f"　把上面每一集自己那一段原樣貼進它的派工單。")
    print("嚴重度「高」的集數，派工單可以額外寫一句「下界例外由你讀完素材自己判」——"
          "**但不要替它預判會不會觸發**。這一行是給你看的，不要貼進派工單。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
