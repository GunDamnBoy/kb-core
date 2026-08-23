#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Houseview 的每週整合檢查。**這支只讀不寫，除了自己的回執。**

用法：
    houseview_weekly.py [--dir ~/houseview] [--outbox ~/outbox/houseview]

## 為什麼要有這一支

repo-lint 顧的是「**我們**有沒有改壞」，每次 push 跑。
這支顧的是「**他們**有沒有改壞」——houseview 讀五個上游 repo
（chart-of-the-day、convergence-weekly、broker-research-digest、kb-core、
自己的 content），而唯一會踩過整條整合的東西是月報，**一個月才踩一次**。

2026-08-23 那次端到端，光是 `prep_hv.py` 就撞到兩次上游形狀改變
（`sections` 是 list 不是 dict、`range` 是 `{quant, narrative}`），
是因為當下有人在跑它才發現的。沒人跑的話，那兩個會安靜躺到九月底，
而九月底正是要交稿的那一天。

## 為什麼要跟上一次比

`prep_hv.py` 有一種失敗**不會**讓退出碼非 0：某一節解析回空，
輸出照印、格式照對、只是短了一段。這正是這套系統修過兩次的靜默失效。

**單張快照永遠答不出「有沒有掉東西」**（哨兵那支的原話）。
所以回執記下每一節的字元數，下一次跟它比：
匯流從 4,413 掉到 0 是訊號，而單看 0 分不出是上游壞了還是月初還沒有料。

**跨月不比。** 每月 1 號當月盤點本來就接近空的，拿它跟上月底比會固定紅，
而**會固定響的警報就是雜訊**。

## 退出碼

    0   全綠
    1   有檢查失敗（上游或自己壞了）
    2   跑不起來（node 不在、houseview 目錄不在）——**這不是通過**
