#!/usr/bin/env python3
"""驗一期 Houseview 月報。**這支只讀不寫。**

用法：
    houseview_verify.py --period 2026-08 [--dir ~/houseview]
    houseview_verify.py --period 2026-08 --script s.json --content c.json

## 為什麼在 kb-core 而不在 houseview

`healthcheck_hv.py` 修過三處「永遠會 PASS 的檢查」，三次都是人抓到的。
`Check` 契約的 `fixture`／`near_miss` 把它變成機制 —— `verify.py --selftest`
會擋掉觸發不了自己 fixture 的檢查，也會擋掉在錯的地方叫的門檻。

**但這一套沒有 System，也不走發布軌。** 月報的產出是 pptx ＋ docx，
不是 `data/<date>.json`，所以只註冊 suite、不註冊 System。

## IO 全部在這裡

檢查一律不做 IO —— 那樣每條檢查才能用純資料當 fixture。
這支負責把檔案讀成 payload，讀不到的鍵留 None，對應的檢查誠實回 SKIPPED。

**SKIPPED 不是 PASS。** 舊 healthcheck 在檔案缺席時是**整段不印**，
於是 19 條同時消失，而輸出看起來只是短了一點。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import checks  # noqa: E402,F401
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402

FILES = ("build_hv3.js", "build_hv.js", "HOUSEVIEW_BRIEF.md", "style-exemplar.md")


def find_node():
    p = shutil.which("node")
    if p:
        return p
    for c in ("/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if os.path.exists(c):
            return c
    cands = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
    return cands[-1] if cands else None


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return None


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--period")
    ap.add_argument("--dir", default="~/houseview")
    ap.add_argument("--script", default=None)
    ap.add_argument("--content", default=None)
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or unknown or not a.period:
        if unknown:
            print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr)
            return Exit.BAD_INPUT
        print(__doc__)
        return 2

    d = Path(os.path.expanduser(a.dir))
    if not d.is_dir():
        print(f"找不到 {d}", file=sys.stderr)
        return Exit.BAD_INPUT

    src = read(d / "build_hv3.js")
    node = find_node()
    syntax = None
    if src is not None and node:
        r = subprocess.run([node, "--check", str(d / "build_hv3.js")],
                           capture_output=True, text=True, timeout=30)
        syntax = {"ok": r.returncode == 0, "err": (r.stderr or "").strip()}

    sp = Path(os.path.expanduser(a.script)) if a.script else d / f"script-{a.period}.json"
    cp = Path(os.path.expanduser(a.content)) if a.content else d / f"content-{a.period}.json"

    payload = {
        "period": a.period,
        "files": {f: (d / f).exists() for f in FILES},
        "build_src": src,
        "build_syntax": syntax,
        "brief": read(d / "HOUSEVIEW_BRIEF.md"),
        "script": load(sp),
        "content": load(cp),
    }

    print(f"Houseview {a.period}｜{d}")
    print(f"  講稿 {sp.name}：{'讀到' if payload['script'] else '**沒有**'}"
          f"　投影片 {cp.name}：{'讀到' if payload['content'] else '**沒有**'}")
    if node is None:
        print("  **找不到 node** —— 語法檢查會 SKIPPED，而那不是通過")
    print()
    return report(run_all(payload, suite="houseview"))


if __name__ == "__main__":
    sys.exit(main())
