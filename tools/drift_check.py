#!/usr/bin/env python3
"""正本 vs 部署副本：**逐節比對，不比整份。**

## 為什麼是逐節

2026-08-24 拿到第一筆真實資料：chart 排程裡那份 prompt 與 `scripts/chart/RUN-PROMPT.md`
**七個章節標題完全一致、順序一樣，只有最後一節〈用量〉不同** —— 而那一節正是
當天早上才改過的那一節。

**漂移不是整份走樣，是一節走樣，而且通常是最新改動的那一節。**
比整份只會得到「不一樣」三個字；逐節才指得出「是哪一節、要重貼什麼」。

那一節的內容也說明了代價：部署副本帶的是 08-23 之前的舊文，它叫輪次在雲端容器
`git clone` 再跑 `usage_report.py`，而 `MEASURE.md` 記著那句「逐字稿只存在於雲端
那一側」**剛好講反**。於是每天一次注定失敗的 clone 與量測，而且它沒有切界線 ——
`usage.csv` 上 08-23 chart 那列的 `bounded=no` 就是它寫出來的。

## 部署副本從哪來

**帳號 skill 自己找得到**（Cowork 把它同步到每一場對話的 `.claude/skills/synced/`）。
**排程 prompt 找不到** —— 桌面版本機建的排程不在 `list_triggers` 裡，也沒有檔案落地。
那一種要人貼一份快照到 `~/.kbusage/deployed/<id>.md`，而這一支會把**快照的年紀**
印出來：**過期的快照與同步的副本在畫面上長得一樣**，所以年紀要講。

## 它只報，不改

改法是「整份重貼」，而那一步只有人做得到（排程在桌面版、帳號 skill 在網頁）。
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import hashlib
import os
import sys

TPE = dt.timezone(dt.timedelta(hours=8))

# 正本 ↔ 部署位置。**這張表在別處不存在** —— 它就是一直沒有被寫下來的那件事。
#   kind "skill"    ：帳號 skill，值是 skill 名稱，自己找
#   kind "snapshot" ：排程 prompt，值是 ~/.kbusage/deployed/<值>.md，要人貼
PAIRS = [
    ("advisory", "skills/advisory/SKILL.md", "skill", "advisory-daily"),
    ("podcast", "scripts/podcast/DIGEST-PROMPT.md", "skill", "podcast-digest"),
    ("chart", "scripts/chart/RUN-PROMPT.md", "snapshot", "chart"),
    ("broker-research", "scripts/research/RUN-PROMPT.md", "snapshot", "research"),
    ("bubble", "skills/bubble/SKILL.md", "snapshot", "bubble"),
    ("convergence", "skills/convergence/SKILL.md", "snapshot", "convergence"),
    ("houseview", "skills/houseview/SKILL.md", "snapshot", "houseview"),
]

SKILL_GLOB = ("~/Library/Application Support/Claude/local-agent-mode-sessions"
              "/*/*/local_*/.claude/skills/synced/{name}/SKILL.md")


def sections(text: str):
    """切成 `[(標題, 正規化內容)]`；第一段沒有標題的叫「前言」。

    正規化只做兩件事：**去掉行尾空白、丟掉空行**。
    重新斷行與多一個空行不是漂移，**而把它們算成漂移，這支就會天天喊狼來了**。
    """
    out, title, buf = [], "（前言）", []
    for line in text.splitlines():
        if line.startswith("## "):
            out.append((title, buf))
            title, buf = line.strip(), []
        else:
            s = line.rstrip()
            if s:
                buf.append(s)
    out.append((title, buf))
    return [(t, "\n".join(b)) for t, b in out if t != "（前言）" or b]


def digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def find_skill(name: str):
    """帳號 skill 的實體檔。多場對話各有一份副本，取**最新**的那一場。"""
    cands = glob.glob(os.path.expanduser(SKILL_GLOB.format(name=name)))
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def age_of(path: str) -> str:
    m = dt.datetime.fromtimestamp(os.path.getmtime(path), TPE)
    # 掛載層的寫入時間可能比本機時鐘快一點點，`max` 是為了不要印出「-0 小時前」。
    hours = max(0.0, (dt.datetime.now(TPE) - m).total_seconds() / 3600)
    if hours < 1:
        s = "剛剛"
    elif hours < 48:
        s = f"{hours:.0f} 小時前"
    else:
        s = f"{hours/24:.0f} 天前"
    return f"{m:%Y-%m-%d %H:%M}（{s}）"


def compare(name, src_path, kind, key, kb, snap_dir):
    src = os.path.join(kb, src_path)
    if not os.path.exists(src):
        return "env", [f"  找不到正本 {src_path}"]

    if kind == "skill":
        dep = find_skill(key)
        if dep is None:
            return "missing", [f"  找不到帳號 skill `{key}` 的實體檔 —— "
                               f"**這不等於沒有漂移，是看不到**"]
        where = f"帳號 skill `{key}`"
    else:
        dep = os.path.join(snap_dir, f"{key}.md")
        if not os.path.exists(dep):
            return "missing", [f"  沒有快照 `{dep}` —— 排程 prompt 沒有檔案落地，"
                               f"要人貼一份進來（`pbpaste > {dep}`）"]
        where = f"排程 prompt 快照 `{key}.md`"

    a = sections(open(src, encoding="utf-8").read())
    b = sections(open(dep, encoding="utf-8").read())
    bmap = dict(b)
    lines = [f"  正本 {src_path}", f"  部署 {where}　{age_of(dep)}"]
    # **快照比正本舊，是誤報的主要來源。** 改完正本、重貼進排程之後若沒有重拍快照，
    # 這一支會一直喊漂移 —— 而**哨兵誤報一次之後就沒有人看了**。
    # 所以這裡不猜，直接把「快照可能還沒跟上」講出來，讓人先重拍再判。
    if kind == "snapshot" and os.path.getmtime(dep) < os.path.getmtime(src):
        lines.append("  ⚠︎ **快照比正本舊** —— 重貼進排程之後要重拍一次快照，"
                     "否則下面的差異可能只是快照沒跟上")
    bad = 0
    for title, body in a:
        if title not in bmap:
            lines.append(f"  ❌ {title} —— **部署副本裡沒有這一節**")
            bad += 1
        elif digest(bmap[title]) != digest(body):
            lines.append(f"  ❌ {title} —— 內容不同")
            bad += 1
        else:
            lines.append(f"  ✅ {title}")
    amap = dict(a)
    for title, _ in b:
        if title not in amap:
            lines.append(f"  ⚠︎ {title} —— 只在部署副本裡，正本已經沒有了")
            bad += 1
    return ("drift" if bad else "ok"), lines


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--kb", default="~/kb-core")
    ap.add_argument("--snapshots", default="~/.kbusage/deployed")
    ap.add_argument("--report", default="~/.kbusage/drift.md")
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12

    kb = os.path.expanduser(a.kb)
    snap = os.path.expanduser(a.snapshots)
    os.makedirs(snap, exist_ok=True)

    out = [f"# 正本 vs 部署副本 · {dt.datetime.now(TPE):%Y-%m-%d %H:%M}（台北）", ""]
    drift = seen = 0
    for name, src, kind, key in PAIRS:
        state, lines = compare(name, src, kind, key, kb, snap)
        mark = {"ok": "✅", "drift": "❌", "missing": "⚠︎", "env": "⚠︎"}[state]
        out.append(f"## {mark} {name}")
        out += lines + [""]
        drift += state == "drift"
        seen += state in ("ok", "drift")
    out += ["---", "",
            f"比得動的 {seen} 套，其中 **{drift} 套有漂移**。",
            "**逐節比，不比整份** —— 漂移通常只有一節，而那一節多半是最新改過的那一節。",
            "改法是整份重貼，這一支只報不改。"]
    text = "\n".join(out)
    print(text)
    rp = os.path.expanduser(a.report)
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    open(rp, "w", encoding="utf-8").write(text + "\n")
    return 12 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
