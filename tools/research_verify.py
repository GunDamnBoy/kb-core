#!/usr/bin/env python3
"""驗一批抽好的外資報告。**這支只讀不寫。**

用法：research_verify.py [抽取輸出目錄]（預設 ~/broker-research/extracted）

## 為什麼 payload 是整批

去重與 slug 唯一性是**跨檔**的問題，單份看不出來：同一份報告用兩個檔名各抽一次，
每一份自己都完全合格。週頻的產出本來就是一批。

## 這支跟 `systems/research.py` 的關係

2026-08-21 起這一套會發布，payload 的正本因此搬到 `systems/research.py` 的
`build()`（publish 的閘門走那條）。**這支留下來，因為它是不寫檔的那一條路**：
組檔中途、還沒打算發布的時候要看檢查結果，走這裡。

兩邊組出來的 payload 形狀要一致 —— 不一致的樣子是「這裡全綠、publish 擋下來」，
或更糟的反過來。差別只有一個且是刻意的：這支自己去 digest 目錄撈最新一期，
`build()` 則吃 publish 交給它的那份草稿。
"""
import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
from systems.research import reference_anchors  # noqa: E402
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402

REQUIRED = ["brokers", "extract", "page_one_is_the_thesis"]


def main(argv):
    out = (os.path.expanduser(argv[1]) if len(argv) > 1
           else os.path.join(os.path.expanduser(
               os.environ.get("BROKER_RESEARCH_ROOT", "~/broker-research")), "extracted"))
    if not os.path.isdir(out):
        print(f"找不到 {out} —— **跟「抽過但沒有東西」是兩件事**", file=sys.stderr)
        return Exit.BAD_INPUT
    files = sorted(glob.glob(os.path.join(out, "*.json")))
    if not files:
        print("目錄在但沒有抽取結果 —— 空輪次，不是失敗")
        return Exit.EMPTY_ROUND

    docs = []
    for f in files:
        try:
            docs.append(json.load(open(f, encoding="utf-8")))
        except json.JSONDecodeError as e:
            print(f"BAD_INPUT  {os.path.basename(f)} 不是合法 JSON：{e}", file=sys.stderr)
            return Exit.BAD_INPUT

    refs = reference_anchors()
    anchors = refs["anchors"]
    miss = [k for k in REQUIRED if k not in anchors]
    if miss:
        print(f"research/anchors.json 缺 {miss} —— 門檻沒有家，這一輪沒有資格判",
              file=sys.stderr)
        return Exit.BAD_INPUT

    # 第 2 層的產出（有才帶；沒有的話那兩條檢查回 SKIPPED 而不是 PASS）
    dig = os.path.join(os.path.dirname(out), "digest")
    dfiles = sorted(glob.glob(os.path.join(dig, "*.json")))
    digest = json.load(open(dfiles[-1], encoding="utf-8")) if dfiles else None

    # **三張參照表跟 `build()` 讀同一個 `reference_anchors()`。**
    # 兩邊各自組的時候漂過一次：第 14 條檢查讀 `chart_anchors`，build() 有、這裡沒有，
    # 於是這支紅燈而 publish 綠燈 —— 而檔頭正好把這個情況寫成「更糟的反過來」。
    payload = {"docs": docs, "digest": digest, **refs,
               "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    eng = {d.get("engine") for d in docs}
    print(f"{len(docs)} 份｜digest {'有' if digest else '無（那兩條回 SKIPPED）'}｜抽取器 {'／'.join(sorted(e or '?' for e in eng))}｜{out}")
    if len(eng) > 1:
        print("  ⚠︎ **這一批是用不同抽取器抽的** —— 兩軌對同一份檔可能給不同答案，"
              "比較跨份的結果之前先整批用同一支重抽")
    print()
    return report(run_all(payload, suite="research"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
