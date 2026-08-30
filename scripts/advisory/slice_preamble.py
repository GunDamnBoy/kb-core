#!/usr/bin/env python3
"""把採集前言按採集員切片。**正本永遠只有 `preamble.md` 一份。**

用法：slice_preamble.py [--only C] [--dry-run] [--check]

## 為什麼

2026-08-25 量到：`preamble.md`（19,193 字元 ≈ 18,987 token）在第 2 輪進到每個
採集員的 context，然後被重讀到收工 —— **08-24 那一輪是 11.0M 重讀、佔子代理
重讀成本的 17%、換算有效 token 佔整輪 advisory 的 8%**。

而它有六成是「只有一個採集員用得到」的東西：第六節那張選擇器表 21 列、一列一家來源，
每個採集員只碰自己那幾家；第七節只有台灣組要、第七之二與第八節只有信用債與黃金那兩組要。

## 為什麼是「切成檔」而不是「塞進任務卡」

任務卡是模型寫的。要它把八千字元抄進去，既貴又會抄錯，而且抄完還是進同一個 context。
切成檔、任務卡只改指路的那一行，成本才真的下去。

## 一份變七份就會漂移 —— 這支怎麼擋

**七份都是生成物，不可以手改。** `--check` 會就地重生成一次再比對，不同就非零退出，
可以掛進 repo-lint。改內容一律改 `preamble.md`，重跑這支。

## 分類表在這支裡，而且漏一節就會炸

`SECTION_OWNER` 必須涵蓋 `preamble.md` 的每一節。新增一節而忘了分類 —— 這支
**直接非零退出**，不會安靜地把它塞給全體、也不會安靜地丟掉。
歸屬用的是來源關鍵字，經 `anchors.json` 的 `roster` 換算成採集員代號，
**所以改 roster 這支就跟著改，代號不寫死在這裡。**
"""
from __future__ import annotations
import argparse, io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(HERE, "preamble.md")
ANCHORS = os.path.join(ROOT, "advisory", "anchors.json")
OUT = os.path.join(HERE, "preamble")

ALL = "＊全體＊"

# 節標題（去掉 `## ` 之後的開頭）→ 誰要。值是 ALL，或一串「來源關鍵字」，
# 關鍵字經 roster 換算成採集員。**新增節而沒列進來，這支會非零退出。**
SECTION_OWNER = {
    "# 採集前言":            ALL,
    "## 一、收什麼":          ALL,
    "## 二、怎麼讀":          ALL,
    "## 三、擋源三分":        ALL,
    # 2026-08-28 新增。中文來源的門檻只有讀中文站的那三個採集員用得到；
    # 關鍵字經 roster 換算：鉅亨→F、華爾街見聞→C、TrendForce→D（MoneyDJ 同屬 F）。
    "### 中文來源用另一組數字": ["鉅亨", "華爾街見聞", "TrendForce"],
    "## 四、上限與節流":      ALL,
    "### 節流：":            ALL,
    "## 五、合規":            ALL,
    "## 六、來源":            ALL,          # 散文全體共用，只有裡面那張表要篩
    # 2026-08-30 新增。記的是「哪幾家在哪幾天本來就不發稿」，判準同下面那一列：
    # **表上出現了誰的來源**，不是「這個教訓誰用得到」。表列 SemiAnalysis／OGJ／EIA／
    # TrendForce（→D）、The Economist（→B）、MoneyDJ／鉅亨（→F）、Fierce／STAT（→G）。
    # A、C、E 手上沒有任何一家出現在表上，所以拿不到 —— 那正是切片要的效果。
    # （表裡另有 CME 一列，它不在 roster 的任何來源清單裡，故不影響歸屬。）
    "### 發稿日曆":           ["SemiAnalysis", "Oil & Gas Journal", "EIA", "TrendForce",
                              "The Economist", "MoneyDJ", "鉅亨", "Fierce Biotech", "STAT News"],
    "### `[BLOCKED:":        ALL,
    # 2026-08-28 改：原本只給 SemiAnalysis（＝D），但那張表列的是 NYT／WSJ／
    # The Economist，一個都不屬於 D —— **真正需要它的三個採集員一列都看不到**。
    # 同日又在 Bloomberg 撞到兩種（Washington Edition 電子報、Big Take podcast 頁），
    # 所以再加 A。判準是「表上出現了誰的來源」，不是「這個教訓誰用得到」——
    # 後者會一路擴張成 ALL，而那等於沒有切片。
    "### 電子報彙整頁":       ["NYT", "WSJ", "The Economist", "Bloomberg", "SemiAnalysis"],
    "## 六之二、":            ALL,
    "## 七、台股官方端點":     ["TWSE"],
    "## 七之二、":            ["EIA", "SPDR Gold Shares", "央行官方"],
    "## 八、保底數據":         ["FRED", "SPDR Gold Shares"],
    "## 九、回報格式":         ALL,
}

