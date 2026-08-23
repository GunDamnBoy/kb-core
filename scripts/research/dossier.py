#!/usr/bin/env python3
"""一份報告 → 一份給撰稿子代理讀的卷宗。**這支會寫檔。**

用法：dossier.py <slug> [--extracted DIR] [--out DIR]

## 為什麼要有它

2026-08-22 量出來的：一次工具往返約 1.5 萬到 2 萬有效 token，
而**真正寫出來的字只佔 0–1%**。最貴的那個子代理跑了 85 輪，其中

- **第 3 到 20 輪在讀同一個檔**，每次切不同片段；
- **第 21 到 30 輪在逆向工程規格** —— 找字數規則、找閘門怎麼比對、找 chartkit 支援哪些圖型。

兩段都是文件問題。前者是**每個分支都要的東西被藏在一個檔案路徑後面**，
於是它只能盲切；後者是**規格說了規則存在、沒說規則是什麼**
（有個子代理明講「發布閘門的實作我找不到」）。

卷宗把兩件事一起解掉：規格內嵌在最前面，內文附**頁次目錄**，
所以要跳哪一頁是看得出來的，不是猜的。

## 為什麼不整份塞進派工單

內文平均 6.3 萬 token，最大一份 20.8 萬 —— 整份塞會撐爆子代理的脈絡。
**卷宗是讓它不必盲切，不是讓它不必選。**
"""
from __future__ import annotations
import argparse, json, os, re, sys

_KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

A = json.load(open(os.path.join(_KB, "research", "anchors.json"), encoding="utf-8"))
ADV = json.load(open(os.path.join(_KB, "advisory", "anchors.json"), encoding="utf-8"))

# 揭露頁佔內文 10%，而它對撰稿沒有任何用處。**剃掉它是為了讓目錄短，不是為了省那 10%。**
DISC = re.compile(r"Disclosure Appendix|Reg AC|analyst certification|"
                  r"Distribution of ratings|Global Investment Research", re.I)

CH = json.load(open(os.path.join(_KB, "chart", "anchors.json"), encoding="utf-8"))["kinds"]

# **圖型的值域與選型判準都住在每日五圖的 anchors 裡**，這裡讀它、不抄它。
# 抄一份的代價 2026-08-22 付過了：`waterfall` 的數字被寫進 `groups`，
# 而 `_draw_waterfall` 讀的是 `vals` —— 圖畫成空白、不丟例外、檢查全綠。
KINDS = {k: v for k, v in CH.items() if isinstance(v, dict) and "data" in v}
PICK = {k: v for k, v in (CH.get("_pick") or {}).items() if not k.startswith("_")}


def tier_of(pages):
    for t in A["summary_tiers"]["tiers"]:
        if t["under_pages"] is None or pages < t["under_pages"]:
            return t
    return A["summary_tiers"]["tiers"][-1]


def head(line, n=68):
    """每一頁的第一句可讀的話，當目錄用。"""
    for raw in line.split("\n"):
        s = raw.strip()
        if len(s) > 24 and re.search(r"[a-z]{4}", s):
            return s[:n]
    return (line.strip().replace("\n", " ")[:n]) or "（無可讀文字）"