"""
import argparse, datetime as dt, glob, json, os, re, subprocess, sys

TPE = dt.timezone(dt.timedelta(hours=8))
# 這一節掉到 0 就是訊號。1、2 節（每日五圖、上一期骨架）不列入：
# 前者月初本來就空，後者在第一期時本來就沒有。
WATCHED = ("4. 匯流訊號報", "5. 外資報告")


def sh(cmd, cwd=None, env=None):
    e = dict(os.environ); e.update(env or {})
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def parse_sections(out):
    """從 prep 的頁尾抓分節體積。抓不到就回 None —— **抓不到不等於零**。

    節名自己就含數字（`4. 匯流訊號報 · 當月 3 期 4,413`），所以不能用
    「名字＋數字」去掃 —— 第一版那樣寫，結果匯流記成 3、外資記成 3，
    而 5,560 掛在一個叫「期」的欄位上。**回執長得完全正常**：數字在該在的
    位置、型別也對，只有值是錯的，而下一週就會拿它當基準去比。

    改法有兩層：以 `、` 切段、每段取**行尾**那個數字當體積；
    然後拿各段之和去對 prep 自己算的「合計」——**來源已經算過一次的數字，
    就是這個解析器最便宜的裁判**。對不上就回 None，不留半信半疑的值。
    """
    m = re.search(r"\*\*分節體積\*\*[^：]*：(.+?)\*\*合計\s*([\d,]+)", out, re.S)
    if not m:
        return None
    secs = {}
    for seg in m.group(1).split("、"):
        mm = re.search(r"^(.*?)\s+([\d,]+)\s*$", seg.strip())
        if mm:
            secs[mm.group(1).strip()] = int(mm.group(2).replace(",", ""))
    total = int(m.group(2).replace(",", ""))
    if not secs or abs(sum(secs.values()) - total) > 2:
        return None
    return secs


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--dir", default=os.path.expanduser("~/houseview"))
    ap.add_argument("--outbox", default=os.path.expanduser("~/outbox/houseview"))
    ap.add_argument("--kbcore", default=os.path.expanduser("~/kb-core"))
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args(argv[1:])
    if a.help:
        print(__doc__); return 0
    if a.selftest:
        return selftest()

    now = dt.datetime.now(TPE)
    stamp = now.date().isoformat()
    R = {"system": "houseview", "stamp": stamp, "at": now.isoformat(),
         "checks": {}, "sections": None, "exit": 0, "notes": []}

    def die(code, why):
        R["exit"] = code; R["notes"].append(why)
        write(a.outbox, stamp, R)
        print(f"跑不起來：{why}", file=sys.stderr)
        return code

    if not os.path.isdir(a.dir):
        return die(2, f"houseview 目錄不在：{a.dir}")
    if sh(["node", "-v"])[0] != 0:
        return die(2, "這台機器沒有 node —— 產生器與邊界測試都跑不了，**這不是通過**")
    if not os.path.isdir(os.path.join(a.dir, "node_modules")):
        return die(2, "node_modules 不在（跑 `npm ci`）—— 邊界測試會全部以載入錯誤收場，"
                      "而那種失敗長得跟守衛叫了一樣")

    # ── 1. prep：上游五庫的形狀有沒有變 ────────────────────────
    period = now.strftime("%Y-%m")
    rc, out, err = sh([sys.executable, "prep_hv.py", period, "--stdout"], cwd=a.dir)
    R["checks"]["prep"] = {"exit": rc, "period": period,
                           "stderr": err.strip()[:800] or None}
    if rc == 0:
        R["sections"] = parse_sections(out)
        if R["sections"] is None:
            R["notes"].append("prep 跑完了，但分節體積解析不出來、或各節之和對不上"
                              "它自己印的合計 —— **格式變了，下一次就比不出東西掉了沒有**。"
                              "這裡刻意不存半信半疑的值：錯的基準比沒有基準更糟")

    # ── 2. 邊界測試 ────────────────────────────────────────────
    rc2, o2, e2 = sh(["node", "test_build_hv3.js"], cwd=a.dir)
    R["checks"]["boundary"] = {"exit": rc2,
                               "tail": (o2 or e2).strip().splitlines()[-1:] or None}

    # ── 3. 每個 content 檔對得上自己宣告的版面 ──────────────────
    bad = []
    for f in sorted(glob.glob(os.path.join(a.dir, "content-*.json"))
                    + glob.glob(os.path.join(a.dir, "content-*.json.example"))):
        rc3, _, e3 = sh(["node", "build_hv3.js", os.path.basename(f), "/dev/null"],
                        cwd=a.dir, env={"HV_VALIDATE_ONLY": "1"})
        if rc3 != 0:
            bad.append({"file": os.path.basename(f), "err": e3.strip()[:300]})
    R["checks"]["content_layout"] = {"exit": 1 if bad else 0, "bad": bad or None}

    # ── 4. kb-core 那 32 條 ────────────────────────────────────
    per = sorted({m.group(1) for f in glob.glob(os.path.join(a.dir, "content-*.json"))
                  for m in [re.search(r"content-(\d{4}-\d{2})\.json$", f)] if m})
    latest = per[-1] if per else None
    if latest:
        rc4, o4, e4 = sh([sys.executable, "tools/houseview_verify.py",
                          "--period", latest, "--dir", a.dir], cwd=a.kbcore)
        line = next((l for l in (o4 + e4).splitlines() if "PASS ·" in l), None)
        R["checks"]["kbcore"] = {"exit": rc4, "period": latest, "summary": line}
    else:
        R["checks"]["kbcore"] = {"exit": 2, "period": None,
                                 "summary": "一個 content-YYYY-MM.json 都沒有"}

    # ── 5. 跟上一次比：有沒有哪一節掉光了 ──────────────────────
    prev = load_prev(a.outbox, stamp)
    R["compared_to"] = prev.get("stamp") if prev else None
    if prev and R["sections"] and prev.get("sections") \
            and prev.get("checks", {}).get("prep", {}).get("period") == period:
        drops = find_drops(prev["sections"], R["sections"])
        R["checks"]["sections_kept"] = {"exit": 1 if drops else 0, "drops": drops or None}
    else:
        why = ("沒有上一次的回執" if not prev else
               "上一次是別的月份，跨月不比 —— 月初本來就接近空的")
        R["checks"]["sections_kept"] = {"exit": 0, "skipped": why}
        R["notes"].append("分節體積這次沒有比：" + why)

    R["exit"] = 1 if any(c.get("exit") for c in R["checks"].values()) else 0
    write(a.outbox, stamp, R)
    report(R)
    return R["exit"]


def find_drops(prev, now):
    """上一次有、這一次歸零的受監控節。

    節名帶期數（`4. 匯流訊號報 · 當月 3 期`），期數每月會變，所以用前綴對，
    不用等值對 —— 等值對的話每個月都會「找不到 → 當成 0 → 全部誤報」，
    而**會固定響的警報就是雜訊**。
    """
    out = []
    for k, v in prev.items():
        if not any(k.startswith(w) for w in WATCHED):
            continue
        cur = next((n for kk, n in now.items() if kk.startswith(k[:8])), 0)
        if v > 0 and cur == 0:
            out.append(f"{k}：{v:,} → 0")
    return out


def selftest():
    """**這道守衛必須被看過叫一次。** fail 一組、貼著邊界的 pass 一組。"""
    P = {"1. 每日五圖盤點": 13264, "4. 匯流訊號報 · 當月 3 期": 4413,
         "5. 外資報告 · 當月 3 期": 5560}
    cases = [
        ("匯流歸零 · 要叫", True,
         {"1. 每日五圖盤點": 13264, "4. 匯流訊號報 · 當月 0 期": 0,
          "5. 外資報告 · 當月 3 期": 5560}),
        ("匯流只剩一條 · 不要叫", False,
         {"1. 每日五圖盤點": 13264, "4. 匯流訊號報 · 當月 1 期": 812,
          "5. 外資報告 · 當月 3 期": 5560}),
        ("期數變了但都在 · 不要叫", False,
         {"1. 每日五圖盤點": 13264, "4. 匯流訊號報 · 當月 5 期": 7010,
          "5. 外資報告 · 當月 4 期": 6001}),
        ("每日五圖歸零 · 不要叫（不在監控名單，月初本來就空）", False,
         {"1. 每日五圖盤點": 0, "4. 匯流訊號報 · 當月 3 期": 4413,
          "5. 外資報告 · 當月 3 期": 5560}),
        ("兩節同時歸零 · 要叫兩條", True,
         {"1. 每日五圖盤點": 13264, "4. 匯流訊號報 · 當月 0 期": 0,
          "5. 外資報告 · 當月 0 期": 0}),
    ]
    bad = 0
    for name, want, now in cases:
        got = find_drops(P, now)
        okk = bool(got) == want
        bad += not okk
        print(("PASS  " if okk else "FAIL  ") + name + (f"　{got}" if got else ""))
    # 解析器對不上合計時要回 None，不要留半信半疑的值
    foot = ("**分節體積**：（前言） 28、4. 匯流訊號報 · 當月 3 期 4,413"
            "　**合計 4,441 字元**")
    for name, txt, want in [("解析 · 和對得上", foot, True),
                            ("解析 · 和對不上要回 None", foot.replace("4,441", "9,999"), False)]:
        got = parse_sections(txt) is not None
        okk = got == want
        bad += not okk
        print(("PASS  " if okk else "FAIL  ") + name)
    print(f"\n{len(cases) + 2 - bad}/{len(cases) + 2} 通過")
    return 1 if bad else 0


def load_prev(outbox, stamp):
    fs = sorted(glob.glob(os.path.join(outbox, "*.receipt.json")))
    fs = [f for f in fs if not f.endswith(f"{stamp}.receipt.json")]
    for f in reversed(fs):
        try:
            return json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
    return None


def write(outbox, stamp, R):
    """**每一次都寫，綠的也寫。** 沉默的成功與沒有跑過長得一模一樣 ——
    這是 ai-bubble-monitor 那次空輪次 0 bytes 的教訓。"""
    os.makedirs(outbox, exist_ok=True)
    p = os.path.join(outbox, f"{stamp}.receipt.json")
    tmp = p + ".new"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def report(R):
    NAME = {"prep": "prep 讀得動上游五庫", "boundary": "產生器邊界測試",
            "content_layout": "content 檔對得上自己的版面",
            "kbcore": "kb-core 的 houseview 那一套",
            "sections_kept": "分節體積沒有掉光（跟上一次比）"}
    for k, c in R["checks"].items():
        mark = "PASS" if not c.get("exit") else "FAIL"
        extra = c.get("summary") or c.get("skipped") or ""
        if c.get("drops"):
            extra = "；".join(c["drops"])
        if c.get("bad"):
            extra = "；".join(b["file"] for b in c["bad"])
        print(f"{mark}  {NAME.get(k, k)}" + (f" —— {extra}" if extra else ""))
    for n in R["notes"]:
        print("      · " + n)
    print(f"\n退出碼 {R['exit']}　回執 {R['stamp']}.receipt.json")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
