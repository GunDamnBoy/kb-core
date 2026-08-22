#!/usr/bin/env python3
"""驗一份撰稿子代理的交件。**這支只讀不寫。**

用法：check_part.py <part.json 路徑>

## 為什麼要有它

2026-08-22 量出來的：十一個撰稿子代理**各自寫了一次同一支比對腳本** ——
它們要驗原句對不對得上、字數怎麼算、標籤幾個算合格，而那三條規則
分別住在 `checks/research.py`、`assemble.py`、`research/anchors.json`。

規則有三個家，於是每個子代理都得先去找、再自己實作一次。
**環境本來就該是真相來源** —— 出一支指令，一輪驗完，
而它跑的是**跟發布閘門同一套 `_norm`**，不是另一套長得很像的。
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "research"))

from checks.research import _norm            # noqa: E402  **同一套折疊規則，不是另一套**
from kbcore.result import Exit               # noqa: E402

A = json.loads((ROOT / "research" / "anchors.json").read_text(encoding="utf-8"))
ADV = json.loads((ROOT / "advisory" / "anchors.json").read_text(encoding="utf-8"))
THEMES = {g["name"] for g in ADV["groups"]}


def count(s):
    """`anchors.summary_tiers.count_rule` 的唯一實作，與 `assemble.py` 逐字相同。"""
    s = re.sub(r"^#{1,6}\s*", "", s or "", flags=re.M)
    s = re.sub(r"\*\*|__|`|\*|^[-–—]\s*", "", s, flags=re.M)
    return len(re.sub(r"\s+", "", s))


def tier_of(pages):
    for t in A["summary_tiers"]["tiers"]:
        if t["under_pages"] is None or pages < t["under_pages"]:
            return t
    return A["summary_tiers"]["tiers"][-1]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    p = Path(os.path.expanduser(argv[1]))
    if not p.exists():
        print(f"找不到 {p}", file=sys.stderr)
        return Exit.BAD_INPUT
    part = json.loads(p.read_text(encoding="utf-8"))
    slug = part.get("slug") or p.stem

    root = os.path.expanduser(os.environ.get("BROKER_RESEARCH_ROOT", "~/broker-research"))
    ex = Path(root) / "extracted" / f"{slug}.json"
    if not ex.exists():
        print(f"找不到抽取結果 {ex} —— **沒有東西可以比對，這不是「都對」**", file=sys.stderr)
        return Exit.BAD_INPUT
    d = json.loads(ex.read_text(encoding="utf-8"))
    blob = _norm("\n".join([d.get("page_one") or ""] + (d.get("body") or [])
                           + [" ".join(r) for t in (d.get("tables") or [])
                              for r in t.get("rows") or []]))

    bad = []
    ok = []

    # 1. 篇幅
    n, t = count(part.get("summary", "")), tier_of(d["pages"])
    lo, hi = t["chars"]
    if n < lo:
        bad.append(f"篇幅 {n:,} < {lo:,} **不足**（{d['pages']} 頁 → 目標 {t['target']:,}）")
    elif n > hi:
        ok.append(f"篇幅 {n:,} > {hi:,} 超出（WARN，不擋）")
    else:
        ok.append(f"篇幅 {n:,}（目標 {t['target']:,}，區間 {lo:,}–{hi:,}）")

    # 2. 第一個標題是不是主張
    first = next((l for l in (part.get("summary") or "").splitlines()
                  if l.startswith("#")), "")
    h = re.sub(r"^#+\s*", "", first).strip()
    if re.search(r"(?:什麼|嗎|呢|\?|？)\s*$", h):
        bad.append(f"第一個標題是問句：「{h[:34]}」—— **它會被原封不動抬到網站卡片上**，"
                   "要寫成一個主張")
    elif h:
        ok.append(f"第一個標題：{h[:40]}")

    # 3. 原句
    ss = part.get("stances") or []
    if not ss:
        bad.append("一筆立場都沒有")
    for i, s in enumerate(ss, 1):
        q = _norm(s.get("quote"))
        if not q:
            bad.append(f"立場 {i} 的 quote 是空的")
        elif q not in blob:
            bad.append(f"立場 {i} 的原句**在報告裡找不到**：「{q[:46]}…」")
        if s.get("theme") not in THEMES:
            bad.append(f"立場 {i} 的 theme「{s.get('theme')}」不在 15 組值域裡")
        if s.get("label") is not None:
            bad.append(f"立場 {i} 的 label 要留 null（受控詞表還沒訂）")
    if ss and not any("原句" in b or "theme" in b for b in bad):
        ok.append(f"立場 {len(ss)} 筆，原句與 theme 全數通過")

    # 4. 標籤
    T = A["tags"]
    tg = [x.strip() for x in (part.get("tags") or []) if x and x.strip()]
    tlo, thi = T["per_report"]
    if not tlo <= len(tg) <= thi:
        bad.append(f"標籤 {len(tg)} 個，要 {tlo}–{thi} 個")
    for x in tg:
        if len(x) > 12 or re.search(r"[\s，。、；：,.;:!?！？]", x):
            bad.append(f"標籤「{x}」帶空白標點或超過 12 字 —— 標籤是名詞不是句子")
    if tg and not any("標籤" in b for b in bad):
        ok.append(f"標籤 {len(tg)} 個：{'、'.join(tg)}")

    # 5. 圖
    cs = part.get("charts") or []
    clo, chi = A["charts"]["per_report"]
    if not clo <= len(cs) <= chi:
        bad.append(f"圖 {len(cs)} 張，每份 {clo}–{chi} 張")
    for c in cs:
        g = c.get("grounding") or []
        if not g:
            bad.append(f"圖「{c.get('title','?')[:20]}」沒有 grounding —— **不得發布**")
        for frag in g:
            if _norm(frag) not in blob:
                bad.append(f"grounding **在報告裡找不到**：「{_norm(frag)[:46]}…」"
                           " —— 前後不要加任何說明文字")
    if cs and not any("grounding" in b or "圖 " in b for b in bad):
        ok.append(f"圖 {len(cs)} 張，grounding 共 "
                  f"{sum(len(c.get('grounding') or []) for c in cs)} 條全數通過")

    extra = sorted(set(part) - {"slug", "summary", "tags", "stances", "charts"})

    print(f"\n{slug}　（{d['pages']} 頁）")
    for x in ok:
        print(f"  ✓ {x}")
    if extra:
        print(f"  · 多了不會被讀的鍵：{extra} —— 交件就五個鍵")
    if bad:
        print(f"\n**{len(bad)} 項要改：**")
        for x in bad:
            print(f"  ✗ {x}")
        return Exit.CONTENT
    print("\n全數通過 —— 可以交件")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
