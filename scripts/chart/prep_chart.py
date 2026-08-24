#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日五圖 · 第 1 步的盤點表。**這支只讀不寫。**

用法：
    python3 scripts/chart/prep_chart.py [YYYY-MM-DD]

## 為什麼有這一支

第 1 步的完成條件本來就寫得很清楚：「手上有一張表 —— 今天是星期幾、
該出哪一條軌道、預抓涵蓋到哪些序列、以及上游今天給了什麼題材。」

**那張表是確定性的，不需要代理逐份讀檔去湊。** 而代價很具體：
上游投顧的當日 JSON 是 **11 萬字元（約 77k token）**，整份讀進來之後，
**後面每一輪都要重讀它一次**。2026-08-23 量到 chart 一輪 179 輪、
重讀 36.7M —— 光那一份就佔了三分之一上下。

這支把它壓成「群組｜tag｜標題」的清單：87 張 card、3.9k 字元，**28 倍**。
選定五個題目之後再去讀那五張的全文（`--card N`），是分層取材，
與 `prep_hv.py` 對每日五圖做的事同一招。

## 它不做的事

**不判斷、不選題、不取數。** 它只把四份輸入攤成一張表。
選哪五個題目、theme 撞不撞、素材夠不夠 —— 那些是第 2 步，是判斷。