# 選擇器表裡對不上 roster 的列。**留在這裡是為了讓「對不上」變成一個有名字的決定，
# 而不是一個安靜的遺漏** —— 沒有這張表，這兩列會被每一個採集員都丟掉。
ROW_OVERRIDE = {"ECB（官方站）": "央行官方", "美國財政部": "央行官方",
                "Fed 官方演說": "央行官方"}

ESCAPE = ("\n---\n\n**這一份只含你負責的來源。** 需要別組的選擇器或端點"
          "（補位輪跨組取材時會用到），去讀完整版 `scripts/advisory/preamble.md`。\n")


def roster(path):
    a = json.load(io.open(path, encoding="utf-8"))
    r = a["collectors"]["roster"]
    return r, {s: g for g, v in r.items() for s in v["sources"]}


def who(keyword, owners):
    """來源關鍵字 → 採集員代號集合。對不到就是設定錯了，要炸。"""
    hit = {g for s, g in owners.items() if keyword.lower() in s.lower()}
    if not hit:
        raise SystemExit(f"分類表裡的來源關鍵字對不到 roster：{keyword!r}")
    return hit


TABLE_MARK = "**選擇器與路徑"


def split_sections(text):
    lines = text.split("\n")
    idx = [i for i, l in enumerate(lines) if re.match(r"^#{1,3} ", l)]
    idx.append(len(lines))
    secs = [("\n".join(lines[a:b])).rstrip("\n") for a, b in zip(idx, idx[1:])]

    # 2026-08-30 加的護欄。**只驗一件事：那張選擇器表還在第六節裡面嗎。**
    #
    # 為什麼需要它：`filter_table` 只對開頭是「## 六、來源」的那一節生效，
    # 而 `owner_of` 是按節分配的。**在表的前面插一個 `###` 子標題，
    # 表就會被切進那個子節** —— 於是①它不再被過濾（每個人拿到全部 21 列）
    # ②它跟著那個子節的 owner 走（沒被分到的人整張表都拿不到）。
    #
    # 這正是 2026-08-30 發生的事：新增的〈發稿日曆〉插在表前面，
    # A／C／E 三份切片的選擇器表整張消失、B／D／F／G 則拿到了別人的來源，
    # **而 `--check` 是綠的**（它比的是磁碟與重生成，兩邊一起錯）。
    # 那一輪沒有排程跑過，所以沒有造成實害 —— 下一次不會這麼幸運。
    six = next((s for s in secs if s.startswith("## 六、來源")), None)
    if six is not None and TABLE_MARK not in six:
        where = next((s.split("\n", 1)[0] for s in secs if TABLE_MARK in s), "（整份都找不到）")
        raise SystemExit(
            f"選擇器表跑出「## 六、來源」了，它現在在：{where}\n"
            f"→ 那一節前面多了一個 `###` 子標題，把表切走了。**把子標題移到表後面。**\n"
            f"**不修就繼續**：表不再被 `filter_table` 過濾，而且只有那個子節的 owner 拿得到。")
    return secs


