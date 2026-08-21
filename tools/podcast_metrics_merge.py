#!/usr/bin/env python3
"""把兩份各寫各的 metrics.csv 合併成一份。**一次性遷移腳本，做完可以刪。**

用法：
    podcast_metrics_merge.py                # 試跑，只印出會發生什麼，不動任何檔案
    podcast_metrics_merge.py --apply        # 真的寫入

## 為什麼會有兩份

2026-08-22 查證發現：

- `healthcheck.py` 的 `collect_metrics()` 寫的是 `~/.podfetch/metrics.csv`
- 而 `DIGEST-PROMPT.md` 第 8 步叫每日排程把四個人工欄位填進
  `kb-core/scripts/podcast/metrics.csv`

**兩個寫入者、兩個檔案、沒有仲裁者。** 2026-08-22 實測：兩份都是 22 天、內容大致相同，但**有 6 天在特定儲存格上已經漂移**（`output_json_kb` 差約 3%、`brief_kb`／`segments_done`／`podfetch_minutes` 只有 `~/.podfetch` 那份有）。這份檔案存在的唯一目的是當**可解析且可比較**的基線，而基線有兩份就沒有一份是權威的：衝突時沒有人仲裁，`healthcheck.py` 的回填與排序只作用在它自己那一份，另一份會慢慢落後。

## 合併規則：**兩類欄位的勝方相反**

2026-08-22 第一次試跑時發現兩份其實**同樣是 22 天、沒有任何一天只在單邊**——
它們不是被切成兩半的基線，是兩份幾乎相同的副本在特定儲存格上漂移。
所以規則的重點不是「誰有比較多天」，而是**每一欄該信哪一把尺**：

| 欄位 | 勝方 | 理由 |
|---|---|---|
| `eff_tokens_k`／`subagents`／`agent_turns`／`subagent_tokens_k` | **kb-core** | 這四欄只有一個生產者：每日排程照 `DIGEST-PROMPT.md` 第 8 步寫進 kb-core。`healthcheck.py` 產不出它們 |
| 其餘全部 | **`~/.podfetch`** | 那是 `healthcheck.py` 在 Mac 上寫的，而 Mac 是這套系統真正執行的地方。**同一欄跨日要用同一把尺**——單格的準確度不如整欄的可比性重要 |

那張表不是偏好問題，是踩到才立的：08-22 那一列的 `transcript_kb` 兩邊是 688 與 654，
**688 是主代理在沙箱用 `du -sk` 手量的**（算磁碟區塊、含檔案系統開銷），
654 是 `healthcheck.py` 算的實際位元組；`speaker_flags` 的 5 與 4 同理。
留下手量的那個，整欄就有兩把尺——而這份檔案存在的唯一目的是當**可比較**的基線。

其餘規則：
- 以日期為鍵取聯集；欄數不足的舊列補空欄到與表頭等長（沿用 `healthcheck.py` 2026-08-09 的做法）
- 某一邊為空時取另一邊，不論勝方是誰
- 依日期排序

## 最壞情況

**這支程式會覆寫基線，而基線沒有第二份。** 所以：
預設是試跑；`--apply` 之前一定先備份兩份原檔（本程式自己會備份，帶時間戳）；
合併後**逐日印出哪些欄位是從哪一邊來的**，讓人看得見有沒有東西被吃掉。
"""
import datetime as dt
import shutil
import sys
from pathlib import Path

KB = Path.home() / "kb-core" / "scripts" / "podcast" / "metrics.csv"
PF = Path.home() / ".podfetch" / "metrics.csv"

# 只有這四欄以 kb-core 為準；其餘一律以 ~/.podfetch（healthcheck 在 Mac 量的）為準。
MANUAL = {"eff_tokens_k", "subagents", "agent_turns", "subagent_tokens_k"}


def read(p: Path):
    if not p.exists():
        return [], {}
    lines = [ln.rstrip("\n") for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return [], {}
    header = lines[0].split(",")
    rows = {}
    for ln in lines[1:]:
        cells = ln.split(",")
        cells += [""] * (len(header) - len(cells))
        rows[cells[0]] = cells[:len(header)]
    return header, rows


def main(argv) -> int:
    apply = "--apply" in argv[1:]

    hk, rk = read(KB)
    hp, rp = read(PF)
    if not hk and not hp:
        print("兩份都讀不到 —— 沒有東西可以合併")
        return 2

    header = hk or hp
    if hk and hp and hk != hp:
        # 欄位集合不同時取 kb-core 的順序，再把只存在於另一邊的欄位接在後面。
        extra = [c for c in hp if c not in hk]
        if extra:
            print(f"⚠ 兩份表頭不同，`~/.podfetch` 多出這些欄位：{extra}")
            header = hk + extra
        else:
            print("⚠ 兩份表頭順序不同，以 kb-core 那份為準")

    def get(row, hdr, col):
        return row[hdr.index(col)] if col in hdr and hdr.index(col) < len(row) else ""

    merged, notes = {}, []
    for d in sorted(set(rk) | set(rp)):
        out, src = [], []
        for c in header:
            a = get(rk.get(d, []), hk, c) if d in rk else ""
            b = get(rp.get(d, []), hp, c) if d in rp else ""
            if a and b and a != b:
                # **勝方依欄位而定，見檔頭那張表。** 人工四欄只有 kb 有生產者；
                # 其餘一律以 healthcheck 在 Mac 上量的為準，因為同一欄要同一把尺。
                if c in MANUAL:
                    out.append(a); src.append(f"{c}=kb({a}) 勝 pf({b})〔人工欄〕")
                else:
                    out.append(b); src.append(f"{c}=pf({b}) 勝 kb({a})〔同一把尺〕")
            elif a:
                out.append(a)
            elif b:
                out.append(b); src.append(f"{c}←pf")
            else:
                out.append("")
        merged[d] = out
        where = "兩邊" if d in rk and d in rp else ("僅 kb-core" if d in rk else "僅 .podfetch")
        notes.append((d, where, src))

    print(f"kb-core：{len(rk)} 天　~/.podfetch：{len(rp)} 天　合併後：{len(merged)} 天")
    print(f"表頭 {len(header)} 欄\n")
    for d, where, src in notes:
        flag = "" if where == "兩邊" and not src else f"  ← {where}" + (
            "；" + "、".join(src) if src else "")
        print(f"  {d}{flag}")

    only_pf = [d for d, w, _ in notes if w == "僅 .podfetch"]
    if only_pf:
        print(f"\n**這 {len(only_pf)} 天只存在於 ~/.podfetch，合併後才會進 git：{only_pf}**")

    if not apply:
        print("\n（試跑，沒有動任何檔案。確認上面沒問題後加 --apply）")
        return 0

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for p in (KB, PF):
        if p.exists() and not p.is_symlink():
            shutil.copy2(p, p.with_suffix(f".csv.bak-{ts}"))
            print(f"已備份 {p} → {p.with_suffix(f'.csv.bak-{ts}').name}")

    body = ",".join(header) + "\n" + "\n".join(
        ",".join(merged[d]) for d in sorted(merged)) + "\n"
    KB.write_text(body, encoding="utf-8")
    print(f"已寫入 {KB}（{len(merged)} 天）")

    if PF.exists() or PF.is_symlink():
        PF.unlink()
    PF.symlink_to(KB)
    print(f"已把 {PF} 改成指向 {KB} 的 symlink")
    print("\n**接著在 Mac 上跑一次 healthcheck.py**：它會保留人工四欄、回填缺漏日期、"
          "重新排序，並且是就地寫入（`open(path,'w')`），不會把 symlink 換成實體檔。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