`_macro_release.json` **整份原樣印出**（含 `checked_at` 與可能的 `error`），
因為 SKILL 明寫要整份搬進 `about.macro_release`，而且它只有幾百位元組。
**「偵測失敗」與「今天沒發布」是兩件事，而空的 items 與「沒發布」在下游長得一樣。**
"""
import argparse
import datetime as dt
import json
import os
import sys

TPE = dt.timezone(dt.timedelta(hours=8))
# 路徑從自己的位置推，不猜 `~`。這支住在 <某處>/kb-core/scripts/chart/，
# 其他 repo 是 kb-core 的兄弟 —— Mac 本機與 Cowork 工作區同一條規則。
# （2026-08-23 這個坑在 houseview_weekly.py 上踩過一次。）
KBCORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIB = os.path.dirname(KBCORE)
WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ZH = ["一", "二", "三", "四", "五", "六", "日"]


def sib(name):
    p = os.path.join(SIB, name)
    return p if os.path.isdir(p) else os.path.expanduser("~/" + name)


def load(path, what):
    """讀不到就說出來並回 None。**讀不到與「裡面是空的」是兩件事。**"""
    if not os.path.exists(path):
        return None, f"{what} 不在：{path}"
    try:
        return json.load(open(path, encoding="utf-8")), None
    except Exception as e:
        return None, f"{what} 讀不開：{type(e).__name__}: {e}"


def topics(adv):
    """把上游的 card 攤成一行一條。

    **形狀不對就說出來，不要靜靜跳過。** `prep_hv.py` 2026-08-23 踩過：
    `sections` 是 list 不是 dict，而它的 isinstance 判斷讓整節無聲消失，
    輸出仍然看起來完整。這裡每一層都回報遇到的實際型別。
    """
    out, notes = [], []
    secs = adv.get("sections")
    if not isinstance(secs, list):
        return [], [f"sections 不是 list，是 {type(secs).__name__} —— 上游形狀變了"]
    for si, s in enumerate(secs):
        gs = s.get("groups")
        if not isinstance(gs, list):
            notes.append(f"第 {si+1} 節「{s.get('title','?')}」的 groups 是 "
                         f"{type(gs).__name__}，跳過這一節")
            continue
        for g in gs:
            for c in g.get("cards") or []:
                out.append({
                    "group": g.get("label", "?"), "tag": c.get("tag", ""),
                    "title": c.get("title") or c.get("head") or "",
                    "date": c.get("date", ""), "tone": c.get("tone", ""),
                    "deep": bool(c.get("deep")), "src": c.get("src", "")})
    return out, notes


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--card", type=int, default=None,
                    help="印出第 N 張 card 的全文（選定題目之後才用）")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args(argv[1:])
    if a.help:
        print(__doc__)
        return 0

    day = a.date or dt.datetime.now(TPE).date().isoformat()
    d = dt.date.fromisoformat(day)
    anchors, e1 = load(os.path.join(KBCORE, "chart", "anchors.json"), "chart/anchors.json")
    if anchors is None:
        print(e1, file=sys.stderr)
        return 12
    adv, e_adv = load(os.path.join(sib("advisory-rewrite"), "data", f"{day}.json"),
                      "上游投顧當日 JSON")
    pre, e_pre = load(os.path.join(sib("chart-of-the-day"), "data", "_prefetch_status.json"),
                      "預抓狀態檔")
    mac, e_mac = load(os.path.join(sib("chart-of-the-day"), "data", "_macro_release.json"),
                      "三大數據發布偵測")

    if a.card is not None:
        if adv is None:
            print(e_adv, file=sys.stderr)
            return 12
        cards = []
        for s in adv.get("sections") or []:
            for g in s.get("groups") or []:
                cards += (g.get("cards") or [])
        if not 1 <= a.card <= len(cards):
            print(f"--card 要在 1..{len(cards)}", file=sys.stderr)
            return 12
        print(json.dumps(cards[a.card - 1], ensure_ascii=False, indent=1))
        return 0

    print(f"# 每日五圖 · 開工盤點　{day}（星期{ZH[d.weekday()]}）\n")

    # ── 軌道 ──────────────────────────────────────────────
    T = anchors.get("tracks") or {}
    wk = WD[d.weekday()]
    if d.weekday() >= 5:
        prev = (d - dt.timedelta(days=1)).isoformat()
        pdat, _ = load(os.path.join(sib("chart-of-the-day"), "data", f"{prev}.json"), "前一日")
        used = ""
        for c in ((pdat or {}).get("charts") or []):
            if "軌道圖" in str(c.get("slot", "")):
                used = str(c.get("slot", ""))
        print(f"**軌道**：週末 → {T.get('weekend_mode','週線複查')}　"
              f"（標籤格式 `{T.get('weekend_slot_label','')}`）")
        print(f"　昨天（{prev}）用的是：{used or '（讀不到前一日，要人工確認）'}")
        if T.get("weekend_distinct_days"):
            print("　**週六與週日不得挑同一條** —— 上面那一條今天不能再用")
    else:
        print(f"**軌道**：{T.get(wk, '（anchors.tracks 裡沒有這一天）')}（{wk} 綁死，不是輪流）")
    S = anchors.get("structure") or {}
    print(f"**版位**：{'／'.join(S.get('slots') or [])}"
          f"　theme 不得重複＝{S.get('theme_unique_within_day')}\n")

    # ── 預抓 ──────────────────────────────────────────────
    print("## 預抓")
    if pre is None:
        print(f"　**{e_pre}** —— 沒有狀態檔＝預抓沒跑，"
              "**不是「可能沒跑」**；`about.data_path` 不可宣稱 prefetch")
    else:
        vh = ((anchors.get("prefetch") or {}).get("status_valid_hours")) or 30
        fin = pre.get("finished") or pre.get("started") or ""
        age = None
        try:
            age = (dt.datetime.now(TPE) - dt.datetime.fromisoformat(fin)).total_seconds() / 3600
        except Exception:
            pass
        mark = "逾期" if (age is not None and age > vh) else "有效"
        print(f"　{fin}　{'%.1f 小時前' % age if age is not None else '（時間讀不出來）'}"
              f"　門檻 {vh}h → **{mark}**")
        print(f"　{pre.get('ok','?')}/{pre.get('requested','?')} 條成功　"
              f"失敗 {len(pre.get('failed') or {})}　跳過 {len(pre.get('skipped') or {})}")
        hs = (pre.get("handshake") or {}).get("failed") or []
        if hs:
            print(f"　**握手失敗**：{'、'.join(hs)} —— 這幾條今天退回代理或改題，"
                  "並在 `about.run` 說明")
        ser = pre.get("series") or []
        if ser:
            print(f"　涵蓋 {len(ser)} 條，末日最舊的五條：")
            for s in sorted(ser, key=lambda x: str(x.get("last", "")))[:5]:
                print(f"　　{s.get('id','?'):<14}n={s.get('n','?'):<6}last={s.get('last','?')}")
    print()

    # ── 三大數據：整份原樣 ────────────────────────────────
    print("## 三大數據發布偵測（整份原樣，直接搬進 `about.macro_release`）")
    print("```json")
    print(json.dumps(mac, ensure_ascii=False, indent=1) if mac is not None else f"// {e_mac}")
    print("```")
    if mac is not None and mac.get("error"):
        print("**帶 error** —— 檢查會判 SKIPPED 並把錯誤說出來。"
              "「偵測失敗」與「今天沒發布」是兩件事，不要自己去問 FRED。")
    print()

    # ── 上游題材 ──────────────────────────────────────────
    print("## 上游題材")
    if adv is None:
        wait = (anchors.get("schedule") or {}).get("upstream_wait_minutes", 15)
        print(f"　**{e_adv}**")
        print(f"　上游還沒好就等 {wait} 分鐘；仍無則用前一日並在 `about.run` 註明。")
        print("　**不要改讀別的目錄** —— 舊 checkout 讀起來不會報錯，只會安靜拿到舊題材。")
        return 0
    tp, notes = topics(adv)
    for n in notes:
        print(f"　⚠︎ {n}")
    raw = len(json.dumps(adv, ensure_ascii=False))
    print(f"　{len(tp)} 條（上游整份 {raw:,} 字元，這裡只列標題）")
    print(f"　`{os.path.basename(sys.argv[0])} {day} --card N` 印第 N 張的全文\n")
    cur = None
    for i, t in enumerate(tp, 1):
        if t["group"] != cur:
            cur = t["group"]
            print(f"　── {cur}")
        flag = "★" if t["deep"] else " "
        stale = "" if t["date"] == day else f"（{t['date']}）"
        print(f"　{i:>3}{flag} [{t['tag']}] {t['title']}{stale}")
    dig = sum(len(f"{t['group']}{t['tag']}{t['title']}") for t in tp)
    print(f"\n　（標題合計約 {dig:,} 字元，壓縮 {raw/max(1,dig):.0f}×；"
          "★＝上游標為深度。**選題是第 2 步，這支不選**）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