def build(d):
    pages, t = d["pages"], tier_of(d["pages"])
    lo, hi = t["chars"]
    themes = "\n".join(f"  - {g['name']}" for g in ADV["groups"])
    body = d.get("body") or []
    keep = [(i, pg) for i, pg in enumerate(body) if not DISC.search(pg[:1200])]

    L = [f"# 卷宗｜{d.get('broker','?')}　{d.get('title','?')}", "",
         f"- slug：`{d['slug']}`",
         f"- 日期：{d.get('date','?')}　頁數：**{pages}**　抽取器：{d.get('engine','?')}",
         f"- **精華目標 {t['target']:,} 字（區間 {lo:,}–{hi:,}）**", "",
         "---", "",
         "## 規格：你需要的規則全在這裡，不用去別的地方找", "",
         "**字數怎麼算**（`assemble.py` 的 `count()`，會覆寫你自報的數字）：",
         "剝掉標題記號與 `**` `__` `` ` `` `*` 與行首破折號，"
         "再去掉**所有**空白，數剩下的字元。中英文一視同仁。", "",
         "**原句與 grounding 怎麼比對**（發布閘門 `checks/research.py` 的 `_norm`）：",
         "比對前會把連續空白塌縮成單一空格、把彎引號與各式破折號折疊成直的。",
         "所以**跨行可以**，跨頁不行（中間夾著頁尾與頁碼）。用子字串包含，不是整行相等。", "",
         "**選型：先問資料長什麼形狀，不是先問哪張好看。**", "",
         "| 你的資料是 | 用 | 數字填在這些欄位 |", "|---|---|---|"]
    for desc, kind in PICK.items():
        flds = "、".join(f"`{x}`" for x in KINDS.get(kind, {}).get("data", []))
        L.append(f"| {desc} | `{kind}` | {flds} |")
    L += ["",
          "**填錯欄位不會報錯，會畫出一張空白圖。** "
          f"{CH.get('_pick', {}).get('_anti', '')}", "",
         "**`theme` 只能從這 15 組挑，一字不差**：", themes, "",
         "---", "",
         f"## 第一頁（分析師自己寫的立場，{len(d.get('page_one') or ''):,} 字元）", "",
         "```", (d.get("page_one") or "").rstrip(), "```", "",
         "---", ""]
    if d.get("page_one_columns"):
        L += ["## 第一頁（右側分析師欄已切開的版本）", "",
              "**這一份是機械切欄的結果，不保證對。** 上面那一份 `page_one` 才是"
              "閘門拿來比對的正本 —— `quote` 與 `grounding` 一律從**上面那份**取。",
              "",
              "第一頁右側常是分析師姓名與電話，逐行抽取會把它插進句子中間"
              "（`…quarters, yet its` ／ `Niklas Garnadt` ／ `labour market remains weak.`）。"
              "**兩份讀起來哪一份是通順的，你一眼看得出來，偵測程式看不出來。**",
              "", "```", (d.get("page_one_columns") or "").rstrip(), "```", "",
              "---", ""]
    L += [f"## 內文目錄（{len(keep)} 頁，已剃除揭露頁；"
         f"合計 {sum(len(p) for _, p in keep):,} 字元）", "",
         "**要哪一頁就取哪一頁，不要整份載入。** 下面每一行是那一頁的第一句可讀的話。", ""]
    for i, pg in keep:
        L.append(f"- **第 {i + 2} 頁**（`body[{i}]`，{len(pg):,} 字元）　{head(pg)}")
    # **這一行不能寫死絕對路徑。** 卷宗會活過產生它的那個工作階段，而
    # `_paths.extracted()` 在 Cowork 裡展開成
    # `/sessions/<階段 id>/mnt/broker-research/extracted` —— 階段 id 每次都不一樣。
    # 2026-08-23 讀到的卷宗裡就還留著上一個階段的 id，
    # **照著它跑會拿到「檔案不存在」，而那看起來像資料掉了，不像路徑過期。**
    # 改成執行時才決定：跟 `_paths.root()` 同一套規則（環境變數優先，沒設才退回 `~`）。
    L += ["", "取單頁：", "```",
          "python3 -c \"import json,os;"
          f"r=os.environ.get('{_paths.ENV}') or os.path.expanduser('~/broker-research');"
          f"d=json.load(open(r+'/extracted/{d['slug']}.json',encoding='utf-8'));"
          "print(d['body'][N])\"", "```", ""]

    tb = d.get("tables") or []
    if tb:
        L += ["---", "", f"## 表格（{len(tb)} 個，抽取器解出來的）", "",
              "**欄位常常錯位**，所以它們不是重製圖的來源 —— "
              "圖裡的數字要從內文明確寫出來的地方取。表格列可以當 `grounding`，"
              "但要整列原文複製。", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("slug")
    ap.add_argument("--extracted", default=None)
    ap.add_argument("--out", default=None)
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12
    E = os.path.expanduser(a.extracted) if a.extracted else _paths.extracted()
    O = os.path.expanduser(a.out) if a.out else _paths.under("dossier")
    src = os.path.join(E, f"{a.slug}.json")
    if not os.path.exists(src):
        print(f"找不到 {src}", file=sys.stderr)
        return 12
    d = json.load(open(src, encoding="utf-8"))
    os.makedirs(O, exist_ok=True)
    out = os.path.join(O, f"{a.slug}.md")
    open(out, "w", encoding="utf-8").write(build(d))
    print(f"→ {out}（{os.path.getsize(out):,} bytes）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