def owner_of(sec, owners):
    head = sec.split("\n", 1)[0]
    for key, val in SECTION_OWNER.items():
        if head.startswith(key):
            if val is ALL:
                return None                       # None ＝ 全體
            out = set()
            for kw in val:
                out |= who(kw, owners)
            return out
    raise SystemExit(f"這一節沒有分類：{head[:60]!r}\n"
                     f"→ 去 slice_preamble.py 的 SECTION_OWNER 補一列。"
                     f"**不補就不會生成**，因為安靜地猜比停下來貴。")


def filter_table(sec, code, owners):
    """第六節那張選擇器表：只留這個採集員的來源。表外的字一個都不動。"""
    out, kept, seen_rows = [], 0, 0
    for l in sec.split("\n"):
        if not l.startswith("|"):
            out.append(l)
            continue
        label = l.strip("|").split("|")[0].strip()
        if label == "來源" or set(label) <= set("-: "):
            out.append(l)
            continue
        seen_rows += 1
        key = next((v for k, v in ROW_OVERRIDE.items() if k in label), label)
        hit = {g for s, g in owners.items()
               if key.lower() in s.lower() or s.split("（")[0].lower() in key.lower()}
        if not hit:
            raise SystemExit(f"選擇器表這一列對不到任何採集員：{label!r}\n"
                             f"→ 去 ROW_OVERRIDE 補一列，或修 anchors 的 roster。"
                             f"**丟掉它等於讓某一組瞎掉，所以這裡不容許猜。**")
        if code in hit:
            out.append(l)
            kept += 1
    if seen_rows and not kept:
        raise SystemExit(f"{code} 在選擇器表上一列都沒有 —— roster 與表對不起來")
    return "\n".join(out)


def build(code, secs, owners):
    parts = []
    for sec in secs:
        o = owner_of(sec, owners)
        if o is not None and code not in o:
            continue
        parts.append(filter_table(sec, code, owners)
                     if sec.startswith("## 六、來源") else sec)
    return "\n\n".join(parts).rstrip("\n") + "\n" + ESCAPE


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--only", default=None, help="只切這幾個（逗號分隔），預設全部")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="比對磁碟上的與重生成的")
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12

    src = io.open(SRC, encoding="utf-8").read()
    secs = split_sections(src)
    r, owners = roster(ANCHORS)
    codes = [c.strip() for c in a.only.split(",")] if a.only else sorted(r)
    bad = [c for c in codes if c not in r]
    if bad:
        print(f"roster 裡沒有：{'／'.join(bad)}", file=sys.stderr)
        return 12

    print(f"正本 {len(src):,} 字元、{len(secs)} 節\n")
    print(f"{'採集員':8}{'題材':30}{'字元':>8}{'省':>7}  檔案")
    print("─" * 78)
    rc = 0
    for c in codes:
        body = build(c, secs, owners)
        path = os.path.join(OUT, f"{c}.md")
        rel = os.path.relpath(path, ROOT)
        if a.check:
            cur = io.open(path, encoding="utf-8").read() if os.path.exists(path) else None
            state = "一致" if cur == body else ("**不一致 —— 有人手改了**" if cur else "**缺檔**")
            if cur != body:
                rc = 1
        elif a.dry_run:
            state = "（試跑，沒寫）"
        else:
            os.makedirs(OUT, exist_ok=True)
            io.open(path, "w", encoding="utf-8").write(body)
            state = rel
        print(f"{c:8}{r[c]['topic'][:28]:30}{len(body):>8,}"
              f"{(1-len(body)/len(src))*100:>6.0f}%  {state}")
    print()
    if a.check:
        print("一致 ＝ 磁碟上那份就是從正本生出來的。"
              "**不一致就是有人手改了切片** —— 改回 `preamble.md`，重跑這支。")
    else:
        print("七份都是生成物，**不要手改**。內容要改就改 `preamble.md` 再重跑。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
