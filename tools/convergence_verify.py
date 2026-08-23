#!/usr/bin/env python3
"""驗一期匯流訊號報。**這支只讀不寫。**

用法：convergence_verify.py <單期 JSON> [--repo <資料 repo>] [--work <work 目錄>]

## 這支跟 `systems/convergence.py` 的關係

payload 的正本在 `systems/convergence.py` 的 `build()`（publish 的閘門走那條）。
**這支留下來，因為它是不寫檔的那一條路**：組檔中途、或拿舊期回頭稽核時走這裡。

兩邊組出來的 payload 形狀要一致 —— 不一致的樣子是「這裡全綠、publish 擋下來」，
或更糟的反過來。**差別只有一個而且是刻意的**：

`build()` 缺語料就 `raise`（因為那條路會發布，而空語料會讓佐證檢查
vacuously 通過）；這支缺語料就把那幾個鍵留空，對應的檢查誠實回 SKIPPED。

**SKIPPED 不是 PASS。** 拿舊期回頭稽核時語料本來就不在，那時「佐證回查」
這件事就是沒做，報告要說得出來 —— 而不是印一個綠燈。

## 拿舊期驗今天的上游一定會 FAIL

`quant_reconcile` 會把期刊的 `quant` 對回**現在的**監控庫。指標退役、
架構改版、數字每天都在動，所以舊期一定對不上。**那不代表那一期當時是錯的。**
稽核舊期時把 `--work` 指向當時的快照，或接受那條 FAIL 並讀它的訊息。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import checks  # noqa: E402,F401   註冊全部檢查
import systems  # noqa: E402,F401  註冊全部系統
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("issue", nargs="?")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown or not a.issue:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr)
            return Exit.BAD_INPUT
        print(__doc__)
        return 2

    ip = Path(os.path.expanduser(a.issue))
    if not ip.exists():
        print(f"找不到 {ip}", file=sys.stderr)
        return Exit.BAD_INPUT
    draft = json.loads(ip.read_text(encoding="utf-8"))

    repo = Path(os.path.expanduser(a.repo)) if a.repo else ip.parent.parent
    work = Path(os.path.expanduser(
        a.work or os.environ.get("CONVERGENCE_WORK", str(repo / "work"))))

    corpora = {}
    for k in ("adv", "pod", "cotd", "res"):
        f = work / f"{k}.txt"
        if f.exists():
            corpora[k] = f.read_text(encoding="utf-8")
    bub_p = work / "bub" / "data.json"
    idx_p = repo / "data" / "index.json"
    st_p = work / "stances.json"

    payload = {
        "draft": draft,
        # **全有或全無**：只給一部分會讓缺的那庫全部假 FAIL ——
        # 那是參數沒給，不是引用錯了。
        "corpora": corpora if len(corpora) == 4 else None,
        "bub": json.loads(bub_p.read_text(encoding="utf-8")) if bub_p.exists() else None,
        "stances": json.loads(st_p.read_text(encoding="utf-8")) if st_p.exists() else None,
        "index": (json.loads(idx_p.read_text(encoding="utf-8"))
                  if idx_p.exists() else {"days": []}),
    }
    miss = [k for k in ("corpora", "bub") if not payload[k]]
    print(f"{ip.name}｜第 {draft.get('issue')} 期｜repo {repo}｜work {work}")
    if miss:
        print(f"  **缺 {miss} —— 對應的檢查會回 SKIPPED，那不是 PASS**")
    print()
    return report(run_all(payload, suite="convergence"))


if __name__ == "__main__":
    sys.exit(main())
